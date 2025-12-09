-- Apache Iceberg Schema Definition
-- Purpose: Create Iceberg tables for multi-engine query testing
-- Engines: Trino, ClickHouse, StarRocks
-- Storage: MinIO (S3-compatible object storage)
-- Catalog: Hive Metastore

-- ================================================
-- Create Iceberg Database/Schema
-- ================================================

CREATE SCHEMA IF NOT EXISTS iceberg.cybersecurity
WITH (location = 's3://warehouse/cybersecurity');

-- Set the default schema for subsequent commands
USE iceberg.cybersecurity;

-- ================================================
-- Security Logs Table (Main Event Table)
-- ================================================

CREATE TABLE IF NOT EXISTS security_logs (
    -- Timestamp and Event Identification
    timestamp TIMESTAMP(6) WITH TIME ZONE NOT NULL,
    event_id BIGINT NOT NULL,

    -- User Information
    user_id VARCHAR(100),
    user_type VARCHAR(50),

    -- Host and Network Information
    host VARCHAR(255),
    source_ip VARCHAR(45),  -- Supports IPv4 and IPv6
    dest_ip VARCHAR(45),
    port INTEGER,

    -- Event Classification
    event_type VARCHAR(100) NOT NULL,
    status VARCHAR(50),

    -- Data Transfer Metrics
    bytes_in BIGINT,
    bytes_out BIGINT,

    -- Flexible Event Data (JSON)
    event_data VARCHAR  -- Stored as JSON string
)
WITH (
    -- Table Format and Storage
    format = 'PARQUET',
    partitioning = ARRAY['day(timestamp)'],  -- Partition by day for efficient querying
    sorted_by = ARRAY['timestamp', 'event_id'],

    -- Compression
    compression_codec = 'ZSTD',

    -- Performance Optimizations
    format_version = 2,  -- Iceberg v2 format with row-level updates

    -- File Size Management
    target_file_size_bytes = 134217728  -- 128 MB target file size
);

-- Add table comment
COMMENT ON TABLE security_logs IS 'Cybersecurity event logs stored in Apache Iceberg format';

-- Add column comments
COMMENT ON COLUMN security_logs.timestamp IS 'Event occurrence timestamp with timezone';
COMMENT ON COLUMN security_logs.event_id IS 'Unique event identifier';
COMMENT ON COLUMN security_logs.user_id IS 'User identifier (employee ID, username, etc.)';
COMMENT ON COLUMN security_logs.event_type IS 'Type of security event (login, file_access, network_connection, etc.)';
COMMENT ON COLUMN security_logs.status IS 'Event status (success, failed, blocked, etc.)';

-- ================================================
-- Network Logs Table
-- ================================================

CREATE TABLE IF NOT EXISTS network_logs (
    -- Timestamp and Connection ID
    timestamp TIMESTAMP(6) WITH TIME ZONE NOT NULL,
    connection_id BIGINT NOT NULL,

    -- Network Endpoints
    src_ip VARCHAR(45) NOT NULL,
    dest_ip VARCHAR(45) NOT NULL,
    src_port INTEGER,
    dest_port INTEGER,

    -- Connection Metadata
    direction VARCHAR(20),  -- inbound, outbound, lateral
    protocol VARCHAR(20),   -- TCP, UDP, ICMP, etc.

    -- Traffic Metrics
    bytes_in BIGINT,
    bytes_out BIGINT,
    bytes_total BIGINT,
    packets_in INTEGER,
    packets_out INTEGER,

    -- Connection State
    connection_state VARCHAR(50)  -- established, closed, timeout, etc.
)
WITH (
    format = 'PARQUET',
    partitioning = ARRAY['day(timestamp)'],
    sorted_by = ARRAY['timestamp', 'connection_id'],
    compression_codec = 'ZSTD',
    format_version = 2,
    target_file_size_bytes = 134217728
);

COMMENT ON TABLE network_logs IS 'Network connection logs stored in Apache Iceberg format';

-- ================================================
-- User Activity Summary Table (Aggregated)
-- ================================================

