#!/usr/bin/env python3
"""
Load Zeek Sample Data into Benchmark Databases
Purpose: Transform existing Zeek conn.log data for PostgreSQL and ClickHouse
Source: /Users/jeremy.wiley/Git projects/iceberg-ocsf-poc/data/raw-zeek/conn-sample.json
"""

import json
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
ZEEK_DATA_PATH = '/Users/jeremy.wiley/Git projects/iceberg-ocsf-poc/data/raw-zeek/conn-sample.json'
BATCH_SIZE = 1000

def load_zeek_json() -> List[dict]:
    """Load Zeek JSON data (NDJSON format)"""
    print(f"Loading Zeek data from {ZEEK_DATA_PATH}...")
    records = []
    with open(ZEEK_DATA_PATH, 'r') as f:
        for line in f:
            try:
                records.append(json.loads(line.strip()))
            except json.JSONDecodeError as e:
                print(f"Warning: Skipping malformed JSON line: {e}")
                continue
    print(f"✓ Loaded {len(records):,} Zeek records")
    return records

def transform_zeek_to_network_logs(zeek_records: List[dict]) -> List[Tuple]:
    """Transform Zeek conn.log to network_logs schema"""
    print("Transforming Zeek data to network_logs schema...")
    network_logs = []

    for record in zeek_records:
        try:
            # Parse timestamp
            timestamp = datetime.fromisoformat(record['ts'].replace('Z', '+00:00'))

            # Extract fields with defaults
            src_ip = record['id.orig_h']
            dest_ip = record['id.resp_h']
            src_port = record.get('id.orig_p', 0)
            dest_port = record.get('id.resp_p', 0)
            protocol = record.get('proto', 'unknown').upper()

            # Determine direction based on RFC1918 private IPs
            is_src_private = src_ip.startswith(('10.', '192.168.', '172.16.', '172.17.', '172.18.', '172.19.', '172.2', '172.30.', '172.31.'))
            is_dest_private = dest_ip.startswith(('10.', '192.168.', '172.16.', '172.17.', '172.18.', '172.19.', '172.2', '172.30.', '172.31.'))

            if is_src_private and not is_dest_private:
                direction = 'outbound'
            elif not is_src_private and is_dest_private:
                direction = 'inbound'
            elif is_src_private and is_dest_private:
                direction = 'internal'
            else:
                direction = 'external'

            # Calculate total bytes
            orig_bytes = record.get('orig_bytes', 0) or 0
            resp_bytes = record.get('resp_bytes', 0) or 0
            bytes_total = orig_bytes + resp_bytes

            # Duration in milliseconds
            duration_ms = int((record.get('duration', 0) or 0) * 1000)

            network_logs.append((
                timestamp,
                src_ip,
                dest_ip,
                src_port,
                dest_port,
                protocol,
                direction,
                bytes_total,
                duration_ms
            ))

        except (KeyError, ValueError, TypeError) as e:
            print(f"Warning: Skipping record due to error: {e}")
            continue

    print(f"✓ Transformed {len(network_logs):,} network log records")
    return network_logs

def generate_security_logs(num_records: int = 100000) -> List[Tuple]:
    """Generate security logs based on Zeek data patterns"""
    print(f"Generating {num_records:,} security log records...")

    EVENT_TYPES = ['ssh_login', 'web_request', 'file_access', 'api_call', 'database_query', 'admin_action']
    STATUSES = ['success', 'failed', 'blocked', 'timeout']
    USERS = [f'user_{i:05d}' for i in range(1, 501)]
    HOSTS = [f'host-{i:03d}.internal' for i in range(1, 101)]

    def random_ip():
        return f"{random.randint(10, 192)}.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(1, 254)}"

    security_logs = []
    for _ in range(num_records):
        timestamp = datetime.now() - timedelta(
            days=random.randint(0, 90),
            hours=random.randint(0, 23),
            minutes=random.randint(0, 59),
            seconds=random.randint(0, 59)
        )

        event_type = random.choice(EVENT_TYPES)

        # Make failed logins more likely for SSH
        if event_type == 'ssh_login':
            status = random.choices(STATUSES, weights=[60, 30, 8, 2])[0]
        else:
            status = random.choices(STATUSES, weights=[80, 10, 5, 5])[0]

        security_logs.append((
            timestamp,
            event_type,
            status,
            random.choice(USERS),
            random_ip(),
            random_ip(),
            random.choice(HOSTS),
            random.randint(100, 50000),
            random.randint(100, 50000)
        ))

    print(f"✓ Generated {len(security_logs):,} security log records")
    return security_logs

