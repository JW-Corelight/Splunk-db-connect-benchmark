#!/bin/bash
# ================================================
# Cleanup Script
# ================================================
# Purpose: Stop containers and optionally remove data
# ================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

echo "🧹 Database Benchmark Cleanup"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Confirm cleanup
read -p "This will stop all containers. Continue? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cleanup cancelled."
    exit 0
fi

# Stop all containers
echo -n "Stopping all containers... "
docker-compose -f docker-compose.m3.yml down > /dev/null 2>&1
echo -e "${GREEN}✓${NC}"

# Remove containers
echo -n "Removing containers... "
docker rm -f benchmark-postgresql benchmark-clickhouse \
    benchmark-starrocks-fe benchmark-starrocks-be \
    benchmark-splunk 2>/dev/null || true
echo -e "${GREEN}✓${NC}"

# Ask about data deletion
echo ""
read -p "Delete all data directories? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo -n "Deleting data directories... "
    rm -rf data/postgresql/*
    rm -rf data/clickhouse/*
    rm -rf data/starrocks-fe/*
    rm -rf data/starrocks-be/*
    rm -rf data/splunk/*
    echo -e "${GREEN}✓${NC}"
fi

# Ask about result deletion
echo ""
read -p "Delete benchmark results? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo -n "Deleting results... "
    rm -rf results/*
    echo -e "${GREEN}✓${NC}"
fi

# Ask about Docker cleanup
echo ""
read -p "Run Docker system prune (removes unused images/networks)? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Running Docker system prune..."
    docker system prune -f
    echo -e "${GREEN}✓${NC}"
fi

# Verify cleanup
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Cleanup Status:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

RUNNING=$(docker ps -q --filter "label=benchmark.category" | wc -l | tr -d ' ')
if [[ "$RUNNING" -eq 0 ]]; then
    echo -e "${GREEN}✓${NC} No benchmark containers running"
else
    echo -e "${YELLOW}⚠${NC}  ${RUNNING} containers still running"
    docker ps --format "table {{.Names}}\t{{.Status}}"
fi

# Display disk usage
echo ""
echo "Disk Usage:"
du -sh data/* 2>/dev/null || echo "  No data directories"

echo ""
echo -e "${GREEN}✅ Cleanup complete${NC}"
echo ""
echo "To restart the environment, run: bash scripts/setup_all.sh"
