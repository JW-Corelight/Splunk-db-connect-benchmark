# Splunk DB Connect Setup Guide

## Overview

This guide walks through installing and configuring Splunk DB Connect to measure the overhead added by Splunk's dbxquery proxy layer when querying PostgreSQL and ClickHouse.

## Prerequisites

- ✅ Splunk Enterprise running (container: `benchmark-splunk`)
- ✅ PostgreSQL running with 400K records
- ✅ ClickHouse running with 400K records
- ⚠️ Splunk DB Connect app (needs installation)

---

## Step 1: Install Splunk DB Connect App

### Option A: Via Splunk Web UI (Recommended)

1. **Access Splunk Web**:
   ```
   https://localhost:8000
   Username: admin
   Password: changeme
   ```

2. **Navigate to Apps**:
   - Click "Apps" in the top-left corner
   - Click "Find More Apps"

3. **Search for DB Connect**:
   - Search: "Splunk DB Connect"
   - Click "Install"
   - Login with your Splunk.com credentials (or create free account)

4. **Restart Splunk**:
   ```bash
   docker restart benchmark-splunk
   ```

### Option B: Via Command Line

```bash
# Download DB Connect from Splunkbase (requires login)
# Or manually download and copy to container

docker cp splunk-db-connect_*.tar.gz benchmark-splunk:/opt/splunk/etc/apps/
docker exec benchmark-splunk tar -xzf /opt/splunk/etc/apps/splunk-db-connect_*.tar.gz -C /opt/splunk/etc/apps/
docker restart benchmark-splunk
```

---

## Step 2: Download JDBC Drivers

### PostgreSQL JDBC Driver

```bash
# Download PostgreSQL JDBC driver
curl -L -o postgresql-42.7.1.jar https://jdbc.postgresql.org/download/postgresql-42.7.1.jar

# Copy to Splunk DB Connect drivers directory
docker cp postgresql-42.7.1.jar benchmark-splunk:/opt/splunk/etc/apps/splunk_app_db_connect/drivers/
```

### ClickHouse JDBC Driver

```bash
# Download ClickHouse JDBC driver
curl -L -o clickhouse-jdbc-0.6.0-patch5-all.jar \
  https://github.com/ClickHouse/clickhouse-java/releases/download/v0.6.0-patch5/clickhouse-jdbc-0.6.0-patch5-all.jar

# Copy to Splunk DB Connect drivers directory
docker cp clickhouse-jdbc-0.6.0-patch5-all.jar benchmark-splunk:/opt/splunk/etc/apps/splunk_app_db_connect/drivers/
```

### Restart Splunk

```bash
docker restart benchmark-splunk
```

---

## Step 3: Configure Database Connections

### Access DB Connect Settings

1. Go to **Splunk Web** → **Apps** → **DB Connect**
2. Click **Configuration** → **Databases** → **Identities**

### Create Identity for PostgreSQL

1. Click **New Identity**
2. Fill in:
   - **Identity Name**: `postgres_identity`
   - **Username**: `postgres`
   - **Password**: `postgres123`
3. Click **Save**

### Create Identity for ClickHouse

1. Click **New Identity**
2. Fill in:
   - **Identity Name**: `clickhouse_identity`
   - **Username**: `default`
   - **Password**: (leave empty)
3. Click **Save**

### Create PostgreSQL Connection

1. Go to **Configuration** → **Databases** → **Connections**
2. Click **New Connection**
3. Fill in:
   - **Connection Name**: `postgresql_conn`
   - **Identity**: `postgres_identity`
   - **Connection Type**: `PostgreSQL`
   - **JDBC URL**: `jdbc:postgresql://benchmark-postgresql:5432/cybersecurity`
   - **Readonly**: Yes (recommended for benchmarks)
4. Click **Save**
5. Click **Test Connection** to verify

### Create ClickHouse Connection

1. Click **New Connection**
2. Fill in:
   - **Connection Name**: `clickhouse_conn`
   - **Identity**: `clickhouse_identity`
   - **Connection Type**: `Generic` (or `MySQL` if available - ClickHouse supports MySQL protocol)
   - **JDBC URL**: `jdbc:clickhouse://benchmark-clickhouse:8123/cybersecurity`
   - **Readonly**: Yes