def load_postgresql_network_logs(records: List[Tuple]):
    """Load network logs into PostgreSQL"""
    print("Loading network logs into PostgreSQL...")
    conn = psycopg2.connect(**POSTGRES_CONFIG)
    cursor = conn.cursor()

    # Convert bytes_total to bytes_in and bytes_out (split evenly for simplicity)
    converted_records = []
    for record in records:
        timestamp, src_ip, dest_ip, src_port, dest_port, protocol, direction, bytes_total, duration_ms = record
        bytes_in = bytes_total // 2
        bytes_out = bytes_total - bytes_in
        converted_records.append((timestamp, src_ip, dest_ip, src_port, dest_port, protocol, direction, bytes_in, bytes_out, duration_ms))

    insert_query = """
    INSERT INTO network_logs (timestamp, src_ip, dest_ip, src_port, dest_port, protocol, direction, bytes_in, bytes_out, duration_ms)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    for i in range(0, len(converted_records), BATCH_SIZE):
        batch = converted_records[i:i+BATCH_SIZE]
        cursor.executemany(insert_query, batch)
        conn.commit()

    cursor.close()
    conn.close()
    print(f"✓ PostgreSQL network_logs: {len(records):,} records loaded")

def load_postgresql_security_logs(records: List[Tuple]):
    """Load security logs into PostgreSQL"""
    print("Loading security logs into PostgreSQL...")
    conn = psycopg2.connect(**POSTGRES_CONFIG)
    cursor = conn.cursor()

    insert_query = """
    INSERT INTO security_logs (timestamp, event_type, status, user_id, source_ip, dest_ip, host, bytes_in, bytes_out)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    for i in range(0, len(records), BATCH_SIZE):
        batch = records[i:i+BATCH_SIZE]
        cursor.executemany(insert_query, batch)
        conn.commit()
        if (i + BATCH_SIZE) % 10000 == 0:
            print(f"  PostgreSQL security_logs: {i + BATCH_SIZE:,}/{len(records):,} records loaded")

    cursor.close()
    conn.close()
    print(f"✓ PostgreSQL security_logs: {len(records):,} records loaded")

def load_clickhouse_network_logs(records: List[Tuple]):
    """Load network logs into ClickHouse"""
    print("Loading network logs into ClickHouse...")

    # Use VALUES format which is simpler
    for i in range(0, len(records), BATCH_SIZE):
        batch = records[i:i+BATCH_SIZE]

        # Build VALUES format
        value_strings = []
        for record in batch:
            timestamp, src_ip, dest_ip, src_port, dest_port, protocol, direction, bytes_total, duration_ms = record

            # VALUES format with proper quoting
            value_str = f"('{timestamp.strftime('%Y-%m-%d %H:%M:%S')}', '{src_ip}', '{dest_ip}', {src_port}, {dest_port}, '{protocol}', '{direction}', {bytes_total}, {duration_ms})"
            value_strings.append(value_str)

        values_clause = ",\n".join(value_strings)

        query = f"""
        INSERT INTO cybersecurity.network_logs
        (timestamp, src_ip, dest_ip, src_port, dest_port, protocol, direction, bytes_total, duration_ms)
        VALUES {values_clause}
        """

        response = requests.post(
            CLICKHOUSE_URL,
            params={'query': query}
        )

        if response.status_code != 200:
            print(f"Error loading ClickHouse batch {i}: {response.text}")
            return

    print(f"✓ ClickHouse network_logs: {len(records):,} records loaded")

