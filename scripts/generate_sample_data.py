#!/usr/bin/env python3
"""
Generate Sample Cybersecurity Data
Purpose: Create 100K realistic cybersecurity events for benchmarking
Targets: PostgreSQL and ClickHouse
"""

import random
import psycopg2
import requests
from datetime import datetime, timedelta
from typing import List, Tuple

# Configuration
POSTGRES_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'cybersecurity',
    'user': 'postgres',
    'password': 'postgres123'
}

CLICKHOUSE_URL = 'http://localhost:8123'
NUM_RECORDS = 100000
BATCH_SIZE = 1000

# Sample data pools
EVENT_TYPES = ['ssh_login', 'web_request', 'file_access', 'api_call', 'database_query']
STATUSES = ['success', 'failed', 'blocked', 'timeout']
USERS = [f'user_{i:05d}' for i in range(1, 501)]  # 500 users
HOSTS = [f'host-{i:03d}.internal' for i in range(1, 101)]  # 100 hosts

def random_ip() -> str:
    """Generate random IPv4 address"""
    return f"{random.randint(10, 192)}.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(1, 254)}"

def generate_security_log() -> Tuple:
    """Generate single security log entry"""
    timestamp = datetime.now() - timedelta(
        days=random.randint(0, 90),
        hours=random.randint(0, 23),
        minutes=random.randint(0, 59),
        seconds=random.randint(0, 59)
    )

    event_type = random.choice(EVENT_TYPES)
    status = random.choice(STATUSES)
    user_id = random.choice(USERS)
    source_ip = random_ip()
    dest_ip = random_ip()
    host = random.choice(HOSTS)
    bytes_in = random.randint(100, 50000)
    bytes_out = random.randint(100, 50000)

    return (timestamp, event_type, status, user_id, source_ip, dest_ip, host, bytes_in, bytes_out)

def load_postgresql(records: List[Tuple]):
    """Load data into PostgreSQL"""
    print("Loading data into PostgreSQL...")
    conn = psycopg2.connect(**POSTGRES_CONFIG)
    cursor = conn.cursor()

    # Insert in batches
    insert_query = """
    INSERT INTO security_logs (timestamp, event_type, status, user_id, source_ip, dest_ip, host, bytes_in, bytes_out)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    for i in range(0, len(records), BATCH_SIZE):
        batch = records[i:i+BATCH_SIZE]
        cursor.executemany(insert_query, batch)
        conn.commit()
        if (i + BATCH_SIZE) % 10000 == 0:
            print(f"  PostgreSQL: {i + BATCH_SIZE}/{len(records)} records loaded")

    cursor.close()
    conn.close()
    print(f"✓ PostgreSQL: {len(records)} records loaded")

def load_clickhouse(records: List[Tuple]):
    """Load data into ClickHouse"""
    print("Loading data into ClickHouse...")

    # Prepare CSV data
    csv_data = []
    for record in records:
        timestamp, event_type, status, user_id, source_ip, dest_ip, host, bytes_in, bytes_out = record
        csv_line = f"{timestamp.strftime('%Y-%m-%d %H:%M:%S')},{event_type},{status},{user_id},{source_ip},{dest_ip},{host},{bytes_in},{bytes_out}"
        csv_data.append(csv_line)

    csv_content = "\n".join(csv_data)

    # Insert in batches
    for i in range(0, len(csv_data), BATCH_SIZE):
        batch_csv = "\n".join(csv_data[i:i+BATCH_SIZE])

        query = """
        INSERT INTO cybersecurity.security_logs
        (timestamp, event_type, status, user_id, source_ip, dest_ip, host, bytes_in, bytes_out)
        FORMAT CSV
        """

        response = requests.post(
            CLICKHOUSE_URL,
            params={'query': query},
            data=batch_csv.encode('utf-8')
        )

        if response.status_code != 200:
            print(f"Error loading ClickHouse batch {i}: {response.text}")
            return

        if (i + BATCH_SIZE) % 10000 == 0:
            print(f"  ClickHouse: {i + BATCH_SIZE}/{len(records)} records loaded")

    print(f"✓ ClickHouse: {len(records)} records loaded")

def generate_network_logs(num_records: int = 50000) -> List[Tuple]:
    """Generate network traffic logs"""
    print(f"Generating {num_records} network logs...")
    logs = []

    protocols = ['TCP', 'UDP', 'ICMP']
    directions = ['inbound', 'outbound', 'internal']
    ports = [22, 80, 443, 3306, 5432, 8080, 8443, 9000, 9090]

    for _ in range(num_records):
        timestamp = datetime.now() - timedelta(
            days=random.randint(0, 90),
            hours=random.randint(0, 23),
            minutes=random.randint(0, 59)
        )

        logs.append((
            timestamp,
            random_ip(),  # src_ip
            random_ip(),  # dest_ip
            random.randint(1024, 65535),  # src_port
            random.choice(ports),  # dest_port
            random.choice(protocols),
            random.choice(directions),
            random.randint(0, 100000),  # bytes_total
            random.randint(10, 5000)  # duration_ms
        ))

    return logs

def load_network_logs_postgresql(records: List[Tuple]):
    """Load network logs into PostgreSQL"""
    print("Loading network logs into PostgreSQL...")
    conn = psycopg2.connect(**POSTGRES_CONFIG)
    cursor = conn.cursor()

    insert_query = """
    INSERT INTO network_logs (timestamp, src_ip, dest_ip, src_port, dest_port, protocol, direction, bytes_total, duration_ms)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    for i in range(0, len(records), BATCH_SIZE):
        batch = records[i:i+BATCH_SIZE]
        cursor.executemany(insert_query, batch)
        conn.commit()

    cursor.close()
    conn.close()
    print(f"✓ PostgreSQL network_logs: {len(records)} records loaded")

