#!/bin/bash
#===============================================================================
# Script: setup_splunk_dbconnect.sh
# Purpose: Install and configure Splunk DB Connect for external database querying
# Dependencies: Docker, Splunk Enterprise container
# Usage: ./scripts/setup_splunk_dbconnect.sh
#===============================================================================

set -euo pipefail

# === Configuration ===
SPLUNK_HOST="localhost"
SPLUNK_PORT="8089"
SPLUNK_WEB_PORT="8000"
SPLUNK_USER="${SPLUNK_USER:-admin}"
SPLUNK_PASSWORD="${SPLUNK_PASSWORD:-changeme}"

SPLUNK_CONTAINER="benchmark-splunk"
SPLUNK_HOME="/opt/splunk"
DBCONNECT_APP="${SPLUNK_HOME}/etc/apps/splunk_app_db_connect"

# Database connection details
POSTGRES_HOST="postgresql"
POSTGRES_PORT="5432"
POSTGRES_DB="cybersecurity"
POSTGRES_USER="benchmark_user"
POSTGRES_PASSWORD="benchmark_pass"

CLICKHOUSE_HOST="clickhouse"
CLICKHOUSE_PORT="8123"
CLICKHOUSE_DB="cybersecurity"

STARROCKS_HOST="starrocks-fe"
STARROCKS_PORT="9030"
STARROCKS_DB="cybersecurity"
STARROCKS_USER="root"
STARROCKS_PASSWORD=""

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

# === Wait for Splunk to be ready ===
wait_for_splunk() {
    local max_attempts=60
    local attempt=1

    log_info "Waiting for Splunk to be ready..."

    while [ $attempt -le $max_attempts ]; do
        if curl -k -u "${SPLUNK_USER}:${SPLUNK_PASSWORD}" \
            "https://${SPLUNK_HOST}:${SPLUNK_PORT}/services/server/info" \
            > /dev/null 2>&1; then
            log_info "Splunk is ready!"
            return 0
        fi

        log_warn "Attempt $attempt/$max_attempts: Splunk not ready yet, waiting 10s..."
        sleep 10
        ((attempt++))
    done

    log_error "Splunk failed to become ready after $max_attempts attempts"
    return 1
}

# === Check if DB Connect app is installed ===
check_dbconnect_installed() {
    log_info "Checking if DB Connect is installed..."

    if docker exec "${SPLUNK_CONTAINER}" test -d "${DBCONNECT_APP}"; then
        log_info "DB Connect app is already installed"
        return 0
    else
        log_warn "DB Connect app is not installed"
        return 1
    fi
}

# === Install DB Connect app ===
install_dbconnect() {
    log_info "Installing Splunk DB Connect app..."

    log_warn "DB Connect requires manual installation:"
    log_warn "1. Download DB Connect from Splunkbase: https://splunkbase.splunk.com/app/2686"
    log_warn "2. Place the .spl or .tgz file in: ./data/splunk/dbconnect/"
    log_warn "3. Or install via Splunk Web UI: http://localhost:8000"
    log_warn ""
    log_warn "After installation, re-run this script to configure connections"

    return 1
}

# === Create database identity (credentials) ===
create_db_identity() {
    local identity_name="$1"
    local username="$2"
    local password="$3"

    log_info "Creating database identity: ${identity_name}..."

    # Use Splunk REST API to create identity
    curl -k -u "${SPLUNK_USER}:${SPLUNK_PASSWORD}" \
        "https://${SPLUNK_HOST}:${SPLUNK_PORT}/servicesNS/nobody/splunk_app_db_connect/db_connect/identities" \
        -d name="${identity_name}" \
        -d username="${username}" \
        -d password="${password}" \
        > /dev/null 2>&1

    if [ $? -eq 0 ]; then
        log_info "Identity '${identity_name}' created successfully"
    else
        log_warn "Failed to create identity '${identity_name}' (may already exist)"
    fi
}

