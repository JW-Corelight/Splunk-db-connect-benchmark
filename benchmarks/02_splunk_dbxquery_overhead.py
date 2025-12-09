#!/usr/bin/env python3
"""
Benchmark Script: Splunk dbxquery Overhead
Purpose: Measure overhead added by Splunk's dbxquery proxy
Method: Compare direct database queries vs queries through Splunk dbxquery
Databases: PostgreSQL, ClickHouse, StarRocks
Metrics: Latency difference, throughput impact
"""

import time
import psycopg2
import clickhouse_connect
import pymysql
import subprocess
import json
import statistics
import re
from typing import Dict, List, Tuple, Optional
from datetime import datetime

# === Configuration ===
SPLUNK_CONFIG = {
    'container': 'benchmark-splunk',
    'splunk_home': '/opt/splunk',
    'auth': 'admin:changeme'
}

POSTGRESQL_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'cybersecurity',
    'user': 'benchmark_user',
    'password': 'benchmark_pass',
    'splunk_connection': 'postgresql_conn'
}

CLICKHOUSE_CONFIG = {
    'host': 'localhost',
    'port': 8123,
    'database': 'cybersecurity',
    'user': 'default',
    'password': '',
    'splunk_connection': 'clickhouse_conn'
}

STARROCKS_CONFIG = {
    'host': 'localhost',
    'port': 9030,
    'database': 'cybersecurity',
    'user': 'root',
    'password': '',
    'splunk_connection': 'starrocks_conn'
}

# Number of iterations for each query
ITERATIONS = 5

