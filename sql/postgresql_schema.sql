-- PostgreSQL Schema for Cybersecurity Logs
-- Optimized for analytical queries on M3 architecture
-- Version: 1.0.0
-- Last Updated: December 7, 2024

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS pg_trgm;     -- Trigram matching for pattern searches
CREATE EXTENSION IF NOT EXISTS btree_gin;   -- GIN indexes for B-tree types
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;  -- Query statistics

\timing on

BEGIN;

-- ===========================================
-- Main Security Events Table
-- ===========================================
CREATE TABLE IF NOT EXISTS security_logs (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL,
    event_id BIGINT,
    user_id VARCHAR(100),
    user_type VARCHAR(50),
    host VARCHAR(255),
    source_ip INET,
    dest_ip INET,
    port INTEGER CHECK (port >= 0 AND port <= 65535),
    event_type VARCHAR(100),
    status VARCHAR(50),
    bytes_in BIGINT CHECK (bytes_in >= 0),
    bytes_out BIGINT CHECK (bytes_out >= 0),
    event_data JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes optimized for common query patterns
-- BRIN index for timestamp (efficient for time-series data)
CREATE INDEX idx_security_logs_timestamp
    ON security_logs USING BRIN (timestamp)
    WITH (pages_per_range = 128);

-- B-tree indexes for exact lookups
CREATE INDEX idx_security_logs_user_id
    ON security_logs (user_id);

CREATE INDEX idx_security_logs_event_type
    ON security_logs (event_type);

CREATE INDEX idx_security_logs_status
    ON security_logs (status);

CREATE INDEX idx_security_logs_user_type
    ON security_logs (user_type);

-- GIST index for IP address range queries
CREATE INDEX idx_security_logs_source_ip
    ON security_logs USING GIST (source_ip inet_ops);

CREATE INDEX idx_security_logs_dest_ip
    ON security_logs USING GIST (dest_ip inet_ops);

-- GIN index for JSONB data
CREATE INDEX idx_security_logs_event_data
    ON security_logs USING GIN (event_data);

-- Composite index for common query patterns
CREATE INDEX idx_security_logs_timestamp_user_event
    ON security_logs (timestamp, user_id, event_type);

-- ===========================================
-- Network Connection Logs Table
-- ===========================================
CREATE TABLE IF NOT EXISTS network_logs (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL,
    connection_id BIGINT,
    src_ip INET NOT NULL,
    dest_ip INET NOT NULL,
    src_port INTEGER CHECK (src_port >= 0 AND src_port <= 65535),
    dest_port INTEGER CHECK (dest_port >= 0 AND dest_port <= 65535),
    direction VARCHAR(20) CHECK (direction IN ('inbound', 'outbound', 'internal')),
    protocol VARCHAR(20) CHECK (protocol IN ('TCP', 'UDP', 'ICMP', 'HTTP', 'HTTPS', 'DNS')),
    bytes_in BIGINT DEFAULT 0,
    bytes_out BIGINT DEFAULT 0,
    bytes_total BIGINT GENERATED ALWAYS AS (bytes_in + bytes_out) STORED,
    packets_in INTEGER DEFAULT 0,
    packets_out INTEGER DEFAULT 0,
    connection_state VARCHAR(50),
    duration_ms INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for network_logs
CREATE INDEX idx_network_logs_timestamp
    ON network_logs USING BRIN (timestamp);

CREATE INDEX idx_network_logs_src_ip
    ON network_logs USING GIST (src_ip inet_ops);

CREATE INDEX idx_network_logs_dest_ip
    ON network_logs USING GIST (dest_ip inet_ops);

CREATE INDEX idx_network_logs_dest_port
    ON network_logs (dest_port);

CREATE INDEX idx_network_logs_protocol
    ON network_logs (protocol);

CREATE INDEX idx_network_logs_connection_state
    ON network_logs (connection_state);

-- Composite index for firewall-like queries
CREATE INDEX idx_network_logs_src_dest
    ON network_logs (src_ip, dest_ip, dest_port);

-- ===========================================
-- User Activity Summary Table (Aggregated)
-- ===========================================
CREATE TABLE IF NOT EXISTS user_activity_summary (
    user_id VARCHAR(100) NOT NULL,
    day DATE NOT NULL,
    total_events INTEGER DEFAULT 0,
    failed_logins INTEGER DEFAULT 0,
    successful_logins INTEGER DEFAULT 0,
    data_transferred BIGINT DEFAULT 0,
    unique_hosts INTEGER DEFAULT 0,
    unique_ips INTEGER DEFAULT 0,
    last_activity TIMESTAMP,
    PRIMARY KEY (user_id, day)
);

CREATE INDEX idx_user_activity_day
    ON user_activity_summary (day);

CREATE INDEX idx_user_activity_failed_logins
    ON user_activity_summary (failed_logins)
    WHERE failed_logins > 5;

-- ===========================================
-- Threat Intelligence Table
-- ===========================================
CREATE TABLE IF NOT EXISTS threat_intel (
    id SERIAL PRIMARY KEY,
    indicator_type VARCHAR(50) NOT NULL,  -- ip, domain, hash, etc.
    indicator_value TEXT NOT NULL,
    threat_level VARCHAR(20) CHECK (threat_level IN ('low', 'medium', 'high', 'critical')),
    threat_category VARCHAR(100),
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source VARCHAR(100),
    metadata JSONB DEFAULT '{}'::jsonb,
    UNIQUE (indicator_type, indicator_value)
);

CREATE INDEX idx_threat_intel_indicator
    ON threat_intel (indicator_type, indicator_value);

CREATE INDEX idx_threat_intel_level
    ON threat_intel (threat_level);

-- ===========================================
-- Materialized Views for Common Queries
-- ===========================================

-- Hourly event counts by type
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_hourly_events AS
SELECT
    date_trunc('hour', timestamp) AS hour,
    event_type,
    COUNT(*) AS event_count,
    COUNT(DISTINCT user_id) AS unique_users,
    COUNT(DISTINCT source_ip) AS unique_ips
FROM security_logs
GROUP BY date_trunc('hour', timestamp), event_type
WITH DATA;

CREATE INDEX idx_mv_hourly_events_hour ON mv_hourly_events (hour);
CREATE INDEX idx_mv_hourly_events_type ON mv_hourly_events (event_type);

-- Failed login attempts summary
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_failed_logins AS
SELECT
    user_id,
    source_ip,
    COUNT(*) AS failed_attempts,
    MIN(timestamp) AS first_failure,
    MAX(timestamp) AS last_failure
FROM security_logs
WHERE event_type = 'login' AND status = 'failed'
GROUP BY user_id, source_ip
HAVING COUNT(*) >= 3
WITH DATA;

CREATE INDEX idx_mv_failed_logins_user ON mv_failed_logins (user_id);
CREATE INDEX idx_mv_failed_logins_ip ON mv_failed_logins (source_ip);

-- ===========================================
-- Functions for Common Operations
-- ===========================================

-- Refresh materialized views
CREATE OR REPLACE FUNCTION refresh_all_mv()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_hourly_events;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_failed_logins;
END;
$$ LANGUAGE plpgsql;

-- Calculate user risk score
CREATE OR REPLACE FUNCTION calculate_user_risk_score(p_user_id VARCHAR)
RETURNS INTEGER AS $$
DECLARE
    risk_score INTEGER := 0;
    failed_count INTEGER;
    unique_ip_count INTEGER;
    after_hours_count INTEGER;
BEGIN
    -- Failed login attempts (weight: 10 points each)
    SELECT COUNT(*) INTO failed_count
    FROM security_logs
    WHERE user_id = p_user_id
      AND event_type = 'login'
      AND status = 'failed'
      AND timestamp > CURRENT_TIMESTAMP - INTERVAL '24 hours';

    risk_score := risk_score + (failed_count * 10);

    -- Multiple IPs (weight: 5 points each unique IP)
    SELECT COUNT(DISTINCT source_ip) INTO unique_ip_count
    FROM security_logs
    WHERE user_id = p_user_id
      AND timestamp > CURRENT_TIMESTAMP - INTERVAL '24 hours';

    IF unique_ip_count > 3 THEN
        risk_score := risk_score + ((unique_ip_count - 3) * 5);
    END IF;

    -- After-hours activity (weight: 3 points each)
    SELECT COUNT(*) INTO after_hours_count
    FROM security_logs
    WHERE user_id = p_user_id
      AND EXTRACT(HOUR FROM timestamp) NOT BETWEEN 8 AND 18
      AND timestamp > CURRENT_TIMESTAMP - INTERVAL '24 hours';

    risk_score := risk_score + (after_hours_count * 3);

    RETURN risk_score;
END;
$$ LANGUAGE plpgsql;

-- ===========================================
-- Statistics and Analysis
-- ===========================================

-- Analyze tables for query optimization
ANALYZE security_logs;
ANALYZE network_logs;
ANALYZE user_activity_summary;
ANALYZE threat_intel;

COMMIT;

-- ===========================================
-- Validation Queries
-- ===========================================

-- Display table sizes
\echo '=== Table Sizes ==='
SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

-- Display index information
\echo '=== Index Information ==='
SELECT
    tablename,
    indexname,
    pg_size_pretty(pg_relation_size(indexname::regclass)) AS index_size
FROM pg_indexes
WHERE schemaname = 'public'
ORDER BY pg_relation_size(indexname::regclass) DESC
LIMIT 10;

\echo '=== Schema Creation Complete ==='