# === Create database connection ===
create_db_connection() {
    local connection_name="$1"
    local connection_type="$2"
    local host="$3"
    local port="$4"
    local database="$5"
    local identity="$6"

    log_info "Creating database connection: ${connection_name}..."

    # Build JDBC URL based on connection type
    local jdbc_url=""
    case "${connection_type}" in
        "postgresql")
            jdbc_url="jdbc:postgresql://${host}:${port}/${database}"
            ;;
        "clickhouse")
            jdbc_url="jdbc:clickhouse://${host}:${port}/${database}"
            ;;
        "mysql")
            # StarRocks uses MySQL protocol
            jdbc_url="jdbc:mysql://${host}:${port}/${database}"
            ;;
        *)
            log_error "Unknown connection type: ${connection_type}"
            return 1
            ;;
    esac

    # Use Splunk REST API to create connection
    curl -k -u "${SPLUNK_USER}:${SPLUNK_PASSWORD}" \
        "https://${SPLUNK_HOST}:${SPLUNK_PORT}/servicesNS/nobody/splunk_app_db_connect/db_connect/connections" \
        -d name="${connection_name}" \
        -d connection_type="${connection_type}" \
        -d host="${host}" \
        -d port="${port}" \
        -d database="${database}" \
        -d identity="${identity}" \
        -d jdbcUrl="${jdbc_url}" \
        > /dev/null 2>&1

    if [ $? -eq 0 ]; then
        log_info "Connection '${connection_name}' created successfully"
    else
        log_warn "Failed to create connection '${connection_name}' (may already exist)"
    fi
}

# === Test database connection ===
test_db_connection() {
    local connection_name="$1"

    log_info "Testing database connection: ${connection_name}..."

    # Use dbxquery to test connection
    docker exec "${SPLUNK_CONTAINER}" ${SPLUNK_HOME}/bin/splunk search \
        "| dbxquery connection=\"${connection_name}\" query=\"SELECT 1\"" \
        -auth "${SPLUNK_USER}:${SPLUNK_PASSWORD}" \
        > /dev/null 2>&1

    if [ $? -eq 0 ]; then
        log_info "Connection '${connection_name}' tested successfully"
    else
        log_warn "Failed to test connection '${connection_name}'"
    fi
}

# === Configure PostgreSQL connection ===
configure_postgresql() {
    log_info "Configuring PostgreSQL connection..."

    create_db_identity "postgresql_identity" "${POSTGRES_USER}" "${POSTGRES_PASSWORD}"
    create_db_connection "postgresql_conn" "postgresql" \
        "${POSTGRES_HOST}" "${POSTGRES_PORT}" "${POSTGRES_DB}" "postgresql_identity"
    test_db_connection "postgresql_conn"
}

# === Configure ClickHouse connection ===
configure_clickhouse() {
    log_info "Configuring ClickHouse connection..."

    log_warn "ClickHouse connection requires ClickHouse JDBC driver"
    log_warn "1. Download from: https://github.com/ClickHouse/clickhouse-jdbc"
    log_warn "2. Place .jar file in: ${DBCONNECT_APP}/drivers/"
    log_warn ""

    create_db_identity "clickhouse_identity" "default" ""
    create_db_connection "clickhouse_conn" "clickhouse" \
        "${CLICKHOUSE_HOST}" "${CLICKHOUSE_PORT}" "${CLICKHOUSE_DB}" "clickhouse_identity"
    test_db_connection "clickhouse_conn"
}

# === Configure StarRocks connection ===
configure_starrocks() {
    log_info "Configuring StarRocks connection (via MySQL protocol)..."

    log_info "StarRocks uses MySQL protocol, no additional driver needed"

    create_db_identity "starrocks_identity" "${STARROCKS_USER}" "${STARROCKS_PASSWORD}"
    create_db_connection "starrocks_conn" "mysql" \
        "${STARROCKS_HOST}" "${STARROCKS_PORT}" "${STARROCKS_DB}" "starrocks_identity"
    test_db_connection "starrocks_conn"
}

