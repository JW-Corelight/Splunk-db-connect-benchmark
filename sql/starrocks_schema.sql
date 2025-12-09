-- StarRocks Schema for Cybersecurity Logs
-- MPP architecture with duplicate key model
-- Version: 1.0.0
-- Last Updated: December 7, 2024

CREATE DATABASE IF NOT EXISTS cybersecurity;
USE cybersecurity;

-- ===========================================
-- Main Security Events Table
-- ===========================================
CREATE TABLE IF NOT EXISTS security_logs (
    timestamp DATETIME NOT NULL COMMENT 'Event timestamp',
    event_id BIGINT COMMENT 'Unique event identifier',
    user_id VARCHAR(100) COMMENT 'User identifier',
    user_type VARCHAR(50) COMMENT 'Type of user (admin, standard, service)',
    host VARCHAR(255) COMMENT 'Hostname',
    source_ip VARCHAR(45) COMMENT 'Source IP address (IPv4/IPv6)',
    dest_ip VARCHAR(45) COMMENT 'Destination IP address',
    port INT COMMENT 'Network port',
    event_type VARCHAR(100) COMMENT 'Type of security event',
    status VARCHAR(50) COMMENT 'Event status (success, failed, blocked)',
    bytes_in BIGINT COMMENT 'Bytes received',
    bytes_out BIGINT COMMENT 'Bytes sent',
    event_data JSON COMMENT 'Additional event metadata',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP() COMMENT 'Record creation time'
) ENGINE=OLAP
DUPLICATE KEY(timestamp, event_id)
COMMENT 'Security event logs'
PARTITION BY RANGE(timestamp) (
    PARTITION p202410 VALUES LESS THAN ('2024-11-01'),
    PARTITION p202411 VALUES LESS THAN ('2024-12-01'),
    PARTITION p202412 VALUES LESS THAN ('2025-01-01'),
    PARTITION p202501 VALUES LESS THAN ('2025-02-01'),
    PARTITION p202502 VALUES LESS THAN ('2025-03-01')
)
DISTRIBUTED BY HASH(event_id) BUCKETS 16
PROPERTIES (
    "replication_num" = "1",
    "storage_format" = "V2",
    "compression" = "LZ4",
    "enable_persistent_index" = "true"
);

-- Bitmap index for low-cardinality columns (StarRocks-specific optimization)
CREATE INDEX idx_event_type ON security_logs (event_type) USING BITMAP COMMENT 'Bitmap index on event_type';
CREATE INDEX idx_status ON security_logs (status) USING BITMAP COMMENT 'Bitmap index on status';
CREATE INDEX idx_user_type ON security_logs (user_type) USING BITMAP COMMENT 'Bitmap index on user_type';

-- ===========================================
-- Network Connection Logs Table
-- ===========================================
CREATE TABLE IF NOT EXISTS network_logs (
    timestamp DATETIME NOT NULL COMMENT 'Connection timestamp',
    connection_id BIGINT COMMENT 'Unique connection identifier',
    src_ip VARCHAR(45) NOT NULL COMMENT 'Source IP address',
    dest_ip VARCHAR(45) NOT NULL COMMENT 'Destination IP address',
    src_port INT COMMENT 'Source port',
    dest_port INT COMMENT 'Destination port',
    direction VARCHAR(20) COMMENT 'Traffic direction (inbound, outbound, internal)',
    protocol VARCHAR(20) COMMENT 'Network protocol (TCP, UDP, ICMP)',
    bytes_in BIGINT DEFAULT 0 COMMENT 'Bytes received',
    bytes_out BIGINT DEFAULT 0 COMMENT 'Bytes sent',
    bytes_total BIGINT AS (bytes_in + bytes_out) COMMENT 'Total bytes transferred',
    packets_in INT DEFAULT 0 COMMENT 'Packets received',
    packets_out INT DEFAULT 0 COMMENT 'Packets sent',
    connection_state VARCHAR(50) COMMENT 'Connection state',
    duration_ms INT COMMENT 'Connection duration in milliseconds',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP() COMMENT 'Record creation time'
) ENGINE=OLAP
DUPLICATE KEY(timestamp, connection_id)
COMMENT 'Network connection logs'
PARTITION BY RANGE(timestamp) (
    PARTITION p202410 VALUES LESS THAN ('2024-11-01'),
    PARTITION p202411 VALUES LESS THAN ('2024-12-01'),
    PARTITION p202412 VALUES LESS THAN ('2025-01-01'),
    PARTITION p202501 VALUES LESS THAN ('2025-02-01')
)
DISTRIBUTED BY HASH(connection_id) BUCKETS 16
PROPERTIES (
    "replication_num" = "1",
    "storage_format" = "V2",
    "compression" = "LZ4"
);