# === Test Queries (same queries for fair comparison) ===
QUERIES = {
    'count_all': {
        'name': 'Count All Records',
        'sql': 'SELECT COUNT(*) as count FROM security_logs'
    },
    'aggregation_by_event_type': {
        'name': 'Aggregate by Event Type (Top 10)',
        'sql': '''
            SELECT event_type, COUNT(*) as count,
                   SUM(bytes_in) as total_bytes_in
            FROM security_logs
            GROUP BY event_type
            ORDER BY count DESC
            LIMIT 10
        '''
    },
    'filter_failed_logins': {
        'name': 'Filter Failed Login Events',
        'sql': '''
            SELECT user_id, COUNT(*) as failed_attempts
            FROM security_logs
            WHERE event_type = 'ssh_login' AND status = 'failed'
            GROUP BY user_id
            HAVING COUNT(*) > 3
            ORDER BY failed_attempts DESC
        '''
    },
    'top_data_transfer': {
        'name': 'Top 100 Data Transfer Events',
        'sql': '''
            SELECT user_id, event_type, source_ip, dest_ip
            FROM security_logs
            WHERE bytes_in IS NOT NULL AND bytes_out IS NOT NULL
            ORDER BY (bytes_in + bytes_out) DESC
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

def print_comparison(query_name: str, db_name: str, direct_latency: float,
                     splunk_latency: float, overhead_ms: float, overhead_pct: float) -> None:
    """Print overhead comparison results"""
    print(f"Query: {query_name}")
    print(f"Database: {db_name}")
    print(f"Direct Query Latency:  {direct_latency:.2f} ms")
    print(f"Splunk dbxquery Latency: {splunk_latency:.2f} ms")
    print(f"Overhead: {overhead_ms:.2f} ms ({overhead_pct:.1f}%)")
    print(f"{'-'*80}\n")

# === Direct Database Query Functions ===
def query_postgresql_direct(query: str) -> Tuple[List[Tuple], float]:
    """Execute query directly on PostgreSQL"""
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

def query_clickhouse_direct(query: str) -> Tuple[List[Tuple], float]:
    """Execute query directly on ClickHouse"""
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

def query_starrocks_direct(query: str) -> Tuple[List[Tuple], float]:
    """Execute query directly on StarRocks"""
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

# === Splunk dbxquery Functions ===
def query_via_splunk_dbxquery(connection: str, query: str) -> Tuple[Optional[str], float]:
    """Execute query via Splunk dbxquery and return results + latency"""

    # Escape single quotes in SQL query
    escaped_query = query.replace("'", "\\'")

    # Build Splunk search command
    search_query = f'| dbxquery connection="{connection}" query="{escaped_query}"'

    # Execute via docker exec
    cmd = [
        'docker', 'exec', SPLUNK_CONFIG['container'],
        f"{SPLUNK_CONFIG['splunk_home']}/bin/splunk", 'search',
        search_query,
        '-auth', SPLUNK_CONFIG['auth']
    ]

    start_time = time.perf_counter()

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        end_time = time.perf_counter()

        latency_ms = (end_time - start_time) * 1000

        if result.returncode == 0:
            return result.stdout, latency_ms
        else:
            print(f"ERROR: dbxquery failed with return code {result.returncode}")
            print(f"STDERR: {result.stderr}")
            return None, latency_ms

    except subprocess.TimeoutExpired:
        end_time = time.perf_counter()
        latency_ms = (end_time - start_time) * 1000
        print(f"ERROR: dbxquery timed out after {latency_ms:.0f} ms")
        return None, latency_ms
    except Exception as e:
        end_time = time.perf_counter()
        latency_ms = (end_time - start_time) * 1000
        print(f"ERROR: dbxquery exception: {e}")
        return None, latency_ms

# === Benchmark Execution ===
def run_overhead_benchmark(db_name: str, direct_query_func, splunk_connection: str, query: str) -> Dict:
    """Compare direct query vs Splunk dbxquery for a single query"""

    direct_latencies = []
    splunk_latencies = []

    # Run direct queries
    for i in range(ITERATIONS):
        try:
            _, latency = direct_query_func(query)
            direct_latencies.append(latency)
        except Exception as e:
            print(f"Error in direct query on {db_name}: {e}")
            return None

    # Run Splunk dbxquery queries
    for i in range(ITERATIONS):
        try:
            _, latency = query_via_splunk_dbxquery(splunk_connection, query)
            splunk_latencies.append(latency)
        except Exception as e:
            print(f"Error in Splunk dbxquery on {db_name}: {e}")
            return None

    avg_direct = statistics.mean(direct_latencies)
    avg_splunk = statistics.mean(splunk_latencies)
    overhead_ms = avg_splunk - avg_direct
    overhead_pct = (overhead_ms / avg_direct) * 100 if avg_direct > 0 else 0

    return {
        'direct_latencies': direct_latencies,
        'splunk_latencies': splunk_latencies,
        'avg_direct_ms': avg_direct,
        'avg_splunk_ms': avg_splunk,
        'overhead_ms': overhead_ms,
        'overhead_pct': overhead_pct
    }

def main():
    """Main benchmark execution"""
    print_header("Splunk dbxquery Overhead Benchmark")
    print(f"Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Iterations per Query: {ITERATIONS}")
    print(f"Testing: Direct Queries vs Splunk dbxquery Proxy")

    all_results = {}

    # === PostgreSQL Overhead Tests ===
    print_header("PostgreSQL: Direct vs Splunk dbxquery")
    all_results['postgresql'] = {}

    for query_id, query_info in QUERIES.items():
        print(f"\n[PostgreSQL] Running: {query_info['name']}...")
        result = run_overhead_benchmark(
            'PostgreSQL',
            query_postgresql_direct,
            POSTGRESQL_CONFIG['splunk_connection'],
            query_info['sql']
        )

        if result:
            all_results['postgresql'][query_id] = result
            print_comparison(
                query_info['name'],
                'PostgreSQL',
                result['avg_direct_ms'],
                result['avg_splunk_ms'],
                result['overhead_ms'],
                result['overhead_pct']
            )

    # === ClickHouse Overhead Tests ===
    print_header("ClickHouse: Direct vs Splunk dbxquery")
    all_results['clickhouse'] = {}

    for query_id, query_info in QUERIES.items():
        print(f"\n[ClickHouse] Running: {query_info['name']}...")
        result = run_overhead_benchmark(
            'ClickHouse',
            query_clickhouse_direct,
            CLICKHOUSE_CONFIG['splunk_connection'],
            query_info['sql']
        )

        if result:
            all_results['clickhouse'][query_id] = result
            print_comparison(
                query_info['name'],
                'ClickHouse',
                result['avg_direct_ms'],
                result['avg_splunk_ms'],
                result['overhead_ms'],
                result['overhead_pct']
            )

    # === StarRocks Overhead Tests ===
    print_header("StarRocks: Direct vs Splunk dbxquery")
    all_results['starrocks'] = {}

    for query_id, query_info in QUERIES.items():
        print(f"\n[StarRocks] Running: {query_info['name']}...")
        result = run_overhead_benchmark(
            'StarRocks',
            query_starrocks_direct,
            STARROCKS_CONFIG['splunk_connection'],
            query_info['sql']
        )

        if result:
            all_results['starrocks'][query_id] = result
            print_comparison(
                query_info['name'],
                'StarRocks',
                result['avg_direct_ms'],
                result['avg_splunk_ms'],
                result['overhead_ms'],
                result['overhead_pct']
            )

    # === Summary ===
    print_header("Overhead Summary")

    for db in ['postgresql', 'clickhouse', 'starrocks']:
        avg_overhead_ms = statistics.mean([
            all_results[db][q]['overhead_ms'] for q in QUERIES.keys()
        ])
        avg_overhead_pct = statistics.mean([
            all_results[db][q]['overhead_pct'] for q in QUERIES.keys()
        ])

        print(f"\n{db.upper()}:")
        print(f"  Average Overhead: {avg_overhead_ms:.2f} ms ({avg_overhead_pct:.1f}%)")

    # === Save Results ===
    output_file = f"results/splunk_overhead_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w') as f:
        json.dump(all_results, f, indent=2)

    print(f"\n\nResults saved to: {output_file}")
    print(f"End Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print_header("Benchmark Complete")

if __name__ == '__main__':
    main()
