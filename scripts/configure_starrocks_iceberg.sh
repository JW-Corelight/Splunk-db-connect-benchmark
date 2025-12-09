#!/bin/bash
#===============================================================================
# Script: configure_starrocks_iceberg.sh
# Purpose: Configure StarRocks to query/write Apache Iceberg tables
# Dependencies: Docker, mysql client
# Usage: ./scripts/configure_starrocks_iceberg.sh
#===============================================================================

set -euo pipefail

# === Configuration ===
STARROCKS_HOST="localhost"
STARROCKS_MYSQL_PORT="9030"
STARROCKS_USER="root"
STARROCKS_PASSWORD=""

HIVE_METASTORE_URI="thrift://hive-metastore:9083"
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

# === Wait for StarRocks to be ready ===
wait_for_starrocks() {
    local max_attempts=30
    local attempt=1

    log_info "Waiting for StarRocks to be ready..."

    while [ $attempt -le $max_attempts ]; do
        if docker exec benchmark-starrocks-fe mysql -h127.0.0.1 -P9030 -uroot -e "SELECT 1" > /dev/null 2>&1; then
            log_info "StarRocks is ready!"
            return 0
        fi

        log_warn "Attempt $attempt/$max_attempts: StarRocks not ready yet, waiting 10s..."
        sleep 10
        ((attempt++))
    done

    log_error "StarRocks failed to become ready after $max_attempts attempts"
    return 1
}

# === Execute StarRocks Query ===
execute_query() {
    local query="$1"

    docker exec -i benchmark-starrocks-fe mysql -h127.0.0.1 -P9030 -uroot -e "${query}"
}

# === Create Iceberg External Catalog ===
create_iceberg_catalog() {
    log_info "Creating Iceberg external catalog in StarRocks..."

    local create_catalog_query="
CREATE EXTERNAL CATALOG IF NOT EXISTS iceberg_catalog
PROPERTIES
(
    'type' = 'iceberg',
    'iceberg.catalog.type' = 'hive',
    'hive.metastore.uris' = '${HIVE_METASTORE_URI}',
    'aws.s3.endpoint' = '${MINIO_ENDPOINT}',
    'aws.s3.access_key' = '${MINIO_ACCESS_KEY}',
    'aws.s3.secret_key' = '${MINIO_SECRET_KEY}',
    'aws.s3.use_instance_profile' = 'false',
    'aws.s3.enable_ssl' = 'false',
    'aws.s3.enable_path_style_access' = 'true',
    'client.factory' = 'com.starrocks.connector.iceberg.IcebergAwsClientFactory'
);
"

    if execute_query "${create_catalog_query}"; then
        log_info "Iceberg catalog created successfully"
    else
        log_error "Failed to create Iceberg catalog"
        return 1
    fi
}

# === Verify Iceberg Catalog ===
verify_iceberg_catalog() {
    log_info "Verifying Iceberg catalog..."

    # Show catalogs
    log_info "Listing catalogs..."
    execute_query "SHOW CATALOGS"

    # Show databases in Iceberg catalog
    log_info "Listing databases in iceberg_catalog..."
    execute_query "SHOW DATABASES FROM iceberg_catalog"

    # Show tables in cybersecurity database
    log_info "Listing tables in iceberg_catalog.cybersecurity..."
    execute_query "SHOW TABLES FROM iceberg_catalog.cybersecurity" || log_warn "No tables found (this is expected if Iceberg tables haven't been created yet)"

    # Try to query Iceberg table
    log_info "Attempting to query security_logs..."
    execute_query "SELECT COUNT(*) as row_count FROM iceberg_catalog.cybersecurity.security_logs" 2>/dev/null || log_warn "Could not query table (may not exist yet)"
}

# === Show Example Queries ===
show_examples() {
    log_info "=================================="
    log_info "StarRocks Iceberg Query Examples"
    log_info "=================================="

    cat <<EOF

# Query Iceberg tables
docker exec -it benchmark-starrocks-fe mysql -h127.0.0.1 -P9030 -uroot -e \\
    "SELECT COUNT(*) FROM iceberg_catalog.cybersecurity.security_logs"

# Filter and aggregate Iceberg data
docker exec -it benchmark-starrocks-fe mysql -h127.0.0.1 -P9030 -uroot -e \\
    "SELECT event_type, COUNT(*) as count
     FROM iceberg_catalog.cybersecurity.security_logs
     WHERE timestamp >= '2024-12-01'
     GROUP BY event_type
     ORDER BY count DESC"

# INSERT data into Iceberg (StarRocks supports writes!)
docker exec -it benchmark-starrocks-fe mysql -h127.0.0.1 -P9030 -uroot -e \\
    "INSERT INTO iceberg_catalog.cybersecurity.security_logs
     (timestamp, event_id, user_id, event_type, status)
     VALUES
     (NOW(), 1001, 'user123', 'login', 'success')"

# UPDATE Iceberg data (ACID transactions)
docker exec -it benchmark-starrocks-fe mysql -h127.0.0.1 -P9030 -uroot -e \\
    "UPDATE iceberg_catalog.cybersecurity.security_logs
     SET status = 'reviewed'
     WHERE event_id = 1001"

# Join Iceberg with native StarRocks table
docker exec -it benchmark-starrocks-fe mysql -h127.0.0.1 -P9030 -uroot -e \\
    "SELECT
         ice.event_type,
         sr.user_name,
         COUNT(*) as events
     FROM iceberg_catalog.cybersecurity.security_logs ice
     JOIN cybersecurity.security_logs sr ON ice.user_id = sr.user_id
     GROUP BY ice.event_type, sr.user_name"

# Switch between catalogs
docker exec -it benchmark-starrocks-fe mysql -h127.0.0.1 -P9030 -uroot -e \\
    "SET CATALOG iceberg_catalog; SHOW DATABASES;"

# Cross-catalog query
docker exec -it benchmark-starrocks-fe mysql -h127.0.0.1 -P9030 -uroot -e \\
    "SELECT
         COUNT(DISTINCT ice.user_id) as unique_users_iceberg,
         COUNT(DISTINCT sr.user_id) as unique_users_native
     FROM iceberg_catalog.cybersecurity.security_logs ice,
          default_catalog.cybersecurity.security_logs sr"

EOF
}

# === Main Execution ===
main() {
    log_info "=================================="
    log_info "StarRocks Iceberg Configuration"
    log_info "=================================="

    # Step 1: Wait for StarRocks
    log_info "Step 1: Checking StarRocks availability..."
    wait_for_starrocks || exit 1

    # Step 2: Create Iceberg catalog
    log_info "Step 2: Creating Iceberg external catalog..."
    create_iceberg_catalog || exit 1

    # Step 3: Verify setup
    log_info "Step 3: Verifying setup..."
    verify_iceberg_catalog

    # Step 4: Show examples
    show_examples

    log_info "=================================="
    log_info "StarRocks Iceberg configuration complete!"
    log_info "=================================="
    log_info ""
    log_info "Note: StarRocks supports FULL READ/WRITE on Iceberg"
    log_info "You can INSERT, UPDATE, DELETE, and MERGE data"
    log_info ""
    log_info "Access StarRocks MySQL protocol: mysql -h${STARROCKS_HOST} -P${STARROCKS_MYSQL_PORT} -u${STARROCKS_USER}"
    log_info "Access StarRocks HTTP UI: http://localhost:8030"
}

# Execute main function
main "$@"
