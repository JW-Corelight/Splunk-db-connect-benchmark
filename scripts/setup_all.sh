#!/bin/bash
# ================================================
# Master Setup Script for Database Benchmark
# ================================================
# Purpose: Orchestrate complete environment setup
# Platform: MacBook Pro M3 (Apple Silicon)
# Version: 1.0.0
# Last Updated: December 7, 2024
# ================================================

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Logging
LOG_FILE="${PROJECT_ROOT}/logs/setup_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "${PROJECT_ROOT}/logs"

# Functions
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"
}

error() {
    echo -e "${RED}[ERROR] $1${NC}" | tee -a "$LOG_FILE"
    exit 1
}

warning() {
    echo -e "${YELLOW}[WARNING] $1${NC}" | tee -a "$LOG_FILE"
}

info() {
    echo -e "${BLUE}[INFO] $1${NC}" | tee -a "$LOG_FILE"
}

# Banner
cat << "EOF"
╔════════════════════════════════════════════════════════════╗
║                                                            ║
║   Database Benchmark Environment Setup                    ║
║   MacBook Pro M3 (Apple Silicon)                          ║
║                                                            ║
║   Components:                                              ║
║   - PostgreSQL 16 (ARM64 native)                          ║
║   - ClickHouse 24.1 (ARM64 native)                        ║
║   - StarRocks 3.2 (Rosetta 2)                             ║
║   - Splunk 9.1 (Rosetta 2)                                ║
║                                                            ║
╚════════════════════════════════════════════════════════════╝
EOF

echo ""
log "Starting setup process..."
log "Log file: $LOG_FILE"
echo ""

# Change to project root
cd "$PROJECT_ROOT"

# ================================================
# Phase 1: System Verification
# ================================================
log "Phase 1: System Verification"
bash "${SCRIPT_DIR}/phase1_verify_system.sh" || error "Phase 1 failed"
log "✅ Phase 1 complete"
echo ""

# ================================================
# Phase 2: Docker Configuration
# ================================================
log "Phase 2: Docker Configuration"
bash "${SCRIPT_DIR}/phase2_configure_docker.sh" || error "Phase 2 failed"
log "✅ Phase 2 complete"
echo ""

# ================================================
# Phase 3: Container Deployment
# ================================================
log "Phase 3: Container Deployment"
bash "${SCRIPT_DIR}/phase3_deploy_containers.sh" || error "Phase 3 failed"
log "✅ Phase 3 complete"
echo ""

# ================================================
# Phase 4: Data Generation and Loading
# ================================================
log "Phase 4: Data Generation and Loading"
bash "${SCRIPT_DIR}/phase4_load_data.sh" || error "Phase 4 failed"
log "✅ Phase 4 complete"
echo ""

# ================================================
# Phase 5: Validation
# ================================================
log "Phase 5: Validation"
python3 "${SCRIPT_DIR}/../tests/validate_environment.py" || error "Validation failed"
log "✅ Phase 5 complete"
echo ""

# ================================================
# Summary
# ================================================
echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║                    SETUP COMPLETE                          ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""
log "All phases completed successfully!"
echo ""
info "Service Endpoints:"
echo "  PostgreSQL:   localhost:5432"
echo "  ClickHouse:   http://localhost:8123"
echo "  StarRocks FE: http://localhost:8030"
echo "  StarRocks BE: http://localhost:8040"
echo "  Splunk UI:    http://localhost:8000 (admin/ComplexP@ss123)"
echo ""
info "Next Steps:"
echo "  1. Run benchmarks:     bash scripts/run_benchmarks.sh"
echo "  2. View results:       cat results/benchmark_results.json"
echo "  3. Monitor resources:  bash scripts/monitor_resources.sh"
echo "  4. Cleanup:            bash scripts/cleanup.sh"
echo ""
log "Setup log saved to: $LOG_FILE"
