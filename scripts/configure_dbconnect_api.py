#!/usr/bin/env python3
"""
Configure Splunk DB Connect using REST API
"""

import requests
import urllib3
import json
import time

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SPLUNK_URL = "https://localhost:8089"
USERNAME = "admin"
PASSWORD = "ComplexP@ss123"

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
    create_identity(session_key, "postgres_identity", "postgres", "postgres123")

    # Create ClickHouse identity
    create_identity(session_key, "clickhouse_identity", "default", "")

    # Create PostgreSQL connection
    create_connection(
        session_key,
        "postgresql_conn",
        "postgres_identity",
        "postgres",
        "jdbc:postgresql://benchmark-postgresql:5432/cybersecurity"
    )

    # Create ClickHouse connection (using MySQL type since ClickHouse is MySQL-compatible)
    create_connection(
        session_key,
        "clickhouse_conn",
        "clickhouse_identity",
        "mysql",
        "jdbc:clickhouse://benchmark-clickhouse:8123/cybersecurity"
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
