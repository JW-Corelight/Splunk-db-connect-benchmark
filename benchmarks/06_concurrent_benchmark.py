#!/usr/bin/env python3
"""
Benchmark Script: Concurrent Query Performance
Purpose: Measure database throughput under concurrent query load
Engines: PostgreSQL, ClickHouse, DuckDB (StarRocks optional)
Concurrency Levels: 1, 5, 10, 25 simultaneous queries
Metrics: Throughput (queries/sec), p50/p95/p99 latency, error rate
"""

import time
import json
import statistics
import sys
import os
import argparse
import platform
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
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

DUCKDB_DB_PATH = 'results/duckdb_benchmark.db'

CONCURRENCY_LEVELS = [1, 5, 10, 25]

# Each thread runs this many queries at each concurrency level
QUERIES_PER_THREAD = 5

# === Query Mix ===
# A representative set of queries varying in complexity.
# Each engine gets its own SQL where syntax differs.
QUERY_MIX = [
    {
        'name': 'count_all',
        'postgresql': 'SELECT COUNT(*) FROM security_logs',
        'clickhouse': 'SELECT COUNT(*) FROM security_logs',
        'starrocks': 'SELECT COUNT(*) FROM security_logs',
        'duckdb': 'SELECT COUNT(*) FROM security_logs'
    },
    {
        'name': 'aggregation',
        'postgresql': '''
            SELECT event_type, COUNT(*) as cnt, SUM(bytes_in) as total_in
            FROM security_logs GROUP BY event_type ORDER BY cnt DESC LIMIT 10
        ''',
        'clickhouse': '''
            SELECT event_type, COUNT(*) as cnt, SUM(bytes_in) as total_in
            FROM security_logs GROUP BY event_type ORDER BY cnt DESC LIMIT 10
        ''',
        'starrocks': '''
            SELECT event_type, COUNT(*) as cnt, SUM(bytes_in) as total_in
            FROM security_logs GROUP BY event_type ORDER BY cnt DESC LIMIT 10
        ''',
        'duckdb': '''
            SELECT event_type, COUNT(*) as cnt, SUM(bytes_in) as total_in
            FROM security_logs GROUP BY event_type ORDER BY cnt DESC LIMIT 10
        '''
    },
    {
        'name': 'filter',
        'postgresql': '''
            SELECT user_id, COUNT(*) as failed
            FROM security_logs
            WHERE event_type = 'ssh_login' AND status = 'failed'
            GROUP BY user_id HAVING COUNT(*) > 3
            ORDER BY failed DESC
        ''',
        'clickhouse': '''
            SELECT user_id, COUNT(*) as failed
            FROM security_logs
            WHERE event_type = 'ssh_login' AND status = 'failed'
            GROUP BY user_id HAVING COUNT(*) > 3
            ORDER BY failed DESC
        ''',
        'starrocks': '''
            SELECT user_id, COUNT(*) as failed
            FROM security_logs
            WHERE event_type = 'ssh_login' AND status = 'failed'
            GROUP BY user_id HAVING COUNT(*) > 3
            ORDER BY failed DESC
        ''',
        'duckdb': '''
            SELECT user_id, COUNT(*) as failed
            FROM security_logs
            WHERE event_type = 'ssh_login' AND status = 'failed'
            GROUP BY user_id HAVING COUNT(*) > 3
            ORDER BY failed DESC
        '''
    },
    {
        'name': 'time_range',
        'postgresql': '''
            SELECT DATE(timestamp) as day, COUNT(*) as events
            FROM security_logs
            WHERE timestamp >= NOW() - INTERVAL '7 days'
            GROUP BY DATE(timestamp) ORDER BY day DESC
        ''',
        'clickhouse': '''
            SELECT toDate(timestamp) as day, COUNT(*) as events
            FROM security_logs
            WHERE timestamp >= now() - INTERVAL 7 DAY
            GROUP BY toDate(timestamp) ORDER BY day DESC
        ''',
        'starrocks': '''
            SELECT DATE(timestamp) as day, COUNT(*) as events
            FROM security_logs
            WHERE timestamp >= NOW() - INTERVAL 7 DAY
            GROUP BY DATE(timestamp) ORDER BY day DESC
        ''',
        'duckdb': '''
            SELECT DATE_TRUNC('day', timestamp) as day, COUNT(*) as events
            FROM security_logs
            WHERE timestamp >= CURRENT_TIMESTAMP - INTERVAL '7 days'
            GROUP BY DATE_TRUNC('day', timestamp) ORDER BY day DESC
        '''
    },
    {
        'name': 'top_transfer',
        'postgresql': '''
            SELECT user_id, event_type, (bytes_in + bytes_out) as total_bytes
            FROM security_logs
            WHERE bytes_in IS NOT NULL AND bytes_out IS NOT NULL
            ORDER BY total_bytes DESC LIMIT 100
        ''',
        'clickhouse': '''
            SELECT user_id, event_type, (bytes_in + bytes_out) as total_bytes
            FROM security_logs
            WHERE bytes_in IS NOT NULL AND bytes_out IS NOT NULL
            ORDER BY total_bytes DESC LIMIT 100
        ''',
        'starrocks': '''
            SELECT user_id, event_type, (bytes_in + bytes_out) as total_bytes
            FROM security_logs
            WHERE bytes_in IS NOT NULL AND bytes_out IS NOT NULL
            ORDER BY total_bytes DESC LIMIT 100
        ''',
        'duckdb': '''
            SELECT user_id, event_type, (bytes_in + bytes_out) as total_bytes
            FROM security_logs
            WHERE bytes_in IS NOT NULL AND bytes_out IS NOT NULL
            ORDER BY total_bytes DESC LIMIT 100
        '''
    }
]

