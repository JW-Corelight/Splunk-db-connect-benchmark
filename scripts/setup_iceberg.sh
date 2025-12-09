#!/bin/bash
#===============================================================================
# Script: setup_iceberg.sh
# Purpose: Initialize MinIO buckets and create Apache Iceberg tables via Trino
# Dependencies: Docker, MinIO client (mc), curl
# Usage: ./scripts/setup_iceberg.sh
#===============================================================================

set -euo pipefail

# === Configuration ===
MINIO_ENDPOINT="http://localhost:9000"
MINIO_ROOT_USER="${MINIO_ROOT_USER:-admin}"
MINIO_ROOT_PASSWORD="${MINIO_ROOT_PASSWORD:-password123}"
MINIO_BUCKET="warehouse"

TRINO_ENDPOINT="http://localhost:8080"
HIVE_METASTORE_ENDPOINT="hive-metastore:9083"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

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

# === Wait for service to be ready ===
wait_for_service() {
    local service_name=$1
    local health_url=$2
    local max_attempts=${3:-30}
    local attempt=1

    log_info "Waiting for $service_name to be ready..."

    while [ $attempt -le $max_attempts ]; do
        if curl -sf "$health_url" > /dev/null 2>&1; then
            log_info "$service_name is ready!"
            return 0
        fi

        log_warn "Attempt $attempt/$max_attempts: $service_name not ready yet, waiting 10s..."
        sleep 10
        ((attempt++))
    done

    log_error "$service_name failed to become ready after $max_attempts attempts"
    return 1
}

# === Check if MinIO client is installed ===
check_minio_client() {
    if ! command -v mc &> /dev/null; then
        log_warn "MinIO client (mc) not found. Installing..."

        if [[ "$OSTYPE" == "darwin"* ]]; then
            # macOS
            if command -v brew &> /dev/null; then
                brew install minio/stable/mc
            else
                log_error "Homebrew not found. Please install MinIO client manually:"
                log_error "https://min.io/docs/minio/macos/reference/minio-mc.html"
                return 1
            fi
        elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
            # Linux
            curl https://dl.min.io/client/mc/release/linux-amd64/mc \
                --create-dirs \
                -o $HOME/minio-binaries/mc
            chmod +x $HOME/minio-binaries/mc
            export PATH=$PATH:$HOME/minio-binaries/
        else
            log_error "Unsupported OS. Please install MinIO client manually."
            return 1
        fi
    fi

    log_info "MinIO client is installed"
    return 0
}

# === Initialize MinIO ===
initialize_minio() {
    log_info "Initializing MinIO..."

    # Wait for MinIO to be ready
    wait_for_service "MinIO" "${MINIO_ENDPOINT}/minio/health/live" 30

    # Configure MinIO client alias
    log_info "Configuring MinIO client..."
    mc alias set local_minio "${MINIO_ENDPOINT}" "${MINIO_ROOT_USER}" "${MINIO_ROOT_PASSWORD}"

    # Create warehouse bucket if it doesn't exist
    if mc ls local_minio/${MINIO_BUCKET} > /dev/null 2>&1; then
        log_info "Bucket '${MINIO_BUCKET}' already exists"
    else
        log_info "Creating bucket '${MINIO_BUCKET}'..."
        mc mb local_minio/${MINIO_BUCKET}
    fi

    # Set bucket policy to allow access (for development)
    log_info "Setting bucket policy..."
    mc anonymous set download local_minio/${MINIO_BUCKET}

    # Create subdirectory for cybersecurity namespace
    log_info "Creating namespace directory..."
    mc mb --ignore-existing local_minio/${MINIO_BUCKET}/cybersecurity/

    log_info "MinIO initialization complete!"
}

# === Initialize Hive Metastore ===
initialize_hive_metastore() {
    log_info "Initializing Hive Metastore..."

    # Wait for Hive Metastore to be ready
    log_info "Waiting for Hive Metastore service..."
    local attempt=1
    local max_attempts=30

    while [ $attempt -le $max_attempts ]; do
        if nc -z localhost 9083 2>/dev/null; then
            log_info "Hive Metastore is ready!"
            return 0
        fi

        log_warn "Attempt $attempt/$max_attempts: Hive Metastore not ready yet, waiting 10s..."
        sleep 10
        ((attempt++))
    done

    log_error "Hive Metastore failed to become ready"
    return 1
}

# === Create Iceberg Tables via Trino ===
create_iceberg_tables() {
    log_info "Creating Iceberg tables via Trino..."

    # Wait for Trino to be ready
    wait_for_service "Trino" "${TRINO_ENDPOINT}/v1/info" 60

    # Execute Iceberg schema SQL
    log_info "Executing Iceberg schema creation..."

    if [ ! -f "${PROJECT_ROOT}/sql/iceberg_schema.sql" ]; then
        log_error "Iceberg schema file not found: ${PROJECT_ROOT}/sql/iceberg_schema.sql"
        return 1
    fi

    # Use docker exec to run Trino CLI inside the container
    docker exec -i benchmark-trino trino --server localhost:8080 --catalog iceberg \
        < "${PROJECT_ROOT}/sql/iceberg_schema.sql"

    if [ $? -eq 0 ]; then
        log_info "Iceberg tables created successfully!"
    else
        log_error "Failed to create Iceberg tables"
        return 1
    fi
}

