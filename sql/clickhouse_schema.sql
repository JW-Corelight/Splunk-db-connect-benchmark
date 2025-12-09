-- ClickHouse Schema for Cybersecurity Logs
-- Optimized for ARM64 with columnar storage and NEON SIMD
-- Version: 1.0.0
-- Last Updated: December 7, 2024

CREATE DATABASE IF NOT EXISTS cybersecurity;
USE cybersecurity;

-- ===========================================
-- Main Security Events Table
-- ===========================================
CREATE TABLE IF NOT EXISTS security_logs (
    timestamp DateTime,
    event_id UInt64,
    user_id String,
    user_type LowCardinality(String),
    host LowCardinality(String),
    source_ip IPv4,
    dest_ip IPv4,
    port UInt16,
    event_type LowCardinality(String),
    status LowCardinality(String),
    bytes_in UInt64,
    bytes_out UInt64,
    event_data String,
    created_at DateTime DEFAULT now()
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (timestamp, user_id, event_type)
SETTINGS
    index_granularity = 8192,
    enable_mixed_granularity_parts = 1,
    compress_marks = 1,
    compress_primary_key = 1,
    min_bytes_for_wide_part = 0,
    min_rows_for_wide_part = 0;

-- Secondary data skipping indices
ALTER TABLE security_logs
ADD INDEX idx_source_ip source_ip TYPE minmax GRANULARITY 4;

ALTER TABLE security_logs
ADD INDEX idx_user_id user_id TYPE bloom_filter(0.01) GRANULARITY 4;

ALTER TABLE security_logs
ADD INDEX idx_event_type event_type TYPE set(100) GRANULARITY 4;

-- ===========================================
-- Network Connection Logs Table
-- ===========================================
CREATE TABLE IF NOT EXISTS network_logs (
    timestamp DateTime,
    connection_id UInt64,
    src_ip IPv4,
    dest_ip IPv4,
    src_port UInt16,
    dest_port UInt16,
    direction LowCardinality(String),
    protocol LowCardinality(String),
    bytes_in UInt64,
    bytes_out UInt64,
    bytes_total UInt64,
    packets_in UInt32,
    packets_out UInt32,
    connection_state LowCardinality(String),
    duration_ms UInt32,
    created_at DateTime DEFAULT now()
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (timestamp, src_ip, dest_ip, dest_port)
SETTINGS
    index_granularity = 8192,
    compress_marks = 1;

-- Data skipping indices for network_logs
ALTER TABLE network_logs
ADD INDEX idx_dest_port dest_port TYPE minmax GRANULARITY 4;

ALTER TABLE network_logs
ADD INDEX idx_protocol protocol TYPE set(10) GRANULARITY 4;

-- ===========================================
-- Materialized View: User Activity Summary
-- ===========================================
CREATE TABLE IF NOT EXISTS user_activity_summary_target (
    user_id String,
    day Date,
    total_events UInt64,
    failed_logins UInt64,
    successful_logins UInt64,
    data_transferred UInt64,
    unique_hosts UInt64,
    unique_ips UInt64
) ENGINE = SummingMergeTree()
PARTITION BY toYYYYMM(day)
ORDER BY (user_id, day)
SETTINGS index_granularity = 8192;

CREATE MATERIALIZED VIEW IF NOT EXISTS user_activity_summary
TO user_activity_summary_target
AS SELECT
    user_id,
    toDate(timestamp) AS day,
    count() AS total_events,
    countIf(event_type = 'login' AND status = 'failed') AS failed_logins,
    countIf(event_type = 'login' AND status = 'success') AS successful_logins,
    sum(bytes_in + bytes_out) AS data_transferred,
    uniq(host) AS unique_hosts,
    uniq(source_ip) AS unique_ips
FROM security_logs
GROUP BY user_id, day;

-- ===========================================
-- Materialized View: Hourly Event Statistics
-- ===========================================
CREATE TABLE IF NOT EXISTS hourly_events_target (
    hour DateTime,
    event_type String,
    event_count UInt64,
    unique_users UInt64,
    unique_ips UInt64,
    total_bytes UInt64
) ENGINE = SummingMergeTree()
PARTITION BY toYYYYMM(hour)
ORDER BY (hour, event_type)
SETTINGS index_granularity = 8192;

CREATE MATERIALIZED VIEW IF NOT EXISTS hourly_events
TO hourly_events_target
AS SELECT
    toStartOfHour(timestamp) AS hour,
    event_type,
    count() AS event_count,
    uniq(user_id) AS unique_users,
    uniq(source_ip) AS unique_ips,
    sum(bytes_in + bytes_out) AS total_bytes
FROM security_logs
GROUP BY hour, event_type;

-- ===========================================
-- Materialized View: Failed Login Tracking
-- ===========================================
CREATE TABLE IF NOT EXISTS failed_logins_target (
    user_id String,
    source_ip IPv4,
    failed_attempts UInt64,
    first_failure DateTime,
    last_failure DateTime
) ENGINE = AggregatingMergeTree()
PARTITION BY toYYYYMM(last_failure)
ORDER BY (user_id, source_ip)
SETTINGS index_granularity = 8192;

CREATE MATERIALIZED VIEW IF NOT EXISTS failed_logins_mv
TO failed_logins_target
AS SELECT
    user_id,
    source_ip,
    count() AS failed_attempts,
    min(timestamp) AS first_failure,
    max(timestamp) AS last_failure
FROM security_logs
WHERE event_type = 'login' AND status = 'failed'
GROUP BY user_id, source_ip;

-- ===========================================
-- Threat Intelligence Table
-- ===========================================
CREATE TABLE IF NOT EXISTS threat_intel (
    indicator_type LowCardinality(String),
    indicator_value String,
    threat_level LowCardinality(String),
    threat_category LowCardinality(String),
    first_seen DateTime,
    last_seen DateTime,
    source LowCardinality(String),
    metadata String,
    created_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(last_seen)
PARTITION BY toYYYYMM(last_seen)
ORDER BY (indicator_type, indicator_value)
SETTINGS index_granularity = 8192;

-- ===========================================
-- Aggregation Functions / Views
-- ===========================================

-- Top N suspicious users (can be used as subquery)
CREATE VIEW IF NOT EXISTS v_suspicious_users AS
SELECT
    user_id,
    countIf(status = 'failed') AS failed_count,
    uniq(source_ip) AS unique_ips,
    sum(bytes_out) AS total_data_out,
    (failed_count * 10 +
     if(unique_ips > 3, (unique_ips - 3) * 5, 0) +
     countIf(toHour(timestamp) NOT BETWEEN 8 AND 18) * 3) AS risk_score
FROM security_logs
WHERE timestamp > now() - INTERVAL 24 HOUR
GROUP BY user_id
HAVING failed_count > 0 OR unique_ips > 3
ORDER BY risk_score DESC;

-- Network traffic summary
CREATE VIEW IF NOT EXISTS v_network_traffic_summary AS
SELECT
    dest_port,
    protocol,
    direction,
    count() AS connection_count,
    uniq(src_ip) AS unique_sources,
    uniq(dest_ip) AS unique_destinations,
    sum(bytes_total) AS total_bytes,
    avg(duration_ms) AS avg_duration_ms
FROM network_logs
WHERE timestamp > now() - INTERVAL 1 HOUR
GROUP BY dest_port, protocol, direction
ORDER BY connection_count DESC;

-- Anomaly detection: port scanning
CREATE VIEW IF NOT EXISTS v_port_scan_detection AS
SELECT
    src_ip,
    count(DISTINCT dest_port) AS unique_ports_accessed,
    count() AS connection_attempts,
    uniq(dest_ip) AS unique_destinations,
    min(timestamp) AS first_seen,
    max(timestamp) AS last_seen,
    dateDiff('second', min(timestamp), max(timestamp)) AS time_window_seconds
FROM network_logs
WHERE timestamp > now() - INTERVAL 5 MINUTE
GROUP BY src_ip
HAVING unique_ports_accessed > 20 AND time_window_seconds < 60
ORDER BY unique_ports_accessed DESC;

-- ===========================================
-- Optimization Commands
-- ===========================================

-- Optimize tables (merge parts)
OPTIMIZE TABLE security_logs FINAL;
OPTIMIZE TABLE network_logs FINAL;
OPTIMIZE TABLE user_activity_summary_target FINAL;
OPTIMIZE TABLE hourly_events_target FINAL;
OPTIMIZE TABLE failed_logins_target FINAL;

-- ===========================================
-- System Settings for Optimal Performance
-- ===========================================

-- Query-level settings (can be SET per session)
-- Example:
-- SET max_threads = 6;
-- SET max_memory_usage = 4000000000;
-- SET enable_optimize_predicate_expression = 1;

-- ===========================================
-- Validation Queries
-- ===========================================

-- Check table sizes
SELECT
    database,
    table,
    formatReadableSize(sum(bytes)) AS size,
    sum(rows) AS rows,
    max(modification_time) AS latest_modification
FROM system.parts
WHERE database = 'cybersecurity' AND active
GROUP BY database, table
ORDER BY sum(bytes) DESC;

-- Check partitions
SELECT
    table,
    partition,
    sum(rows) AS rows,
    formatReadableSize(sum(bytes_on_disk)) AS size_on_disk,
    count() AS parts
FROM system.parts
WHERE database = 'cybersecurity' AND active
GROUP BY table, partition
ORDER BY table, partition;

-- Display materialized views
SELECT
    database,
    name,
    engine,
    create_table_query
FROM system.tables
WHERE database = 'cybersecurity' AND engine LIKE '%View%';

SELECT '=== ClickHouse Schema Creation Complete ===' AS status;
