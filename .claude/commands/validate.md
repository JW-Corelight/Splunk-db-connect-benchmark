# Validate Environment

## Overview
Validates that all database services in the benchmark environment are running, accessible, and properly configured. This command executes the comprehensive validation test script that checks Docker container health, database connectivity, schema presence, and basic query functionality across all seven services.

## What This Command Does

When you run `/validate`, it performs the following checks:

1. **Docker Container Health**: Verifies all containers are running with healthy status
2. **Database Connectivity**: Tests network connections to PostgreSQL, ClickHouse, StarRocks
3. **Service Accessibility**: Checks Splunk, Trino, MinIO, and Hive Metastore endpoints
4. **Schema Validation**: Confirms database schemas and tables exist
5. **Basic Query Tests**: Executes simple SELECT queries to verify data access

The validation script is located at `tests/validate_environment.py` and provides colored output indicating success (green) or failure (red) for each check.

## When to Use This Command

- **After initial setup**: Verify all services deployed correctly
- **Before running benchmarks**: Ensure environment is healthy
- **After system reboot**: Confirm services restarted properly
- **During troubleshooting**: Identify which services have issues
- **After configuration changes**: Verify changes didn't break connectivity

## Prerequisites

- Docker Desktop must be running
- Services deployed via `docker-compose -f docker-compose.m3.yml up -d`
- Python 3.8+ installed on host machine
- Required Python packages: `psycopg2-binary`, `clickhouse-driver`, `requests`

## Output Format

The validation script outputs:
```
✅ PostgreSQL: Connection successful, schema valid
✅ ClickHouse: Connection successful, 300K events found
✅ StarRocks: Connection successful, tables accessible
⚠️  Splunk: Service running but DB Connect not configured
✅ Trino: Connection successful, catalogs loaded
✅ MinIO: API accessible, bucket 'warehouse' exists
✅ Hive Metastore: Thrift service responding

Summary: 6/7 services healthy (1 warning)
```

## Common Issues and Solutions

**Issue**: "Connection refused to PostgreSQL"
- **Solution**: Wait 30 seconds after `docker-compose up`, PostgreSQL initialization takes time
- **Check**: `docker logs benchmark-postgresql` for startup completion

**Issue**: "ClickHouse schema not found"
- **Solution**: Run `sql/clickhouse_schema.sql` to create tables
- **Command**: `docker exec benchmark-clickhouse clickhouse-client --multiquery < sql/clickhouse_schema.sql`

**Issue**: "Splunk API returns 401 Unauthorized"
- **Solution**: Check `SPLUNK_ADMIN_PASSWORD` in `.env` file matches configured password
- **Verify**: Login at https://localhost:8000 with admin credentials

**Issue**: "All services failing"
- **Solution**: Check Docker Desktop has sufficient resources (12GB+ memory, 6+ CPUs)
- **Check**: Docker Desktop → Settings → Resources

**Issue**: "MinIO bucket not found"
- **Solution**: Create bucket manually or run Iceberg setup script
- **Command**: `docker exec minio mc mb /data/warehouse`

## Related Commands

- `/status` - Quick check of Docker service status (faster, less thorough)
- `/cleanup` - Clean up environment if validation finds corrupted state
- `/benchmark` - Run benchmarks after successful validation

## Technical Details

The validation script uses:
- **psycopg2**: Direct PostgreSQL connection
- **clickhouse_driver**: Native ClickHouse protocol
- **requests**: HTTP/REST API calls for Splunk, MinIO
- **socket**: TCP connectivity tests for StarRocks, Trino

Health check timeout: 10 seconds per service
Total validation time: ~30-60 seconds

## Exit Codes

- **0**: All services validated successfully
- **1**: One or more services failed validation
- **2**: Critical error (Docker not running, missing dependencies)
