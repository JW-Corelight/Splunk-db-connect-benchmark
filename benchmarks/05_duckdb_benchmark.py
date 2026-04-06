#!/usr/bin/env python3
"""
Benchmark Script: DuckDB Embedded Engine Performance
Purpose: Measure DuckDB performance as an embedded analytics engine
Modes: Native (file-backed), Parquet (S3/MinIO), Iceberg (metadata scan)
Metrics: Cold/warm query latency, startup time, memory footprint
Dataset: 100K cybersecurity events (same as other benchmarks)
"""

import time
import json
import statistics
import sys
import os
import argparse
import glob
import platform
import resource
from typing import Dict, List, Optional, Tuple
from datetime import datetime

# DuckDB is imported lazily in measure_startup() to time the import itself.
# After that call, `duckdb` is available as a global.
duckdb = None

# === Configuration ===
MINIO_CONFIG = {
    'endpoint': 'localhost:9000',
    'access_key': 'admin',
    'secret_key': 'password123',
    'bucket': 'warehouse',
    'region': 'us-east-1',
    'use_ssl': False
}

POSTGRESQL_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'cybersecurity',
    'user': 'postgres',
    'password': 'postgres123'
}

DUCKDB_DB_PATH = 'results/duckdb_benchmark.db'

# Number of iterations for each query (warm)
ITERATIONS = 5

# === Test Queries ===
# DuckDB uses PostgreSQL-compatible SQL.
# Parquet/Iceberg variants replace the table name with a function call.
PARQUET_SOURCE = "read_parquet('s3://warehouse/security_logs/data.parquet')"
ICEBERG_SOURCE = "iceberg_scan('s3://warehouse/cybersecurity/security_logs/')"