# === Show example dbxquery commands ===
show_examples() {
    log_info "======================================"
    log_info "Splunk DB Connect Query Examples"
    log_info "======================================"

    cat <<EOF

# Query PostgreSQL
docker exec ${SPLUNK_CONTAINER} ${SPLUNK_HOME}/bin/splunk search \\
    '| dbxquery connection="postgresql_conn" query="SELECT COUNT(*) FROM security_logs"' \\
    -auth ${SPLUNK_USER}:${SPLUNK_PASSWORD}

# Query ClickHouse
docker exec ${SPLUNK_CONTAINER} ${SPLUNK_HOME}/bin/splunk search \\
    '| dbxquery connection="clickhouse_conn" query="SELECT COUNT(*) FROM security_logs"' \\
    -auth ${SPLUNK_USER}:${SPLUNK_PASSWORD}

# Query StarRocks
docker exec ${SPLUNK_CONTAINER} ${SPLUNK_HOME}/bin/splunk search \\
    '| dbxquery connection="starrocks_conn" query="SELECT COUNT(*) FROM security_logs"' \\
    -auth ${SPLUNK_USER}:${SPLUNK_PASSWORD}

# Complex aggregation query
docker exec ${SPLUNK_CONTAINER} ${SPLUNK_HOME}/bin/splunk search \\
    '| dbxquery connection="postgresql_conn" query="
        SELECT event_type, COUNT(*) as count
        FROM security_logs
        WHERE timestamp >= NOW() - INTERVAL '1 day'
        GROUP BY event_type
        ORDER BY count DESC
        LIMIT 10
    "' \\
    -auth ${SPLUNK_USER}:${SPLUNK_PASSWORD}

# Query with parameters (escaped for bash)
docker exec ${SPLUNK_CONTAINER} ${SPLUNK_HOME}/bin/splunk search \\
    '| dbxquery connection="postgresql_conn" \\
      query="SELECT * FROM security_logs WHERE user_id = '\''user123'\'' LIMIT 100"' \\
    -auth ${SPLUNK_USER}:${SPLUNK_PASSWORD}

# Access via Splunk Web UI
# 1. Go to: http://localhost:8000
# 2. Search: | dbxquery connection="postgresql_conn" query="SELECT COUNT(*) FROM security_logs"
# 3. Results will appear in Splunk's search results

# Access DB Connect UI
# 1. Go to: http://localhost:8000/en-US/app/splunk_app_db_connect/overview
# 2. Navigate to: Data Lab > SQL Explorer
# 3. Select connection and run queries interactively

EOF
}

# === Main Execution ===
main() {
    log_info "======================================"
    log_info "Splunk DB Connect Setup"
    log_info "======================================"

    # Step 1: Wait for Splunk
    log_info "Step 1: Checking Splunk availability..."
    wait_for_splunk || exit 1

    # Step 2: Check if DB Connect is installed
    log_info "Step 2: Checking DB Connect installation..."
    if ! check_dbconnect_installed; then
        install_dbconnect || exit 1
    fi

    # Step 3: Configure database connections
    log_info "Step 3: Configuring database connections..."

    configure_postgresql
    configure_clickhouse
    configure_starrocks

    # Step 4: Show examples
    show_examples

    log_info "======================================"
    log_info "Splunk DB Connect setup complete!"
    log_info "======================================"
    log_info ""
    log_info "Important Notes:"
    log_info "1. DB Connect must be manually downloaded from Splunkbase"
    log_info "2. ClickHouse requires ClickHouse JDBC driver (.jar file)"
    log_info "3. Test connections via Splunk Web UI before running benchmarks"
    log_info ""
    log_info "Access Splunk Web UI: http://localhost:${SPLUNK_WEB_PORT}"
    log_info "Access DB Connect: http://localhost:${SPLUNK_WEB_PORT}/en-US/app/splunk_app_db_connect/overview"
}

# Execute main function
main "$@"
