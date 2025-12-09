#!/usr/bin/env python3
"""
Benchmark: Native Format vs Multi-Engine Parquet/S3
Purpose: Measure performance trade-off of using shared format (Parquet/S3) vs native format
Comparison: ClickHouse native (MergeTree) vs ClickHouse S3 (Parquet in MinIO)
Insight: Demonstrates cost of multi-engine access patterns
"""

import clickhouse_connect
import time
import statistics
import json
from datetime import datetime
from typing import Dict, List

# Configuration
CLICKHOUSE_CONFIG = {
    'host': 'localhost',
    'port': 8123,
    'database': 'cybersecurity',
    'username': 'default',
    'password': ''
}

ITERATIONS = 5

# Test Queries
QUERIES = {
    'count_all': {
        'name': 'Count All Records',
        'native': 'SELECT COUNT(*) as count FROM security_logs',
        'parquet': 'SELECT COUNT(*) as count FROM security_logs_parquet'
    },
    'aggregation_by_event_type': {
        'name': 'Aggregate by Event Type',
        'native': '''
            SELECT event_type, COUNT(*) as count,
                   AVG(bytes_in) as avg_bytes_in
            FROM security_logs
            GROUP BY event_type
            ORDER BY count DESC
            LIMIT 10
        ''',
        'parquet': '''
            SELECT event_type, COUNT(*) as count,
                   AVG(bytes_in) as avg_bytes_in
            FROM security_logs_parquet
            GROUP BY event_type
            ORDER BY count DESC
            LIMIT 10
        '''
    },
    'filter_failed_logins': {
        'name': 'Filter Failed Login Events',
        'native': '''
            SELECT user_id, COUNT(*) as failed_attempts
            FROM security_logs
            WHERE event_type = 'ssh_login' AND status = 'failed'
            GROUP BY user_id
            HAVING COUNT(*) > 3
            ORDER BY failed_attempts DESC
            LIMIT 20
        ''',
        'parquet': '''
            SELECT user_id, COUNT(*) as failed_attempts
            FROM security_logs_parquet
            WHERE event_type = 'ssh_login' AND status = 'failed'
            GROUP BY user_id
            HAVING COUNT(*) > 3
            ORDER BY failed_attempts DESC
            LIMIT 20
        '''
    },
    'top_data_transfer': {
        'name': 'Top 100 Data Transfer Events',
        'native': '''
            SELECT user_id, event_type, source_ip
            FROM security_logs
            WHERE bytes_in IS NOT NULL AND bytes_out IS NOT NULL
            ORDER BY (bytes_in + bytes_out) DESC
            LIMIT 100
        ''',
        'parquet': '''
            SELECT user_id, event_type, source_ip
            FROM security_logs_parquet
            WHERE bytes_in IS NOT NULL AND bytes_out IS NOT NULL
            ORDER BY (bytes_in + bytes_out) DESC
            LIMIT 100
        '''
    }
}

def print_header(text: str) -> None:
    print(f"\n{'='*80}")
    print(f"{text:^80}")
    print(f"{'='*80}\n")

def benchmark_query(client, query: str, iterations: int = ITERATIONS) -> Dict:
    """Execute query multiple times and return timing statistics"""
    latencies = []

    for i in range(iterations):
        start_time = time.perf_counter()
        client.query(query)
        end_time = time.perf_counter()
        latency_ms = (end_time - start_time) * 1000
        latencies.append(latency_ms)

    return {
        'min_ms': min(latencies),
        'max_ms': max(latencies),
        'avg_ms': statistics.mean(latencies),
        'median_ms': statistics.median(latencies),
        'stddev_ms': statistics.stdev(latencies) if len(latencies) > 1 else 0,
        'latencies': latencies
    }