-- Bitmap indexes
CREATE INDEX idx_protocol ON network_logs (protocol) USING BITMAP;
CREATE INDEX idx_direction ON network_logs (direction) USING BITMAP;
CREATE INDEX idx_connection_state ON network_logs (connection_state) USING BITMAP;

-- ===========================================
-- User Activity Aggregate Table
-- ===========================================
CREATE TABLE IF NOT EXISTS user_activity_agg (
    user_id VARCHAR(100) NOT NULL COMMENT 'User identifier',
    day DATE NOT NULL COMMENT 'Activity date',
    total_events BIGINT SUM DEFAULT "0" COMMENT 'Total events for user',
    failed_logins BIGINT SUM DEFAULT "0" COMMENT 'Failed login attempts',
    successful_logins BIGINT SUM DEFAULT "0" COMMENT 'Successful logins',
    data_transferred BIGINT SUM DEFAULT "0" COMMENT 'Total data transferred',
    unique_hosts BIGINT MAX DEFAULT "0" COMMENT 'Unique hosts accessed',
    unique_ips BIGINT MAX DEFAULT "0" COMMENT 'Unique IP addresses',
    last_activity DATETIME REPLACE DEFAULT CURRENT_TIMESTAMP() COMMENT 'Last activity timestamp'
) ENGINE=OLAP
AGGREGATE KEY(user_id, day)
COMMENT 'Daily user activity aggregates'
PARTITION BY RANGE(day) (
    PARTITION p202410 VALUES LESS THAN ('2024-11-01'),
    PARTITION p202411 VALUES LESS THAN ('2024-12-01'),
    PARTITION p202412 VALUES LESS THAN ('2025-01-01'),
    PARTITION p202501 VALUES LESS THAN ('2025-02-01')
)
DISTRIBUTED BY HASH(user_id) BUCKETS 8
PROPERTIES (
    "replication_num" = "1",
    "storage_format" = "V2"
);

-- ===========================================
-- Hourly Event Statistics Aggregate Table
-- ===========================================
CREATE TABLE IF NOT EXISTS hourly_events_agg (
    hour DATETIME NOT NULL COMMENT 'Hour bucket',
    event_type VARCHAR(100) NOT NULL COMMENT 'Event type',
    event_count BIGINT SUM DEFAULT "0" COMMENT 'Count of events',
    unique_users BIGINT HLL_UNION COMMENT 'Approximate unique users',
    unique_ips BIGINT HLL_UNION COMMENT 'Approximate unique IPs',
    total_bytes BIGINT SUM DEFAULT "0" COMMENT 'Total bytes transferred'
) ENGINE=OLAP
AGGREGATE KEY(hour, event_type)
COMMENT 'Hourly event statistics'
PARTITION BY RANGE(hour) (
    PARTITION p202410 VALUES LESS THAN ('2024-11-01'),
    PARTITION p202411 VALUES LESS THAN ('2024-12-01'),
    PARTITION p202412 VALUES LESS THAN ('2025-01-01')
)
DISTRIBUTED BY HASH(hour) BUCKETS 16
PROPERTIES (
    "replication_num" = "1"
);

-- ===========================================
-- Threat Intelligence Table
-- ===========================================
CREATE TABLE IF NOT EXISTS threat_intel (
    indicator_type VARCHAR(50) NOT NULL COMMENT 'Type of indicator (ip, domain, hash)',
    indicator_value VARCHAR(500) NOT NULL COMMENT 'Indicator value',
    threat_level VARCHAR(20) COMMENT 'Threat severity level',
    threat_category VARCHAR(100) COMMENT 'Threat classification',
    first_seen DATETIME DEFAULT CURRENT_TIMESTAMP() COMMENT 'First observation',
    last_seen DATETIME DEFAULT CURRENT_TIMESTAMP() COMMENT 'Last observation',
    source VARCHAR(100) COMMENT 'Intelligence source',
    metadata JSON COMMENT 'Additional threat information',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP()
) ENGINE=OLAP
PRIMARY KEY(indicator_type, indicator_value)
COMMENT 'Threat intelligence indicators'
DISTRIBUTED BY HASH(indicator_type, indicator_value) BUCKETS 8
PROPERTIES (
    "replication_num" = "1",
    "storage_format" = "V2"
);