def load_clickhouse_security_logs(records: List[Tuple]):
    """Load security logs into ClickHouse"""
    print("Loading security logs into ClickHouse...")

    # ClickHouse schema: timestamp, event_id, user_id, user_type, host, source_ip, dest_ip, port, event_type, status, bytes_in, bytes_out, event_data
    for i in range(0, len(records), BATCH_SIZE):
        batch = records[i:i+BATCH_SIZE]

        # Build VALUES format matching ClickHouse schema
        value_strings = []
        for idx, record in enumerate(batch):
            timestamp, event_type, status, user_id, source_ip, dest_ip, host, bytes_in, bytes_out = record

            # VALUES format: timestamp, event_id, user_id, user_type, host, source_ip, dest_ip, port, event_type, status, bytes_in, bytes_out, event_data
            event_id = i + idx + 1
            user_type = "standard"  # Default user type
            port = 0  # Default port
            event_data = "{}"  # Empty JSON

            value_str = f"('{timestamp.strftime('%Y-%m-%d %H:%M:%S')}', {event_id}, '{user_id}', '{user_type}', '{host}', '{source_ip}', '{dest_ip}', {port}, '{event_type}', '{status}', {bytes_in}, {bytes_out}, '{event_data}')"
            value_strings.append(value_str)

        values_clause = ",\n".join(value_strings)

        query = f"""
        INSERT INTO cybersecurity.security_logs
        (timestamp, event_id, user_id, user_type, host, source_ip, dest_ip, port, event_type, status, bytes_in, bytes_out, event_data)
        VALUES {values_clause}
        """

        response = requests.post(
            CLICKHOUSE_URL,
            params={'query': query}
        )

        if response.status_code != 200:
            print(f"Error loading ClickHouse batch {i}: {response.text}")
            return

        if (i + BATCH_SIZE) % 10000 == 0:
            print(f"  ClickHouse security_logs: {i + BATCH_SIZE:,}/{len(records):,} records loaded")

    print(f"✓ ClickHouse security_logs: {len(records):,} records loaded")

def main():
    print("=" * 70)
    print("Loading Sample Data from Zeek Dataset")
    print("=" * 70)

    # Load and transform Zeek data
    zeek_records = load_zeek_json()
    network_logs = transform_zeek_to_network_logs(zeek_records)

    print(f"\n{'='*70}")
    print("Loading Network Logs (from Zeek data)")
    print(f"{'='*70}")

    try:
        load_postgresql_network_logs(network_logs)
    except Exception as e:
        print(f"✗ PostgreSQL network logs error: {e}")

    try:
        load_clickhouse_network_logs(network_logs)
    except Exception as e:
        print(f"✗ ClickHouse network logs error: {e}")

    # Generate security logs
    print(f"\n{'='*70}")
    print("Generating and Loading Security Logs")
    print(f"{'='*70}")

    security_logs = generate_security_logs(100000)

    try:
        load_postgresql_security_logs(security_logs)
    except Exception as e:
        print(f"✗ PostgreSQL security logs error: {e}")

    try:
        load_clickhouse_security_logs(security_logs)
    except Exception as e:
        print(f"✗ ClickHouse security logs error: {e}")

    # Verify counts
    print(f"\n{'='*70}")
    print("Data Loading Complete - Verification")
    print(f"{'='*70}")

    try:
        conn = psycopg2.connect(**POSTGRES_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM security_logs")
        pg_security = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM network_logs")
        pg_network = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        print(f"\nPostgreSQL:")
        print(f"  security_logs: {pg_security:,}")
        print(f"  network_logs: {pg_network:,}")
    except Exception as e:
        print(f"PostgreSQL verification error: {e}")

    try:
        response = requests.get(f"{CLICKHOUSE_URL}/?query=SELECT COUNT(*) FROM cybersecurity.security_logs")
        ch_security = int(response.text.strip())
        response = requests.get(f"{CLICKHOUSE_URL}/?query=SELECT COUNT(*) FROM cybersecurity.network_logs")
        ch_network = int(response.text.strip())
        print(f"\nClickHouse:")
        print(f"  security_logs: {ch_security:,}")
        print(f"  network_logs: {ch_network:,}")
    except Exception as e:
        print(f"ClickHouse verification error: {e}")

    print(f"\n{'='*70}")
    print("Ready for benchmark testing!")
    print(f"{'='*70}\n")

if __name__ == "__main__":
    main()
