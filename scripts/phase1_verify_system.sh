#!/bin/bash
# ================================================
# Phase 1: System Verification
# ================================================
# Purpose: Verify M3 hardware and software requirements
# ================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "🔍 Phase 1: System Verification"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 1.1 Verify Architecture
echo -n "Checking architecture... "
ARCH=$(uname -m)
if [[ "$ARCH" != "arm64" ]]; then
    echo -e "${RED}❌${NC}"
    echo "ERROR: ARM64 (Apple Silicon) required. Detected: $ARCH"
    exit 1
fi
echo -e "${GREEN}✓${NC} $ARCH"

# 1.2 Verify macOS Version
echo -n "Checking macOS version... "
MACOS_VERSION=$(sw_vers -productVersion)
MACOS_MAJOR=$(echo "$MACOS_VERSION" | cut -d. -f1)
if [[ "$MACOS_MAJOR" -lt 14 ]]; then
    echo -e "${RED}❌${NC}"
    echo "ERROR: macOS 14.0+ required. Current: $MACOS_VERSION"
    exit 1
fi
echo -e "${GREEN}✓${NC} $MACOS_VERSION"

# 1.3 Check Available Memory
echo -n "Checking memory... "
MEMORY_GB=$(sysctl hw.memsize | awk '{print int($2/1024/1024/1024)}')
if [[ "$MEMORY_GB" -lt 16 ]]; then
    echo -e "${RED}❌${NC}"
    echo "ERROR: 16GB+ RAM required. Detected: ${MEMORY_GB}GB"
    exit 1
elif [[ "$MEMORY_GB" -lt 24 ]]; then
    echo -e "${YELLOW}⚠${NC}  ${MEMORY_GB}GB (24GB recommended)"
fi
echo -e "${GREEN}✓${NC} ${MEMORY_GB}GB"

# 1.4 Check Disk Space
echo -n "Checking disk space... "
DISK_FREE_GB=$(df -g / | awk 'NR==2 {print $4}')
if [[ "$DISK_FREE_GB" -lt 80 ]]; then
    echo -e "${RED}❌${NC}"
    echo "ERROR: 80GB+ free space required. Available: ${DISK_FREE_GB}GB"
    exit 1
fi
echo -e "${GREEN}✓${NC} ${DISK_FREE_GB}GB available"

# 1.5 Check CPU Cores
echo -n "Checking CPU cores... "
CPU_CORES=$(sysctl -n hw.ncpu)
if [[ "$CPU_CORES" -lt 8 ]]; then
    echo -e "${RED}❌${NC}"
    echo "ERROR: 8+ cores required. Detected: ${CPU_CORES}"
    exit 1
fi
echo -e "${GREEN}✓${NC} ${CPU_CORES} cores"

# 1.6 Verify Docker Desktop
echo -n "Checking Docker Desktop... "
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌${NC}"
    echo "ERROR: Docker Desktop not installed"
    echo "Please install from: https://www.docker.com/products/docker-desktop/"
    exit 1
fi
DOCKER_VERSION=$(docker --version | awk '{print $3}' | tr -d ',')
echo -e "${GREEN}✓${NC} $DOCKER_VERSION"

# 1.7 Verify Docker is Running
echo -n "Checking Docker status... "
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}❌${NC}"
    echo "ERROR: Docker Desktop is not running"
    echo "Please start Docker Desktop and try again"
    exit 1
fi
echo -e "${GREEN}✓${NC} Running"

# 1.8 Check Rosetta 2
echo -n "Checking Rosetta 2... "
if ! pkgutil --pkg-info=com.apple.pkg.RosettaUpdateAuto > /dev/null 2>&1; then
    echo -e "${YELLOW}⚠${NC}  Not installed - installing now..."
    softwareupdate --install-rosetta --agree-to-license
    if [[ $? -eq 0 ]]; then
        echo -e "${GREEN}✓${NC} Installed"
    else
        echo -e "${RED}❌${NC}"
        echo "ERROR: Failed to install Rosetta 2"
        exit 1
    fi
else
    echo -e "${GREEN}✓${NC} Installed"
fi

# 1.9 Verify Python 3
echo -n "Checking Python... "
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌${NC}"
    echo "ERROR: Python 3 not found"
    echo "Install with: brew install python@3.11"
    exit 1
fi
PYTHON_VERSION=$(python3 --version | awk '{print $2}')
echo -e "${GREEN}✓${NC} $PYTHON_VERSION"

# 1.10 Check Python Dependencies
echo -n "Checking Python dependencies... "
MISSING_DEPS=()
python3 -c "import psycopg2" 2>/dev/null || MISSING_DEPS+=("psycopg2-binary")
python3 -c "import requests" 2>/dev/null || MISSING_DEPS+=("requests")

if [[ ${#MISSING_DEPS[@]} -gt 0 ]]; then
    echo -e "${YELLOW}⚠${NC}  Installing: ${MISSING_DEPS[*]}"
    pip3 install "${MISSING_DEPS[@]}" --quiet
    echo -e "${GREEN}✓${NC} Installed"
else
    echo -e "${GREEN}✓${NC} All present"
fi

# 1.11 Display System Summary
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "System Summary:"
echo "  Architecture:  $ARCH"
echo "  macOS:         $MACOS_VERSION"
echo "  Memory:        ${MEMORY_GB}GB"
echo "  Disk Free:     ${DISK_FREE_GB}GB"
echo "  CPU Cores:     ${CPU_CORES}"
echo "  Docker:        $DOCKER_VERSION"
echo "  Python:        $PYTHON_VERSION"
echo "  Rosetta 2:     Installed"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

exit 0