QUERIES = {
    'count_all': {
        'name': 'Count All Records',
        'duckdb_native': 'SELECT COUNT(*) as count FROM security_logs',
        'duckdb_parquet': f'SELECT COUNT(*) as count FROM {PARQUET_SOURCE}',
        'duckdb_iceberg': f'SELECT COUNT(*) as count FROM {ICEBERG_SOURCE}'
    },
    'aggregation_by_event_type': {
        'name': 'Aggregate by Event Type',
        'duckdb_native': '''
            SELECT event_type, COUNT(*) as count,
                   SUM(bytes_in) as total_bytes_in,
                   AVG(bytes_out) as avg_bytes_out
            FROM security_logs
            GROUP BY event_type
            ORDER BY count DESC
            LIMIT 10
        ''',
        'duckdb_parquet': f'''
            SELECT event_type, COUNT(*) as count,
                   SUM(bytes_in) as total_bytes_in,
                   AVG(bytes_out) as avg_bytes_out
            FROM {PARQUET_SOURCE}
            GROUP BY event_type
            ORDER BY count DESC
            LIMIT 10
        ''',
        'duckdb_iceberg': f'''
            SELECT event_type, COUNT(*) as count,
                   SUM(bytes_in) as total_bytes_in,
                   AVG(bytes_out) as avg_bytes_out
            FROM {ICEBERG_SOURCE}
            GROUP BY event_type
            ORDER BY count DESC
            LIMIT 10
        '''
    },
    'filter_failed_logins': {
        'name': 'Filter Failed Login Events',
        'duckdb_native': '''
            SELECT user_id, COUNT(*) as failed_attempts
            FROM security_logs
            WHERE event_type = 'ssh_login' AND status = 'failed'
            GROUP BY user_id
            HAVING COUNT(*) > 3
            ORDER BY failed_attempts DESC
        ''',
        'duckdb_parquet': f'''
            SELECT user_id, COUNT(*) as failed_attempts
            FROM {PARQUET_SOURCE}
            WHERE event_type = 'ssh_login' AND status = 'failed'
            GROUP BY user_id
            HAVING COUNT(*) > 3
            ORDER BY failed_attempts DESC
        ''',
        'duckdb_iceberg': f'''
            SELECT user_id, COUNT(*) as failed_attempts
            FROM {ICEBERG_SOURCE}
            WHERE event_type = 'ssh_login' AND status = 'failed'
            GROUP BY user_id
            HAVING COUNT(*) > 3
            ORDER BY failed_attempts DESC
        '''
    },
    'time_range_aggregation': {
        'name': 'Time Range Aggregation (Last 7 Days)',
        'duckdb_native': '''
            SELECT DATE_TRUNC('day', timestamp) as day,
                   COUNT(*) as events,
                   COUNT(DISTINCT user_id) as unique_users
            FROM security_logs
            WHERE timestamp >= CURRENT_TIMESTAMP - INTERVAL '7 days'
            GROUP BY DATE_TRUNC('day', timestamp)
            ORDER BY day DESC
        ''',
        'duckdb_parquet': f'''
            SELECT DATE_TRUNC('day', timestamp) as day,
                   COUNT(*) as events,
                   COUNT(DISTINCT user_id) as unique_users
            FROM {PARQUET_SOURCE}
            WHERE timestamp >= CURRENT_TIMESTAMP - INTERVAL '7 days'
            GROUP BY DATE_TRUNC('day', timestamp)
            ORDER BY day DESC
        ''',
        'duckdb_iceberg': f'''
            SELECT DATE_TRUNC('day', timestamp) as day,
                   COUNT(*) as events,
                   COUNT(DISTINCT user_id) as unique_users
            FROM {ICEBERG_SOURCE}
            WHERE timestamp >= CURRENT_TIMESTAMP - INTERVAL '7 days'
            GROUP BY DATE_TRUNC('day', timestamp)
            ORDER BY day DESC
        '''
    },
    'top_data_transfer': {
        'name': 'Top Data Transfer Events',
        'duckdb_native': '''
            SELECT user_id, event_type, source_ip, dest_ip,
                   (bytes_in + bytes_out) as total_bytes
            FROM security_logs
            WHERE bytes_in IS NOT NULL AND bytes_out IS NOT NULL
            ORDER BY total_bytes DESC
            LIMIT 100
        ''',
        'duckdb_parquet': f'''
            SELECT user_id, event_type, source_ip, dest_ip,
                   (bytes_in + bytes_out) as total_bytes
            FROM {PARQUET_SOURCE}
            WHERE bytes_in IS NOT NULL AND bytes_out IS NOT NULL
            ORDER BY total_bytes DESC
            LIMIT 100
        ''',
        'duckdb_iceberg': f'''
            SELECT user_id, event_type, source_ip, dest_ip,
                   (bytes_in + bytes_out) as total_bytes
            FROM {ICEBERG_SOURCE}
            WHERE bytes_in IS NOT NULL AND bytes_out IS NOT NULL
            ORDER BY total_bytes DESC
            LIMIT 100
        '''
    }
}

# === Utility Functions ===
def print_header(text: str) -> None:
    """Print a formatted header"""
    print(f"\n{'='*80}")
    print(f"{text:^80}")
    print(f"{'='*80}\n")

def print_result(query_name: str, mode: str, cold_ms: float,
                 warm_latencies: List[float], row_count: int) -> None:
    """Print query execution results with cold/warm split"""
    avg_warm = statistics.mean(warm_latencies)
    min_warm = min(warm_latencies)
    max_warm = max(warm_latencies)
    std_warm = statistics.stdev(warm_latencies) if len(warm_latencies) > 1 else 0

    print(f"Query: {query_name}")
    print(f"Mode: {mode}")
    print(f"Rows Returned: {row_count}")
    print(f"Cold Latency: {cold_ms:.2f} ms")
    print(f"Warm Latency (ms):")
    print(f"  Avg: {avg_warm:.2f}")
    print(f"  Min: {min_warm:.2f}")
    print(f"  Max: {max_warm:.2f}")
    print(f"  StdDev: {std_warm:.2f}")
    print(f"{'-'*80}\n")

def get_memory_mb() -> float:
    """Get current process peak RSS in MB (macOS: ru_maxrss is bytes)"""
    usage = resource.getrusage(resource.RUSAGE_SELF)
    if platform.system() == 'Darwin':
        return usage.ru_maxrss / (1024 * 1024)
    else:
        # Linux: ru_maxrss is in KB
        return usage.ru_maxrss / 1024

