#!/usr/bin/env python3
"""
Benchmark Script: Iceberg Multi-Engine Performance
Purpose: Test ClickHouse and StarRocks querying Apache Iceberg tables
Comparison: Native format performance vs Iceberg format performance
Pattern: Multi-engine access to shared Iceberg tables
Storage: MinIO (S3-compatible) + Hive Metastore catalog
"""

import time
import clickhouse_connect
import pymysql
import json
import statistics
from typing import Dict, List, Tuple
from datetime import datetime

# === Configuration ===
CLICKHOUSE_CONFIG = {
    'host': 'localhost',
    'port': 8123,
    'database': 'cybersecurity',
    'iceberg_database': 'iceberg_db',
    'user': 'default',
    'password': ''
}

STARROCKS_CONFIG = {
    'host': 'localhost',
    'port': 9030,
    'database': 'cybersecurity',
    'iceberg_catalog': 'iceberg_catalog',
    'iceberg_database': 'cybersecurity',
    'user': 'root',
    'password': ''
}

# Number of iterations for each query
ITERATIONS = 5

# === Test Queries ===
QUERIES = {
    'count_all': {
        'name': 'Count All Records',
        'clickhouse_native': 'SELECT COUNT(*) as count FROM cybersecurity.security_logs',
        'clickhouse_iceberg': 'SELECT COUNT(*) as count FROM iceberg_db.security_logs',
        'starrocks_native': 'SELECT COUNT(*) as count FROM cybersecurity.security_logs',
        'starrocks_iceberg': 'SELECT COUNT(*) as count FROM iceberg_catalog.cybersecurity.security_logs'
    },
    'aggregation_by_event_type': {
        'name': 'Aggregate by Event Type',
        'clickhouse_native': '''
            SELECT event_type, COUNT(*) as count,
                   SUM(bytes_in) as total_bytes_in
            FROM cybersecurity.security_logs
            GROUP BY event_type
            ORDER BY count DESC
            LIMIT 10
        ''',
        'clickhouse_iceberg': '''
            SELECT event_type, COUNT(*) as count,
                   SUM(bytes_in) as total_bytes_in
            FROM iceberg_db.security_logs
            GROUP BY event_type
            ORDER BY count DESC
            LIMIT 10
        ''',
        'starrocks_native': '''
            SELECT event_type, COUNT(*) as count,
                   SUM(bytes_in) as total_bytes_in
            FROM cybersecurity.security_logs
            GROUP BY event_type
            ORDER BY count DESC
            LIMIT 10
        ''',
        'starrocks_iceberg': '''
            SELECT event_type, COUNT(*) as count,
                   SUM(bytes_in) as total_bytes_in
            FROM iceberg_catalog.cybersecurity.security_logs
            GROUP BY event_type
            ORDER BY count DESC
            LIMIT 10
        '''
    },
    'filter_by_event_type': {
        'name': 'Filter by Event Type',
        'clickhouse_native': '''
            SELECT user_id, COUNT(*) as events
            FROM cybersecurity.security_logs
            WHERE event_type = 'ssh_login'
            GROUP BY user_id
            ORDER BY events DESC
            LIMIT 20
        ''',
        'clickhouse_iceberg': '''
            SELECT user_id, COUNT(*) as events
            FROM iceberg_db.security_logs
            WHERE event_type = 'ssh_login'
            GROUP BY user_id
            ORDER BY events DESC
            LIMIT 20
        ''',
        'starrocks_native': '''
            SELECT user_id, COUNT(*) as events
            FROM cybersecurity.security_logs
            WHERE event_type = 'ssh_login'
            GROUP BY user_id
            ORDER BY events DESC
            LIMIT 20
        ''',
        'starrocks_iceberg': '''
            SELECT user_id, COUNT(*) as events
            FROM iceberg_catalog.cybersecurity.security_logs
            WHERE event_type = 'ssh_login'
            GROUP BY user_id
            ORDER BY events DESC
            LIMIT 20
        '''
    },
    'top_data_transfer': {
        'name': 'Top Data Transfer Events',
        'clickhouse_native': '''
            SELECT user_id, event_type,
                   (bytes_in + bytes_out) as total_bytes
            FROM cybersecurity.security_logs
            WHERE bytes_in IS NOT NULL AND bytes_out IS NOT NULL
            ORDER BY total_bytes DESC
            LIMIT 50
        ''',
        'clickhouse_iceberg': '''
            SELECT user_id, event_type,
                   (bytes_in + bytes_out) as total_bytes
            FROM iceberg_db.security_logs
            WHERE bytes_in IS NOT NULL AND bytes_out IS NOT NULL
            ORDER BY total_bytes DESC
            LIMIT 50
        ''',
        'starrocks_native': '''
            SELECT user_id, event_type,
                   (bytes_in + bytes_out) as total_bytes
            FROM cybersecurity.security_logs
            WHERE bytes_in IS NOT NULL AND bytes_out IS NOT NULL
            ORDER BY total_bytes DESC
            LIMIT 50
        ''',
        'starrocks_iceberg': '''
            SELECT user_id, event_type,
                   (bytes_in + bytes_out) as total_bytes
            FROM iceberg_catalog.cybersecurity.security_logs
            WHERE bytes_in IS NOT NULL AND bytes_out IS NOT NULL
            ORDER BY total_bytes DESC
            LIMIT 50
        '''
    }
}