def load_network_logs_clickhouse(records: List[Tuple]):
    """Load network logs into ClickHouse"""
    print("Loading network logs into ClickHouse...")

    csv_data = []
    for record in records:
        timestamp, src_ip, dest_ip, src_port, dest_port, protocol, direction, bytes_total, duration_ms = record
        csv_line = f"{timestamp.strftime('%Y-%m-%d %H:%M:%S')},{src_ip},{dest_ip},{src_port},{dest_port},{protocol},{direction},{bytes_total},{duration_ms}"
        csv_data.append(csv_line)

    for i in range(0, len(csv_data), BATCH_SIZE):
        batch_csv = "\n".join(csv_data[i:i+BATCH_SIZE])

        query = """
        INSERT INTO cybersecurity.network_logs
        (timestamp, src_ip, dest_ip, src_port, dest_port, protocol, direction, bytes_total, duration_ms)
        FORMAT CSV
        """

        response = requests.post(
            CLICKHOUSE_URL,
            params={'query': query},
            data=batch_csv.encode('utf-8')
        )

        if response.status_code != 200:
            print(f"Error loading ClickHouse network logs: {response.text}")
            return

    print(f"✓ ClickHouse network_logs: {len(records)} records loaded")

def main():
    print("=" * 60)
    print("Generating Sample Cybersecurity Data")
    print("=" * 60)

    # Generate security logs
    print(f"\n1. Generating {NUM_RECORDS} security logs...")
    security_logs = [generate_security_log() for _ in range(NUM_RECORDS)]
    print(f"✓ Generated {len(security_logs)} security logs")

    # Load into databases
    print("\n2. Loading security logs into databases...")
    try:
        load_postgresql(security_logs)
    except Exception as e:
        print(f"✗ PostgreSQL error: {e}")

    try:
        load_clickhouse(security_logs)
    except Exception as e:
        print(f"✗ ClickHouse error: {e}")

    # Generate and load network logs
    print("\n3. Generating network traffic logs...")
    network_logs = generate_network_logs(50000)
    print(f"✓ Generated {len(network_logs)} network logs")

    print("\n4. Loading network logs into databases...")
    try:
        load_network_logs_postgresql(network_logs)
    except Exception as e:
        print(f"✗ PostgreSQL network logs error: {e}")

    try:
        load_network_logs_clickhouse(network_logs)
    except Exception as e:
        print(f"✗ ClickHouse network logs error: {e}")

    # Verify counts
    print("\n" + "=" * 60)
    print("Data Loading Complete")
    print("=" * 60)
    print("\nVerifying record counts...")

    try:
        conn = psycopg2.connect(**POSTGRES_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM security_logs")
        pg_security = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM network_logs")
        pg_network = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        print(f"PostgreSQL:")
        print(f"  security_logs: {pg_security:,}")
        print(f"  network_logs: {pg_network:,}")
    except Exception as e:
        print(f"PostgreSQL verification error: {e}")

    try:
        response = requests.get(f"{CLICKHOUSE_URL}/?query=SELECT COUNT(*) FROM cybersecurity.security_logs")
        ch_security = int(response.text.strip())
        response = requests.get(f"{CLICKHOUSE_URL}/?query=SELECT COUNT(*) FROM cybersecurity.network_logs")
        ch_network = int(response.text.strip())
        print(f"ClickHouse:")
        print(f"  security_logs: {ch_security:,}")
        print(f"  network_logs: {ch_network:,}")
    except Exception as e:
        print(f"ClickHouse verification error: {e}")

if __name__ == "__main__":
    main()