# === Utility Functions ===
def print_header(text: str) -> None:
    """Print a formatted header"""
    print(f"\n{'='*80}")
    print(f"{text:^80}")
    print(f"{'='*80}\n")

def percentile(data: List[float], p: float) -> float:
    """Calculate the p-th percentile of a list"""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * (p / 100.0)
    f = int(k)
    c = f + 1
    if c >= len(sorted_data):
        return sorted_data[f]
    return sorted_data[f] + (k - f) * (sorted_data[c] - sorted_data[f])

# === Connection Factories ===
# Each returns a (query_func, close_func) pair.
# query_func(sql) -> (rows, latency_ms)
# close_func() cleans up the connection.

def make_postgresql_conn():
    import psycopg2
    conn = psycopg2.connect(**POSTGRESQL_CONFIG)

    def query(sql):
        cur = conn.cursor()
        start = time.perf_counter()
        cur.execute(sql)
        rows = cur.fetchall()
        latency = (time.perf_counter() - start) * 1000
        cur.close()
        return rows, latency

    return query, conn.close

def make_clickhouse_conn():
    import clickhouse_connect
    client = clickhouse_connect.get_client(
        host=CLICKHOUSE_CONFIG['host'],
        port=CLICKHOUSE_CONFIG['port'],
        database=CLICKHOUSE_CONFIG['database'],
        username=CLICKHOUSE_CONFIG['user'],
        password=CLICKHOUSE_CONFIG['password']
    )

    def query(sql):
        start = time.perf_counter()
        result = client.query(sql)
        latency = (time.perf_counter() - start) * 1000
        return result.result_rows, latency

    return query, client.close

def make_starrocks_conn():
    import pymysql
    conn = pymysql.connect(
        host=STARROCKS_CONFIG['host'],
        port=STARROCKS_CONFIG['port'],
        database=STARROCKS_CONFIG['database'],
        user=STARROCKS_CONFIG['user'],
        password=STARROCKS_CONFIG['password']
    )

    def query(sql):
        cur = conn.cursor()
        start = time.perf_counter()
        cur.execute(sql)
        rows = cur.fetchall()
        latency = (time.perf_counter() - start) * 1000
        cur.close()
        return rows, latency

    return query, conn.close

def make_duckdb_conn(db_path: str):
    import duckdb
    conn = duckdb.connect(db_path, read_only=True)

    def query(sql):
        start = time.perf_counter()
        rows = conn.execute(sql).fetchall()
        latency = (time.perf_counter() - start) * 1000
        return rows, latency

    return query, conn.close

# === Worker Function ===
def worker(engine_name: str, engine_key: str, conn_factory, queries_per_thread: int) -> List[Dict]:
    """
    Run a batch of queries on a single connection.
    Returns a list of {query_name, latency_ms, error} dicts.
    """
    results = []
    try:
        query_func, close_func = conn_factory()
    except Exception as e:
        # Connection failed — return errors for all planned queries
        for i in range(queries_per_thread):
            q = QUERY_MIX[i % len(QUERY_MIX)]
            results.append({'query_name': q['name'], 'latency_ms': None, 'error': str(e)})
        return results

    try:
        for i in range(queries_per_thread):
            q = QUERY_MIX[i % len(QUERY_MIX)]
            try:
                _, latency = query_func(q[engine_key])
                results.append({'query_name': q['name'], 'latency_ms': latency, 'error': None})
            except Exception as e:
                results.append({'query_name': q['name'], 'latency_ms': None, 'error': str(e)})
    finally:
        try:
            close_func()
        except Exception:
            pass

    return results