# === Utility Functions ===
def print_header(text: str) -> None:
    """Print a formatted header"""
    print(f"\n{'='*80}")
    print(f"{text:^80}")
    print(f"{'='*80}\n")

def print_comparison(query_name: str, engine: str, native_latency: float,
                     iceberg_latency: float, slowdown_factor: float) -> None:
    """Print performance comparison"""
    print(f"Query: {query_name}")
    print(f"Engine: {engine}")
    print(f"Native Format Latency:  {native_latency:.2f} ms")
    print(f"Iceberg Format Latency: {iceberg_latency:.2f} ms")
    print(f"Slowdown Factor: {slowdown_factor:.2f}x")
    print(f"{'-'*80}\n")

# === Query Functions ===
def query_clickhouse(query: str) -> Tuple[List[Tuple], float]:
    """Execute query on ClickHouse"""
    client = clickhouse_connect.get_client(
        host=CLICKHOUSE_CONFIG['host'],
        port=CLICKHOUSE_CONFIG['port'],
        username=CLICKHOUSE_CONFIG['user'],
        password=CLICKHOUSE_CONFIG['password']
    )

    start_time = time.perf_counter()
    result = client.query(query)
    end_time = time.perf_counter()

    latency_ms = (end_time - start_time) * 1000

    return result.result_rows, latency_ms

def query_starrocks(query: str) -> Tuple[List[Tuple], float]:
    """Execute query on StarRocks"""
    conn = pymysql.connect(
        host=STARROCKS_CONFIG['host'],
        port=STARROCKS_CONFIG['port'],
        user=STARROCKS_CONFIG['user'],
        password=STARROCKS_CONFIG['password']
    )
    cursor = conn.cursor()

    start_time = time.perf_counter()
    cursor.execute(query)
    results = cursor.fetchall()
    end_time = time.perf_counter()

    latency_ms = (end_time - start_time) * 1000

    cursor.close()
    conn.close()

    return results, latency_ms

# === Benchmark Execution ===
def run_iceberg_comparison(engine_name: str, query_func, native_query: str, iceberg_query: str) -> Dict:
    """Compare native format vs Iceberg format for a single query"""

    native_latencies = []
    iceberg_latencies = []

    # Run native format queries
    for i in range(ITERATIONS):
        try:
            _, latency = query_func(native_query)
            native_latencies.append(latency)
        except Exception as e:
            print(f"Error in native query on {engine_name}: {e}")
            return None

    # Run Iceberg format queries
    for i in range(ITERATIONS):
        try:
            _, latency = query_func(iceberg_query)
            iceberg_latencies.append(latency)
        except Exception as e:
            print(f"Error in Iceberg query on {engine_name}: {e}")
            # Iceberg tables may not exist yet, this is acceptable
            return None

    avg_native = statistics.mean(native_latencies)
    avg_iceberg = statistics.mean(iceberg_latencies)
    slowdown_factor = avg_iceberg / avg_native if avg_native > 0 else 0

    return {
        'native_latencies': native_latencies,
        'iceberg_latencies': iceberg_latencies,
        'avg_native_ms': avg_native,
        'avg_iceberg_ms': avg_iceberg,
        'slowdown_factor': slowdown_factor
    }