def main():
    print_header("Native Format vs Multi-Engine Parquet/S3 Benchmark")
    print(f"Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Iterations per Query: {ITERATIONS}")
    print(f"Comparison: ClickHouse Native (MergeTree) vs S3/Parquet\n")

    # Connect to ClickHouse
    print("Connecting to ClickHouse...")
    client = clickhouse_connect.get_client(**CLICKHOUSE_CONFIG)
    print("✅ Connected\n")

    # Get row counts
    print("📊 Dataset Information:")
    native_count = client.query("SELECT COUNT(*) FROM security_logs").result_rows[0][0]
    parquet_count = client.query("SELECT COUNT(*) FROM security_logs_parquet").result_rows[0][0]
    print(f"  Native table (MergeTree):  {native_count:,} records")
    print(f"  Parquet table (S3/MinIO):  {parquet_count:,} records")

    all_results = {}

    # Run benchmarks
    for query_id, query_info in QUERIES.items():
        print(f"\n{'='*80}")
        print(f"Query: {query_info['name']}")
        print(f"{'='*80}")

        # Benchmark native format
        print(f"\n  [Native] Running...")
        native_result = benchmark_query(client, query_info['native'])

        # Benchmark Parquet format
        print(f"  [Parquet] Running...")
        parquet_result = benchmark_query(client, query_info['parquet'])

        # Calculate overhead
        overhead_ms = parquet_result['avg_ms'] - native_result['avg_ms']
        overhead_pct = (overhead_ms / native_result['avg_ms']) * 100 if native_result['avg_ms'] > 0 else 0
        slowdown_factor = parquet_result['avg_ms'] / native_result['avg_ms'] if native_result['avg_ms'] > 0 else 0

        # Print results
        print(f"\n  📊 Results:")
        print(f"     Native (MergeTree):  {native_result['avg_ms']:.2f} ms  "
              f"(min: {native_result['min_ms']:.2f}, max: {native_result['max_ms']:.2f})")
        print(f"     Parquet (S3/MinIO):  {parquet_result['avg_ms']:.2f} ms  "
              f"(min: {parquet_result['min_ms']:.2f}, max: {parquet_result['max_ms']:.2f})")
        print(f"     Overhead:            {overhead_ms:+.2f} ms ({overhead_pct:+.1f}%)")
        print(f"     Slowdown Factor:     {slowdown_factor:.2f}x")

        # Store results
        all_results[query_id] = {
            'name': query_info['name'],
            'native': native_result,
            'parquet': parquet_result,
            'overhead_ms': overhead_ms,
            'overhead_pct': overhead_pct,
            'slowdown_factor': slowdown_factor
        }

    # Summary
    print_header("Summary")

    avg_native = statistics.mean([r['native']['avg_ms'] for r in all_results.values()])
    avg_parquet = statistics.mean([r['parquet']['avg_ms'] for r in all_results.values()])
    avg_overhead = statistics.mean([r['overhead_ms'] for r in all_results.values()])
    avg_overhead_pct = statistics.mean([r['overhead_pct'] for r in all_results.values()])
    avg_slowdown = statistics.mean([r['slowdown_factor'] for r in all_results.values()])

    print(f"Average Query Performance:")
    print(f"  Native (MergeTree):      {avg_native:.2f} ms")
    print(f"  Parquet (S3/MinIO):      {avg_parquet:.2f} ms")
    print(f"  Average Overhead:        {avg_overhead:+.2f} ms ({avg_overhead_pct:+.1f}%)")
    print(f"  Average Slowdown Factor: {avg_slowdown:.2f}x")

    print(f"\n🔍 Key Insights:")
    print(f"  - Multi-engine access (Parquet/S3) is {avg_slowdown:.1f}x slower than native")
    print(f"  - Trade-off: Flexibility (multiple engines) vs Performance (native)")
    print(f"  - Parquet/S3 enables: ClickHouse, Trino, Spark, Presto, etc.")
    print(f"  - Native format optimal for: Single-engine, performance-critical workloads")

    # Save results
    output_file = f"results/parquet_overhead_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w') as f:
        json.dump({
            'metadata': {
                'timestamp': datetime.now().isoformat(),
                'iterations': ITERATIONS,
                'native_format': 'ClickHouse MergeTree',
                'shared_format': 'Parquet on S3 (MinIO)',
                'native_row_count': native_count,
                'parquet_row_count': parquet_count
            },
            'results': all_results,
            'summary': {
                'avg_native_ms': avg_native,
                'avg_parquet_ms': avg_parquet,
                'avg_overhead_ms': avg_overhead,
                'avg_overhead_pct': avg_overhead_pct,
                'avg_slowdown_factor': avg_slowdown
            }
        }, f, indent=2)

    print(f"\n\n✅ Results saved to: {output_file}")
    print(f"End Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print_header("Benchmark Complete")

if __name__ == '__main__':
    main()
