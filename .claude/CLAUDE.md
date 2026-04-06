# Splunk DB Connect Benchmark Project

## Project Purpose

A comprehensive benchmarking environment for cybersecurity analytics on Apple Silicon (M3), comparing:
- **Native database formats** (PostgreSQL, ClickHouse, StarRocks)
- **Splunk DB Connect overhead** (proxy layer performance impact)
- **Apache Iceberg multi-engine** (shared data access vs native performance)

Helps organizations make informed decisions about database engine selection, Splunk DB Connect usage, and Apache Iceberg trade-offs for security log analysis.

## Current Status

**Completion**: ~100% - All infrastructure, benchmarks, and modernization complete

**What's Complete**:
- ✅ Docker orchestration for 9 services (added Polaris, DuckDB embedded)
- ✅ Complete schemas and 9 benchmark scripts
- ✅ DuckDB embedded engine benchmarks (P1)
- ✅ Concurrent query + scale testing (P2)
- ✅ OCSF v1.8 format testing (P3)
- ✅ Polaris REST catalog integration (P4)
- ✅ Engine version updates to 2026 stable (P5)
- ✅ Setup scripts and documentation
- ✅ Security fixes (credentials in .env)

## Architecture Quick Reference

### Multi-Database Stack (9 Services + DuckDB Embedded)

| Service | Version | Port | Architecture | Status | Purpose |
|---------|---------|------|--------------|--------|---------|
| PostgreSQL | 16 | 5432 | ARM64 | Optimal | Relational baseline |
| ClickHouse | 26.3 | 8123 | ARM64 | Optimal | Columnar OLAP |
| StarRocks | 3.5 LTS | 9030 | ARM64 | Optimal | MPP analytics |
| Splunk | 9.3 | 8000 | Rosetta 2 | 30-40% overhead | SIEM + DB Connect |
| Trino | 480 | 8080 | ARM64 | Optimal | Iceberg coordinator |
| MinIO | latest | 9000 | ARM64 | Optimal | S3 storage |
| Hive Metastore | 3.1.3 | 9083 | Rosetta 2 | Acceptable | Iceberg catalog |
| Apache Polaris | 1.3.0 | 8181 | ARM64 | Optimal | Iceberg REST catalog |
| DuckDB | 1.5+ | embedded | ARM64 | Optimal | In-process analytics |

### Performance Expectations (M3 Mac)

- **ClickHouse**: 10-20ms simple, 30-50ms aggregation
- **DuckDB (native)**: 1-5ms simple, 5-20ms aggregation (embedded, zero network)
- **PostgreSQL**: 50-100ms simple, 150-300ms aggregation
- **StarRocks**: 40-60ms simple, 80-150ms aggregation (now ARM64 native)
- **Splunk Overhead**: +100-200ms
- **Iceberg**: 4-25x slower than native (trade-off for flexibility)

## Quality Standards

### All Code

- **Shell Scripts**: Use `set -euo pipefail`, colored output (GREEN/RED/YELLOW), log to `logs/`
- **Python**: Type hints, docstrings, PEP 8, error handling, connection pooling
- **Docker**: Resource limits for M3, health checks, ARM64/Rosetta documented
- **Security**: All credentials in `.env` (gitignored), never hardcoded

### Before Making Changes

1. Run `/validate` - Check environment health
2. Run `/status` - Verify Docker services
3. After changes: Restart affected services, run benchmarks, validate within 20% of baseline

## Common Tasks

### Environment Management
```bash
# Start
docker-compose -f docker-compose.m3.yml up -d

# Stop
docker-compose -f docker-compose.m3.yml down

# Clean up (WARNING: Deletes all data)
/cleanup

# Check status
/status

# Validate environment
/validate
```

### Run Benchmarks
```bash
cd benchmarks && ./run_all.sh   # All benchmarks (~45 min)
/benchmark                       # Via skill

# Individual benchmarks (no services required for 05, 07, 08):
python3 benchmarks/05_duckdb_benchmark.py --skip-parquet --skip-iceberg
python3 benchmarks/06_concurrent_benchmark.py --engines duckdb
python3 benchmarks/07_scale_benchmark.py --engines duckdb --scales 100000 1000000
python3 benchmarks/08_ocsf_benchmark.py
python3 benchmarks/09_catalog_benchmark.py  # requires Trino + Polaris
```

