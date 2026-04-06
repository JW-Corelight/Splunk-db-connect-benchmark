#!/bin/bash
#===============================================================================
# Script: setup_polaris.sh
# Purpose: Initialize Apache Polaris catalog with warehouse and namespace
# Usage: ./scripts/setup_polaris.sh
#===============================================================================

set -euo pipefail

# === Configuration ===
POLARIS_HOST="${POLARIS_HOST:-localhost}"
POLARIS_PORT="${POLARIS_PORT:-8181}"
POLARIS_URL="http://${POLARIS_HOST}:${POLARIS_PORT}"
REALM="benchmark"

# === Colors ===
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# === Wait for Polaris ===
echo "Waiting for Polaris to be ready..."
for i in $(seq 1 30); do
    if curl -sf "${POLARIS_URL}/healthcheck" > /dev/null 2>&1; then
        log_info "Polaris is ready"
        break
    fi
    if [ "$i" -eq 30 ]; then
        log_error "Polaris did not become ready in time"
        exit 1
    fi
    sleep 2
done

# === Create Catalog ===
log_info "Creating 'benchmark' catalog..."
curl -sf -X POST "${POLARIS_URL}/api/management/v1/catalogs" \
    -H "Content-Type: application/json" \
    -d '{
        "catalog": {
            "name": "benchmark",
            "type": "INTERNAL",
            "properties": {
                "default-base-location": "s3://warehouse/"
            },
            "storageConfigInfo": {
                "storageType": "S3",
                "allowedLocations": ["s3://warehouse/"],
                "s3": {
                    "endpoint": "http://minio:9000",
                    "pathStyleAccess": true,
                    "region": "us-east-1"
                }
            }
        }
    }' 2>/dev/null && log_info "Catalog created" || log_warn "Catalog may already exist"

# === Create Namespace ===
log_info "Creating 'cybersecurity' namespace..."
curl -sf -X POST "${POLARIS_URL}/api/catalog/v1/benchmark/namespaces" \
    -H "Content-Type: application/json" \
    -d '{
        "namespace": ["cybersecurity"],
        "properties": {
            "location": "s3://warehouse/cybersecurity/"
        }
    }' 2>/dev/null && log_info "Namespace created" || log_warn "Namespace may already exist"

# === Verify ===
log_info "Verifying catalog setup..."
echo "  Catalogs:"
curl -sf "${POLARIS_URL}/api/management/v1/catalogs" 2>/dev/null | python3 -m json.tool 2>/dev/null || echo "  (could not list catalogs)"

echo "  Namespaces:"
curl -sf "${POLARIS_URL}/api/catalog/v1/benchmark/namespaces" 2>/dev/null | python3 -m json.tool 2>/dev/null || echo "  (could not list namespaces)"

log_info "Polaris setup complete"
log_info "Trino catalog 'iceberg_polaris' is configured to use this catalog"
