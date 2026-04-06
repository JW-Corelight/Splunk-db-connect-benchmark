#!/usr/bin/env python3
"""
Benchmark Script: Iceberg Catalog Comparison
Purpose: Compare Hive Metastore vs Apache Polaris REST catalog performance
Engine: Trino (querying Iceberg tables via both catalogs)
Metrics: Catalog metadata operations, query planning time, partition pruning
"""

import time
import json
import statistics
import os
import argparse
import platform
from typing import Dict, List, Optional, Tuple
from datetime import datetime

# Trino connection via requests (HTTP protocol)
import requests

# === Configuration ===
TRINO_CONFIG = {
    'host': 'localhost',
    'port': 8080,
    'user': 'benchmark'
}

ITERATIONS = 5

# Catalog names as configured in Trino
HIVE_CATALOG = 'iceberg'            # configs/trino/catalog/iceberg.properties
POLARIS_CATALOG = 'iceberg_polaris'  # configs/trino/catalog/iceberg_polaris.properties
SCHEMA = 'cybersecurity'

# === Trino HTTP Client ===
class TrinoClient:
    """Simple Trino HTTP client for benchmarking."""

    def __init__(self, host: str, port: int, user: str, catalog: str, schema: str):
        self.base_url = f"http://{host}:{port}"
        self.user = user
        self.catalog = catalog
        self.schema = schema

    def execute(self, sql: str) -> Tuple[List, float, Optional[Dict]]:
        """
        Execute SQL via Trino HTTP protocol.
        Returns (rows, latency_ms, query_stats).
        """
        headers = {
            'X-Trino-User': self.user,
            'X-Trino-Catalog': self.catalog,
            'X-Trino-Schema': self.schema,
            'Content-Type': 'text/plain'
        }

        start = time.perf_counter()

        resp = requests.post(
            f"{self.base_url}/v1/statement",
            data=sql,
            headers=headers
        )
        resp.raise_for_status()
        result = resp.json()

        # Poll for results
        rows = []
        stats = None
        while True:
            if 'data' in result:
                rows.extend(result['data'])

            if 'stats' in result:
                stats = result['stats']

            next_uri = result.get('nextUri')
            if not next_uri:
                break

            resp = requests.get(next_uri, headers=headers)
            resp.raise_for_status()
            result = resp.json()

        latency_ms = (time.perf_counter() - start) * 1000
        return rows, latency_ms, stats

    def is_available(self) -> bool:
        """Check if Trino and this catalog are accessible."""
        try:
            rows, _, _ = self.execute("SELECT 1")
            return True
        except Exception:
            return False


# === Benchmark Queries ===
# Metadata operations (catalog-level)
METADATA_QUERIES = {
    'list_schemas': {
        'name': 'List Schemas',
        'sql': 'SHOW SCHEMAS'
    },
    'list_tables': {
        'name': 'List Tables',
        'sql': f'SHOW TABLES FROM {SCHEMA}'
    },
    'describe_table': {
        'name': 'Describe Table',
        'sql': f'DESCRIBE {SCHEMA}.security_logs'
    },
    'table_properties': {
        'name': 'Table Properties',
        'sql': f"SHOW CREATE TABLE {SCHEMA}.security_logs"
    }
}

# Data queries (partition pruning, predicate pushdown)
DATA_QUERIES = {
    'count_all': {
        'name': 'Count All Records',
        'sql': f'SELECT COUNT(*) FROM {SCHEMA}.security_logs'
    },
    'aggregation': {
        'name': 'Aggregate by Event Type',
        'sql': f'''
            SELECT event_type, COUNT(*) as cnt, SUM(bytes_in) as total_in
            FROM {SCHEMA}.security_logs
            GROUP BY event_type ORDER BY cnt DESC LIMIT 10
        '''
    },
    'partition_prune': {
        'name': 'Partition Pruning (Time Filter)',
        'sql': f'''
            SELECT COUNT(*), SUM(bytes_in)
            FROM {SCHEMA}.security_logs
            WHERE timestamp >= CURRENT_TIMESTAMP - INTERVAL '7' DAY
        '''
    },
    'filter_predicate': {
        'name': 'Predicate Pushdown (Event Type)',
        'sql': f'''
            SELECT user_id, COUNT(*) as events
            FROM {SCHEMA}.security_logs
            WHERE event_type = 'ssh_login'
            GROUP BY user_id ORDER BY events DESC LIMIT 20
        '''
    }
}