### Troubleshooting
```bash
# Service logs
docker logs benchmark-<service> --tail 100 --follow

# Resource usage
docker stats

# Restart service
docker-compose -f docker-compose.m3.yml restart <service>
```

## Git Workflow

### Commit Format (Conventional Commits)

```
<type>: <description>

<optional body>
```

**Types**: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `perf`

**Examples**:
```
feat: Add query for failed login aggregation by source IP
fix: Correct ClickHouse memory limit for M3 Pro
docs: Update Iceberg setup with troubleshooting
perf: Optimize StarRocks partitioning (baseline: 45ms → 32ms)
```

### Before Committing
1. Test affected components
2. Run validation if config changed
3. Update docs if behavior changed
4. Note performance impacts in message

## Key Documentation

- **README.md**: Quick start and user guide
- **ARCHITECTURE.md**: System design and component architecture
- **DECISIONS.md**: Architecture decision records (ADRs)
- **SPECIFICATION.md**: Technical specification
- **IMPLEMENTATION_SUMMARY.md**: Completion status
- **docs/**: Detailed guides (SPLUNK_DBXQUERY_LIMITATIONS.md, ICEBERG_MULTI_ENGINE.md, etc.)

## Resource Requirements

### Memory (M3 Mac)
- **Minimum**: 18GB total, 16GB Docker allocation
- **Recommended**: 24GB total for comfortable operation
- **Per Service**: Limits defined in docker-compose.m3.yml

### Disk Space
- **Minimum**: 100GB free
- **Databases + Logs**: ~60GB after data loading
- **Docker Images**: ~20GB

### Troubleshooting Priority
1. `/status` - Docker service health
2. `docker logs <service>` - Container logs
3. `/validate` - Connectivity tests
4. `df -h` - Disk space
5. `docker stats` - Memory usage
6. Consult `docs/` for specific issues

## Project Structure

```
.
├── .claude/                # Claude Code config, skills, hooks
├── benchmarks/             # Performance benchmarks
├── configs/                # Service configurations
├── docs/                   # Additional documentation
├── scripts/                # Setup and utility scripts
├── specs/                  # SDD specifications
├── sql/                    # Database schemas
├── tests/                  # Validation scripts
├── docker-compose.m3.yml   # Main orchestration
├── .env                    # Credentials (gitignored)
├── .env.example            # Template
├── ARCHITECTURE.md         # System design
├── DECISIONS.md            # ADRs
└── README.md               # User documentation
```

## Success Metrics

Project succeeds when:
- ✅ All 7 services deploy and remain healthy
- ✅ All benchmark scripts execute successfully
- ✅ Performance within 20% of documented baselines
- ✅ Environment runs continuously 24+ hours
- ✅ Setup completes in <2 hours from scratch

## Quick Commands (Skills)

- `/validate` - Comprehensive environment validation
- `/status` - Quick Docker service status check
- `/benchmark` - Run all performance benchmarks
- `/cleanup` - Clean up environment (WARNING: Deletes data)

## Security Notes

- **Credentials**: All in `.env` file (gitignored)
- **Development Only**: Self-signed certs, no authentication on some services
- **Sample Data**: Synthetic data, no PII, safe for testing

## Important Reminders

- **ARM64 Performance**: PostgreSQL, ClickHouse, Trino run natively (optimal)
- **Rosetta Overhead**: Splunk (~30-40%), StarRocks (~15-20%) - acceptable for development
- **Memory Management**: Stop Splunk/Trino when not testing if resources tight
- **Baseline Values**: Document any intentional performance changes in commit messages

## Related Resources

- SPECIFICATION.md: Complete technical details
- ARCHITECTURE.md: Component design and data flow
- DECISIONS.md: Why specific technologies chosen
- docs/: Troubleshooting guides and advanced topics
