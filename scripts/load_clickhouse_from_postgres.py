#!/usr/bin/env python3
"""
Load ClickHouse from PostgreSQL
Quick script to copy data from PostgreSQL to ClickHouse using native clients
"""

import psycopg2
import clickhouse_connect

# Configuration
POSTGRES_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'cybersecurity',
    'user': 'postgres',
    'password': 'postgres123'
}

CLICKHOUSE_CONFIG = {
    'host': 'localhost',
    'port': 8123,
    'database': 'cybersecurity',
    'user': 'default',
    'password': ''
}

BATCH_SIZE = 10000

def load_security_logs():
    """Load security logs from PostgreSQL to ClickHouse"""
    print("Connecting to PostgreSQL...")
    pg_conn = psycopg2.connect(**POSTGRES_CONFIG)
    pg_cursor = pg_conn.cursor()

    print("Connecting to ClickHouse...")
    ch_client = clickhouse_connect.get_client(
        host=CLICKHOUSE_CONFIG['host'],
        port=CLICKHOUSE_CONFIG['port'],
        database=CLICKHOUSE_CONFIG['database'],
        username=CLICKHOUSE_CONFIG['user'],
        password=CLICKHOUSE_CONFIG['password']
    )

    # Get total count
    pg_cursor.execute("SELECT COUNT(*) FROM security_logs")
    total = pg_cursor.fetchone()[0]
    print(f"Total records in PostgreSQL: {total:,}")

    # Load in batches
    offset = 0
    loaded = 0

    while offset < total:
        print(f"Loading batch {offset//BATCH_SIZE + 1} (records {offset:,} to {min(offset+BATCH_SIZE, total):,})...")

        # Fetch batch from PostgreSQL
        query = f"""
            SELECT
                timestamp,
                COALESCE(event_id, id) as event_id,
                user_id,
                COALESCE(user_type, 'standard') as user_type,
                host,
                host(source_ip) as source_ip,
                host(dest_ip) as dest_ip,
                COALESCE(port, 0) as port,
                event_type,
                status,
                bytes_in,
                bytes_out,
                '{{}}'::text as event_data
            FROM security_logs
            ORDER BY id
            LIMIT {BATCH_SIZE} OFFSET {offset}
        """

        pg_cursor.execute(query)
        rows = pg_cursor.fetchall()

        if not rows:
            break

        # Insert into ClickHouse
        ch_client.insert(
            'cybersecurity.security_logs',
            rows,
            column_names=['timestamp', 'event_id', 'user_id', 'user_type', 'host',
                         'source_ip', 'dest_ip', 'port', 'event_type', 'status',
                         'bytes_in', 'bytes_out', 'event_data']
        )

        loaded += len(rows)
        offset += BATCH_SIZE

        if loaded % 50000 == 0:
            print(f"  Progress: {loaded:,}/{total:,} records ({loaded*100//total}%)")

    print(f"\n✓ Loaded {loaded:,} records into ClickHouse")

    # Verify
    result = ch_client.query("SELECT COUNT(*) FROM cybersecurity.security_logs")
    ch_count = result.result_rows[0][0]
    print(f"✓ Verification: ClickHouse now has {ch_count:,} records")

    pg_cursor.close()
    pg_conn.close()

def main():
    print("="*70)
    print("Load ClickHouse from PostgreSQL")
    print("="*70)

    try:
        load_security_logs()
        print("\n" + "="*70)
        print("Data loading complete!")
        print("="*70)
    except Exception as e:
        print(f"\n✗ Error: {e}")
        raise

if __name__ == "__main__":
    main()