# === Startup Measurement ===
def measure_startup() -> Dict:
    """Measure DuckDB import, connection, and extension load times"""
    global duckdb

    # Measure import time
    start = time.perf_counter()
    import duckdb as _duckdb
    import_time_ms = (time.perf_counter() - start) * 1000
    duckdb = _duckdb

    # Measure connection time (in-memory)
    start = time.perf_counter()
    conn = duckdb.connect(':memory:')
    connection_time_ms = (time.perf_counter() - start) * 1000

    # Measure extension install+load time (httpfs)
    start = time.perf_counter()
    try:
        conn.execute("INSTALL httpfs; LOAD httpfs;")
        extension_load_time_ms = (time.perf_counter() - start) * 1000
    except Exception as e:
        print(f"Warning: httpfs extension load failed: {e}")
        extension_load_time_ms = -1

    conn.close()

    return {
        'import_time_ms': round(import_time_ms, 2),
        'connection_time_ms': round(connection_time_ms, 2),
        'extension_load_time_ms': round(extension_load_time_ms, 2),
        'duckdb_version': duckdb.__version__
    }

# === Setup Functions ===
def setup_httpfs(conn) -> None:
    """Install and configure httpfs extension for S3/MinIO access"""
    conn.execute("INSTALL httpfs; LOAD httpfs;")
    conn.execute(f"SET s3_endpoint='{MINIO_CONFIG['endpoint']}'")
    conn.execute(f"SET s3_access_key_id='{MINIO_CONFIG['access_key']}'")
    conn.execute(f"SET s3_secret_access_key='{MINIO_CONFIG['secret_key']}'")
    conn.execute(f"SET s3_region='{MINIO_CONFIG['region']}'")
    conn.execute(f"SET s3_use_ssl={'true' if MINIO_CONFIG['use_ssl'] else 'false'}")
    conn.execute("SET s3_url_style='path'")

def setup_iceberg_extension(conn) -> bool:
    """Install and load iceberg extension. Returns True if successful."""
    try:
        conn.execute("INSTALL iceberg; LOAD iceberg;")
        return True
    except Exception as e:
        print(f"Warning: Iceberg extension not available: {e}")
        return False

def generate_synthetic_data(conn, num_records: int = 100000) -> Tuple[str, float]:
    """
    Generate synthetic security_logs data directly in DuckDB.
    Matches the schema and data patterns from scripts/generate_sample_data.py.
    No external dependencies required.
    """
    print(f"Generating {num_records:,} synthetic security log records...")
    start = time.perf_counter()

    conn.execute(f"""
        CREATE TABLE security_logs AS
        SELECT
            -- timestamp: random time within last 90 days
            CURRENT_TIMESTAMP - INTERVAL (floor(random() * 90)::INT) DAY
                              - INTERVAL (floor(random() * 24)::INT) HOUR
                              - INTERVAL (floor(random() * 60)::INT) MINUTE
                              - INTERVAL (floor(random() * 60)::INT) SECOND
                AS timestamp,
            i AS event_id,
            'user_' || lpad(cast(floor(random() * 500 + 1)::INT AS VARCHAR), 5, '0')
                AS user_id,
            CASE floor(random() * 3)::INT
                WHEN 0 THEN 'human'
                WHEN 1 THEN 'service'
                ELSE 'admin'
            END AS user_type,
            'host-' || lpad(cast(floor(random() * 100 + 1)::INT AS VARCHAR), 3, '0') || '.internal'
                AS host,
            floor(random() * 183 + 10)::INT || '.' ||
            floor(random() * 256)::INT || '.' ||
            floor(random() * 256)::INT || '.' ||
            floor(random() * 254 + 1)::INT
                AS source_ip,
            floor(random() * 183 + 10)::INT || '.' ||
            floor(random() * 256)::INT || '.' ||
            floor(random() * 256)::INT || '.' ||
            floor(random() * 254 + 1)::INT
                AS dest_ip,
            CASE floor(random() * 9)::INT
                WHEN 0 THEN 22 WHEN 1 THEN 80 WHEN 2 THEN 443
                WHEN 3 THEN 3306 WHEN 4 THEN 5432 WHEN 5 THEN 8080
                WHEN 6 THEN 8443 WHEN 7 THEN 9000 ELSE 9090
            END AS port,
            CASE floor(random() * 5)::INT
                WHEN 0 THEN 'ssh_login'
                WHEN 1 THEN 'web_request'
                WHEN 2 THEN 'file_access'
                WHEN 3 THEN 'api_call'
                ELSE 'database_query'
            END AS event_type,
            CASE floor(random() * 4)::INT
                WHEN 0 THEN 'success'
                WHEN 1 THEN 'failed'
                WHEN 2 THEN 'blocked'
                ELSE 'timeout'
            END AS status,
            floor(random() * 49901 + 100)::INT AS bytes_in,
            floor(random() * 49901 + 100)::INT AS bytes_out,
            '{{}}'::VARCHAR AS event_data
        FROM generate_series(1, {num_records}) AS t(i)
    """)

    load_time_ms = (time.perf_counter() - start) * 1000
    count = conn.execute("SELECT COUNT(*) FROM security_logs").fetchone()[0]
    print(f"Generated {count:,} synthetic records in {load_time_ms:.0f} ms")
    return 'synthetic', load_time_ms

