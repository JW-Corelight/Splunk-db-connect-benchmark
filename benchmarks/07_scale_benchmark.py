#!/usr/bin/env python3
"""
Benchmark Script: Dataset Scale Performance
Purpose: Measure how query performance scales with dataset size
Engines: PostgreSQL, ClickHouse, DuckDB (StarRocks optional)
Scales: 100K, 1M, 10M rows (configurable)
Output: Performance curves showing latency vs dataset size per engine
"""

import time
import json
import statistics
import sys
import os
import argparse
import platform
from typing import Dict, List, Optional, Tuple
from datetime import datetime

# === Configuration ===
POSTGRESQL_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'cybersecurity',
    'user': 'postgres',
    'password': 'postgres123'
}

CLICKHOUSE_CONFIG = {
    'host': 'localhost',
    'port': 8123,
    'database': 'cybersecurity',
    'user': 'default',
    'password': ''
}

STARROCKS_CONFIG = {
    'host': 'localhost',
    'port': 9030,
    'database': 'cybersecurity',
    'user': 'root',
    'password': ''
}

DEFAULT_SCALES = [100_000, 1_000_000, 10_000_000]
ITERATIONS = 3  # Fewer iterations since we're testing multiple scales
SCALE_TABLE_PREFIX = 'security_logs_scale'

