#!/bin/bash
# ================================================
# Phase 2: Docker Configuration
# ================================================
# Purpose: Configure Docker Desktop for optimal M3 performance
# ================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo "🐳 Phase 2: Docker Configuration"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Detect memory size and set Docker resources
MEMORY_GB=$(sysctl hw.memsize | awk '{print int($2/1024/1024/1024)}')

if [[ "$MEMORY_GB" -ge 24 ]]; then
    DOCKER_MEMORY=18432
    DOCKER_CPUS=8
    echo "Detected 24GB+ Mac - allocating 18GB to Docker"
elif [[ "$MEMORY_GB" -ge 16 ]]; then
    DOCKER_MEMORY=12288
    DOCKER_CPUS=6
    echo "Detected 16GB Mac - allocating 12GB to Docker"
else
    echo -e "${RED}❌ Insufficient RAM. 16GB minimum required.${NC}"
    exit 1
fi

# Backup existing Docker settings
DOCKER_SETTINGS_DIR="$HOME/Library/Group Containers/group.com.docker"
SETTINGS_FILE="$DOCKER_SETTINGS_DIR/settings.json"

if [[ -f "$SETTINGS_FILE" ]]; then
    echo -n "Backing up existing Docker settings... "
    cp "$SETTINGS_FILE" "${SETTINGS_FILE}.backup.$(date +%Y%m%d_%H%M%S)"
    echo -e "${GREEN}✓${NC}"
fi

# Create optimized Docker settings
echo -n "Configuring Docker Desktop... "
cat > "$SETTINGS_FILE" << EOF
{
  "memoryMiB": ${DOCKER_MEMORY},
  "cpus": ${DOCKER_CPUS},
  "diskSizeMiB": 81920,
  "swapMiB": 2048,
  "filesharingDirectories": [
    "/Users",
    "/tmp",
    "/var/folders"
  ],
  "experimentalFeatures": {
    "rosetta": true,
    "virtualizationFramework": true,
    "useVirtioFS": true
  },
  "useContainerdSnapshotter": true,
  "useGrpcfuse": false
}
EOF
echo -e "${GREEN}✓${NC}"

# Restart Docker Desktop
echo -n "Restarting Docker Desktop... "
osascript -e 'quit app "Docker"' 2>/dev/null || true
sleep 5
open -a Docker

# Wait for Docker to be ready
echo -n "Waiting for Docker to start"
MAX_WAIT=60
ELAPSED=0
while ! docker info >/dev/null 2>&1; do
    if [[ $ELAPSED -ge $MAX_WAIT ]]; then
        echo -e " ${RED}❌${NC}"
        echo "ERROR: Docker failed to start within ${MAX_WAIT} seconds"
        exit 1
    fi
    echo -n "."
    sleep 2
    ELAPSED=$((ELAPSED + 2))
done
echo -e " ${GREEN}✓${NC}"

# Verify Docker configuration
echo ""
echo "Docker Configuration:"
docker info --format 'Memory:        {{.MemTotal}}
CPUs:          {{.NCPU}}
OS:            {{.OperatingSystem}}
Storage:       {{.Driver}}
Server:        {{.ServerVersion}}'

# Enable experimental features check
echo ""
echo -n "Verifying Rosetta 2 support... "
if docker info 2>&1 | grep -q "rosetta"; then
    echo -e "${GREEN}✓${NC} Enabled"
else
    echo -e "${YELLOW}⚠${NC}  Not detected (may still work)"
fi

# Test Docker with ARM64 image
echo -n "Testing ARM64 image pull... "
if docker pull --platform linux/arm64 alpine:latest > /dev/null 2>&1; then
    echo -e "${GREEN}✓${NC}"
    docker rmi alpine:latest > /dev/null 2>&1
else
    echo -e "${RED}❌${NC}"
    echo "ERROR: Failed to pull ARM64 image"
    exit 1
fi

# Test Docker with AMD64 image (Rosetta)
echo -n "Testing AMD64 image pull (Rosetta)... "
if docker pull --platform linux/amd64 alpine:latest > /dev/null 2>&1; then
    echo -e "${GREEN}✓${NC}"
    docker rmi alpine:latest > /dev/null 2>&1
else
    echo -e "${RED}❌${NC}"
    echo "ERROR: Failed to pull AMD64 image (Rosetta issue)"
    exit 1
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Docker Desktop configured successfully"
echo "  Memory:  ${DOCKER_MEMORY}MB"
echo "  CPUs:    ${DOCKER_CPUS}"
echo "  Disk:    80GB"
echo "  Rosetta: Enabled"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

exit 0
