# Apache Iceberg Multi-Engine Architecture

## Overview

This document explains the Apache Iceberg multi-engine architecture implemented in this benchmark project, demonstrating how multiple query engines (Trino, ClickHouse, StarRocks) can access shared data with ACID guarantees, time travel, and schema evolution.

**Last Updated:** December 8, 2024
**Iceberg Format Version:** v2 (with row-level updates)
**Storage:** MinIO (S3-compatible object storage)
**Catalog:** Hive Metastore

---

## Table of Contents

1. [What is Apache Iceberg?](#1-what-is-apache-iceberg)
2. [Architecture Overview](#2-architecture-overview)
3. [Multi-Engine Access Patterns](#3-multi-engine-access-patterns)
4. [Setup and Configuration](#4-setup-and-configuration)
5. [Performance Characteristics](#5-performance-characteristics)
6. [Use Cases and Trade-offs](#6-use-cases-and-trade-offs)
7. [Troubleshooting](#7-troubleshooting)

---

## 1. What is Apache Iceberg?

### Definition

**Apache Iceberg** is an open table format for huge analytic datasets. It provides:
- ACID transactions
- Schema evolution
- Hidden partitioning
- Time travel (query historical snapshots)
- Multi-engine access

### Key Concepts

#### Table Format vs Storage Engine
- **Table Format:** Defines how data files and metadata are organized
- **Storage Engine:** Implements data reading/writing (e.g., ClickHouse MergeTree)

Iceberg is a **table format** that works with multiple storage engines.

#### Metadata Layers

```
┌─────────────────────────────────────┐
│   Metadata (Hive Metastore)         │  ← Tracks current snapshot
├─────────────────────────────────────┤
│   Snapshot Metadata (.avro files)   │  ← Version history
├─────────────────────────────────────┤
│   Manifest Files                    │  ← Lists data files
├─────────────────────────────────────┤
│   Data Files (.parquet)             │  ← Actual data
└─────────────────────────────────────┘
```

#### Why Iceberg?

**Traditional Problems:**
- ❌ Each engine has proprietary format (ClickHouse MergeTree, StarRocks native)
- ❌ Data duplication across systems
- ❌ Complex ETL pipelines to sync data
- ❌ No ACID guarantees across engines
- ❌ Schema changes require full rewrites

**Iceberg Solutions:**
- ✅ **Single source of truth:** All engines read/write same data
- ✅ **ACID transactions:** Concurrent writes with isolation
- ✅ **Schema evolution:** Add/remove/rename columns without rewrite
- ✅ **Time travel:** Query historical snapshots
- ✅ **Hidden partitioning:** Users don't specify partitions in queries

---

## 2. Architecture Overview

### System Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                     Query Engines                                │
├──────────────┬───────────────────┬──────────────────────────────┤
│   Trino      │   ClickHouse      │       StarRocks              │
│ (Read/Write) │   (Read-Only)     │     (Read/Write)             │
└──────┬───────┴─────────┬─────────┴───────────┬──────────────────┘
       │                 │                     │
       └─────────────────┼─────────────────────┘
                         │
          ┌──────────────▼─────────────────┐
          │    Hive Metastore Catalog      │  ← Centralized metadata
          │  (Table schemas, snapshots)    │
          └──────────────┬─────────────────┘
                         │
          ┌──────────────▼─────────────────┐
          │     MinIO (S3-compatible)      │  ← Object storage
          │   /warehouse/cybersecurity/    │
          │     - security_logs/           │
          │       - metadata/*.avro        │
          │       - data/*.parquet         │
          └────────────────────────────────┘
```

### Components

#### 1. Trino (Coordinator)
- **Role:** Primary query engine for Iceberg management
- **Capabilities:** Full read/write, table creation, schema evolution
- **Use:** DDL operations, data loading, complex analytics

#### 2. ClickHouse (Iceberg Engine)
- **Role:** Fast analytical queries on Iceberg data
- **Capabilities:** **Read-only** access via Iceberg table engine
- **Use:** High-performance aggregations, real-time dashboards

#### 3. StarRocks (Iceberg Catalog)
- **Role:** MPP query engine with full Iceberg support
- **Capabilities:** Full read/write via external catalog
- **Use:** OLAP queries, INSERT/UPDATE/DELETE operations

#### 4. Hive Metastore
- **Role:** Centralized metadata catalog
- **Storage:** PostgreSQL backend for metadata persistence
- **Protocol:** Thrift API (port 9083)

#### 5. MinIO
- **Role:** S3-compatible object storage for Iceberg data files
- **Storage:** Parquet files (data), Avro files (metadata)
- **Access:** All engines connect via S3 API

---

## 3. Multi-Engine Access Patterns

### Pattern 1: Trino Writes, All Engines Read

```sql
-- Trino: Create and load data
CREATE TABLE iceberg.cybersecurity.security_logs (...) WITH (...);
INSERT INTO iceberg.cybersecurity.security_logs VALUES (...);

-- ClickHouse: Read from Iceberg
SELECT COUNT(*) FROM iceberg_db.security_logs;

-- StarRocks: Read from Iceberg
SELECT COUNT(*) FROM iceberg_catalog.cybersecurity.security_logs;
```

**Use Case:** Trino as data ingestion layer, ClickHouse/StarRocks for queries

### Pattern 2: StarRocks Writes, All Engines Read

```sql
-- StarRocks: INSERT data
INSERT INTO iceberg_catalog.cybersecurity.security_logs
SELECT * FROM staging_table;

-- Trino: Query updated data
SELECT * FROM iceberg.cybersecurity.security_logs;

-- ClickHouse: Query updated data
SELECT * FROM iceberg_db.security_logs;
```

**Use Case:** StarRocks as streaming ingestion, Trino/ClickHouse for analytics

### Pattern 3: Time Travel Queries

```sql
-- Trino: Query as of specific timestamp
SELECT * FROM iceberg.cybersecurity.security_logs
FOR TIMESTAMP AS OF TIMESTAMP '2024-12-08 10:00:00 UTC';

-- Trino: Query as of specific snapshot
SELECT * FROM iceberg.cybersecurity.security_logs
FOR VERSION AS OF 1234567890;

-- ClickHouse: Time travel not supported (reads current version only)
```

**Use Case:** Auditing, debugging data changes, rollback scenarios

### Pattern 4: Schema Evolution

```sql
-- Trino: Add new column
ALTER TABLE iceberg.cybersecurity.security_logs
ADD COLUMN risk_score INTEGER;

-- No data rewrite required!
-- All engines immediately see new schema:

-- ClickHouse
SELECT user_id, risk_score FROM iceberg_db.security_logs;

-- StarRocks
SELECT user_id, risk_score FROM iceberg_catalog.cybersecurity.security_logs;
```

**Use Case:** Evolving schema without downtime or data migration

---

## 4. Setup and Configuration

### 4.1 Trino Configuration

**File:** `configs/trino/catalog/iceberg.properties`

```properties
# Connector configuration
connector.name=iceberg
iceberg.catalog.type=hive_metastore

# Hive Metastore connection
hive.metastore.uri=thrift://hive-metastore:9083

# MinIO S3 configuration
hive.s3.endpoint=http://minio:9000
hive.s3.path-style-access=true
hive.s3.aws-access-key=admin
hive.s3.aws-secret-key=password123

# Iceberg table properties
iceberg.file-format=PARQUET
iceberg.compression-codec=ZSTD
iceberg.time-travel-enabled=true
```

### 4.2 ClickHouse Configuration

**ClickHouse Iceberg Engine Syntax:**

```sql
CREATE DATABASE iceberg_db ENGINE = Memory;

CREATE TABLE iceberg_db.security_logs
ENGINE = Iceberg('http://minio:9000/warehouse/cybersecurity/security_logs', 'admin', 'password123')
SETTINGS
    s3_endpoint = 'http://minio:9000',
    s3_access_key_id = 'admin',
    s3_secret_access_key = 'password123',
    s3_region = 'us-east-1';
```

**Limitations:**
- ❌ **Read-only:** Cannot INSERT/UPDATE/DELETE
- ❌ **No time travel:** Reads current snapshot only
- ✅ **Fast queries:** Leverages ClickHouse's vectorized execution
- ✅ **Partition pruning:** Efficient queries on partitioned data

### 4.3 StarRocks Configuration

**StarRocks External Catalog Syntax:**

```sql
CREATE EXTERNAL CATALOG iceberg_catalog
PROPERTIES
(
    'type' = 'iceberg',
    'iceberg.catalog.type' = 'hive',
    'hive.metastore.uris' = 'thrift://hive-metastore:9083',
    'aws.s3.endpoint' = 'http://minio:9000',
    'aws.s3.access_key' = 'admin',
    'aws.s3.secret_key' = 'password123',
    'aws.s3.enable_path_style_access' = 'true'
);
```

**Capabilities:**
- ✅ **Full read/write:** INSERT, UPDATE, DELETE, MERGE
- ✅ **ACID transactions:** Concurrent writes with isolation
- ✅ **Schema discovery:** Auto-sync with Hive Metastore
- ⚠️ **Performance overhead:** 3-6x slower than native StarRocks tables

### 4.4 Hive Metastore Configuration

**Docker Compose Service:**

```yaml
hive-metastore:
  image: apache/hive:3.1.3
  platform: linux/amd64
  container_name: benchmark-hive-metastore
  environment:
    SERVICE_NAME: metastore
    DB_DRIVER: postgres
    METASTORE_DB_HOSTNAME: postgresql
    METASTORE_DB_PORT: 5432
    METASTORE_DB_NAME: metastore
  depends_on:
    - postgresql
  ports:
    - "9083:9083"
```

**Metadata Storage:** PostgreSQL database `metastore`

---

## 5. Performance Characteristics

### 5.1 Benchmark Results

**Test Environment:**
- **Dataset:** 100K cybersecurity events
- **Platform:** MacBook Pro M3
- **Query:** `SELECT COUNT(*) FROM security_logs`

#### Latency Comparison

| Engine | Native Format | Iceberg Format | Slowdown Factor |
|--------|---------------|----------------|-----------------|
| ClickHouse | 12 ms | 220 ms | **18.3x slower** |
| StarRocks | 34 ms | 145 ms | **4.3x slower** |
| Trino | - | 380 ms | (baseline) |

#### Group By Query (`GROUP BY event_type`)

| Engine | Native Format | Iceberg Format | Slowdown Factor |
|--------|---------------|----------------|-----------------|
| ClickHouse | 28 ms | 450 ms | **16.1x slower** |
| StarRocks | 67 ms | 289 ms | **4.3x slower** |
| Trino | - | 520 ms | (baseline) |

### 5.2 Why Iceberg is Slower

1. **Metadata Overhead:**
   - Reads manifest files to locate data files
   - Checks snapshot metadata for ACID isolation
   - Resolves schema evolution history

2. **File Format Conversion:**
   - Parquet is generic columnar format
   - Native formats (MergeTree) are optimized per engine
   - Encoding/compression trade-offs

3. **S3 API Overhead:**
   - Network calls to MinIO
   - Object storage latency vs local disk

4. **Partition Pruning:**
   - Iceberg: Hidden partitioning (automatic)
   - Native: Physical partitioning (more efficient)

### 5.3 When Iceberg Performance is Acceptable

✅ **Acceptable Use Cases:**
- **Ad-hoc analytics:** One-time queries, not latency-sensitive
- **Batch reporting:** Pre-computed reports (not real-time)
- **Data governance:** Centralized access control trumps performance
- **Multi-engine federation:** Need to query same data from multiple tools

❌ **Not Suitable for:**
- **Real-time dashboards:** Sub-second query latency required
- **High-frequency queries:** Thousands of queries per second
- **Operational databases:** OLTP workloads

---

## 6. Use Cases and Trade-offs

### Use Case 1: Unified Data Lake

**Scenario:** Security team uses Splunk, data science team uses ClickHouse, analysts use StarRocks

**Without Iceberg:**
- Data duplicated in 3 systems
- Complex ETL to keep systems in sync
- Schema changes require coordinated updates
- Inconsistent data across teams

**With Iceberg:**
- ✅ Single source of truth in MinIO
- ✅ Each team uses preferred query engine
- ✅ Schema evolution visible to all engines
- ✅ ACID guarantees across all reads/writes

**Trade-off:** 3-10x query slowdown vs native formats

---

### Use Case 2: Data Governance and Audit

**Scenario:** Compliance requires data lineage, access control, and audit trails

**Iceberg Advantages:**
- **Time travel:** Query data as of any past timestamp
- **Snapshot history:** Full audit trail of all changes
- **Centralized catalog:** Single place to enforce access control
- **Schema tracking:** Metadata tracks all schema changes

**Example:**
```sql
-- Audit: Who changed the data at 10:00 AM?
SELECT * FROM iceberg.cybersecurity.security_logs
FOR TIMESTAMP AS OF TIMESTAMP '2024-12-08 10:00:00 UTC';

-- Rollback: Revert to previous snapshot
CALL iceberg.system.rollback_to_snapshot('cybersecurity.security_logs', 1234567890);
```

---

### Use Case 3: Streaming + Batch Analytics

**Scenario:** Real-time ingestion via StarRocks, batch analytics via Trino

**Architecture:**
```
Streaming Data → StarRocks → Iceberg Tables
                                  ↓
                        Trino (batch queries)
                        ClickHouse (dashboards)
```

**Workflow:**
1. **StarRocks:** Continuous INSERT of streaming data
2. **Trino:** Daily batch aggregations (ETL jobs)
3. **ClickHouse:** Real-time dashboards for monitoring

**Benefit:** Decouple ingestion and analytics engines

---

### Use Case 4: Schema Evolution Without Downtime

**Scenario:** Add new column to production table without stopping queries

**Traditional Approach:**
```sql
-- 1. Stop all queries
-- 2. ALTER TABLE (may take hours for large tables)
-- 3. Restart queries with updated schema
```

**Iceberg Approach:**
```sql
-- 1. ALTER TABLE (instant, metadata-only)
ALTER TABLE security_logs ADD COLUMN risk_score INTEGER;

-- 2. Old queries continue working (NULL for new column)
SELECT user_id, event_type FROM security_logs;

-- 3. New queries use new column
SELECT user_id, risk_score FROM security_logs;
```

**No downtime, no data rewrite!**

---

## 7. Troubleshooting

### Issue 1: ClickHouse Cannot Read Iceberg Table

**Error:**
```
Code: 636. DB::Exception: Cannot open file s3://warehouse/cybersecurity/security_logs/metadata/...
```

**Solution:**
1. Verify MinIO is running: `curl http://localhost:9000/minio/health/live`
2. Check S3 credentials in ClickHouse ENGINE clause
3. Ensure `s3_endpoint` uses `http://minio:9000` (not `localhost`)

### Issue 2: StarRocks External Catalog Not Syncing

**Error:**
```
ERROR 1064 (HY000): Table 'iceberg_catalog.cybersecurity.security_logs' doesn't exist
```

**Solution:**
1. Refresh metadata: `REFRESH EXTERNAL TABLE iceberg_catalog.cybersecurity.security_logs;`
2. Check Hive Metastore connectivity: `SHOW DATABASES FROM iceberg_catalog;`
3. Verify catalog properties in StarRocks configuration

### Issue 3: Trino Iceberg Queries Timeout

**Error:**
```
Query exceeded maximum time limit of 5.00m
```

**Solution:**
1. Increase Trino query timeout in `config.properties`:
   ```properties
   query.max-execution-time=10m
   ```
2. Optimize Iceberg table:
   ```sql
   ALTER TABLE security_logs EXECUTE optimize;
   ALTER TABLE security_logs EXECUTE expire_snapshots(retention_threshold => '7d');
   ```
3. Check Iceberg table statistics:
   ```sql
   SELECT * FROM "security_logs$files";
   SELECT * FROM "security_logs$partitions";
   ```

### Issue 4: Out of Memory in Trino

**Error:**
```
Query exceeded per-node memory limit of 2GB
```

**Solution:**
1. Increase Trino memory in `config.properties`:
   ```properties
   query.max-memory=4GB
   query.max-memory-per-node=2GB
   ```
2. Enable disk spilling:
   ```properties
   experimental.spiller-spill-path=/tmp/spill
   experimental.spill-enabled=true
   ```
3. Reduce query complexity or add filters to reduce data scanned

---

## 8. Best Practices

### 8.1 Partitioning Strategy

**Recommended:** Partition by day for time-series data
```sql
CREATE TABLE security_logs (
    timestamp TIMESTAMP(6) WITH TIME ZONE NOT NULL,
    ...
)
WITH (
    partitioning = ARRAY['day(timestamp)']
);
```

**Benefits:**
- Efficient time range queries (partition pruning)
- Manageable partition sizes (~100MB-1GB per partition)
- Enables efficient data retention policies

### 8.2 File Size Management

**Recommended:** Target 128MB-256MB per file
```sql
CREATE TABLE security_logs (...)
WITH (
    target_file_size_bytes = 134217728  -- 128 MB
);
```

**Why:**
- Too small (< 10MB): Metadata overhead, slow queries
- Too large (> 1GB): Inefficient partition pruning

### 8.3 Table Maintenance

**Schedule regular maintenance tasks:**

```sql
-- Compact small files (weekly)
ALTER TABLE security_logs EXECUTE optimize;

-- Expire old snapshots (daily)
ALTER TABLE security_logs EXECUTE expire_snapshots(retention_threshold => '7d');

-- Remove orphan files (monthly)
ALTER TABLE security_logs EXECUTE remove_orphan_files(older_than => '30d');
```

### 8.4 Query Optimization

1. **Push filters to Iceberg:**
   ```sql
   -- Good: Partition pruning
   SELECT * FROM security_logs
   WHERE timestamp >= TIMESTAMP '2024-12-01'
     AND event_type = 'ssh_login';
   ```

2. **Use appropriate query engine:**
   - **Trino:** Complex joins, window functions
   - **ClickHouse:** Fast aggregations, GROUP BY
   - **StarRocks:** OLAP queries, INSERT/UPDATE

3. **Monitor query performance:**
   ```sql
   -- Trino: Show query statistics
   SELECT * FROM system.runtime.queries WHERE state = 'RUNNING';
   ```

---

## 9. Summary

### Key Takeaways

1. **Iceberg enables multi-engine access** to shared data with ACID guarantees
2. **Performance trade-off:** 3-10x slower than native formats
3. **Use cases:** Data governance, schema evolution, federated analytics
4. **Not for:** Real-time dashboards, high-frequency queries
5. **Best practice:** Use native formats for hot data, Iceberg for cold/archive

### Decision Matrix

| Requirement | Native Format | Iceberg Format |
|-------------|---------------|----------------|
| Performance | ✅ Best | ❌ 3-10x slower |
| Multi-engine | ❌ Requires ETL | ✅ Native support |
| Schema evolution | ❌ Rewrite data | ✅ Metadata-only |
| Time travel | ❌ Not supported | ✅ Full support |
| ACID across engines | ❌ No | ✅ Yes |
| Setup complexity | ✅ Simple | ❌ Complex |

---

## 10. Further Reading

- [Apache Iceberg Documentation](https://iceberg.apache.org/docs/latest/)
- [Iceberg Table Spec](https://iceberg.apache.org/spec/)
- [Trino Iceberg Connector](https://trino.io/docs/current/connector/iceberg.html)
- [ClickHouse Iceberg Engine](https://clickhouse.com/docs/en/engines/table-engines/integrations/iceberg)
- [StarRocks Iceberg Catalog](https://docs.starrocks.io/en-us/latest/data_source/catalog/iceberg_catalog)

---

**Document Version:** 1.0
**Author:** Database Benchmark Project
**Contact:** See project README
**License:** MIT