def setup_duckdb_native(conn) -> Tuple[str, float]:
    """
    Load security_logs into DuckDB native format.
    Tries PostgreSQL first, falls back to Parquet on MinIO.
    Returns (data_source, load_time_ms).
    """
    # Try PostgreSQL first
    try:
        conn.execute("INSTALL postgres; LOAD postgres;")
        dsn = (f"host={POSTGRESQL_CONFIG['host']} "
               f"port={POSTGRESQL_CONFIG['port']} "
               f"dbname={POSTGRESQL_CONFIG['database']} "
               f"user={POSTGRESQL_CONFIG['user']} "
               f"password={POSTGRESQL_CONFIG['password']}")

        print("Loading data from PostgreSQL...")
        start = time.perf_counter()
        conn.execute(f"""
            CREATE TABLE security_logs AS
            SELECT * FROM postgres_scan('{dsn}', 'public', 'security_logs')
        """)
        load_time_ms = (time.perf_counter() - start) * 1000

        count = conn.execute("SELECT COUNT(*) FROM security_logs").fetchone()[0]
        print(f"Loaded {count:,} records from PostgreSQL in {load_time_ms:.0f} ms")
        return 'postgresql', load_time_ms

    except Exception as e:
        print(f"PostgreSQL load failed ({e}), trying Parquet fallback...")

    # Fallback 2: load from Parquet on MinIO
    try:
        setup_httpfs(conn)
        print("Loading data from Parquet on MinIO...")
        start = time.perf_counter()
        conn.execute(f"""
            CREATE TABLE security_logs AS
            SELECT * FROM read_parquet('s3://warehouse/security_logs/data.parquet')
        """)
        load_time_ms = (time.perf_counter() - start) * 1000

        count = conn.execute("SELECT COUNT(*) FROM security_logs").fetchone()[0]
        print(f"Loaded {count:,} records from Parquet in {load_time_ms:.0f} ms")
        return 'parquet', load_time_ms

    except Exception as e:
        print(f"Parquet load also failed ({e}), generating synthetic data...")

    # Fallback 3: generate synthetic data directly in DuckDB
    return generate_synthetic_data(conn)

# === Query Functions ===
def query_duckdb_cold(query: str, db_path: str) -> Tuple[List[Tuple], float]:
    """Cold query: fresh connection, timing includes connection setup"""
    start_time = time.perf_counter()
    conn = duckdb.connect(db_path, read_only=True)
    results = conn.execute(query).fetchall()
    end_time = time.perf_counter()
    conn.close()
    return results, (end_time - start_time) * 1000

def query_duckdb_warm(conn, query: str) -> Tuple[List[Tuple], float]:
    """Warm query: reuse existing connection, timing is query-only"""
    start_time = time.perf_counter()
    results = conn.execute(query).fetchall()
    end_time = time.perf_counter()
    return results, (end_time - start_time) * 1000