# === Verify Iceberg Setup ===
verify_iceberg_setup() {
    log_info "Verifying Iceberg setup..."

    # List Iceberg schemas
    log_info "Listing Iceberg schemas..."
    docker exec -i benchmark-trino trino --server localhost:8080 --catalog iceberg \
        --execute "SHOW SCHEMAS"

    # List tables in cybersecurity schema
    log_info "Listing tables in iceberg.cybersecurity..."
    docker exec -i benchmark-trino trino --server localhost:8080 --catalog iceberg \
        --execute "SHOW TABLES FROM iceberg.cybersecurity"

    # Show table details
    log_info "Showing security_logs table structure..."
    docker exec -i benchmark-trino trino --server localhost:8080 --catalog iceberg \
        --execute "DESCRIBE iceberg.cybersecurity.security_logs"

    log_info "Iceberg setup verification complete!"
}

# === Load Sample Data (Optional) ===
load_sample_data() {
    log_info "Loading sample data into Iceberg tables..."

    # Insert sample security log events
    cat <<EOF | docker exec -i benchmark-trino trino --server localhost:8080 --catalog iceberg
USE iceberg.cybersecurity;

INSERT INTO security_logs (timestamp, event_id, user_id, user_type, host, source_ip, dest_ip, port, event_type, status, bytes_in, bytes_out, event_data)
VALUES
    (TIMESTAMP '2024-12-08 10:00:00 UTC', 1, 'user001', 'admin', 'host001', '192.168.1.100', '10.0.0.50', 22, 'ssh_login', 'success', 0, 0, '{}'),
    (TIMESTAMP '2024-12-08 10:05:00 UTC', 2, 'user002', 'standard', 'host002', '192.168.1.101', '10.0.0.51', 443, 'web_access', 'success', 1024, 2048, '{}'),
    (TIMESTAMP '2024-12-08 10:10:00 UTC', 3, 'user003', 'standard', 'host003', '192.168.1.102', '10.0.0.52', 22, 'ssh_login', 'failed', 0, 0, '{}'),
    (TIMESTAMP '2024-12-08 10:15:00 UTC', 4, 'user001', 'admin', 'host001', '192.168.1.100', '10.0.0.53', 3306, 'database_access', 'success', 4096, 8192, '{}'),
    (TIMESTAMP '2024-12-08 10:20:00 UTC', 5, 'user004', 'service', 'host004', '192.168.1.103', '10.0.0.54', 8080, 'api_call', 'success', 512, 1024, '{}');
EOF

    if [ $? -eq 0 ]; then
        log_info "Sample data loaded successfully!"

        # Verify data
        log_info "Verifying loaded data..."
        docker exec -i benchmark-trino trino --server localhost:8080 --catalog iceberg \
            --execute "SELECT COUNT(*) as row_count FROM iceberg.cybersecurity.security_logs"
    else
        log_warn "Failed to load sample data (this is optional)"
    fi
}

# === Main Execution ===
main() {
    log_info "=================================="
    log_info "Iceberg Setup Script"
    log_info "=================================="

    # Step 1: Check prerequisites
    log_info "Step 1: Checking prerequisites..."
    check_minio_client || exit 1

    # Step 2: Initialize MinIO
    log_info "Step 2: Initializing MinIO..."
    initialize_minio || exit 1

    # Step 3: Initialize Hive Metastore
    log_info "Step 3: Initializing Hive Metastore..."
    initialize_hive_metastore || exit 1

    # Step 4: Create Iceberg tables
    log_info "Step 4: Creating Iceberg tables..."
    create_iceberg_tables || exit 1

    # Step 5: Verify setup
    log_info "Step 5: Verifying setup..."
    verify_iceberg_setup || exit 1

    # Step 6: Load sample data (optional)
    if [ "${LOAD_SAMPLE_DATA:-true}" = "true" ]; then
        log_info "Step 6: Loading sample data..."
        load_sample_data
    else
        log_info "Step 6: Skipping sample data load (set LOAD_SAMPLE_DATA=true to enable)"
    fi

    log_info "=================================="
    log_info "Iceberg setup completed successfully!"
    log_info "=================================="
    log_info ""
    log_info "Next steps:"
    log_info "1. Configure ClickHouse Iceberg engine: ./scripts/configure_clickhouse_iceberg.sh"
    log_info "2. Configure StarRocks Iceberg catalog: ./scripts/configure_starrocks_iceberg.sh"
    log_info "3. Access Trino Web UI: http://localhost:8080"
    log_info "4. Access MinIO Console: http://localhost:9001 (admin/password123)"
}

# Execute main function
main "$@"