# === Utility Functions ===
def print_header(text: str) -> None:
    print(f"\n{'='*80}")
    print(f"{text:^80}")
    print(f"{'='*80}\n")

def run_query_set(client: TrinoClient, queries: Dict, label: str) -> Dict:
    """Run a set of queries and collect timing results."""
    results = {}
    for qid, qinfo in queries.items():
        latencies = []
        row_count = 0
        error = None

        for _ in range(ITERATIONS):
            try:
                rows, latency, stats = client.execute(qinfo['sql'])
                latencies.append(latency)
                row_count = len(rows)
            except Exception as e:
                error = str(e)
                break

        if latencies:
            results[qid] = {
                'avg_latency_ms': round(statistics.mean(latencies), 2),
                'min_latency_ms': round(min(latencies), 2),
                'max_latency_ms': round(max(latencies), 2),
                'row_count': row_count
            }
            print(f"  [{label}] {qinfo['name']}: {results[qid]['avg_latency_ms']:.2f} ms avg")
        else:
            results[qid] = {'error': error}
            print(f"  [{label}] {qinfo['name']}: FAILED ({error})")

    return results


# === Main ===
def main():
    parser = argparse.ArgumentParser(description='Iceberg Catalog Comparison Benchmark')
    parser.add_argument('--skip-polaris', action='store_true',
                        help='Skip Polaris catalog tests')
    parser.add_argument('--skip-hive', action='store_true',
                        help='Skip Hive Metastore catalog tests')
    args = parser.parse_args()

    print_header("Iceberg Catalog Comparison Benchmark")
    print(f"Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Platform: {platform.machine()}")
    print(f"Iterations per Query: {ITERATIONS}")
    print(f"Catalogs: Hive Metastore{' (skipped)' if args.skip_hive else ''}, "
          f"Apache Polaris{' (skipped)' if args.skip_polaris else ''}")

    all_results = {
        'metadata': {
            'timestamp': datetime.now().isoformat(),
            'platform': platform.machine(),
            'iterations': ITERATIONS
        }
    }

    # Check Trino availability
    print("\nChecking Trino connectivity...")
    try:
        resp = requests.get(f"http://{TRINO_CONFIG['host']}:{TRINO_CONFIG['port']}/v1/info")
        resp.raise_for_status()
        trino_info = resp.json()
        print(f"  Trino version: {trino_info.get('nodeVersion', 'unknown')}")
        print(f"  Starting: {trino_info.get('starting', 'unknown')}")
    except Exception as e:
        print(f"  Trino is not available: {e}")
        print("  Start Trino: docker-compose -f docker-compose.m3.yml up -d trino")
        return

    catalogs_tested = []

    # === Hive Metastore Catalog ===
    if not args.skip_hive:
        print_header("Hive Metastore Catalog")
        hive_client = TrinoClient(
            TRINO_CONFIG['host'], TRINO_CONFIG['port'],
            TRINO_CONFIG['user'], HIVE_CATALOG, SCHEMA
        )

        if hive_client.is_available():
            print("Metadata operations:")
            hive_meta = run_query_set(hive_client, METADATA_QUERIES, 'Hive')

            print("\nData queries:")
            hive_data = run_query_set(hive_client, DATA_QUERIES, 'Hive')

            all_results['hive_metastore'] = {
                'catalog': HIVE_CATALOG,
                'metadata_queries': hive_meta,
                'data_queries': hive_data
            }
            catalogs_tested.append('hive_metastore')
        else:
            print("Hive Metastore catalog not available (iceberg tables may not exist)")

    # === Polaris REST Catalog ===
    if not args.skip_polaris:
        print_header("Apache Polaris REST Catalog")
        polaris_client = TrinoClient(
            TRINO_CONFIG['host'], TRINO_CONFIG['port'],
            TRINO_CONFIG['user'], POLARIS_CATALOG, SCHEMA
        )

        if polaris_client.is_available():
            print("Metadata operations:")
            polaris_meta = run_query_set(polaris_client, METADATA_QUERIES, 'Polaris')

            print("\nData queries:")
            polaris_data = run_query_set(polaris_client, DATA_QUERIES, 'Polaris')

            all_results['polaris'] = {
                'catalog': POLARIS_CATALOG,
                'metadata_queries': polaris_meta,
                'data_queries': polaris_data
            }
            catalogs_tested.append('polaris')
        else:
            print("Polaris catalog not available")
            print("  1. Start Polaris: docker-compose -f docker-compose.m3.yml up -d polaris")
            print("  2. Setup catalog: ./scripts/setup_polaris.sh")
            print("  3. Create tables via Trino using 'iceberg_polaris' catalog")

    # === Comparison Summary ===
    if len(catalogs_tested) == 2:
        print_header("Catalog Comparison Summary")

        print(f"{'Query':<35} {'Hive MS':>10} {'Polaris':>10} {'Delta':>10}")
        print("-" * 67)

        for query_type in ['metadata_queries', 'data_queries']:
            for qid in (METADATA_QUERIES if query_type == 'metadata_queries' else DATA_QUERIES):
                qname = (METADATA_QUERIES if query_type == 'metadata_queries' else DATA_QUERIES)[qid]['name']
                hive_ms = all_results.get('hive_metastore', {}).get(query_type, {}).get(qid, {}).get('avg_latency_ms')
                pol_ms = all_results.get('polaris', {}).get(query_type, {}).get(qid, {}).get('avg_latency_ms')

                if hive_ms is not None and pol_ms is not None:
                    delta = pol_ms - hive_ms
                    print(f"{qname:<35} {hive_ms:>8.1f}ms {pol_ms:>8.1f}ms {delta:>+8.1f}ms")
                else:
                    h = f"{hive_ms:.1f}ms" if hive_ms else "N/A"
                    p = f"{pol_ms:.1f}ms" if pol_ms else "N/A"
                    print(f"{qname:<35} {h:>10} {p:>10} {'--':>10}")

    elif len(catalogs_tested) == 1:
        print_header(f"Results ({catalogs_tested[0]} only)")
        cat = catalogs_tested[0]
        for query_type in ['metadata_queries', 'data_queries']:
            queries = METADATA_QUERIES if query_type == 'metadata_queries' else DATA_QUERIES
            print(f"\n{query_type.replace('_', ' ').title()}:")
            for qid, qinfo in queries.items():
                r = all_results.get(cat, {}).get(query_type, {}).get(qid, {})
                avg = r.get('avg_latency_ms', 'N/A')
                if isinstance(avg, (int, float)):
                    print(f"  {qinfo['name']}: {avg:.2f} ms")
                else:
                    print(f"  {qinfo['name']}: {avg}")

    print("\n" + "="*80)
    print("Key Insights:")
    print("- Hive Metastore: Thrift-based, requires PostgreSQL backend, Rosetta 2 on M3")
    print("- Apache Polaris: REST-based, ARM64 native, built-in metadata caching")
    print("- Metadata operations (SHOW/DESCRIBE): Polaris REST should be faster (no Thrift)")
    print("- Data queries: Similar performance (both resolve to same Iceberg files on MinIO)")
    print("- Polaris supports catalog-level access control (future: multi-tenant scenarios)")
    print("="*80 + "\n")

    # Save results
    output_file = f"results/catalog_benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    output_path = os.path.join(os.path.dirname(__file__), output_file)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, 'w') as f:
        json.dump(all_results, f, indent=2)

    print(f"Results saved to: {output_file}")
    print(f"End Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print_header("Benchmark Complete")

if __name__ == '__main__':
    main()
