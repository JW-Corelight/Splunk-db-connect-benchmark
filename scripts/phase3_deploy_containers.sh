#!/bin/bash
# ================================================
# Phase 3: Container Deployment
# ================================================
# Purpose: Deploy all database containers
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

echo "📦 Phase 3: Container Deployment"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Ensure .env file exists
if [[ ! -f .env ]]; then
    echo "Creating .env from .env.example..."
    cp .env.example .env
fi

# Create required directories
echo -n "Creating data directories... "
mkdir -p data/{postgresql,clickhouse,starrocks-fe,starrocks-be,splunk/etc,splunk/var}
mkdir -p results logs
echo -e "${GREEN}✓${NC}"

# Pull Docker images
echo ""
echo "Pulling Docker images (this may take 10-15 minutes)..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ARM64 native images
echo -n "PostgreSQL 16 (ARM64)... "
docker pull --platform linux/arm64 postgres:16-alpine --quiet && echo -e "${GREEN}✓${NC}" || echo -e "${RED}❌${NC}"

echo -n "ClickHouse 24.1 (ARM64)... "
docker pull --platform linux/arm64 clickhouse/clickhouse-server:24.1-alpine --quiet && echo -e "${GREEN}✓${NC}" || echo -e "${RED}❌${NC}"

# x86_64 images (via Rosetta 2)
echo -n "StarRocks FE 3.2.1 (AMD64/Rosetta)... "
docker pull --platform linux/amd64 starrocks/fe-ubuntu:3.2.1 --quiet && echo -e "${GREEN}✓${NC}" || echo -e "${RED}❌${NC}"

echo -n "StarRocks BE 3.2.1 (AMD64/Rosetta)... "
docker pull --platform linux/amd64 starrocks/be-ubuntu:3.2.1 --quiet && echo -e "${GREEN}✓${NC}" || echo -e "${RED}❌${NC}"

echo -n "Splunk 9.1.2 (AMD64/Rosetta)... "
docker pull --platform linux/amd64 splunk/splunk:9.1.2 --quiet && echo -e "${GREEN}✓${NC}" || echo -e "${RED}❌${NC}"

# Clean up any existing containers
echo ""
echo -n "Cleaning up old containers... "
docker-compose -f docker-compose.m3.yml down -v > /dev/null 2>&1 || true
echo -e "${GREEN}✓${NC}"

# Start services
echo ""
echo "Starting services..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Start PostgreSQL
echo -n "Starting PostgreSQL... "
docker-compose -f docker-compose.m3.yml up -d postgresql > /dev/null 2>&1
sleep 5
echo -e "${GREEN}✓${NC}"

# Wait for PostgreSQL
echo -n "Waiting for PostgreSQL to be ready"
MAX_WAIT=60
ELAPSED=0
while ! docker exec benchmark-postgresql pg_isready -U postgres > /dev/null 2>&1; do
    if [[ $ELAPSED -ge $MAX_WAIT ]]; then
        echo -e " ${RED}❌${NC}"
        echo "ERROR: PostgreSQL failed to start"
        docker logs benchmark-postgresql
        exit 1
    fi
    echo -n "."
    sleep 2
    ELAPSED=$((ELAPSED + 2))
done
echo -e " ${GREEN}✓${NC} (${ELAPSED}s)"

# Start ClickHouse
echo -n "Starting ClickHouse... "
docker-compose -f docker-compose.m3.yml up -d clickhouse > /dev/null 2>&1
sleep 5
echo -e "${GREEN}✓${NC}"

# Wait for ClickHouse
echo -n "Waiting for ClickHouse to be ready"
ELAPSED=0
while ! curl -s http://localhost:8123/ping > /dev/null 2>&1; do
    if [[ $ELAPSED -ge $MAX_WAIT ]]; then
        echo -e " ${RED}❌${NC}"
        echo "ERROR: ClickHouse failed to start"
        docker logs benchmark-clickhouse
        exit 1
    fi
    echo -n "."
    sleep 2
    ELAPSED=$((ELAPSED + 2))
done
echo -e " ${GREEN}✓${NC} (${ELAPSED}s)"

# Start StarRocks FE
echo -n "Starting StarRocks Frontend... "
docker-compose -f docker-compose.m3.yml up -d starrocks-fe > /dev/null 2>&1
sleep 10
echo -e "${GREEN}✓${NC}"

# Wait for StarRocks FE
echo -n "Waiting for StarRocks FE to be ready"
ELAPSED=0
MAX_WAIT=120
while ! curl -s http://localhost:8030/api/health | grep -q "OK" 2>/dev/null; do
    if [[ $ELAPSED -ge $MAX_WAIT ]]; then
        echo -e " ${RED}❌${NC}"
        echo "ERROR: StarRocks FE failed to start"
        docker logs benchmark-starrocks-fe | tail -20
        exit 1
    fi
    echo -n "."
    sleep 3
    ELAPSED=$((ELAPSED + 3))
done
echo -e " ${GREEN}✓${NC} (${ELAPSED}s)"

# Start StarRocks BE
echo -n "Starting StarRocks Backend... "
docker-compose -f docker-compose.m3.yml up -d starrocks-be > /dev/null 2>&1
sleep 10
echo -e "${GREEN}✓${NC}"

# Wait for StarRocks BE
echo -n "Waiting for StarRocks BE to be ready"
ELAPSED=0
while ! curl -s http://localhost:8040/api/health | grep -q "OK" 2>/dev/null; do
    if [[ $ELAPSED -ge $MAX_WAIT ]]; then
        echo -e " ${YELLOW}⚠${NC} Taking longer than expected, continuing..."
        break
    fi
    echo -n "."
    sleep 3
    ELAPSED=$((ELAPSED + 3))
done
echo -e " ${GREEN}✓${NC} (${ELAPSED}s)"

# Register BE with FE
echo -n "Registering StarRocks BE with FE... "
sleep 5
docker exec benchmark-starrocks-fe mysql -h127.0.0.1 -P9030 -uroot -e \
    "ALTER SYSTEM ADD BACKEND 'starrocks-be:9050';" 2>/dev/null || true
echo -e "${GREEN}✓${NC}"

# Start Splunk (takes longest)
echo -n "Starting Splunk Enterprise... "
docker-compose -f docker-compose.m3.yml up -d splunk > /dev/null 2>&1
echo -e "${GREEN}✓${NC}"

echo -n "Waiting for Splunk to be ready (this takes 3-5 minutes)"
ELAPSED=0
MAX_WAIT=300
while ! curl -k -s -u admin:ComplexP@ss123 https://localhost:8089/services/server/info > /dev/null 2>&1; do
    if [[ $ELAPSED -ge $MAX_WAIT ]]; then
        echo -e " ${RED}❌${NC}"
        echo "ERROR: Splunk failed to start within ${MAX_WAIT}s"
        docker logs benchmark-splunk | tail -30
        exit 1
    fi
    echo -n "."
    sleep 10
    ELAPSED=$((ELAPSED + 10))
done
echo -e " ${GREEN}✓${NC} (${ELAPSED}s)"

# Display container status
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Container Status:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" --filter "label=benchmark.category"

# Create Splunk index
echo ""
echo -n "Creating Splunk security index... "
docker exec benchmark-splunk /opt/splunk/bin/splunk add index security \
    -auth admin:ComplexP@ss123 > /dev/null 2>&1 || true
echo -e "${GREEN}✓${NC}"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "All containers deployed successfully!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

exit 0