3. Click **Save**
4. Click **Test Connection** to verify

---

## Step 4: Test Connections via Search

### Test PostgreSQL Connection

```spl
| dbxquery connection="postgresql_conn" query="SELECT COUNT(*) as count FROM security_logs"
```

**Expected Output**: Should return `count = 400000`

### Test ClickHouse Connection

```spl
| dbxquery connection="clickhouse_conn" query="SELECT COUNT(*) as count FROM security_logs"
```

**Expected Output**: Should return `count = 400000`

### Test Query with Results

```spl
| dbxquery connection="postgresql_conn" query="
  SELECT event_type, COUNT(*) as count
  FROM security_logs
  GROUP BY event_type
  ORDER BY count DESC
  LIMIT 5
"
```

---

## Step 5: Run Overhead Benchmark

Now that DB Connect is configured, run the overhead benchmark:

```bash
cd /Users/jeremy.wiley/Git\ projects/Splunk-db-connect-benchmark/benchmarks
python3 02_splunk_dbxquery_overhead.py
```

This will:
1. Run the same queries directly against PostgreSQL and ClickHouse
2. Run the same queries via Splunk's `| dbxquery` command
3. Calculate the overhead (latency difference)
4. Generate a report showing:
   - Direct query latency
   - Splunk dbxquery latency
   - Overhead in milliseconds and percentage

---

## Troubleshooting

### Connection Test Fails

**Issue**: "Connection refused" or "Unable to connect"

**Solution**: Verify network connectivity
```bash
# From Splunk container, test PostgreSQL
docker exec benchmark-splunk ping -c 3 benchmark-postgresql

# From Splunk container, test ClickHouse
docker exec benchmark-splunk ping -c 3 benchmark-clickhouse
```

### JDBC Driver Not Found

**Issue**: "No suitable driver found for jdbc:postgresql://"

**Solution**: Verify driver files exist
```bash
docker exec benchmark-splunk ls -lh /opt/splunk/etc/apps/splunk_app_db_connect/drivers/

# Should see postgresql-*.jar and clickhouse-*.jar
```

### Authentication Failed

**Issue**: "Authentication failed for user postgres"

**Solution**: Verify credentials match docker-compose.m3.yml
```bash
# PostgreSQL credentials
grep -A 5 "benchmark-postgresql:" docker-compose.m3.yml

# Test connection directly
docker exec benchmark-postgresql psql -U postgres -d cybersecurity -c "SELECT 1"
```

### dbxquery Command Not Found

**Issue**: "Unknown search command 'dbxquery'"

**Solution**: Ensure DB Connect app is installed and Splunk restarted
```bash
docker exec benchmark-splunk ls /opt/splunk/etc/apps/ | grep db_connect
docker restart benchmark-splunk
```

---

## Expected Results

Once configured, you should be able to:

1. ✅ Query PostgreSQL via `| dbxquery connection="postgresql_conn"`
2. ✅ Query ClickHouse via `| dbxquery connection="clickhouse_conn"`
3. ✅ Run benchmark: `python3 02_splunk_dbxquery_overhead.py`
4. ✅ See overhead comparison (expected: +100-300ms added by Splunk proxy)

---

## Performance Expectations

**Expected Splunk DB Connect Overhead**:
- **Connection pooling**: ~10-50ms (initial overhead)
- **Query translation**: ~5-20ms (SPL → SQL)
- **Result serialization**: ~20-100ms (depending on row count)
- **Network/Docker overhead**: ~10-50ms (container networking)

**Total Expected Overhead**: **100-300ms per query**

This is the trade-off for:
- ✅ Unified query interface (SPL)
- ✅ Access control and auditing
- ✅ Result caching
- ✅ Multi-database federation

---

## Next Steps

After completing this setup:

1. Run the overhead benchmark
2. Analyze results in `benchmarks/results/splunk_overhead_*.json`
3. Compare direct vs. proxied query performance
4. Document findings in `BENCHMARK_RESULTS.md`

---

**Last Updated**: December 9, 2024
**Status**: Ready for configuration
