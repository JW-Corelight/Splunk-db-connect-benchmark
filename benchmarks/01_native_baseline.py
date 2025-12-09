#!/usr/bin/env python3
"""
Benchmark Script: Native Performance Baseline
Purpose: Measure raw query performance on native database formats
Databases: PostgreSQL, ClickHouse, StarRocks
Dataset: 100K cybersecurity events
Queries: Aggregations, filters, joins (5 queries per database)
"""

import time
import psycopg2
import clickhouse_connect
import pymysql
import json
import statistics
import sys
import argparse
from typing import Dict, List, Tuple
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

# Number of iterations for each query
ITERATIONS = 5

# === Test Queries ===
QUERIES = {
    'count_all': {
        'name': 'Count All Records',
        'postgresql': 'SELECT COUNT(*) as count FROM security_logs',
        'clickhouse': 'SELECT COUNT(*) as count FROM security_logs',
        'starrocks': 'SELECT COUNT(*) as count FROM security_logs'
    },
    'aggregation_by_event_type': {
        'name': 'Aggregate by Event Type',
        'postgresql': '''
            SELECT event_type, COUNT(*) as count,
                   SUM(bytes_in) as total_bytes_in,
                   AVG(bytes_out) as avg_bytes_out
            FROM security_logs
            GROUP BY event_type
            ORDER BY count DESC
            LIMIT 10
        ''',
        'clickhouse': '''
            SELECT event_type, COUNT(*) as count,
                   SUM(bytes_in) as total_bytes_in,
                   AVG(bytes_out) as avg_bytes_out
            FROM security_logs
            GROUP BY event_type
            ORDER BY count DESC
            LIMIT 10
        ''',
        'starrocks': '''
            SELECT event_type, COUNT(*) as count,
                   SUM(bytes_in) as total_bytes_in,
                   AVG(bytes_out) as avg_bytes_out
            FROM security_logs
            GROUP BY event_type
            ORDER BY count DESC
            LIMIT 10
        '''
    },
    'filter_failed_logins': {
        'name': 'Filter Failed Login Events',
        'postgresql': '''
            SELECT user_id, COUNT(*) as failed_attempts
            FROM security_logs
            WHERE event_type = 'ssh_login' AND status = 'failed'
            GROUP BY user_id
            HAVING COUNT(*) > 3
            ORDER BY failed_attempts DESC
        ''',
        'clickhouse': '''
            SELECT user_id, COUNT(*) as failed_attempts
            FROM security_logs
            WHERE event_type = 'ssh_login' AND status = 'failed'
            GROUP BY user_id
            HAVING COUNT(*) > 3
            ORDER BY failed_attempts DESC
        ''',
        'starrocks': '''
            SELECT user_id, COUNT(*) as failed_attempts
            FROM security_logs
            WHERE event_type = 'ssh_login' AND status = 'failed'
            GROUP BY user_id
            HAVING COUNT(*) > 3
            ORDER BY failed_attempts DESC
        '''
    },
    'time_range_aggregation': {
        'name': 'Time Range Aggregation (Last 7 Days)',
        'postgresql': '''
            SELECT DATE(timestamp) as day,
                   COUNT(*) as events,
                   COUNT(DISTINCT user_id) as unique_users
            FROM security_logs
            WHERE timestamp >= NOW() - INTERVAL '7 days'
            GROUP BY DATE(timestamp)
            ORDER BY day DESC
        ''',
        'clickhouse': '''
            SELECT toDate(timestamp) as day,
                   COUNT(*) as events,
                   uniqExact(user_id) as unique_users
            FROM security_logs
            WHERE timestamp >= now() - INTERVAL 7 DAY
            GROUP BY toDate(timestamp)
            ORDER BY day DESC
        ''',
        'starrocks': '''
            SELECT DATE(timestamp) as day,
                   COUNT(*) as events,
                   COUNT(DISTINCT user_id) as unique_users
            FROM security_logs
            WHERE timestamp >= NOW() - INTERVAL 7 DAY
            GROUP BY DATE(timestamp)
            ORDER BY day DESC
        '''
    },
    'top_data_transfer': {
        'name': 'Top Data Transfer Events',
        'postgresql': '''
            SELECT user_id, event_type, source_ip, dest_ip,
                   (bytes_in + bytes_out) as total_bytes
            FROM security_logs
            WHERE bytes_in IS NOT NULL AND bytes_out IS NOT NULL
            ORDER BY total_bytes DESC
            LIMIT 100
        ''',
        'clickhouse': '''
            SELECT user_id, event_type, source_ip, dest_ip,
                   (bytes_in + bytes_out) as total_bytes
            FROM security_logs
            WHERE bytes_in IS NOT NULL AND bytes_out IS NOT NULL
            ORDER BY total_bytes DESC
            LIMIT 100
        ''',
        'starrocks': '''
            SELECT user_id, event_type, source_ip, dest_ip,
                   (bytes_in + bytes_out) as total_bytes
            FROM security_logs
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

def print_result(query_name: str, db_name: str, latencies: List[float], row_count: int) -> None:
    """Print query execution results"""
    avg_latency = statistics.mean(latencies)
    min_latency = min(latencies)
    max_latency = max(latencies)
    std_dev = statistics.stdev(latencies) if len(latencies) > 1 else 0

    print(f"Query: {query_name}")
    print(f"Database: {db_name}")
    print(f"Rows Returned: {row_count}")
    print(f"Latency (ms):")
    print(f"  Avg: {avg_latency:.2f}")
    print(f"  Min: {min_latency:.2f}")
    print(f"  Max: {max_latency:.2f}")
    print(f"  StdDev: {std_dev:.2f}")
    print(f"{'-'*80}\n")

# === Database Query Functions ===
def query_postgresql(query: str) -> Tuple[List[Tuple], float]:
    """Execute query on PostgreSQL and return results + latency"""
    conn = psycopg2.connect(**POSTGRESQL_CONFIG)
    cursor = conn.cursor()

    start_time = time.perf_counter()
    cursor.execute(query)
    results = cursor.fetchall()
    end_time = time.perf_counter()

    latency_ms = (end_time - start_time) * 1000

    cursor.close()
    conn.close()

    return results, latency_ms

def query_clickhouse(query: str) -> Tuple[List[Tuple], float]:
    """Execute query on ClickHouse and return results + latency"""
    client = clickhouse_connect.get_client(
        host=CLICKHOUSE_CONFIG['host'],
        port=CLICKHOUSE_CONFIG['port'],
        database=CLICKHOUSE_CONFIG['database'],
        username=CLICKHOUSE_CONFIG['user'],
        password=CLICKHOUSE_CONFIG['password']
    )

    start_time = time.perf_counter()
    result = client.query(query)
    end_time = time.perf_counter()

    latency_ms = (end_time - start_time) * 1000

    return result.result_rows, latency_ms

def query_starrocks(query: str) -> Tuple[List[Tuple], float]:
    """Execute query on StarRocks (MySQL protocol) and return results + latency"""
    conn = pymysql.connect(
        host=STARROCKS_CONFIG['host'],
        port=STARROCKS_CONFIG['port'],
        database=STARROCKS_CONFIG['database'],
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
def run_benchmark(db_name: str, query_func, query: str) -> Dict:
    """Run benchmark for a single query"""
    latencies = []
    results = None

    for i in range(ITERATIONS):
        try:
            results, latency = query_func(query)
            latencies.append(latency)
        except Exception as e:
            print(f"Error executing query on {db_name}: {e}")
            return None

    return {
        'latencies': latencies,
        'row_count': len(results) if results else 0,
        'avg_latency_ms': statistics.mean(latencies),
        'min_latency_ms': min(latencies),
        'max_latency_ms': max(latencies)
    }

def main():
    """Main benchmark execution"""
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Native Performance Baseline Benchmark')
    parser.add_argument('--skip-starrocks', action='store_true',
                        help='Skip StarRocks benchmarks (use on ARM64/Apple Silicon)')
    args = parser.parse_args()

    print_header("Native Performance Baseline Benchmark")
    print(f"Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Iterations per Query: {ITERATIONS}")

    databases_to_test = ['PostgreSQL', 'ClickHouse']
    if not args.skip_starrocks:
        databases_to_test.append('StarRocks')
    else:
        print(f"⚠️  Skipping StarRocks (ARM64 incompatibility)")

    print(f"Databases: {', '.join(databases_to_test)}")
    print(f"Total Queries: {len(QUERIES) * len(databases_to_test)}")

    all_results = {}

    # === PostgreSQL Benchmarks ===
    print_header("PostgreSQL Native Queries")
    all_results['postgresql'] = {}

    for query_id, query_info in QUERIES.items():
        print(f"\n[PostgreSQL] Running: {query_info['name']}...")
        result = run_benchmark('PostgreSQL', query_postgresql, query_info['postgresql'])

        if result:
            all_results['postgresql'][query_id] = result
            print_result(query_info['name'], 'PostgreSQL', result['latencies'], result['row_count'])

    # === ClickHouse Benchmarks ===
    print_header("ClickHouse Native Queries")
    all_results['clickhouse'] = {}

    for query_id, query_info in QUERIES.items():
        print(f"\n[ClickHouse] Running: {query_info['name']}...")
        result = run_benchmark('ClickHouse', query_clickhouse, query_info['clickhouse'])

        if result:
            all_results['clickhouse'][query_id] = result
            print_result(query_info['name'], 'ClickHouse', result['latencies'], result['row_count'])

    # === StarRocks Benchmarks ===
    if not args.skip_starrocks:
        print_header("StarRocks Native Queries")
        all_results['starrocks'] = {}

        for query_id, query_info in QUERIES.items():
            print(f"\n[StarRocks] Running: {query_info['name']}...")
            result = run_benchmark('StarRocks', query_starrocks, query_info['starrocks'])

            if result:
                all_results['starrocks'][query_id] = result
                print_result(query_info['name'], 'StarRocks', result['latencies'], result['row_count'])

    # === Summary ===
    print_header("Benchmark Summary")

    for query_id, query_info in QUERIES.items():
        print(f"\n{query_info['name']}:")
        if query_id in all_results.get('postgresql', {}):
            print(f"  PostgreSQL: {all_results['postgresql'][query_id]['avg_latency_ms']:.2f} ms")
        if query_id in all_results.get('clickhouse', {}):
            print(f"  ClickHouse: {all_results['clickhouse'][query_id]['avg_latency_ms']:.2f} ms")
        if query_id in all_results.get('starrocks', {}):
            print(f"  StarRocks:  {all_results['starrocks'][query_id]['avg_latency_ms']:.2f} ms")

    # === Save Results ===
    output_file = f"results/native_baseline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w') as f:
        json.dump(all_results, f, indent=2)

    print(f"\n\nResults saved to: {output_file}")
    print(f"End Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print_header("Benchmark Complete")

if __name__ == '__main__':
    main()