# === Test Queries ===
# Parameterized with {table} placeholder, replaced at runtime.
QUERIES = {
    'count_all': {
        'name': 'Count All Records',
        'sql': 'SELECT COUNT(*) FROM {table}'
    },
    'aggregation': {
        'name': 'Aggregate by Event Type',
        'sql': '''
            SELECT event_type, COUNT(*) as cnt, SUM(bytes_in) as total_in
            FROM {table}
            GROUP BY event_type
            ORDER BY cnt DESC
            LIMIT 10
        '''
    },
    'filter': {
        'name': 'Filter Failed Logins',
        'sql': '''
            SELECT user_id, COUNT(*) as failed
            FROM {table}
            WHERE event_type = 'ssh_login' AND status = 'failed'
            GROUP BY user_id
            HAVING COUNT(*) > 3
            ORDER BY failed DESC
        '''
    },
    'top_transfer': {
        'name': 'Top Data Transfer',
        'sql': '''
            SELECT user_id, event_type, (bytes_in + bytes_out) as total_bytes
            FROM {table}
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

def format_rows(n: int) -> str:
    """Format row count for display (100K, 1M, 10M, etc.)"""
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.0f}B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.0f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}K"
    return str(n)

# === Data Generation (per-engine) ===

def generate_duckdb_scale_table(conn, table_name: str, num_rows: int) -> float:
    """Generate synthetic data directly in DuckDB. Returns load time in ms."""
    conn.execute(f"DROP TABLE IF EXISTS {table_name}")

    start = time.perf_counter()
    conn.execute(f"""
        CREATE TABLE {table_name} AS
        SELECT
            CURRENT_TIMESTAMP - INTERVAL (floor(random() * 90)::INT) DAY
                              - INTERVAL (floor(random() * 86400)::INT) SECOND
                AS timestamp,
            i AS event_id,
            'user_' || lpad(cast(floor(random() * 500 + 1)::INT AS VARCHAR), 5, '0')
                AS user_id,
            CASE floor(random() * 3)::INT
                WHEN 0 THEN 'human' WHEN 1 THEN 'service' ELSE 'admin'
            END AS user_type,
            'host-' || lpad(cast(floor(random() * 100 + 1)::INT AS VARCHAR), 3, '0') || '.internal'
                AS host,
            floor(random() * 183 + 10)::INT || '.' || floor(random() * 256)::INT || '.' ||
            floor(random() * 256)::INT || '.' || floor(random() * 254 + 1)::INT AS source_ip,
            floor(random() * 183 + 10)::INT || '.' || floor(random() * 256)::INT || '.' ||
            floor(random() * 256)::INT || '.' || floor(random() * 254 + 1)::INT AS dest_ip,
            CASE floor(random() * 5)::INT
                WHEN 0 THEN 'ssh_login' WHEN 1 THEN 'web_request'
                WHEN 2 THEN 'file_access' WHEN 3 THEN 'api_call'
                ELSE 'database_query'
            END AS event_type,
            CASE floor(random() * 4)::INT
                WHEN 0 THEN 'success' WHEN 1 THEN 'failed'
                WHEN 2 THEN 'blocked' ELSE 'timeout'
            END AS status,
            floor(random() * 49901 + 100)::INT AS bytes_in,
            floor(random() * 49901 + 100)::INT AS bytes_out
        FROM generate_series(1, {num_rows}) AS t(i)
    """)
    return (time.perf_counter() - start) * 1000


def generate_postgresql_scale_table(table_name: str, num_rows: int) -> float:
    """Generate synthetic data in PostgreSQL. Returns load time in ms."""
    import psycopg2
    conn = psycopg2.connect(**POSTGRESQL_CONFIG)
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute(f"DROP TABLE IF EXISTS {table_name}")
    cur.execute(f"""
        CREATE TABLE {table_name} AS
        SELECT
            NOW() - (random() * INTERVAL '90 days') AS timestamp,
            i AS event_id,
            'user_' || lpad(cast(floor(random() * 500 + 1)::INT AS VARCHAR), 5, '0')
                AS user_id,
            CASE floor(random() * 3)::INT
                WHEN 0 THEN 'human' WHEN 1 THEN 'service' ELSE 'admin'
            END AS user_type,
            'host-' || lpad(cast(floor(random() * 100 + 1)::INT AS VARCHAR), 3, '0') || '.internal'
                AS host,
            (floor(random() * 183 + 10)::INT || '.' || floor(random() * 256)::INT || '.' ||
             floor(random() * 256)::INT || '.' || floor(random() * 254 + 1)::INT)
                AS source_ip,
            (floor(random() * 183 + 10)::INT || '.' || floor(random() * 256)::INT || '.' ||
             floor(random() * 256)::INT || '.' || floor(random() * 254 + 1)::INT)
                AS dest_ip,
            CASE floor(random() * 5)::INT
                WHEN 0 THEN 'ssh_login' WHEN 1 THEN 'web_request'
                WHEN 2 THEN 'file_access' WHEN 3 THEN 'api_call'
                ELSE 'database_query'
            END AS event_type,
            CASE floor(random() * 4)::INT
                WHEN 0 THEN 'success' WHEN 1 THEN 'failed'
                WHEN 2 THEN 'blocked' ELSE 'timeout'
            END AS status,
            floor(random() * 49901 + 100)::INT AS bytes_in,
            floor(random() * 49901 + 100)::INT AS bytes_out
        FROM generate_series(1, {num_rows}) AS t(i)
    """)

    load_time = 0  # We'll use the wall clock below
    start = time.perf_counter()
    # Force a count to ensure the table is materialized
    cur.execute(f"SELECT COUNT(*) FROM {table_name}")
    cur.fetchone()
    # ANALYZE for query planning
    cur.execute(f"ANALYZE {table_name}")
    load_time = (time.perf_counter() - start) * 1000

    cur.close()
    conn.close()
    return load_time


def generate_clickhouse_scale_table(table_name: str, num_rows: int) -> float:
    """Generate synthetic data in ClickHouse. Returns load time in ms."""
    import clickhouse_connect
    client = clickhouse_connect.get_client(
        host=CLICKHOUSE_CONFIG['host'],
        port=CLICKHOUSE_CONFIG['port'],
        database=CLICKHOUSE_CONFIG['database'],
        username=CLICKHOUSE_CONFIG['user'],
        password=CLICKHOUSE_CONFIG['password']
    )

    client.command(f"DROP TABLE IF EXISTS {table_name}")
    client.command(f"""
        CREATE TABLE {table_name} (
            timestamp DateTime64(3),
            event_id UInt64,
            user_id String,
            user_type LowCardinality(String),
            host LowCardinality(String),
            source_ip String,
            dest_ip String,
            event_type LowCardinality(String),
            status LowCardinality(String),
            bytes_in UInt32,
            bytes_out UInt32
        ) ENGINE = MergeTree()
        ORDER BY (timestamp, event_id)
        PARTITION BY toYYYYMM(timestamp)
    """)

    start = time.perf_counter()
    client.command(f"""
        INSERT INTO {table_name}
        SELECT
            now() - toIntervalSecond(rand() % (90 * 86400)),
            number,
            concat('user_', lpad(toString(rand() % 500 + 1), 5, '0')),
            arrayElement(['human', 'service', 'admin'], rand() % 3 + 1),
            concat('host-', lpad(toString(rand() % 100 + 1), 3, '0'), '.internal'),
            concat(toString(rand() % 183 + 10), '.', toString(rand() % 256), '.',
                   toString(rand() % 256), '.', toString(rand() % 254 + 1)),
            concat(toString(rand() % 183 + 10), '.', toString(rand() % 256), '.',
                   toString(rand() % 256), '.', toString(rand() % 254 + 1)),
            arrayElement(['ssh_login','web_request','file_access','api_call','database_query'],
                         rand() % 5 + 1),
            arrayElement(['success','failed','blocked','timeout'], rand() % 4 + 1),
            rand() % 49901 + 100,
            rand() % 49901 + 100
        FROM numbers({num_rows})
    """)
    load_time = (time.perf_counter() - start) * 1000

    client.close()
    return load_time


def generate_starrocks_scale_table(table_name: str, num_rows: int) -> float:
    """Generate synthetic data in StarRocks. Returns load time in ms."""
    import pymysql
    conn = pymysql.connect(
        host=STARROCKS_CONFIG['host'],
        port=STARROCKS_CONFIG['port'],
        database=STARROCKS_CONFIG['database'],
        user=STARROCKS_CONFIG['user'],
        password=STARROCKS_CONFIG['password']
    )
    cur = conn.cursor()

    cur.execute(f"DROP TABLE IF EXISTS {table_name}")
    cur.execute(f"""
        CREATE TABLE {table_name} (
            event_id BIGINT,
            timestamp DATETIME,
            user_id VARCHAR(20),
            user_type VARCHAR(10),
            host VARCHAR(50),
            source_ip VARCHAR(15),
            dest_ip VARCHAR(15),
            event_type VARCHAR(20),
            status VARCHAR(10),
            bytes_in INT,
            bytes_out INT
        )
        DUPLICATE KEY(event_id)
        DISTRIBUTED BY HASH(event_id)
    """)

    # StarRocks doesn't have generate_series; insert in batches using a numbers trick
    start = time.perf_counter()
    batch = 100_000
    inserted = 0
    while inserted < num_rows:
        chunk = min(batch, num_rows - inserted)
        cur.execute(f"""
            INSERT INTO {table_name}
            SELECT
                {inserted} + row_number() OVER (),
                now() - INTERVAL floor(rand() * 90) DAY,
                concat('user_', lpad(cast(floor(rand() * 500 + 1) AS VARCHAR), 5, '0')),
                ELT(floor(rand() * 3 + 1), 'human', 'service', 'admin'),
                concat('host-', lpad(cast(floor(rand() * 100 + 1) AS VARCHAR), 3, '0'), '.internal'),
                concat(cast(floor(rand() * 183 + 10) AS VARCHAR), '.',
                       cast(floor(rand() * 256) AS VARCHAR), '.',
                       cast(floor(rand() * 256) AS VARCHAR), '.',
                       cast(floor(rand() * 254 + 1) AS VARCHAR)),
                concat(cast(floor(rand() * 183 + 10) AS VARCHAR), '.',
                       cast(floor(rand() * 256) AS VARCHAR), '.',
                       cast(floor(rand() * 256) AS VARCHAR), '.',
                       cast(floor(rand() * 254 + 1) AS VARCHAR)),
                ELT(floor(rand() * 5 + 1), 'ssh_login','web_request','file_access','api_call','database_query'),
                ELT(floor(rand() * 4 + 1), 'success','failed','blocked','timeout'),
                floor(rand() * 49901 + 100),
                floor(rand() * 49901 + 100)
            FROM TABLE(generate_series(1, {chunk}))
        """)
        inserted += chunk
    conn.commit()

    load_time = (time.perf_counter() - start) * 1000

    cur.close()
    conn.close()
    return load_time


# === Query Execution ===

def run_queries_postgresql(table_name: str) -> Dict:
    import psycopg2
    conn = psycopg2.connect(**POSTGRESQL_CONFIG)
    cur = conn.cursor()
    results = {}

    for qid, qinfo in QUERIES.items():
        sql = qinfo['sql'].format(table=table_name)
        latencies = []
        row_count = 0
        for _ in range(ITERATIONS):
            start = time.perf_counter()
            cur.execute(sql)
            rows = cur.fetchall()
            latencies.append((time.perf_counter() - start) * 1000)
            row_count = len(rows)

        results[qid] = {
            'avg_latency_ms': round(statistics.mean(latencies), 2),
            'min_latency_ms': round(min(latencies), 2),
            'max_latency_ms': round(max(latencies), 2),
            'row_count': row_count
        }

    cur.close()
    conn.close()
    return results


def run_queries_clickhouse(table_name: str) -> Dict:
    import clickhouse_connect
    client = clickhouse_connect.get_client(
        host=CLICKHOUSE_CONFIG['host'],
        port=CLICKHOUSE_CONFIG['port'],
        database=CLICKHOUSE_CONFIG['database'],
        username=CLICKHOUSE_CONFIG['user'],
        password=CLICKHOUSE_CONFIG['password']
    )
    results = {}

    for qid, qinfo in QUERIES.items():
        sql = qinfo['sql'].format(table=table_name)
        latencies = []
        row_count = 0
        for _ in range(ITERATIONS):
            start = time.perf_counter()
            result = client.query(sql)
            latencies.append((time.perf_counter() - start) * 1000)
            row_count = len(result.result_rows)

        results[qid] = {
            'avg_latency_ms': round(statistics.mean(latencies), 2),
            'min_latency_ms': round(min(latencies), 2),
            'max_latency_ms': round(max(latencies), 2),
            'row_count': row_count
        }

    client.close()
    return results


def run_queries_duckdb(conn, table_name: str) -> Dict:
    results = {}

    for qid, qinfo in QUERIES.items():
        sql = qinfo['sql'].format(table=table_name)
        latencies = []
        row_count = 0
        for _ in range(ITERATIONS):
            start = time.perf_counter()
            rows = conn.execute(sql).fetchall()
            latencies.append((time.perf_counter() - start) * 1000)
            row_count = len(rows)

        results[qid] = {
            'avg_latency_ms': round(statistics.mean(latencies), 2),
            'min_latency_ms': round(min(latencies), 2),
            'max_latency_ms': round(max(latencies), 2),
            'row_count': row_count
        }

    return results


def run_queries_starrocks(table_name: str) -> Dict:
    import pymysql
    conn = pymysql.connect(
        host=STARROCKS_CONFIG['host'],
        port=STARROCKS_CONFIG['port'],
        database=STARROCKS_CONFIG['database'],
        user=STARROCKS_CONFIG['user'],
        password=STARROCKS_CONFIG['password']
    )
    cur = conn.cursor()
    results = {}

    for qid, qinfo in QUERIES.items():
        sql = qinfo['sql'].format(table=table_name)
        latencies = []
        row_count = 0
        for _ in range(ITERATIONS):
            start = time.perf_counter()
            cur.execute(sql)
            rows = cur.fetchall()
            latencies.append((time.perf_counter() - start) * 1000)
            row_count = len(rows)

        results[qid] = {
            'avg_latency_ms': round(statistics.mean(latencies), 2),
            'min_latency_ms': round(min(latencies), 2),
            'max_latency_ms': round(max(latencies), 2),
            'row_count': row_count
        }

    cur.close()
    conn.close()
    return results


# === Cleanup ===

def cleanup_scale_tables(engines: List[str], scales: List[int]):
    """Drop temporary scale test tables."""
    for scale in scales:
        table = f"{SCALE_TABLE_PREFIX}_{scale}"
        if 'postgresql' in engines:
            try:
                import psycopg2
                conn = psycopg2.connect(**POSTGRESQL_CONFIG)
                conn.autocommit = True
                conn.cursor().execute(f"DROP TABLE IF EXISTS {table}")
                conn.close()
            except Exception:
                pass
        if 'clickhouse' in engines:
            try:
                import clickhouse_connect
                client = clickhouse_connect.get_client(
                    host=CLICKHOUSE_CONFIG['host'], port=CLICKHOUSE_CONFIG['port'],
                    database=CLICKHOUSE_CONFIG['database'],
                    username=CLICKHOUSE_CONFIG['user'], password=CLICKHOUSE_CONFIG['password'])
                client.command(f"DROP TABLE IF EXISTS {table}")
                client.close()
            except Exception:
                pass
        if 'starrocks' in engines:
            try:
                import pymysql
                conn = pymysql.connect(
                    host=STARROCKS_CONFIG['host'], port=STARROCKS_CONFIG['port'],
                    database=STARROCKS_CONFIG['database'],
                    user=STARROCKS_CONFIG['user'], password=STARROCKS_CONFIG['password'])
                conn.cursor().execute(f"DROP TABLE IF EXISTS {table}")
                conn.close()
            except Exception:
                pass


# === Availability Checks (same as 06) ===

def check_postgresql() -> bool:
    try:
        import psycopg2
        conn = psycopg2.connect(**POSTGRESQL_CONFIG)
        conn.close()
        return True
    except Exception:
        return False

def check_clickhouse() -> bool:
    try:
        import clickhouse_connect
        client = clickhouse_connect.get_client(
            host=CLICKHOUSE_CONFIG['host'], port=CLICKHOUSE_CONFIG['port'],
            database=CLICKHOUSE_CONFIG['database'],
            username=CLICKHOUSE_CONFIG['user'], password=CLICKHOUSE_CONFIG['password'])
        client.close()
        return True
    except Exception:
        return False

def check_starrocks() -> bool:
    try:
        import pymysql
        conn = pymysql.connect(
            host=STARROCKS_CONFIG['host'], port=STARROCKS_CONFIG['port'],
            database=STARROCKS_CONFIG['database'],
            user=STARROCKS_CONFIG['user'], password=STARROCKS_CONFIG['password'])
        conn.close()
        return True
    except Exception:
        return False


# === Main ===
def main():
    parser = argparse.ArgumentParser(description='Dataset Scale Performance Benchmark')
    parser.add_argument('--engines', nargs='+',
                        choices=['postgresql', 'clickhouse', 'starrocks', 'duckdb'],
                        help='Engines to test (default: auto-detect available)')
    parser.add_argument('--scales', nargs='+', type=int,
                        default=DEFAULT_SCALES,
                        help=f'Row counts to test (default: {[format_rows(s) for s in DEFAULT_SCALES]})')
    parser.add_argument('--keep-tables', action='store_true',
                        help='Do not drop scale test tables after benchmark')
    args = parser.parse_args()

    print_header("Dataset Scale Performance Benchmark")
    print(f"Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Platform: {platform.machine()}")
    print(f"Scales: {[format_rows(s) for s in args.scales]}")
    print(f"Iterations per Query: {ITERATIONS}")

    # Detect engines — DuckDB is always available (embedded)
    available = {}
    requested = args.engines or ['duckdb', 'postgresql', 'clickhouse', 'starrocks']

    print("\nEngine availability:")
    for eng in requested:
        if eng == 'duckdb':
            available['duckdb'] = True
            print(f"  DuckDB: available (embedded)")
        elif eng == 'postgresql':
            ok = check_postgresql()
            available['postgresql'] = ok
            print(f"  PostgreSQL: {'available' if ok else 'not available'}")
        elif eng == 'clickhouse':
            ok = check_clickhouse()
            available['clickhouse'] = ok
            print(f"  ClickHouse: {'available' if ok else 'not available'}")
        elif eng == 'starrocks':
            ok = check_starrocks()
            available['starrocks'] = ok
            print(f"  StarRocks: {'available' if ok else 'not available'}")

    engines = [e for e in requested if available.get(e)]
    if not engines:
        print("\nNo engines available.")
        return

    all_results = {
        'metadata': {
            'timestamp': datetime.now().isoformat(),
            'platform': platform.machine(),
            'scales': args.scales,
            'iterations': ITERATIONS,
            'engines': engines
        }
    }

    # DuckDB uses a temporary in-memory database for scale tests
    duckdb_conn = None
    if 'duckdb' in engines:
        import duckdb
        duckdb_conn = duckdb.connect(':memory:')

    for scale in args.scales:
        scale_label = format_rows(scale)
        table_name = f"{SCALE_TABLE_PREFIX}_{scale}"
        print_header(f"Scale: {scale_label} ({scale:,} rows)")

        scale_results = {}

        for eng in engines:
            print(f"\n--- {eng.upper()} ---")

            # Generate data
            print(f"  Generating {scale_label} rows...")
            try:
                if eng == 'duckdb':
                    load_ms = generate_duckdb_scale_table(duckdb_conn, table_name, scale)
                elif eng == 'postgresql':
                    load_ms = generate_postgresql_scale_table(table_name, scale)
                elif eng == 'clickhouse':
                    load_ms = generate_clickhouse_scale_table(table_name, scale)
                elif eng == 'starrocks':
                    load_ms = generate_starrocks_scale_table(table_name, scale)
                else:
                    continue
            except Exception as e:
                print(f"  Data generation failed: {e}")
                scale_results[eng] = {'error': str(e)}
                continue

            print(f"  Data loaded in {load_ms:.0f} ms")

            # Run queries
            print(f"  Running queries ({ITERATIONS} iterations each)...")
            try:
                if eng == 'duckdb':
                    query_results = run_queries_duckdb(duckdb_conn, table_name)
                elif eng == 'postgresql':
                    query_results = run_queries_postgresql(table_name)
                elif eng == 'clickhouse':
                    query_results = run_queries_clickhouse(table_name)
                elif eng == 'starrocks':
                    query_results = run_queries_starrocks(table_name)
                else:
                    continue
            except Exception as e:
                print(f"  Query execution failed: {e}")
                scale_results[eng] = {'error': str(e), 'load_time_ms': round(load_ms, 2)}
                continue

            scale_results[eng] = {
                'load_time_ms': round(load_ms, 2),
                'queries': query_results
            }

            for qid, qinfo in QUERIES.items():
                if qid in query_results:
                    r = query_results[qid]
                    print(f"  {qinfo['name']}: {r['avg_latency_ms']:.2f} ms avg")

        all_results[f"scale_{scale}"] = scale_results

    # Cleanup DuckDB connection
    if duckdb_conn:
        duckdb_conn.close()

    # Cleanup scale tables (unless --keep-tables)
    if not args.keep_tables:
        print("\nCleaning up scale test tables...")
        cleanup_scale_tables(engines, args.scales)
        print("Done.")

    # === Summary ===
    print_header("Scale Benchmark Summary")

    for qid, qinfo in QUERIES.items():
        print(f"\n{qinfo['name']}:")
        header = f"  {'Engine':<14}"
        for scale in args.scales:
            header += f" {format_rows(scale):>10}"
        print(header)
        print("  " + "-" * (14 + 11 * len(args.scales)))

        for eng in engines:
            row = f"  {eng:<14}"
            for scale in args.scales:
                sr = all_results.get(f"scale_{scale}", {}).get(eng, {})
                qr = sr.get('queries', {}).get(qid, {})
                avg = qr.get('avg_latency_ms')
                if avg is not None:
                    row += f" {avg:>8.1f}ms"
                else:
                    row += f" {'--':>10}"
            print(row)

    # Data load times
    print(f"\nData Load Times:")
    header = f"  {'Engine':<14}"
    for scale in args.scales:
        header += f" {format_rows(scale):>10}"
    print(header)
    print("  " + "-" * (14 + 11 * len(args.scales)))

    for eng in engines:
        row = f"  {eng:<14}"
        for scale in args.scales:
            sr = all_results.get(f"scale_{scale}", {}).get(eng, {})
            lt = sr.get('load_time_ms')
            if lt is not None:
                if lt >= 1000:
                    row += f" {lt/1000:>7.1f}s  "
                else:
                    row += f" {lt:>7.0f}ms "
                    row = row[:-1]  # trim trailing space for alignment
            else:
                row += f" {'--':>10}"
        print(row)

    print("\n" + "="*80)
    print("Key Insights:")
    print("- Linear scaling = good engine optimization for this query type")
    print("- Sub-linear = engine benefits from batch processing at scale")
    print("- Super-linear = watch for memory pressure or index degradation")
    print("- DuckDB generates data in-memory (fastest); server engines use INSERT")
    print("="*80 + "\n")

    # Save results
    output_file = f"results/scale_benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    output_path = os.path.join(os.path.dirname(__file__), output_file)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, 'w') as f:
        json.dump(all_results, f, indent=2)

    print(f"Results saved to: {output_file}")
    print(f"End Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print_header("Benchmark Complete")

if __name__ == '__main__':
    main()
