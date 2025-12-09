#!/usr/bin/env python3
"""
Setup Apache Iceberg tables via ClickHouse native engine
Simplified approach: Skip Hive Metastore/Trino, use ClickHouse IcebergS3 directly
"""

import clickhouse_connect
import time

# Configuration
CLICKHOUSE_CONFIG = {
    'host': 'localhost',
    'port': 8123,
    'database': 'cybersecurity',
    'username': 'default',
    'password': ''
}

MINIO_CONFIG = {
    'endpoint': 'http://benchmark-minio:9000',
    'access_key': 'admin',
    'secret_key': 'password123',
    'bucket': 'warehouse',
    'region': 'us-east-1'
}

def print_header(text):
    print(f"\n{'='*80}")
    print(f"{text:^80}")
    print(f"{'='*80}\n")

def main():
    print_header("Apache Iceberg Setup via ClickHouse")

    # Connect to ClickHouse
    print("Connecting to ClickHouse...")
    client = clickhouse_connect.get_client(**CLICKHOUSE_CONFIG)
    print("✅ Connected")

    # Check current data
    print("\n📊 Checking existing data...")
    result = client.query("SELECT COUNT(*) as count FROM security_logs")
    row_count = result.result_rows[0][0]
    print(f"✅ Found {row_count:,} records in security_logs table")

    # Create Iceberg table using CREATE TABLE AS SELECT
    # Note: ClickHouse Iceberg engine writes to S3-compatible storage
    print("\n🔨 Creating Iceberg table...")

    # First, we need to use the S3 table function to write Iceberg format
    # ClickHouse doesn't directly support CREATE TABLE with Iceberg engine for writing
    # Instead, we'll use the s3 table function with Parquet format

    print("\n⚠️  Note: ClickHouse's Iceberg engine is read-only.")
    print("Alternative approach: Use S3/Parquet format for multi-engine access.")
    print("\nCreating Parquet table in MinIO for multi-engine access...")

    # Create table using S3 with Parquet format
    # This can be read by multiple engines (ClickHouse, Trino, etc.)
    # Use specific filename (not glob) for writing
    s3_path_write = f"http://benchmark-minio:9000/warehouse/security_logs/data.parquet"
    s3_path_read = f"http://benchmark-minio:9000/warehouse/security_logs/*.parquet"

    # Export data to S3/MinIO in Parquet format
    export_query = f"""
    INSERT INTO FUNCTION s3(
        '{s3_path_write}',
        '{MINIO_CONFIG['access_key']}',
        '{MINIO_CONFIG['secret_key']}',
        'Parquet'
    )
    SELECT *
    FROM security_logs
    LIMIT 10000
    """

    print(f"Exporting 10,000 records to MinIO (Parquet format)...")
    start_time = time.time()

    try:
        client.command(export_query)
        export_time = time.time() - start_time
        print(f"✅ Export completed in {export_time:.2f} seconds")
    except Exception as e:
        print(f"❌ Export failed: {e}")
        print("\nThis may be due to S3 endpoint configuration.")
        print("Skipping Iceberg setup for now.")
        return 1

    # Create external table to read the Parquet data
    print("\n🔨 Creating external S3/Parquet table...")

    create_external_table = f"""
    CREATE OR REPLACE TABLE security_logs_parquet ENGINE = S3(
        '{s3_path_read}',
        '{MINIO_CONFIG['access_key']}',
        '{MINIO_CONFIG['secret_key']}',
        'Parquet'
    )
    """

    try:
        client.command(create_external_table)
        print("✅ External table created")
    except Exception as e:
        print(f"❌ Failed to create external table: {e}")
        return 1

    # Verify we can read the data
    print("\n🔍 Verifying Parquet data...")
    verify_query = "SELECT COUNT(*) as count FROM security_logs_parquet"
    result = client.query(verify_query)
    parquet_count = result.result_rows[0][0]
    print(f"✅ Verified: {parquet_count:,} records readable from Parquet")

    # Run a sample query
    print("\n🔍 Testing query performance...")
    test_query = """
    SELECT event_type, COUNT(*) as count
    FROM security_logs_parquet
    GROUP BY event_type
    ORDER BY count DESC
    LIMIT 5
    """

    start_time = time.time()
    result = client.query(test_query)
    query_time = time.time() - start_time

    print(f"✅ Query completed in {query_time*1000:.2f}ms")
    print("\nTop event types:")
    for row in result.result_rows:
        print(f"  {row[0]}: {row[1]:,} events")

    print_header("Setup Complete")
    print("✅ Parquet data exported to MinIO")
    print("✅ External table created for multi-engine access")
    print("\n📝 Note: This Parquet format can be read by:")
    print("  - ClickHouse (via S3 engine)")
    print("  - Trino (via S3 connector)")
    print("  - Spark (via S3 connector)")
    print("  - Any tool that supports Parquet + S3")

    return 0

if __name__ == '__main__':
    exit(main())
