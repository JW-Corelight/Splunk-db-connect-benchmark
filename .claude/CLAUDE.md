# Splunk DB Connect Benchmark Project

## Project Purpose

A comprehensive benchmarking environment for cybersecurity analytics, comparing **native database formats**, **Splunk DB Connect overhead**, and **Apache Iceberg multi-engine architecture** on Apple Silicon (M3).

This project helps organizations make informed decisions about:
- Database engine selection for security log analysis
- Performance impact of Splunk DB Connect proxy layer
- Trade-offs of Apache Iceberg for multi-engine access vs. native format performance

## Current Phase

**Status**: Active Development (~85% complete)

**What's Complete**:
- ✅ Docker Compose orchestration for 7 services (PostgreSQL, ClickHouse, StarRocks, Splunk, Trino, MinIO, Hive Metastore)
- ✅ Complete schemas for all databases
- ✅ Benchmark scripts for native, dbxquery overhead, and Iceberg performance
- ✅ Setup and configuration scripts
- ✅ Comprehensive documentation

**What Remains**:
- ⚠️ Data loading script (outlined in IMPLEMENTATION_SUMMARY.md)
- ⚠️ Results reporting automation
- ⚠️ Some troubleshooting documentation

## Architecture Overview

### Multi-Database Stack

| Service | Purpose | Port | Architecture | Status |
|---------|---------|------|--------------|--------|
| PostgreSQL 16 | Relational baseline | 5432 | ARM64 native | Optimal |
| ClickHouse 24.1 | Columnar OLAP + Iceberg | 8123 | ARM64 native | Optimal |
| StarRocks 3.2 | MPP analytics + Iceberg | 9030 | Rosetta 2 | 15-20% overhead |
| Splunk Enterprise | SIEM + DB Connect | 8000 | Rosetta 2 | 30-40% overhead |
| Trino | Iceberg coordinator | 8080 | ARM64 native | Optimal |
| MinIO | S3-compatible storage | 9000 | ARM64 native | Optimal |
| Hive Metastore | Iceberg catalog | 9083 | Rosetta 2 | Acceptable |

### Key Architecture Patterns

1. **Native Performance Baseline**: Direct queries to databases in their native formats (PostgreSQL, ClickHouse MergeTree, StarRocks)
2. **Splunk DB Connect Proxy**: Same queries routed through Splunk's dbxquery command (adds ~100-200ms overhead)
3. **Apache Iceberg Multi-Engine**: Shared Iceberg tables queried by multiple engines (4-25x slower than native, but enables federation)

## Quality Standards

### Shell Scripts

**Requirements**:
- Always use `set -euo pipefail` at the top
- Provide clear, colored output (GREEN for success, RED for errors, YELLOW for warnings)
- Log to `logs/` directory with timestamps
- Include descriptive headers with purpose, platform, version
- Validate prerequisites before proceeding
- Provide helpful error messages with remediation steps

**Example**:
```bash
#!/bin/bash
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

error() {
    echo -e "${RED}[ERROR] $1${NC}"
    exit 1
}
```

### Python Scripts

**Requirements**:
- Follow PEP 8 style guide
- Use type hints for function parameters and returns
- Include docstrings for modules, classes, and functions
- Handle errors gracefully with try/except blocks
- Use connection pooling for database connections
- Log performance metrics (execution time, row counts)

**Example**:
```python
def benchmark_query(conn, query: str, iterations: int = 5) -> Dict[str, float]:
    """
    Execute a query multiple times and return timing statistics.

    Args:
        conn: Database connection object
        query: SQL query string
        iterations: Number of times to execute (default: 5)

    Returns:
        Dict with min, max, avg, median execution times in milliseconds
    """
```

### Docker Compose

**Requirements**:
- Set explicit resource limits (memory, CPU) for M3 compatibility
- Include health checks for all services
- Document ARM64 vs Rosetta 2 architecture in comments
- Use named volumes for data persistence
- Configure networks properly (separate backend network)
- Include restart policies

**ARM64/Rosetta Notes**:
- PostgreSQL, ClickHouse, Trino, MinIO: ARM64 native (optimal)
- StarRocks, Splunk, Hive Metastore: Rosetta 2 (acceptable overhead)
- Document any performance implications in comments

## Testing and Validation

### Before Making Changes

1. **Environment Health Check**:
   ```bash
   python3 tests/validate_environment.py
   ```
   Verifies all services are running and accessible.

2. **Check Docker Services**:
   ```bash
   docker-compose -f docker-compose.m3.yml ps
   ```
   All services should show "healthy" status.

### After Making Changes

1. **Restart Affected Services**:
   ```bash
   docker-compose -f docker-compose.m3.yml restart <service>
   ```

2. **Run Benchmarks to Validate**:
   ```bash
   cd benchmarks
   ./run_all.sh
   ```

3. **Validate Performance**:
   - Results should be within 20% of documented baseline values
   - Any significant deviation requires investigation
   - Update documentation if intentional performance changes

### Benchmark Expectations (M3 Platform)