# === Benchmark Runner ===
def run_concurrent_benchmark(engine_name: str, engine_key: str,
                             conn_factory, concurrency: int) -> Dict:
    """
    Run concurrent benchmark at a given concurrency level.
    Each thread gets its own connection and runs QUERIES_PER_THREAD queries.
    """
    all_latencies = []
    all_errors = 0
    total_queries = concurrency * QUERIES_PER_THREAD

    wall_start = time.perf_counter()

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [
            pool.submit(worker, engine_name, engine_key, conn_factory, QUERIES_PER_THREAD)
            for _ in range(concurrency)
        ]

        for future in as_completed(futures):
            for result in future.result():
                if result['latency_ms'] is not None:
                    all_latencies.append(result['latency_ms'])
                else:
                    all_errors += 1

    wall_time_ms = (time.perf_counter() - wall_start) * 1000
    successful = len(all_latencies)
    throughput = (successful / wall_time_ms) * 1000 if wall_time_ms > 0 else 0

    stats = {}
    if all_latencies:
        stats = {
            'avg_latency_ms': round(statistics.mean(all_latencies), 2),
            'p50_latency_ms': round(percentile(all_latencies, 50), 2),
            'p95_latency_ms': round(percentile(all_latencies, 95), 2),
            'p99_latency_ms': round(percentile(all_latencies, 99), 2),
            'min_latency_ms': round(min(all_latencies), 2),
            'max_latency_ms': round(max(all_latencies), 2)
        }

    return {
        'concurrency': concurrency,
        'total_queries': total_queries,
        'successful_queries': successful,
        'failed_queries': all_errors,
        'wall_time_ms': round(wall_time_ms, 2),
        'throughput_qps': round(throughput, 2),
        'error_rate_pct': round((all_errors / total_queries) * 100, 1) if total_queries > 0 else 0,
        **stats
    }

# === Availability Checks ===
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
            host=CLICKHOUSE_CONFIG['host'],
            port=CLICKHOUSE_CONFIG['port'],
            database=CLICKHOUSE_CONFIG['database'],
            username=CLICKHOUSE_CONFIG['user'],
            password=CLICKHOUSE_CONFIG['password']
        )
        client.close()
        return True
    except Exception:
        return False

def check_starrocks() -> bool:
    try:
        import pymysql
        conn = pymysql.connect(
            host=STARROCKS_CONFIG['host'],
            port=STARROCKS_CONFIG['port'],
            database=STARROCKS_CONFIG['database'],
            user=STARROCKS_CONFIG['user'],
            password=STARROCKS_CONFIG['password']
        )
        conn.close()
        return True
    except Exception:
        return False

def check_duckdb(db_path: str) -> bool:
    try:
        import duckdb
        conn = duckdb.connect(db_path, read_only=True)
        conn.execute("SELECT COUNT(*) FROM security_logs").fetchone()
        conn.close()
        return True
    except Exception:
        return False

