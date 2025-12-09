#!/usr/bin/env python3
"""
PostgreSQL Native Performance Benchmark
Purpose: Measure raw query performance on PostgreSQL
Dataset: 300K security events, 20K network events
"""

import time
import psycopg2
import statistics
from typing import List, Dict

# Configuration
POSTGRES_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'cybersecurity',
    'user': 'postgres',
    'password': 'postgres123'
}

ITERATIONS = 3

# Test Queries
QUERIES = {
    'count_security_logs': {
        'name': 'Count All Security Logs',
        'query': 'SELECT COUNT(*) FROM security_logs'
    },
    'count_network_logs': {
        'name': 'Count All Network Logs',
        'query': 'SELECT COUNT(*) FROM network_logs'
    },
    'aggregate_by_event_type': {
        'name': 'Aggregate Security Logs by Event Type',
        'query': '''
            SELECT event_type, COUNT(*) as count,
                   SUM(bytes_in) as total_bytes_in,
                   AVG(bytes_out) as avg_bytes_out
            FROM security_logs
            GROUP BY event_type
            ORDER BY count DESC
        '''
    },
    'filter_failed_logins': {
        'name': 'Filter Failed SSH Logins',
        'query': '''
            SELECT user_id, COUNT(*) as failed_attempts
            FROM security_logs
            WHERE event_type = 'ssh_login' AND status = 'failed'
            GROUP BY user_id
            HAVING COUNT(*) > 3
            ORDER BY failed_attempts DESC
            LIMIT 20
        '''
    },
    'network_traffic_by_protocol': {
        'name': 'Network Traffic Summary by Protocol',
        'query': '''
            SELECT protocol, direction,
                   COUNT(*) as connection_count,
                   SUM(bytes_total) as total_bytes,
                   AVG(duration_ms) as avg_duration_ms
            FROM network_logs
            GROUP BY protocol, direction
            ORDER BY total_bytes DESC
        '''
    },
    'top_talkers': {
        'name': 'Top 20 Source IPs by Traffic Volume',
        'query': '''
            SELECT src_ip,
                   COUNT(*) as connections,
                   SUM(bytes_total) as total_bytes
            FROM network_logs
            GROUP BY src_ip
            ORDER BY total_bytes DESC
            LIMIT 20
        '''
    },
    'security_timeline': {
        'name': 'Security Events Timeline (Hourly)',
        'query': '''
            SELECT DATE_TRUNC('hour', timestamp) as hour,
                   event_type,
                   COUNT(*) as event_count
            FROM security_logs
            WHERE timestamp > NOW() - INTERVAL '7 days'
            GROUP BY hour, event_type
            ORDER BY hour DESC, event_count DESC
            LIMIT 100
        '''
    },
    'join_security_network': {
        'name': 'Join Security and Network Logs',
        'query': '''
            SELECT s.user_id,
                   s.event_type,
                   COUNT(DISTINCT n.dest_ip) as unique_destinations,
                   SUM(n.bytes_total) as total_traffic
            FROM security_logs s
            JOIN network_logs n ON s.source_ip::text = n.src_ip::text
            WHERE s.timestamp > NOW() - INTERVAL '1 day'
            GROUP BY s.user_id, s.event_type
            HAVING SUM(n.bytes_total) > 100000
            ORDER BY total_traffic DESC
            LIMIT 50
        '''
    }
}

def run_query(conn, query: str) -> float:
    """Run query and return execution time in seconds"""
    cursor = conn.cursor()
    start_time = time.time()
    cursor.execute(query)
    results = cursor.fetchall()
    elapsed_time = time.time() - start_time
    cursor.close()
    return elapsed_time

def benchmark_query(conn, query_name: str, query_info: Dict) -> Dict:
    """Benchmark a single query multiple times"""
    print(f"\n  Running: {query_info['name']}...")

    times = []
    for i in range(ITERATIONS):
        try:
            elapsed = run_query(conn, query_info['query'])
            times.append(elapsed)
            print(f"    Iteration {i+1}: {elapsed:.4f}s")
        except Exception as e:
            print(f"    Error in iteration {i+1}: {e}")
            return None

    if not times:
        return None

    return {
        'name': query_info['name'],
        'query': query_name,
        'min': min(times),
        'max': max(times),
        'avg': statistics.mean(times),
        'median': statistics.median(times),
        'stddev': statistics.stdev(times) if len(times) > 1 else 0,
        'iterations': ITERATIONS
    }

def main():
    print("=" * 70)
    print("PostgreSQL Native Performance Benchmark")
    print("=" * 70)

    # Connect to PostgreSQL
    print("\nConnecting to PostgreSQL...")
    try:
        conn = psycopg2.connect(**POSTGRES_CONFIG)
        print("✓ Connected successfully")
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        return

    # Get table sizes
    print("\nVerifying data...")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM security_logs")
    security_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM network_logs")
    network_count = cursor.fetchone()[0]
    cursor.close()

    print(f"  security_logs: {security_count:,} records")
    print(f"  network_logs: {network_count:,} records")

    # Run benchmarks
    print(f"\n{'='*70}")
    print(f"Running Benchmarks ({ITERATIONS} iterations per query)")
    print("=" * 70)

    results = []
    for query_name, query_info in QUERIES.items():
        result = benchmark_query(conn, query_name, query_info)
        if result:
            results.append(result)

    conn.close()

    # Display results
    print(f"\n{'='*70}")
    print("Benchmark Results Summary")
    print("=" * 70)
    print(f"\n{'Query':<50} {'Min':<10} {'Avg':<10} {'Max':<10}")
    print("-" * 70)

    for result in results:
        print(f"{result['name'][:48]:<50} {result['min']:<10.4f} {result['avg']:<10.4f} {result['max']:<10.4f}")

    # Performance analysis
    print(f"\n{'='*70}")
    print("Performance Analysis")
    print("=" * 70)

    total_time = sum(r['avg'] for r in results)
    fastest = min(results, key=lambda x: x['avg'])
    slowest = max(results, key=lambda x: x['avg'])

    print(f"\nTotal benchmark time: {total_time:.2f}s")
    print(f"Fastest query: {fastest['name']} ({fastest['avg']:.4f}s)")
    print(f"Slowest query: {slowest['name']} ({slowest['avg']:.4f}s)")

    # Database info
    print(f"\n{'='*70}")
    print("Environment Information")
    print("=" * 70)
    print(f"Database: PostgreSQL 16 (ARM64 native)")
    print(f"Platform: Apple Silicon M3")
    print(f"Dataset: {security_count:,} security logs, {network_count:,} network logs")
    print(f"Iterations per query: {ITERATIONS}")

    print(f"\n{'='*70}")
    print("Benchmark Complete")
    print("=" * 70)

if __name__ == "__main__":
    main()
