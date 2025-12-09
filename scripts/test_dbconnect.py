#!/usr/bin/env python3
"""
Test Splunk DB Connect connections
"""

import requests
import urllib3
import time
import json

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SPLUNK_URL = "https://localhost:8089"
USERNAME = "admin"
PASSWORD = "ComplexP@ss123"


def run_search(search_query):
    """Run a Splunk search and wait for results"""
    print(f"\nRunning search: {search_query}")

    # Create search job
    response = requests.post(
        f"{SPLUNK_URL}/services/search/jobs",
        auth=(USERNAME, PASSWORD),
        data={"search": search_query, "output_mode": "json"},
        verify=False
    )

    if response.status_code != 201:
        print(f"❌ Failed to create search job: {response.status_code}")
        print(response.text)
        return None

    job_data = response.json()
    sid = job_data.get("sid")
    print(f"✅ Search job created: {sid}")

    # Wait for job to complete
    print("Waiting for search to complete...")
    for i in range(30):
        status_response = requests.get(
            f"{SPLUNK_URL}/services/search/jobs/{sid}",
            auth=(USERNAME, PASSWORD),
            params={"output_mode": "json"},
            verify=False
        )

        if status_response.status_code == 200:
            status_data = status_response.json()
            dispatch_state = status_data.get("entry", [{}])[0].get("content", {}).get("dispatchState")

            if dispatch_state == "DONE":
                print(f"✅ Search completed!")
                break
            elif dispatch_state == "FAILED":
                print(f"❌ Search failed!")
                return None

        time.sleep(2)
    else:
        print(f"⚠️  Search timed out")
        return None

    # Get results
    results_response = requests.get(
        f"{SPLUNK_URL}/services/search/jobs/{sid}/results",
        auth=(USERNAME, PASSWORD),
        params={"output_mode": "json"},
        verify=False
    )

    if results_response.status_code == 200:
        results = results_response.json()
        return results
    else:
        print(f"❌ Failed to get results: {results_response.status_code}")
        return None


def main():
    print("=== Testing Splunk DB Connect Connections ===\n")

    # Test PostgreSQL
    print("\n" + "="*60)
    print("TEST 1: PostgreSQL Connection")
    print("="*60)

    results = run_search('| dbxquery connection="postgresql_conn" query="SELECT COUNT(*) as count FROM security_logs"')
    if results:
        print(f"\n✅ PostgreSQL Results:")
        print(json.dumps(results, indent=2))

    # Test ClickHouse
    print("\n" + "="*60)
    print("TEST 2: ClickHouse Connection")
    print("="*60)

    results = run_search('| dbxquery connection="clickhouse_conn" query="SELECT COUNT(*) as count FROM security_logs"')
    if results:
        print(f"\n✅ ClickHouse Results:")
        print(json.dumps(results, indent=2))

    print("\n=== Tests Complete ===")
    print("\nIf tests passed, you can now run:")
    print("  cd benchmarks")
    print("  python3 02_splunk_dbxquery_overhead.py")


if __name__ == "__main__":
    main()