def query_duckdb_warm_inmemory(conn, query: str) -> Tuple[List[Tuple], float]:
    """Warm query for in-memory connection (Parquet/Iceberg, no cold variant)"""
    start_time = time.perf_counter()
    results = conn.execute(query).fetchall()
    end_time = time.perf_counter()
    return results, (end_time - start_time) * 1000

# === Benchmark Execution ===
def run_native_benchmark(query: str, db_path: str) -> Optional[Dict]:
    """Run benchmark for a native DuckDB query with cold + warm iterations"""
    # Cold run (fresh connection)
    try:
        _, cold_latency = query_duckdb_cold(query, db_path)
    except Exception as e:
        print(f"Error in cold query: {e}")
        return None

    # Warm runs (persistent connection)
    warm_latencies = []
    results = None
    conn = duckdb.connect(db_path, read_only=True)
    try:
        for _ in range(ITERATIONS):
            try:
                results, latency = query_duckdb_warm(conn, query)
                warm_latencies.append(latency)
            except Exception as e:
                print(f"Error in warm query: {e}")
                conn.close()
                return None
    finally:
        conn.close()

    return {
        'cold_latency_ms': round(cold_latency, 2),
        'warm_latencies': [round(l, 2) for l in warm_latencies],
        'warm_avg_latency_ms': round(statistics.mean(warm_latencies), 2),
        'warm_min_latency_ms': round(min(warm_latencies), 2),
        'warm_max_latency_ms': round(max(warm_latencies), 2),
        'row_count': len(results) if results else 0
    }

def run_remote_benchmark(conn, query: str) -> Optional[Dict]:
    """Run benchmark for Parquet/Iceberg queries (warm only, in-memory conn)"""
    latencies = []
    results = None

    for _ in range(ITERATIONS):
        try:
            results, latency = query_duckdb_warm_inmemory(conn, query)
            latencies.append(latency)
        except Exception as e:
            print(f"Error executing query: {e}")
            return None

    return {
        'warm_latencies': [round(l, 2) for l in latencies],
        'warm_avg_latency_ms': round(statistics.mean(latencies), 2),
        'warm_min_latency_ms': round(min(latencies), 2),
        'warm_max_latency_ms': round(max(latencies), 2),
        'row_count': len(results) if results else 0
    }

# === Cross-Engine Comparison ===
def print_cross_engine_comparison(duckdb_results: Dict) -> None:
    """Load latest native baseline results and print side-by-side comparison"""
    baseline_files = sorted(glob.glob('results/native_baseline_*.json'), reverse=True)
    if not baseline_files:
        print("No native baseline results found for cross-engine comparison.")
        return

    with open(baseline_files[0]) as f:
        baseline = json.load(f)

    print_header("Cross-Engine Comparison")
    print(f"(Baseline file: {os.path.basename(baseline_files[0])})\n")

    for query_id, query_info in QUERIES.items():
        print(f"{query_info['name']}:")

        pg_ms = baseline.get('postgresql', {}).get(query_id, {}).get('avg_latency_ms')
        ch_ms = baseline.get('clickhouse', {}).get(query_id, {}).get('avg_latency_ms')
        sr_ms = baseline.get('starrocks', {}).get(query_id, {}).get('avg_latency_ms')
        dk_ms = duckdb_results.get('duckdb_native', {}).get(query_id, {}).get('warm_avg_latency_ms')

        if pg_ms is not None:
            print(f"  PostgreSQL:       {pg_ms:.2f} ms")
        if ch_ms is not None:
            print(f"  ClickHouse:       {ch_ms:.2f} ms")
        if sr_ms is not None:
            print(f"  StarRocks:        {sr_ms:.2f} ms")
        if dk_ms is not None:
            print(f"  DuckDB (native):  {dk_ms:.2f} ms")

        dk_pq = duckdb_results.get('duckdb_parquet', {}).get(query_id, {}).get('warm_avg_latency_ms')
        dk_ic = duckdb_results.get('duckdb_iceberg', {}).get(query_id, {}).get('warm_avg_latency_ms')
        if dk_pq is not None:
            print(f"  DuckDB (parquet): {dk_pq:.2f} ms")
        if dk_ic is not None:
            print(f"  DuckDB (iceberg): {dk_ic:.2f} ms")

        print()

