# Docker Service Status

## Overview
Quickly checks the status of all Docker containers defined in `docker-compose.m3.yml`, providing a high-level view of which services are running, stopped, or unhealthy. This is a fast diagnostic command that helps you understand the current state of your benchmark environment without deep connectivity testing.

## What This Command Does

When you run `/status`, it executes `docker-compose ps` to display:

1. **Container Names**: Identifier for each service (e.g., `benchmark-postgresql`)
2. **Current State**: Running, stopped, restarting, or exited
3. **Health Status**: Healthy, unhealthy, or starting (if health checks configured)
4. **Port Mappings**: Which host ports map to container ports
5. **Uptime**: How long each container has been running

This is a lightweight check that only queries Docker's control plane - it does not test actual database connectivity or functionality.

## When to Use This Command

- **Quick environment check**: See at a glance which services are up
- **After docker-compose up**: Verify containers started successfully
- **Before running benchmarks**: Ensure all required services are running
- **During development**: Check status without waiting for full validation
- **After resource issues**: See which containers may have crashed

## Output Example

```
Name                          State    Health      Ports
─────────────────────────────────────────────────────────────
benchmark-postgresql          Up       healthy     0.0.0.0:5432->5432/tcp
benchmark-clickhouse          Up       healthy     0.0.0.0:8123->8123/tcp
benchmark-starrocks-fe        Up       healthy     0.0.0.0:9030->9030/tcp
benchmark-starrocks-be        Up       healthy
benchmark-splunk              Up       starting    0.0.0.0:8000->8000/tcp
benchmark-trino               Up       healthy     0.0.0.0:8080->8080/tcp
minio                         Up       healthy     0.0.0.0:9000-9001->9000-9001/tcp
hive-metastore                Up                   0.0.0.0:9083->9083/tcp
```

## Understanding Health Status

- **healthy**: Container passes health checks, ready for use
- **starting**: Container running but health checks not yet passing (wait 30-60s)
- **unhealthy**: Health checks failing, service may not be functional
- **no health check**: Container running but no health check configured

**Note**: Some services (like Hive Metastore) don't have health checks defined and won't show health status.

## Common Scenarios

### Scenario 1: All Services Healthy
```
All 7 services running and healthy - ready for benchmarks
```
**Action**: Proceed with `/benchmark` or `/validate`

### Scenario 2: Services Starting
```
5/7 services healthy, 2 starting (Splunk, StarRocks)
```
**Action**: Wait 1-2 minutes, services are initializing. Run `/status` again.

### Scenario 3: Service Stopped
```
benchmark-clickhouse: Exited (code 137)
```
**Action**: Service likely OOM killed. Check Docker memory allocation and restart:
```bash
docker-compose -f docker-compose.m3.yml restart clickhouse
```

### Scenario 4: Service Unhealthy
```
benchmark-postgresql: Up (unhealthy)
```
**Action**: Check logs for errors:
```bash
docker logs benchmark-postgresql --tail 50
```

## Comparison with /validate

| Feature | /status | /validate |
|---------|---------|-----------|
| Speed | ~1 second | ~30-60 seconds |
| Depth | Container state only | Full connectivity tests |
| Network tests | No | Yes |
| Query tests | No | Yes |
| Schema validation | No | Yes |

**Use /status for**: Quick checks during development
**Use /validate for**: Thorough environment verification before benchmarking

## Troubleshooting

**Issue**: "Cannot connect to Docker daemon"
- **Solution**: Start Docker Desktop application
- **Check**: Docker Desktop icon in menu bar (macOS)

**Issue**: "No services configured"
- **Solution**: Ensure you're in the project root directory
- **Check**: `ls docker-compose.m3.yml` should find the file

**Issue**: "Services keep restarting"
- **Solution**: Check resource limits, may be OOM
- **Action**: Increase Docker Desktop memory allocation to 16GB+

## Related Commands

- `/validate` - Comprehensive environment validation with connectivity tests
- `/cleanup` - Stop and remove all containers
- `/benchmark` - Run performance benchmarks (requires all services healthy)

## Technical Details

This command executes:
```bash
docker-compose -f docker-compose.m3.yml ps
```

If services are defined but not started, you'll need to start them first:
```bash
docker-compose -f docker-compose.m3.yml up -d
```
