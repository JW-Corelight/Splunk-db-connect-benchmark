#!/usr/bin/env python3
"""
Configure Splunk DB Connect using REST API
"""

import requests
import urllib3
import json
import time
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SPLUNK_URL = "https://localhost:8089"
USERNAME = os.getenv("SPLUNK_ADMIN_USERNAME", "admin")
PASSWORD = os.getenv("SPLUNK_ADMIN_PASSWORD")

if not PASSWORD:
    raise ValueError("SPLUNK_ADMIN_PASSWORD not set in .env file")

def get_session_key():
    """Get Splunk session key"""
    print("Getting session key...")
    response = requests.post(
        f"{SPLUNK_URL}/services/auth/login",
        data={"username": USERNAME, "password": PASSWORD},
        verify=False
    )

    if response.status_code == 200:
        # Parse XML response to get sessionKey
        import xml.etree.ElementTree as ET
        root = ET.fromstring(response.text)
        # Try without namespace first
        session_key = root.findtext(".//sessionKey")
        if not session_key:
            # Try with namespace
            session_key = root.findtext(".//{http://dev.splunk.com/ns/rest}key")

        if session_key:
            print(f"✅ Got session key: {session_key[:10]}...")
            return session_key
        else:
            print(f"❌ Could not find sessionKey in response")
            print(response.text)
            return None
    else:
        print(f"❌ Failed to get session key: {response.status_code}")
        print(response.text)
        return None


def create_identity(session_key, name, username, password=""):
    """Create a DB Connect identity"""
    print(f"\n=== Creating Identity: {name} ===")

    headers = {
        "Authorization": f"Splunk {session_key}",
        "X-DBX-SESSION-KEY": session_key,
        "Content-Type": "application/json"
    }

    data = {
        "name": name,
        "username": username,
        "password": password
    }

    response = requests.post(
        f"{SPLUNK_URL}/servicesNS/nobody/splunk_app_db_connect/db_connect/dbxproxy/identities",
        headers=headers,
        json=data,
        verify=False
    )

    if response.status_code in [200, 201]:
        print(f"✅ Identity '{name}' created successfully")
        return True
    else:
        print(f"⚠️  Status: {response.status_code}")
        print(f"Response: {response.text}")
        return False


def create_connection(session_key, name, identity, connection_type, jdbc_url):
    """Create a DB Connect connection"""
    print(f"\n=== Creating Connection: {name} ===")

    headers = {
        "Authorization": f"Splunk {session_key}",
        "X-DBX-SESSION-KEY": session_key,
        "Content-Type": "application/json"
    }

    data = {
        "name": name,
        "identity": identity,
        "connection_type": connection_type,
        "jdbcUrlFormat": jdbc_url,
        "readonly": True
    }

    response = requests.post(
        f"{SPLUNK_URL}/servicesNS/nobody/splunk_app_db_connect/db_connect/dbxproxy/connections",
        headers=headers,
        json=data,
        verify=False
    )

    if response.status_code in [200, 201]:
        print(f"✅ Connection '{name}' created successfully")
        return True
    else:
        print(f"⚠️  Status: {response.status_code}")
        print(f"Response: {response.text}")
        return False


def test_connection(session_key, connection_name):
    """Test a DB Connect connection"""
    print(f"\n=== Testing Connection: {connection_name} ===")

    headers = {
        "Authorization": f"Splunk {session_key}",
        "X-DBX-SESSION-KEY": session_key
    }

    response = requests.post(
        f"{SPLUNK_URL}/servicesNS/nobody/splunk_app_db_connect/db_connect/dbxproxy/connections/{connection_name}/test",
        headers=headers,
        verify=False
    )

    if response.status_code == 200:
        print(f"✅ Connection '{connection_name}' test successful")
        print(f"Response: {response.text}")
        return True
    else:
        print(f"⚠️  Status: {response.status_code}")
        print(f"Response: {response.text}")
        return False


def main():
    print("=== Splunk DB Connect Configuration via REST API ===\n")

    # Get session key
    session_key = get_session_key()
    if not session_key:
        print("❌ Cannot proceed without session key")
        return 1

    # Wait a moment for DB Connect Task Server
    print("\nWaiting 5 seconds for DB Connect Task Server...")
    time.sleep(5)

    # Create PostgreSQL identity
    postgres_user = os.getenv("POSTGRES_USER", "postgres")
    postgres_password = os.getenv("POSTGRES_PASSWORD", "")
    create_identity(session_key, "postgres_identity", postgres_user, postgres_password)

    # Create ClickHouse identity
    clickhouse_user = os.getenv("CLICKHOUSE_USER", "default")
    clickhouse_password = os.getenv("CLICKHOUSE_PASSWORD", "")
    create_identity(session_key, "clickhouse_identity", clickhouse_user, clickhouse_password)

    # Create PostgreSQL connection
    postgres_host = os.getenv("POSTGRES_HOST", "benchmark-postgresql")
    postgres_port = os.getenv("POSTGRES_PORT", "5432")
    postgres_db = os.getenv("POSTGRES_DB", "cybersecurity")
    postgres_jdbc = f"jdbc:postgresql://{postgres_host}:{postgres_port}/{postgres_db}"

    create_connection(
        session_key,
        "postgresql_conn",
        "postgres_identity",
        "postgres",
        postgres_jdbc
    )

    # Create ClickHouse connection (using MySQL type since ClickHouse is MySQL-compatible)
    clickhouse_host = os.getenv("CLICKHOUSE_HOST", "benchmark-clickhouse")
    clickhouse_port = os.getenv("CLICKHOUSE_PORT", "8123")
    clickhouse_db = os.getenv("CLICKHOUSE_DATABASE", "cybersecurity")
    clickhouse_jdbc = f"jdbc:clickhouse://{clickhouse_host}:{clickhouse_port}/{clickhouse_db}"

    create_connection(
        session_key,
        "clickhouse_conn",
        "clickhouse_identity",
        "mysql",
        clickhouse_jdbc
    )

    # Test connections
    print("\n" + "="*50)
    print("Testing Connections")
    print("="*50)

    test_connection(session_key, "postgresql_conn")
    test_connection(session_key, "clickhouse_conn")

    print("\n=== Configuration Complete ===")
    print("\nYou can now test with:")
    print("  cd benchmarks")
    print("  python3 02_splunk_dbxquery_overhead.py")

    return 0


if __name__ == "__main__":
    exit(main())
