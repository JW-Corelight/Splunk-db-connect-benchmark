# Cleanup Environment

## Overview
Performs a complete cleanup of the benchmark environment by stopping all Docker containers, removing volumes, deleting temporary data, and freeing disk space. This command is useful when you need to reset the environment to a fresh state or reclaim disk space after testing.

## What This Command Does

When you run `/cleanup`, it executes `scripts/cleanup.sh` which performs these operations:

1. **Stop All Containers**: Gracefully stops all running benchmark services
2. **Remove Containers**: Deletes container instances (preserves images)
3. **Remove Volumes**: Deletes persistent data volumes (PostgreSQL, ClickHouse, Splunk data)
4. **Remove Networks**: Cleans up Docker networks created by compose
5. **Clean Temporary Files**: Removes logs/, results/, and temp files
6. **Report Disk Space**: Shows disk space reclaimed

**Warning**: This operation is **destructive** and will delete all data in the databases. Benchmark results and logs will also be removed unless you back them up first.

## When to Use This Command

- **Before fresh setup**: Start from clean slate
- **After testing complete**: Reclaim disk space (typically 40-60GB)
- **Troubleshooting**: Fix corrupted state or stuck containers
- **Environment reset**: Clear configuration issues
- **Disk space low**: Free up space when Mac storage is full

**Do NOT use** if you need to preserve:
- Benchmark results (back up `results/` first)
- Database data (would need to reload)
- Splunk configuration (would need to reconfigure DB Connect)

## Safety Measures

The cleanup script includes safety prompts:

```
⚠️  WARNING: This will delete all data and containers!
   - All database data will be lost
   - Benchmark results will be removed
   - Splunk configuration will be reset

Do you want to continue? (yes/no):
```

Type `yes` to proceed or `no` to cancel.

To skip the prompt (dangerous!), use:
```bash
bash scripts/cleanup.sh --force
```

## What Gets Deleted

**Docker Resources**:
- Containers: `benchmark-postgresql`, `benchmark-clickhouse`, `benchmark-starrocks-*`, `benchmark-splunk`, `benchmark-trino`, `minio`, `hive-metastore`
- Volumes: `postgres_data`, `clickhouse_data`, `starrocks_data`, `splunk_data`, `minio_data`, `metastore_data`
- Networks: `benchmark-network`

**Local Files**:
- `data/` - Database data directories (~40GB)
- `logs/` - Application and benchmark logs (~500MB)
- `results/` - Benchmark results (~50MB)
- `.env` - **NOT DELETED** (credentials preserved)

**What's Preserved**:
- Docker images (reused for faster restart)
- Source code and scripts
- Configuration files in `configs/`
- SQL schema files in `sql/`
- `.env` file with credentials

## Post-Cleanup Steps

After cleanup, to restore the environment:

1. **Restart Services**:
   ```bash
   docker-compose -f docker-compose.m3.yml up -d
   ```

2. **Wait for Initialization** (~2-3 minutes):
   ```bash
   watch -n 5 docker-compose ps
   ```

3. **Load Schemas**:
   ```bash
   bash scripts/phase3_deploy_containers.sh
   ```

4. **Load Data**:
   ```bash
   python3 scripts/load_zeek_data.py
   ```

5. **Validate**:
   ```bash
   /validate
   ```

Total restoration time: ~30-45 minutes

## Partial Cleanup Options

If you want to clean only specific parts:

**Remove only containers** (preserve volumes):
```bash
docker-compose -f docker-compose.m3.yml down
```

**Remove specific service data**:
```bash
docker volume rm benchmark_postgres_data
docker volume rm benchmark_clickhouse_data
```

**Clean only logs/results**:
```bash
rm -rf logs/ results/
```

**Clean Docker build cache** (additional space):
```bash
docker system prune -a --volumes
```

## Disk Space Reclaimed

Expected space freed:
- **Database volumes**: ~40GB
- **Container layers**: ~5GB (if removing images)
- **Logs and results**: ~500MB
- **Total**: ~45GB

Check space before/after:
```bash
df -h    # Check available disk space
docker system df    # Check Docker disk usage
```

## Common Issues

**Issue**: "Cannot remove container - container is running"
- **Solution**: Script should stop containers first, but if not:
  ```bash
  docker-compose -f docker-compose.m3.yml down --force
  ```

**Issue**: "Permission denied removing files"
- **Solution**: Some Docker volumes need sudo:
  ```bash
  sudo bash scripts/cleanup.sh
  ```

**Issue**: "Want to keep benchmark results"
- **Solution**: Back up first:
  ```bash
  cp -r results/ ~/backup_results/
  /cleanup
  cp -r ~/backup_results/* results/
  ```

**Issue**: "Cleanup incomplete, some volumes remain"
- **Solution**: Manual cleanup:
  ```bash
  docker volume ls | grep benchmark | awk '{print $2}' | xargs docker volume rm
  ```

## Related Commands

- `/status` - Check what's running before cleanup
- `/validate` - Verify environment after restoration

## Technical Details

The cleanup script is located at `scripts/cleanup.sh` and includes:
- Colored output for visibility (red warnings, green success)
- Error handling for missing containers/volumes
- Dry-run mode available with `--dry-run` flag
- Logs cleanup operations to `logs/cleanup_YYYYMMDD.log`

Cleanup is idempotent - safe to run multiple times.

## Exit Codes

- **0**: Cleanup completed successfully
- **1**: User cancelled operation
- **2**: Cleanup failed (partial cleanup may have occurred)