| Database | Simple Query | Aggregation | Notes |
|----------|--------------|-------------|-------|
| ClickHouse | 10-20ms | 30-50ms | ARM64 native, optimal |
| PostgreSQL | 50-100ms | 150-300ms | ARM64 native, expected |
| StarRocks | 40-60ms | 80-150ms | Rosetta 2, ~15% overhead |

**Splunk DB Connect Overhead**: Consistent +100-200ms added latency

**Iceberg Performance**: 4-25x slower than native (trade-off for multi-engine access)

## Git Workflow

### Branch Strategy

- **main**: Stable, tested configurations
- **feature/***: New features or benchmarks
- **fix/***: Bug fixes or configuration corrections
- **docs/***: Documentation updates

### Commit Message Format

Follow Conventional Commits:

```
<type>: <description>

<optional body>

<optional footer>
```

**Types**:
- `feat`: New feature or benchmark query
- `fix`: Bug fix or configuration correction
- `docs`: Documentation updates
- `refactor`: Code refactoring without behavior change
- `test`: Adding or updating tests/validation
- `chore`: Maintenance (dependencies, cleanup)
- `perf`: Performance improvements

**Examples**:
```
feat: Add query for failed login aggregation by source IP

fix: Correct ClickHouse memory limit for M3 Pro

docs: Update Iceberg setup instructions with troubleshooting steps

perf: Optimize StarRocks table partitioning for time-based queries
```

### Before Committing

1. Test affected components
2. Run validation if configuration changed
3. Update documentation if behavior changed
4. Note any performance impacts in commit message

### Performance-Impacting Changes

If your change affects benchmark performance, include in commit message:
```
perf: Increase ClickHouse max_threads from 4 to 8

Improves complex aggregation performance by ~30% on M3 Pro.
Baseline updated: 45ms → 32ms for GROUP BY queries.
```

## Project Structure Reference

```
.
├── .claude/                     # Claude Code configuration
│   ├── CLAUDE.md               # This file - project context
│   ├── settings.json           # Project-wide settings
│   ├── settings.local.json     # User-specific permissions
│   ├── hooks/                  # Session hooks
│   └── commands/               # Slash commands
├── benchmarks/                 # Performance benchmarks
│   ├── 01_native_baseline.py
│   ├── 02_splunk_dbxquery_overhead.py
│   ├── 03_iceberg_multi_engine.py
│   └── run_all.sh
├── configs/                    # Service configurations
├── docs/                       # Additional documentation
├── scripts/                    # Setup and utility scripts
├── sql/                        # Database schemas
├── tests/                      # Validation scripts
├── docker-compose.m3.yml       # Main orchestration file
├── README.md                   # User-facing documentation
├── SPECIFICATION.md            # Technical specification
└── IMPLEMENTATION_SUMMARY.md   # Current completion status
```

## Common Tasks

### Start Environment
```bash
docker-compose -f docker-compose.m3.yml up -d
```

### Stop Environment
```bash
docker-compose -f docker-compose.m3.yml down
```

### Clean Up Everything
```bash
bash scripts/cleanup.sh
```

### Load Data
```bash
bash scripts/phase4_load_data.sh  # Note: Not yet implemented
```

### Run All Benchmarks
```bash
cd benchmarks && ./run_all.sh
```

### Check Service Logs
```bash
docker logs benchmark-<service-name> --tail 100 --follow
```

## Key Considerations

### Memory Management (M3)

- **Total Required**: 18GB minimum, 24GB recommended
- **Docker Desktop**: Allocate at least 16GB
- **Per Service**: Limits defined in docker-compose.m3.yml
- If experiencing OOM: Stop Splunk/Trino when not actively testing

### Disk Space

- **Minimum**: 100GB free
- **Databases + Logs**: ~60GB after data loading
- **Docker Images**: ~20GB
- **Working Space**: ~20GB buffer

### Performance Baseline Values

Keep these documented baseline values in mind when validating changes:
- ClickHouse: 10-20ms simple, 30-50ms aggregation
- PostgreSQL: 50-100ms simple, 150-300ms aggregation
- StarRocks: 40-60ms simple, 80-150ms aggregation
- Iceberg overhead: 4-20x slower than native

### Troubleshooting Priority

1. Check Docker service health: `docker-compose ps`
2. Check container logs: `docker logs <service>`
3. Verify connectivity: `python3 tests/validate_environment.py`
4. Check disk space: `df -h`
5. Check memory: `docker stats`
6. Consult `docs/` directory for specific issues

## Success Metrics

The project achieves its goals when:
- ✅ All 7 services deploy and remain healthy
- ✅ All benchmark scripts execute successfully
- ✅ Performance results are within 20% of documented baselines
- ✅ Environment can run continuously for 24+ hours
- ✅ Setup completes in under 2 hours from scratch

## Related Documentation

- **README.md**: Quick start and user guide
- **SPECIFICATION.md**: Detailed technical specification
- **IMPLEMENTATION_SUMMARY.md**: Current completion status
- **docs/SPLUNK_DBXQUERY_LIMITATIONS.md**: Splunk DB Connect analysis
- **docs/ICEBERG_MULTI_ENGINE.md**: Iceberg architecture guide
- **docs/SPLUNK_ANALYTICS_QUERIES.md**: Analytics query examples