def main():
    """Main benchmark execution"""
    print_header("Iceberg Multi-Engine Benchmark")
    print(f"Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Iterations per Query: {ITERATIONS}")
    print(f"Testing: Native Format vs Apache Iceberg Format")
    print(f"Engines: ClickHouse (read-only), StarRocks (read-write)")

    all_results = {}

    # === ClickHouse: Native vs Iceberg ===
    print_header("ClickHouse: Native MergeTree vs Iceberg Table Engine")
    all_results['clickhouse'] = {}

    for query_id, query_info in QUERIES.items():
        print(f"\n[ClickHouse] Running: {query_info['name']}...")
        result = run_iceberg_comparison(
            'ClickHouse',
            query_clickhouse,
            query_info['clickhouse_native'],
            query_info['clickhouse_iceberg']
        )

        if result:
            all_results['clickhouse'][query_id] = result
            print_comparison(
                query_info['name'],
                'ClickHouse',
                result['avg_native_ms'],
                result['avg_iceberg_ms'],
                result['slowdown_factor']
            )
        else:
            print(f"Skipping {query_info['name']} - Iceberg tables may not be set up yet")

    # === StarRocks: Native vs Iceberg ===
    print_header("StarRocks: Native Tables vs Iceberg External Catalog")
    all_results['starrocks'] = {}

    for query_id, query_info in QUERIES.items():
        print(f"\n[StarRocks] Running: {query_info['name']}...")
        result = run_iceberg_comparison(
            'StarRocks',
            query_starrocks,
            query_info['starrocks_native'],
            query_info['starrocks_iceberg']
        )

        if result:
            all_results['starrocks'][query_id] = result
            print_comparison(
                query_info['name'],
                'StarRocks',
                result['avg_native_ms'],
                result['avg_iceberg_ms'],
                result['slowdown_factor']
            )
        else:
            print(f"Skipping {query_info['name']} - Iceberg tables may not be set up yet")

    # === Summary ===
    print_header("Multi-Engine Comparison Summary")

    # Calculate averages if we have results
    if all_results.get('clickhouse'):
        clickhouse_slowdowns = [
            all_results['clickhouse'][q]['slowdown_factor']
            for q in QUERIES.keys()
            if q in all_results['clickhouse']
        ]
        if clickhouse_slowdowns:
            avg_slowdown = statistics.mean(clickhouse_slowdowns)
            print(f"\nClickHouse Iceberg Slowdown: {avg_slowdown:.2f}x slower than native MergeTree")

    if all_results.get('starrocks'):
        starrocks_slowdowns = [
            all_results['starrocks'][q]['slowdown_factor']
            for q in QUERIES.keys()
            if q in all_results['starrocks']
        ]
        if starrocks_slowdowns:
            avg_slowdown = statistics.mean(starrocks_slowdowns)
            print(f"StarRocks Iceberg Slowdown: {avg_slowdown:.2f}x slower than native tables")

    print("\n" + "="*80)
    print("Key Insights:")
    print("- ClickHouse Iceberg Engine: READ-ONLY access to shared tables")
    print("- StarRocks Iceberg Catalog: FULL READ-WRITE with ACID transactions")
    print("- Trade-off: Flexibility (multi-engine) vs Performance (native format)")
    print("- Use case: Data governance, unified catalog, cross-engine analytics")
    print("="*80 + "\n")

    # === Save Results ===
    output_file = f"results/iceberg_multi_engine_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w') as f:
        json.dump(all_results, f, indent=2)

    print(f"Results saved to: {output_file}")
    print(f"End Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print_header("Benchmark Complete")

if __name__ == '__main__':
    main()