# === Main ===
def main():
    """Main benchmark execution"""
    parser = argparse.ArgumentParser(description='DuckDB Embedded Engine Benchmark')
    parser.add_argument('--skip-iceberg', action='store_true',
                        help='Skip Iceberg scan benchmarks')
    parser.add_argument('--skip-parquet', action='store_true',
                        help='Skip Parquet/S3 benchmarks (requires MinIO)')
    parser.add_argument('--skip-native-load', action='store_true',
                        help='Skip native DuckDB data load (reuse existing DB file)')
    args = parser.parse_args()

    print_header("DuckDB Embedded Engine Benchmark")
    print(f"Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Platform: {platform.machine()}")
    print(f"Iterations per Query (warm): {ITERATIONS}")

    all_results = {}

    # === Memory Baseline ===
    mem_baseline = get_memory_mb()

    # === Startup Metrics ===
    print("\nMeasuring startup times...")
    startup = measure_startup()
    all_results['startup_metrics'] = startup
    print(f"  DuckDB version: {startup['duckdb_version']}")
    print(f"  Import time: {startup['import_time_ms']:.2f} ms")
    print(f"  Connection time: {startup['connection_time_ms']:.2f} ms")
    print(f"  Extension load (httpfs): {startup['extension_load_time_ms']:.2f} ms")

    mem_after_import = get_memory_mb()

    # === Native DuckDB Benchmarks ===
    print_header("DuckDB Native Format (File-Backed)")

    db_path = os.path.join(os.path.dirname(__file__), DUCKDB_DB_PATH)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    data_source = None
    data_load_time_ms = 0
    database_size_bytes = 0

    if args.skip_native_load and os.path.exists(db_path):
        print(f"Reusing existing database: {db_path}")
        data_source = 'existing'
        database_size_bytes = os.path.getsize(db_path)
    else:
        # Remove old DB for fresh load measurement
        if os.path.exists(db_path):
            os.remove(db_path)

        conn = duckdb.connect(db_path)
        try:
            data_source, data_load_time_ms = setup_duckdb_native(conn)
        except RuntimeError as e:
            print(f"FATAL: {e}")
            print("Cannot run native benchmarks without data.")
            conn.close()
            return
        conn.close()

        database_size_bytes = os.path.getsize(db_path)

    mem_after_load = get_memory_mb()

    all_results['metadata'] = {
        'timestamp': datetime.now().isoformat(),
        'duckdb_version': startup['duckdb_version'],
        'platform': platform.machine(),
        'iterations': ITERATIONS,
        'data_source': data_source,
        'data_load_time_ms': round(data_load_time_ms, 2),
        'database_size_bytes': database_size_bytes
    }

    all_results['memory_metrics'] = {
        'baseline_rss_mb': round(mem_baseline, 1),
        'after_import_rss_mb': round(mem_after_import, 1),
        'after_data_load_rss_mb': round(mem_after_load, 1)
    }

    print(f"\nDatabase size on disk: {database_size_bytes / (1024*1024):.1f} MB")
    print(f"Memory (peak RSS): {mem_after_load:.1f} MB")

    # Run native queries
    all_results['duckdb_native'] = {}
    for query_id, query_info in QUERIES.items():
        print(f"\n[DuckDB Native] Running: {query_info['name']}...")
        result = run_native_benchmark(query_info['duckdb_native'], db_path)

        if result:
            all_results['duckdb_native'][query_id] = result
            print_result(query_info['name'], 'DuckDB Native',
                         result['cold_latency_ms'],
                         result['warm_latencies'],
                         result['row_count'])

    # === Parquet/S3 Benchmarks ===
    if not args.skip_parquet:
        print_header("DuckDB Parquet Scan (S3/MinIO)")
        all_results['duckdb_parquet'] = {}

        parquet_conn = duckdb.connect(':memory:')
        try:
            setup_httpfs(parquet_conn)

            for query_id, query_info in QUERIES.items():
                print(f"\n[DuckDB Parquet] Running: {query_info['name']}...")
                result = run_remote_benchmark(parquet_conn, query_info['duckdb_parquet'])

                if result:
                    all_results['duckdb_parquet'][query_id] = result
                    # Print without cold (no cold measurement for remote)
                    avg = result['warm_avg_latency_ms']
                    print(f"  Avg: {avg:.2f} ms | Rows: {result['row_count']}")
                else:
                    print(f"  Skipped (query failed)")
                    break
        except Exception as e:
            print(f"Parquet benchmarks failed: {e}")
            print("Is MinIO running? (docker-compose -f docker-compose.m3.yml up -d minio)")
        finally:
            parquet_conn.close()
    else:
        print("\nSkipping Parquet/S3 benchmarks (--skip-parquet)")

    # === Iceberg Benchmarks ===
    if not args.skip_iceberg:
        print_header("DuckDB Iceberg Scan (S3/MinIO)")
        all_results['duckdb_iceberg'] = {}

        iceberg_conn = duckdb.connect(':memory:')
        try:
            setup_httpfs(iceberg_conn)
            iceberg_available = setup_iceberg_extension(iceberg_conn)

            if iceberg_available:
                for query_id, query_info in QUERIES.items():
                    print(f"\n[DuckDB Iceberg] Running: {query_info['name']}...")
                    result = run_remote_benchmark(iceberg_conn, query_info['duckdb_iceberg'])

                    if result:
                        all_results['duckdb_iceberg'][query_id] = result
                        avg = result['warm_avg_latency_ms']
                        print(f"  Avg: {avg:.2f} ms | Rows: {result['row_count']}")
                    else:
                        print(f"  Skipped (Iceberg tables may not be set up)")
                        break
            else:
                print("Iceberg extension not available. Skipping Iceberg benchmarks.")
        except Exception as e:
            print(f"Iceberg benchmarks failed: {e}")
        finally:
            iceberg_conn.close()
    else:
        print("\nSkipping Iceberg benchmarks (--skip-iceberg)")

    # === Within-Script Summary ===
    print_header("DuckDB Benchmark Summary")

    for query_id, query_info in QUERIES.items():
        print(f"\n{query_info['name']}:")

        native = all_results.get('duckdb_native', {}).get(query_id)
        parquet = all_results.get('duckdb_parquet', {}).get(query_id)
        iceberg = all_results.get('duckdb_iceberg', {}).get(query_id)

        if native:
            print(f"  Native (warm avg):  {native['warm_avg_latency_ms']:.2f} ms "
                  f"(cold: {native['cold_latency_ms']:.2f} ms)")
        if parquet:
            print(f"  Parquet (warm avg): {parquet['warm_avg_latency_ms']:.2f} ms")
            if native:
                slowdown = parquet['warm_avg_latency_ms'] / native['warm_avg_latency_ms'] \
                    if native['warm_avg_latency_ms'] > 0 else 0
                print(f"    Parquet slowdown: {slowdown:.1f}x vs native")
        if iceberg:
            print(f"  Iceberg (warm avg): {iceberg['warm_avg_latency_ms']:.2f} ms")
            if native:
                slowdown = iceberg['warm_avg_latency_ms'] / native['warm_avg_latency_ms'] \
                    if native['warm_avg_latency_ms'] > 0 else 0
                print(f"    Iceberg slowdown: {slowdown:.1f}x vs native")

    # === Cross-Engine Comparison ===
    print_cross_engine_comparison(all_results)

    # === Key Insights ===
    print("\n" + "="*80)
    print("Key Insights:")
    print("- DuckDB runs embedded (in-process) — zero network overhead")
    print("- ARM64 native on Apple Silicon — no Rosetta translation")
    print("- Cold start includes connection setup; warm queries reuse connection")
    print("- Parquet/Iceberg scans go through httpfs to MinIO (network I/O)")
    print("- Native format uses DuckDB's columnar engine for best performance")
    print("="*80 + "\n")

    # === Save Results ===
    output_file = f"results/duckdb_benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    output_path = os.path.join(os.path.dirname(__file__), output_file)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, 'w') as f:
        json.dump(all_results, f, indent=2)

    print(f"Results saved to: {output_file}")
    print(f"End Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print_header("Benchmark Complete")

if __name__ == '__main__':
    main()
