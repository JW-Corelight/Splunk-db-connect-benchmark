#!/bin/bash
#===============================================================================
# Script: configure_clickhouse_iceberg.sh
# Purpose: Configure ClickHouse to query Apache Iceberg tables from MinIO
# Dependencies: Docker, curl, ClickHouse client
# Usage: ./scripts/configure_clickhouse_iceberg.sh
#===============================================================================

set -euo pipefail

# === Configuration ===
CLICKHOUSE_HOST="localhost"
CLICKHOUSE_HTTP_PORT="8123"
CLICKHOUSE_ENDPOINT="http://${CLICKHOUSE_HOST}:${CLICKHOUSE_HTTP_PORT}"

MINIO_ENDPOINT="http://minio:9000"
MINIO_ACCESS_KEY="${MINIO_ROOT_USER:-admin}"
MINIO_SECRET_KEY="${MINIO_ROOT_PASSWORD:-password123}"

# === Colors for output ===
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# === Logging functions ===
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# === Wait for ClickHouse to be ready ===
wait_for_clickhouse() {
    local max_attempts=30
    local attempt=1

    log_info "Waiting for ClickHouse to be ready..."

    while [ $attempt -le $max_attempts ]; do
        if curl -sf "${CLICKHOUSE_ENDPOINT}/ping" > /dev/null 2>&1; then
            log_info "ClickHouse is ready!"
            return 0
        fi

        log_warn "Attempt $attempt/$max_attempts: ClickHouse not ready yet, waiting 5s..."
        sleep 5
        ((attempt++))
    done

    log_error "ClickHouse failed to become ready after $max_attempts attempts"
    return 1
}

# === Execute ClickHouse Query ===
execute_query() {
    local query="$1"
    local output_format="${2:-Pretty}"

    curl -s "${CLICKHOUSE_ENDPOINT}" \
        --data-binary "${query}" \
        -H "X-ClickHouse-Format: ${output_format}"
}

# === Create Iceberg Database in ClickHouse ===
create_iceberg_database() {
    log_info "Creating Iceberg database in ClickHouse..."

    local query="CREATE DATABASE IF NOT EXISTS iceberg_db ENGINE = Memory COMMENT 'Database for Iceberg table engines'"

    if execute_query "${query}" "Null"; then
        log_info "Iceberg database created successfully"
    else
        log_error "Failed to create Iceberg database"
        return 1
    fi
}

# === Create Iceberg Table Engine ===
create_iceberg_table_engine() {
    log_info "Creating Iceberg table engines in ClickHouse..."

    # Note: ClickHouse Iceberg table engine syntax
    # CREATE TABLE table_name ENGINE = Iceberg(url, [access_key_id, secret_access_key])

    # Create security_logs table
    log_info "Creating security_logs Iceberg table..."

    local security_logs_query="
CREATE TABLE IF NOT EXISTS iceberg_db.security_logs
ENGINE = Iceberg('${MINIO_ENDPOINT}/warehouse/cybersecurity/security_logs', '${MINIO_ACCESS_KEY}', '${MINIO_SECRET_KEY}')
SETTINGS
    s3_endpoint = '${MINIO_ENDPOINT}',
    s3_access_key_id = '${MINIO_ACCESS_KEY}',
    s3_secret_access_key = '${MINIO_SECRET_KEY}',
    s3_region = 'us-east-1'
"

    if execute_query "${security_logs_query}" "Null"; then
        log_info "security_logs Iceberg table created successfully"
    else
        log_warn "Failed to create security_logs table (this is expected if Iceberg table doesn't exist yet)"
    fi

    # Create network_logs table
    log_info "Creating network_logs Iceberg table..."

    local network_logs_query="
CREATE TABLE IF NOT EXISTS iceberg_db.network_logs
ENGINE = Iceberg('${MINIO_ENDPOINT}/warehouse/cybersecurity/network_logs', '${MINIO_ACCESS_KEY}', '${MINIO_SECRET_KEY}')
SETTINGS
    s3_endpoint = '${MINIO_ENDPOINT}',
    s3_access_key_id = '${MINIO_ACCESS_KEY}',
    s3_secret_access_key = '${MINIO_SECRET_KEY}',
    s3_region = 'us-east-1'
"

    if execute_query "${network_logs_query}" "Null"; then
        log_info "network_logs Iceberg table created successfully"
    else
        log_warn "Failed to create network_logs table (this is expected if Iceberg table doesn't exist yet)"
    fi
}

# === Verify Iceberg Setup ===
verify_iceberg_setup() {
    log_info "Verifying ClickHouse Iceberg setup..."

    # Show databases
    log_info "Listing databases..."
    execute_query "SHOW DATABASES" "Pretty"

    # Show tables in iceberg_db
    log_info "Listing tables in iceberg_db..."
    execute_query "SHOW TABLES FROM iceberg_db" "Pretty"

    # Try to query Iceberg table (if it has data)
    log_info "Attempting to query security_logs..."
    local count_query="SELECT COUNT(*) as row_count FROM iceberg_db.security_logs"

    if execute_query "${count_query}" "Pretty" 2>/dev/null; then
        log_info "Successfully queried Iceberg table!"
    else
        log_warn "Could not query Iceberg table (table may be empty or not yet created)"
    fi
}

# === Show Example Queries ===
show_examples() {
    log_info "=================================="
    log_info "ClickHouse Iceberg Query Examples"
    log_info "=================================="

    cat <<EOF

# Count rows in Iceberg table
curl '${CLICKHOUSE_ENDPOINT}' --data-binary \\
    "SELECT COUNT(*) FROM iceberg_db.security_logs"

# Query Iceberg data with filters
curl '${CLICKHOUSE_ENDPOINT}' --data-binary \\
    "SELECT event_type, COUNT(*) as count
     FROM iceberg_db.security_logs
     WHERE timestamp >= '2024-12-01'
     GROUP BY event_type
     ORDER BY count DESC"

# Join Iceberg table with native ClickHouse table
curl '${CLICKHOUSE_ENDPOINT}' --data-binary \\
    "SELECT
         ice.event_type,
         ch.user_name,
         COUNT(*) as events
     FROM iceberg_db.security_logs ice
     JOIN cybersecurity.user_details ch ON ice.user_id = ch.user_id
     GROUP BY ice.event_type, ch.user_name"

# Using ClickHouse client (inside container)
docker exec -it benchmark-clickhouse clickhouse-client --query \\
    "SELECT * FROM iceberg_db.security_logs LIMIT 10"

EOF
}

# === Main Execution ===
main() {
    log_info "=================================="
    log_info "ClickHouse Iceberg Configuration"
    log_info "=================================="

    # Step 1: Wait for ClickHouse
    log_info "Step 1: Checking ClickHouse availability..."
    wait_for_clickhouse || exit 1

    # Step 2: Create Iceberg database
    log_info "Step 2: Creating Iceberg database..."
    create_iceberg_database || exit 1

    # Step 3: Create Iceberg table engines
    log_info "Step 3: Creating Iceberg table engines..."
    create_iceberg_table_engine

    # Step 4: Verify setup
    log_info "Step 4: Verifying setup..."
    verify_iceberg_setup

    # Step 5: Show examples
    show_examples

    log_info "=================================="
    log_info "ClickHouse Iceberg configuration complete!"
    log_info "=================================="
    log_info ""
    log_info "Note: ClickHouse Iceberg engine is READ-ONLY"
    log_info "To write data, use Trino or StarRocks"
    log_info ""
    log_info "Access ClickHouse HTTP interface: ${CLICKHOUSE_ENDPOINT}"
}

# Execute main function
main "$@"