-- ===========================================
-- Materialized View: Failed Login Summary
-- ===========================================
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_failed_logins
DISTRIBUTED BY HASH(user_id) BUCKETS 8
REFRESH ASYNC
AS SELECT
    user_id,
    source_ip,
    COUNT(*) AS failed_attempts,
    MIN(timestamp) AS first_failure,
    MAX(timestamp) AS last_failure,
    date_trunc('day', MAX(timestamp)) AS failure_date
FROM security_logs
WHERE event_type = 'login' AND status = 'failed'
GROUP BY user_id, source_ip;

-- ===========================================
-- Views for Common Query Patterns
-- ===========================================

-- Suspicious user activity
CREATE VIEW IF NOT EXISTS v_suspicious_users AS
SELECT
    user_id,
    COUNT(IF(status = 'failed', 1, NULL)) AS failed_count,
    COUNT(DISTINCT source_ip) AS unique_ips,
    SUM(bytes_out) AS total_data_out,
    MAX(timestamp) AS last_seen,
    (COUNT(IF(status = 'failed', 1, NULL)) * 10 +
     IF(COUNT(DISTINCT source_ip) > 3, (COUNT(DISTINCT source_ip) - 3) * 5, 0) +
     COUNT(IF(HOUR(timestamp) NOT BETWEEN 8 AND 18, 1, NULL)) * 3) AS risk_score
FROM security_logs
WHERE timestamp > DATE_SUB(NOW(), INTERVAL 24 HOUR)
GROUP BY user_id
HAVING failed_count > 0 OR unique_ips > 3
ORDER BY risk_score DESC;

-- Port scan detection
CREATE VIEW IF NOT EXISTS v_port_scan_detection AS
SELECT
    src_ip,
    COUNT(DISTINCT dest_port) AS unique_ports,
    COUNT(*) AS connection_attempts,
    COUNT(DISTINCT dest_ip) AS unique_destinations,
    MIN(timestamp) AS first_seen,
    MAX(timestamp) AS last_seen,
    TIMESTAMPDIFF(SECOND, MIN(timestamp), MAX(timestamp)) AS time_window_seconds
FROM network_logs
WHERE timestamp > DATE_SUB(NOW(), INTERVAL 5 MINUTE)
GROUP BY src_ip
HAVING unique_ports > 20 AND time_window_seconds < 60
ORDER BY unique_ports DESC;

-- Network traffic summary
CREATE VIEW IF NOT EXISTS v_network_traffic_summary AS
SELECT
    dest_port,
    protocol,
    direction,
    COUNT(*) AS connection_count,
    COUNT(DISTINCT src_ip) AS unique_sources,
    COUNT(DISTINCT dest_ip) AS unique_destinations,
    SUM(bytes_total) AS total_bytes,
    AVG(duration_ms) AS avg_duration_ms
FROM network_logs
WHERE timestamp > DATE_SUB(NOW(), INTERVAL 1 HOUR)
GROUP BY dest_port, protocol, direction
ORDER BY connection_count DESC;

-- ===========================================
-- Validation Queries
-- ===========================================

-- Show tables
SHOW TABLES;

-- Table sizes
SELECT
    TABLE_NAME,
    TABLE_ROWS,
    ROUND(DATA_LENGTH / 1024 / 1024, 2) AS DATA_SIZE_MB,
    ROUND(INDEX_LENGTH / 1024 / 1024, 2) AS INDEX_SIZE_MB,
    ROUND((DATA_LENGTH + INDEX_LENGTH) / 1024 / 1024, 2) AS TOTAL_SIZE_MB
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = 'cybersecurity'
ORDER BY (DATA_LENGTH + INDEX_LENGTH) DESC;

-- Partition information
SELECT
    TABLE_NAME,
    PARTITION_NAME,
    PARTITION_EXPRESSION,
    PARTITION_DESCRIPTION,
    TABLE_ROWS
FROM information_schema.PARTITIONS
WHERE TABLE_SCHEMA = 'cybersecurity'
ORDER BY TABLE_NAME, PARTITION_NAME;

SELECT '=== StarRocks Schema Creation Complete ===' AS status;
