#!/usr/bin/env python3
"""
Environment Validation Script
Purpose: Validate all database systems are healthy and ready
Platform: MacBook Pro M3
Version: 1.0.0
"""

import subprocess
import sys
import time
import json
from typing import Tuple, Dict
import psycopg2
import requests

# Colors for output
GREEN = '\033[0;32m'
RED = '\033[0;31m'
YELLOW = '\033[1;33m'
BLUE = '\033[0;34m'
NC = '\033[0m'  # No Color


def check_service(name: str, check_func, expected_value=None) -> Tuple[bool, str]:
    """Check if a service is healthy."""
    try:
        result = check_func()
        if expected_value and result != expected_value:
            return False, f"Unexpected value: {result}"
        return True, "Healthy"
    except Exception as e:
        return False, str(e)


def check_postgresql() -> bool:
    """Check PostgreSQL connectivity and schema."""
    conn = psycopg2.connect(
        host="localhost",
        port=5432,
        database="cybersecurity",
        user="postgres",
        password="postgres123"
    )
    cur = conn.cursor()
    cur.execute("SELECT 1")
    result = cur.fetchone()
    cur.close()
    conn.close()
    return result[0] == 1


def check_clickhouse() -> bool:
    """Check ClickHouse connectivity."""
    response = requests.get('http://localhost:8123/ping', timeout=5)
    return response.text.strip() == 'Ok.'


def check_starrocks_fe() -> bool:
    """Check StarRocks Frontend."""
    response = requests.get('http://localhost:8030/api/health', timeout=5)
    data = response.json()
    return data.get('status') == 'OK'


def check_splunk() -> bool:
    """Check Splunk Enterprise."""
    try:
        response = requests.get(
            'https://localhost:8089/services/server/info',
            auth=('admin', 'ComplexP@ss123'),
            verify=False,
            timeout=10
        )
        return response.status_code == 200
    except:
        return False


def get_postgresql_row_count() -> int:
    """Get PostgreSQL row count."""
    conn = psycopg2.connect(
        host="localhost",
        port=5432,
        database="cybersecurity",
        user="postgres",
        password="postgres123"
    )
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM security_logs")
    count = cur.fetchone()[0]
    cur.close()
    conn.close()
    return count


def get_clickhouse_row_count() -> int:
    """Get ClickHouse row count."""
    response = requests.get(
        'http://localhost:8123/',
        params={'query': 'SELECT COUNT() FROM cybersecurity.security_logs FORMAT JSON'},
        timeout=10
    )
    data = response.json()
    return data['data'][0]['count()'] if data.get('data') else 0


def get_starrocks_row_count() -> int:
    """Get StarRocks row count via MySQL protocol."""
    import pymysql
    try:
        conn = pymysql.connect(
            host='localhost',
            port=9030,
            user='root',
            database='cybersecurity'
        )
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM security_logs")
        count = cur.fetchone()[0]
        cur.close()
        conn.close()
        return count
    except:
        return 0


def main():
    """Main validation routine."""
    print("🔍 Environment Validation")
    print("━" * 40)

    all_healthy = True
    results = {}

    # Check PostgreSQL
    print(f"\n{BLUE}PostgreSQL{NC}")
    print("-" * 40)
    status, message = check_service("PostgreSQL", check_postgresql)
    icon = f"{GREEN}✓{NC}" if status else f"{RED}❌{NC}"
    print(f"{icon} Connection: {message}")
    results['postgresql'] = {'status': status, 'message': message}

    if status:
        try:
            row_count = get_postgresql_row_count()
            print(f"{GREEN}✓{NC} Row count: {row_count:,}")
            results['postgresql']['row_count'] = row_count
        except Exception as e:
            print(f"{RED}❌{NC} Row count check failed: {e}")
            all_healthy = False
    else:
        all_healthy = False

    # Check ClickHouse
    print(f"\n{BLUE}ClickHouse{NC}")
    print("-" * 40)
    status, message = check_service("ClickHouse", check_clickhouse)
    icon = f"{GREEN}✓{NC}" if status else f"{RED}❌{NC}"
    print(f"{icon} Connection: {message}")
    results['clickhouse'] = {'status': status, 'message': message}

    if status:
        try:
            row_count = get_clickhouse_row_count()
            print(f"{GREEN}✓{NC} Row count: {row_count:,}")
            results['clickhouse']['row_count'] = row_count
        except Exception as e:
            print(f"{RED}❌{NC} Row count check failed: {e}")
            all_healthy = False
    else:
        all_healthy = False

    # Check StarRocks FE
    print(f"\n{BLUE}StarRocks Frontend{NC}")
    print("-" * 40)
    status, message = check_service("StarRocks FE", check_starrocks_fe)
    icon = f"{GREEN}✓{NC}" if status else f"{RED}❌{NC}"
    print(f"{icon} Connection: {message}")
    results['starrocks_fe'] = {'status': status, 'message': message}

    if status:
        try:
            row_count = get_starrocks_row_count()
            print(f"{GREEN}✓{NC} Row count: {row_count:,}")
            results['starrocks_fe']['row_count'] = row_count
        except Exception as e:
            print(f"{YELLOW}⚠{NC}  Row count check failed: {e}")
    else:
        all_healthy = False

    # Check Splunk
    print(f"\n{BLUE}Splunk Enterprise{NC}")
    print("-" * 40)
    status, message = check_service("Splunk", check_splunk)
    icon = f"{GREEN}✓{NC}" if status else f"{RED}❌{NC}"
    print(f"{icon} Connection: {message}")
    results['splunk'] = {'status': status, 'message': message}

    if not status:
        all_healthy = False

    # Performance baseline tests
    print(f"\n{BLUE}Performance Baseline{NC}")
    print("-" * 40)

    # PostgreSQL simple query
    try:
        start = time.time()
        conn = psycopg2.connect(
            host="localhost", port=5432, database="cybersecurity",
            user="postgres", password="postgres123"
        )
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM security_logs WHERE event_type = 'login'")
        cur.fetchone()
        elapsed = (time.time() - start) * 1000
        cur.close()
        conn.close()

        icon = f"{GREEN}✓{NC}" if elapsed < 200 else f"{YELLOW}⚠{NC} "
        print(f"{icon} PostgreSQL simple query: {elapsed:.2f}ms")
        results['postgresql']['query_time_ms'] = elapsed
    except Exception as e:
        print(f"{RED}❌{NC} PostgreSQL query failed: {e}")
        all_healthy = False

    # ClickHouse simple query
    try:
        start = time.time()
        response = requests.get(
            'http://localhost:8123/',
            params={'query': "SELECT COUNT() FROM cybersecurity.security_logs WHERE event_type = 'login'"},
            timeout=10
        )
        elapsed = (time.time() - start) * 1000

        icon = f"{GREEN}✓{NC}" if elapsed < 100 else f"{YELLOW}⚠{NC} "
        print(f"{icon} ClickHouse simple query: {elapsed:.2f}ms")
        results['clickhouse']['query_time_ms'] = elapsed
    except Exception as e:
        print(f"{RED}❌{NC} ClickHouse query failed: {e}")
        all_healthy = False

    # Summary
    print("\n" + "━" * 40)
    if all_healthy:
        print(f"{GREEN}✅ All validation checks passed!{NC}")
        print("\nEnvironment is ready for benchmarking.")
        sys.exit(0)
    else:
        print(f"{RED}❌ Some validation checks failed.{NC}")
        print("\nPlease review and fix the issues above.")
        sys.exit(1)


if __name__ == "__main__":
    # Suppress SSL warnings for Splunk
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    main()
