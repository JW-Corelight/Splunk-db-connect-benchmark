#!/bin/bash
#===============================================================================
# Script: run_all.sh
# Purpose: Execute all benchmark scripts and generate comprehensive report
# Usage: ./benchmarks/run_all.sh
#===============================================================================

set -euo pipefail

# === Configuration ===
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
RESULTS_DIR="${SCRIPT_DIR}/results"

# === Colors for output ===
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
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

log_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

log_header() {
    echo ""
    echo -e "${CYAN}================================================================================${NC}"
    echo -e "${CYAN}$1${NC}"
    echo -e "${CYAN}================================================================================${NC}"
    echo ""
}

# === Check Python dependencies ===
check_dependencies() {
    log_step "Checking Python dependencies..."

    local missing_packages=()

    python3 -c "import psycopg2" 2>/dev/null || missing_packages+=("psycopg2-binary")
    python3 -c "import clickhouse_connect" 2>/dev/null || missing_packages+=("clickhouse-connect")
    python3 -c "import pymysql" 2>/dev/null || missing_packages+=("pymysql")

    if [ ${#missing_packages[@]} -gt 0 ]; then
        log_warn "Missing Python packages: ${missing_packages[*]}"
        log_info "Installing missing packages..."
        pip3 install "${missing_packages[@]}"
    else
        log_info "All Python dependencies are installed"
    fi
}

# === Create results directory ===
setup_results_dir() {
    log_step "Setting up results directory..."

    if [ ! -d "$RESULTS_DIR" ]; then
        mkdir -p "$RESULTS_DIR"
        log_info "Created results directory: $RESULTS_DIR"
    else
        log_info "Results directory already exists: $RESULTS_DIR"
    fi
}

# === Run individual benchmark ===
run_benchmark() {
    local script_name="$1"
    local description="$2"

    log_header "Running: $description"

    if [ -f "${SCRIPT_DIR}/${script_name}" ]; then
        python3 "${SCRIPT_DIR}/${script_name}"

        if [ $? -eq 0 ]; then
            log_info "✓ $description completed successfully"
        else
            log_error "✗ $description failed"
            return 1
        fi
    else
        log_error "Script not found: ${SCRIPT_DIR}/${script_name}"
        return 1
    fi
}

# === Check if databases are running ===
check_databases() {
    log_step "Checking if databases are running..."

    local all_healthy=true

    # Check PostgreSQL
    if docker exec benchmark-postgres pg_isready -U benchmark_user > /dev/null 2>&1; then
        log_info "✓ PostgreSQL is running"
    else
        log_error "✗ PostgreSQL is not running"
        all_healthy=false
    fi

    # Check ClickHouse
    if curl -sf http://localhost:8123/ping > /dev/null 2>&1; then
        log_info "✓ ClickHouse is running"
    else
        log_error "✗ ClickHouse is not running"
        all_healthy=false
    fi

    # Check StarRocks
    if docker exec benchmark-starrocks-fe mysql -h127.0.0.1 -P9030 -uroot -e "SELECT 1" > /dev/null 2>&1; then
        log_info "✓ StarRocks is running"
    else
        log_error "✗ StarRocks is not running"
        all_healthy=false
    fi

    # Check Splunk (optional for benchmark 1 and 3)
    if curl -k -u admin:changeme https://localhost:8089/services/server/info > /dev/null 2>&1; then
        log_info "✓ Splunk is running"
    else
        log_warn "⚠ Splunk is not running (required only for benchmark 2)"
    fi

    if [ "$all_healthy" = false ]; then
        log_error "Not all required databases are running"
        log_info "Please start all services with: docker-compose -f docker-compose.m3.yml up -d"
        return 1
    fi

    return 0
}

# === Generate summary report ===
generate_summary() {
    log_header "Benchmark Summary Report"

    local latest_results=($(ls -t "$RESULTS_DIR"/*.json 2>/dev/null | head -3))

    if [ ${#latest_results[@]} -eq 0 ]; then
        log_warn "No results found in $RESULTS_DIR"
        return 1
    fi

    log_info "Latest benchmark results:"
    for result in "${latest_results[@]}"; do
        echo "  - $(basename "$result")"
    done

    echo ""
    log_info "To view detailed results, open the JSON files in: $RESULTS_DIR"
    log_info "To visualize results, consider using jq or a JSON viewer"

    # Example summary extraction (requires jq)
    if command -v jq &> /dev/null; then
        log_info ""
        log_info "Quick Summary (using jq):"

        for result in "${latest_results[@]}"; do
            local filename=$(basename "$result")
            echo ""
            echo "File: $filename"

            # Extract summary based on file type
            if [[ "$filename" =~ native_baseline ]]; then
                echo "  Native Performance:"
                jq -r '.postgresql.count_all.avg_latency_ms as $pg |
                       .clickhouse.count_all.avg_latency_ms as $ch |
                       .starrocks.count_all.avg_latency_ms as $sr |
                       "    PostgreSQL: \($pg) ms\n    ClickHouse: \($ch) ms\n    StarRocks:  \($sr) ms"' "$result" 2>/dev/null || echo "    (parsing failed)"

            elif [[ "$filename" =~ splunk_overhead ]]; then
                echo "  Splunk dbxquery Overhead:"
                jq -r '.postgresql.count_all.overhead_ms as $pg |
                       .clickhouse.count_all.overhead_ms as $ch |
                       .starrocks.count_all.overhead_ms as $sr |
                       "    PostgreSQL: +\($pg) ms\n    ClickHouse: +\($ch) ms\n    StarRocks:  +\($sr) ms"' "$result" 2>/dev/null || echo "    (parsing failed)"

            elif [[ "$filename" =~ iceberg_multi_engine ]]; then
                echo "  Iceberg Format Slowdown:"
                jq -r '.clickhouse.count_all.slowdown_factor as $ch |
                       .starrocks.count_all.slowdown_factor as $sr |
                       "    ClickHouse: \($ch)x slower\n    StarRocks:  \($sr)x slower"' "$result" 2>/dev/null || echo "    (parsing failed)"
            fi
        done
    else
        log_warn "Install 'jq' for automated result parsing: brew install jq"
    fi
}

# === Main Execution ===
main() {
    local start_time=$(date +%s)

    log_header "Database Benchmark Suite - Complete Run"
    log_info "Start Time: $(date '+%Y-%m-%d %H:%M:%S')"
    log_info "Platform: $(uname -m)"

    # Step 1: Check dependencies
    check_dependencies || exit 1

    # Step 2: Setup results directory
    setup_results_dir || exit 1

    # Step 3: Check database health
    check_databases || exit 1

    # Step 4: Run benchmarks
    log_info ""
    log_info "Starting benchmark execution..."
    log_info ""

    # Benchmark 1: Native Performance Baseline
    run_benchmark "01_native_baseline.py" "Benchmark 1: Native Performance Baseline" || log_error "Benchmark 1 failed"

    # Benchmark 2: Splunk dbxquery Overhead
    run_benchmark "02_splunk_dbxquery_overhead.py" "Benchmark 2: Splunk dbxquery Overhead" || log_warn "Benchmark 2 failed (Splunk may not be configured)"

    # Benchmark 3: Iceberg Multi-Engine
    run_benchmark "03_iceberg_multi_engine.py" "Benchmark 3: Iceberg Multi-Engine Performance" || log_warn "Benchmark 3 failed (Iceberg may not be set up)"

    # Step 5: Generate summary
    generate_summary

    local end_time=$(date +%s)
    local duration=$((end_time - start_time))

    log_header "Benchmark Suite Complete"
    log_info "End Time: $(date '+%Y-%m-%d %H:%M:%S')"
    log_info "Total Duration: ${duration} seconds"
    log_info "Results saved in: $RESULTS_DIR"
}

# Execute main function
main "$@"