# === Main ===
def main():
    global QUERIES_PER_THREAD

    parser = argparse.ArgumentParser(description='Concurrent Query Performance Benchmark')
    parser.add_argument('--engines', nargs='+',
                        choices=['postgresql', 'clickhouse', 'starrocks', 'duckdb'],
                        help='Engines to test (default: auto-detect available)')
    parser.add_argument('--levels', nargs='+', type=int,
                        default=CONCURRENCY_LEVELS,
                        help=f'Concurrency levels (default: {CONCURRENCY_LEVELS})')
    parser.add_argument('--queries-per-thread', type=int, default=QUERIES_PER_THREAD,
                        help=f'Queries each thread executes (default: {QUERIES_PER_THREAD})')
    args = parser.parse_args()

    QUERIES_PER_THREAD = args.queries_per_thread

    print_header("Concurrent Query Performance Benchmark")
    print(f"Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Platform: {platform.machine()}")
    print(f"Concurrency Levels: {args.levels}")
    print(f"Queries per Thread: {QUERIES_PER_THREAD}")
    print(f"Query Mix: {len(QUERY_MIX)} queries (cycled)")

    # Detect available engines
    db_path = os.path.join(os.path.dirname(__file__), DUCKDB_DB_PATH)

    engine_checks = {
        'postgresql': ('PostgreSQL', check_postgresql, 'postgresql', make_postgresql_conn),
        'clickhouse': ('ClickHouse', check_clickhouse, 'clickhouse', make_clickhouse_conn),
        'starrocks': ('StarRocks', check_starrocks, 'starrocks', make_starrocks_conn),
        'duckdb': ('DuckDB', lambda: check_duckdb(db_path), 'duckdb',
                   lambda: make_duckdb_conn(db_path)),
    }

    engines_to_test = []
    requested = args.engines or list(engine_checks.keys())

    print("\nEngine availability:")
    for key in requested:
        name, check_fn, engine_key, factory = engine_checks[key]
        available = check_fn()
        status = "available" if available else "not available"
        print(f"  {name}: {status}")
        if available:
            engines_to_test.append((name, engine_key, factory))

    if not engines_to_test:
        print("\nNo engines available. Start services or create DuckDB database first.")
        print("  DuckDB: python3 05_duckdb_benchmark.py --skip-parquet --skip-iceberg")
        print("  Others: docker-compose -f docker-compose.m3.yml up -d")
        return

    all_results = {
        'metadata': {
            'timestamp': datetime.now().isoformat(),
            'platform': platform.machine(),
            'concurrency_levels': args.levels,
            'queries_per_thread': QUERIES_PER_THREAD,
            'query_mix_size': len(QUERY_MIX)
        }
    }

    # Run benchmarks
    for engine_name, engine_key, conn_factory in engines_to_test:
        print_header(f"{engine_name} Concurrent Benchmarks")
        engine_results = []

        for level in args.levels:
            total = level * QUERIES_PER_THREAD
            print(f"\n[{engine_name}] Concurrency={level} ({total} total queries)...")

            result = run_concurrent_benchmark(engine_name, engine_key, conn_factory, level)
            engine_results.append(result)

            print(f"  Throughput: {result['throughput_qps']:.1f} queries/sec")
            print(f"  Wall time: {result['wall_time_ms']:.0f} ms")
            if result.get('p50_latency_ms') is not None:
                print(f"  Latency p50/p95/p99: "
                      f"{result['p50_latency_ms']:.1f} / "
                      f"{result['p95_latency_ms']:.1f} / "
                      f"{result['p99_latency_ms']:.1f} ms")
            if result['failed_queries'] > 0:
                print(f"  Errors: {result['failed_queries']}/{result['total_queries']} "
                      f"({result['error_rate_pct']:.1f}%)")

        all_results[engine_key] = engine_results

    # Summary
    print_header("Concurrent Benchmark Summary")

    # Table header
    header = f"{'Engine':<14} {'Conc':>5} {'QPS':>8} {'p50ms':>8} {'p95ms':>8} {'p99ms':>8} {'Errors':>7}"
    print(header)
    print("-" * len(header))

    for engine_name, engine_key, _ in engines_to_test:
        for result in all_results.get(engine_key, []):
            p50 = result.get('p50_latency_ms', '-')
            p95 = result.get('p95_latency_ms', '-')
            p99 = result.get('p99_latency_ms', '-')
            p50_s = f"{p50:.1f}" if isinstance(p50, (int, float)) else p50
            p95_s = f"{p95:.1f}" if isinstance(p95, (int, float)) else p95
            p99_s = f"{p99:.1f}" if isinstance(p99, (int, float)) else p99
            err = f"{result['error_rate_pct']:.0f}%"
            print(f"{engine_name:<14} {result['concurrency']:>5} "
                  f"{result['throughput_qps']:>8.1f} "
                  f"{p50_s:>8} {p95_s:>8} {p99_s:>8} {err:>7}")

    print("\n" + "="*80)
    print("Key Insights:")
    print("- Throughput (QPS) shows how well each engine handles concurrent load")
    print("- p95/p99 latency reveals tail latency under contention")
    print("- DuckDB uses in-process threads (no network); others use TCP connections")
    print("- Error rate indicates connection pool / concurrency limits")
    print("="*80 + "\n")

    # Save results
    output_file = f"results/concurrent_benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    output_path = os.path.join(os.path.dirname(__file__), output_file)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, 'w') as f:
        json.dump(all_results, f, indent=2)

    print(f"Results saved to: {output_file}")
    print(f"End Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print_header("Benchmark Complete")

if __name__ == '__main__':
    main()