CREATE TABLE IF NOT EXISTS user_activity_summary (
    -- User and Time Period
    user_id VARCHAR(100) NOT NULL,
    day DATE NOT NULL,

    -- Event Counts
    total_events INTEGER,
    failed_logins INTEGER,
    successful_logins INTEGER,

    -- Data Transfer Metrics
    data_transferred BIGINT,

    -- Unique Entities
    unique_hosts INTEGER,
    unique_ips INTEGER,

    -- Risk Metrics
    high_risk_events INTEGER,
    blocked_events INTEGER
)
WITH (
    format = 'PARQUET',
    partitioning = ARRAY['month(day)'],
    sorted_by = ARRAY['day', 'user_id'],
    compression_codec = 'ZSTD',
    format_version = 2
);

COMMENT ON TABLE user_activity_summary IS 'Pre-aggregated user activity metrics by day';

-- ================================================
-- Threat Intelligence Table
-- ================================================

CREATE TABLE IF NOT EXISTS threat_indicators (
    -- Indicator Information
    indicator_id BIGINT NOT NULL,
    indicator_type VARCHAR(50) NOT NULL,  -- ip, domain, hash, url
    indicator_value VARCHAR(500) NOT NULL,

    -- Threat Classification
    threat_type VARCHAR(100),  -- malware, phishing, c2, etc.
    severity VARCHAR(20),      -- critical, high, medium, low
    confidence INTEGER,        -- 0-100

    -- Temporal Information
    first_seen TIMESTAMP(6) WITH TIME ZONE,
    last_seen TIMESTAMP(6) WITH TIME ZONE,

    -- Source and Context
    source VARCHAR(100),       -- threat feed provider
    description VARCHAR,
    tags ARRAY(VARCHAR)        -- Array of tags
)
WITH (
    format = 'PARQUET',
    partitioning = ARRAY['indicator_type'],
    sorted_by = ARRAY['indicator_value'],
    compression_codec = 'ZSTD',
    format_version = 2
);

COMMENT ON TABLE threat_indicators IS 'Threat intelligence indicators of compromise (IOCs)';

-- ================================================
-- Iceberg Table Maintenance Queries
-- ================================================

-- Note: These are examples for reference, not executed automatically

-- Optimize table (compact small files)
-- ALTER TABLE security_logs EXECUTE optimize;

-- Expire old snapshots (cleanup history older than 7 days)
-- ALTER TABLE security_logs EXECUTE expire_snapshots(retention_threshold => '7d');

-- Remove orphan files (cleanup unused data files)
-- ALTER TABLE security_logs EXECUTE remove_orphan_files(older_than => '7d');

-- Rewrite data files to optimize layout
-- ALTER TABLE security_logs EXECUTE rewrite_data_files;

-- Show table history (snapshots)
-- SELECT * FROM "security_logs$snapshots" ORDER BY committed_at DESC;

-- Show table files
-- SELECT * FROM "security_logs$files";

-- Show table partitions
-- SELECT * FROM "security_logs$partitions";

-- ================================================
-- Time Travel Query Examples
-- ================================================

-- Query data as of specific timestamp
-- SELECT * FROM security_logs FOR TIMESTAMP AS OF TIMESTAMP '2024-12-08 10:00:00 UTC';

-- Query data as of specific snapshot ID
-- SELECT * FROM security_logs FOR VERSION AS OF 1234567890;

-- ================================================
-- Schema Evolution Examples
-- ================================================

-- Add new column
-- ALTER TABLE security_logs ADD COLUMN risk_score INTEGER;

-- Rename column
-- ALTER TABLE security_logs RENAME COLUMN event_data TO metadata;

-- Drop column
-- ALTER TABLE security_logs DROP COLUMN risk_score;

-- Change column type (limited support)
-- ALTER TABLE security_logs ALTER COLUMN port TYPE BIGINT;

-- ================================================
-- Partition Evolution Examples
-- ================================================

-- Change partitioning from day to hour
-- ALTER TABLE security_logs SET PROPERTIES partitioning = ARRAY['hour(timestamp)'];

-- Remove partitioning
-- ALTER TABLE security_logs SET PROPERTIES partitioning = ARRAY[];

-- ================================================
-- Notes on Multi-Engine Access
-- ================================================

-- These Iceberg tables can be queried by:
-- 1. Trino (full read/write support)
-- 2. ClickHouse (read-only via Iceberg table engine)
-- 3. StarRocks (read/write via Iceberg external catalog)
-- 4. Spark (full read/write support)
-- 5. Flink (full read/write support)

-- All engines see the same data with ACID guarantees
-- Schema evolution and time travel work across all engines
-- Metadata is synchronized via Hive Metastore
