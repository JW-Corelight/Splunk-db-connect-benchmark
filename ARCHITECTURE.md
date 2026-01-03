# Architecture Documentation
**Splunk DB Connect Benchmark Environment**

## System Overview

This project implements a multi-database benchmarking environment designed to evaluate performance characteristics of different database engines and access patterns for cybersecurity analytics workloads.

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Benchmark Environment                         │
│                         (Docker Compose)                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ┌──────────────────┐    ┌──────────────────┐                      │
│  │   PostgreSQL     │    │   ClickHouse     │                      │
│  │   (ARM64)        │    │   (ARM64)        │                      │
│  │   Port: 5432     │    │   Port: 8123     │                      │
│  └────────┬─────────┘    └────────┬─────────┘                      │
│           │                       │                                  │
│           └───────────┬───────────┘                                  │
│                       │                                              │
│           ┌───────────▼─────────────┐                               │
│           │  Splunk Enterprise      │                               │
│           │  + DB Connect (Rosetta) │                               │
│           │  Port: 8000, 8089       │                               │
│           └───────────┬─────────────┘                               │
│                       │                                              │
│  ┌────────────────────┼────────────────────┐                       │
│  │                    │                    │                        │
│  │  ┌─────────────────▼───────┐  ┌───────▼──────────┐             │
│  │  │   StarRocks (Rosetta)   │  │   Trino (ARM64)  │             │
│  │  │   Port: 9030            │  │   Port: 8080     │             │
│  │  └──────────┬──────────────┘  └────────┬─────────┘             │
│  │             │                           │                        │
│  │             └──────────┬────────────────┘                        │
│  │                        │                                         │
│  │             ┌──────────▼──────────┐                             │
│  │             │  Hive Metastore     │                             │
│  │             │  (Iceberg Catalog)  │                             │
│  │             │  Port: 9083         │                             │
│  │             └──────────┬──────────┘                             │
│  │                        │                                         │
│  │             ┌──────────▼──────────┐                             │
│  │             │   MinIO (ARM64)     │                             │
│  │             │   S3 Storage        │                             │
│  │             │   Port: 9000        │                             │
│  │             └─────────────────────┘                             │
│  │                                                                  │
│  └──────────────── Iceberg Layer ────────────────────────────────┘│
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘
```

## Component Architecture

### 1. Native Database Layer

**Purpose**: Direct database access for baseline performance measurement

**Components**:
- **PostgreSQL 16** (ARM64 native)
  - Traditional RDBMS baseline
  - Row-oriented storage
  - ACID compliance
  - Port: 5432

- **ClickHouse 24.1** (ARM64 native)
  - Columnar OLAP engine
  - MergeTree storage engine
  - Optimized for analytical queries
  - Port: 8123 (HTTP), 9000 (Native)

- **StarRocks 3.2** (Rosetta 2)
  - MPP analytics engine
  - Vectorized execution
  - Compatible with MySQL protocol
  - Port: 9030 (MySQL), 8030 (HTTP)

### 2. Splunk DB Connect Proxy Layer

**Purpose**: Measure overhead of Splunk's database proxy layer

**Architecture**:
- Splunk Enterprise runs on Rosetta 2
- DB Connect app provides `dbxquery` SPL command
- JDBC-based connectivity to PostgreSQL and ClickHouse
- Adds network hop and serialization overhead

**Data Flow**:
```
SPL Query → DB Connect → JDBC Driver → Database → Results → Splunk → User
```

**Expected Overhead**: +100-200ms per query (documented in benchmarks)

### 3. Apache Iceberg Multi-Engine Layer

**Purpose**: Enable multi-engine access to shared data with schema evolution

**Components**:

**Storage Layer**:
- **MinIO**: S3-compatible object storage (ARM64)
- Stores Parquet files and Iceberg metadata
- Bucket: `warehouse/`

**Metadata Layer**:
- **Hive Metastore**: Iceberg table catalog (Rosetta 2)
- Tracks table schemas, partitions, snapshots
- Enables time travel queries

**Query Engines**:
- **Trino**: Distributed SQL query engine (ARM64)
  - Coordinator + worker architecture
  - Accesses Iceberg tables via Iceberg catalog

- **ClickHouse**: Via Iceberg table function
  - Can query Iceberg tables stored in S3

- **StarRocks**: Via external Iceberg catalog
  - Reads Parquet files from MinIO

**Trade-offs**:
- ✅ Multi-engine access (no lock-in)
- ✅ Schema evolution without rewriting data
- ✅ Time travel and versioning
- ❌ 4-25x slower than native formats
- ❌ Additional infrastructure complexity

## Data Flow

### Benchmark 1: Native Baseline
```
Benchmark Script → PostgreSQL/ClickHouse → Results
```
- Direct psycopg2/clickhouse-driver connections
- Minimal overhead
- Fastest path

### Benchmark 2: Splunk DB Connect Overhead
```
Benchmark Script → Splunk REST API → DB Connect → JDBC → Database → Results
```
- Adds Splunk proxy layer
- Network serialization overhead
- Typical: +100-200ms

### Benchmark 3: Iceberg Multi-Engine
```
Benchmark Script → Trino/ClickHouse/StarRocks → Hive Metastore → MinIO (Parquet) → Results
```
- Reads from shared Parquet files
- S3 API overhead
- Columnar file scanning
- Typical: 4-25x slower than native

## Network Architecture

**Docker Network**: `benchmark-network` (bridge)

**Service Discovery**: Docker DNS
- `benchmark-postgresql` → PostgreSQL
- `benchmark-clickhouse` → ClickHouse
- `benchmark-starrocks-fe` → StarRocks Frontend
- `benchmark-splunk` → Splunk Enterprise
- `benchmark-trino` → Trino Coordinator
- `minio` → MinIO S3
- `hive-metastore` → Hive Metastore

**External Access**:
- PostgreSQL: `localhost:5432`
- ClickHouse: `localhost:8123` (HTTP), `localhost:9000` (native)
- StarRocks: `localhost:9030` (MySQL), `localhost:8030` (HTTP)
- Splunk: `https://localhost:8000` (web), `https://localhost:8089` (API)
- Trino: `http://localhost:8080`
- MinIO: `http://localhost:9000` (API), `http://localhost:9001` (console)

## Resource Allocation

**Memory Limits** (M3 Mac):
- PostgreSQL: 2GB
- ClickHouse: 4GB
- StarRocks FE: 2GB
- StarRocks BE: 4GB
- Splunk: 4GB
- Trino: 2GB
- MinIO: 512MB
- Hive Metastore: 1GB

**Total**: ~18GB required (24GB recommended for host OS)

**CPU Allocation**: Shared across all services (6-8 cores recommended)

## Data Model

### Schema Design

**Primary Table**: `security_logs`
- `id`: Unique event identifier
- `timestamp`: Event time (indexed)
- `event_type`: Category of security event
- `severity`: Critical/High/Medium/Low
- `source_ip`, `dest_ip`: Network addresses
- `user_name`, `hostname`: Identity information
- `details`: JSON metadata

**Secondary Table**: `network_logs`
- Connection-level network events
- Foreign key to `security_logs`

**Aggregations**:
- Materialized views for common queries
- Pre-aggregated tables in ClickHouse/StarRocks

### Partitioning Strategy

**PostgreSQL**: Date-based partitioning (monthly)

**ClickHouse**:
- Partition key: `toYYYYMM(timestamp)`
- Order by: `(timestamp, event_type, severity)`

**StarRocks**:
- Partition key: Date range on `timestamp`
- Bucket key: `user_name`

**Iceberg**:
- Hidden partition: Day transformation on `timestamp`
- Automatic partition evolution

## Technology Decisions

See **DECISIONS.md** for rationale behind key architectural choices:
- Why PostgreSQL as baseline
- Why ClickHouse over other columnar databases
- Why Apache Iceberg for multi-engine layer
- Docker Compose vs Kubernetes
- ARM64 vs Rosetta 2 trade-offs

## Performance Characteristics

### Expected Query Performance (M3 Mac)

| Query Type | PostgreSQL | ClickHouse | Iceberg (Trino) |
|------------|------------|------------|-----------------|
| Simple SELECT | 50-100ms | 10-20ms | 200-400ms |
| Aggregation | 150-300ms | 30-50ms | 800-1500ms |
| JOIN | 300-600ms | 50-100ms | 1500-3000ms |
| Full scan | 2-5s | 500-1000ms | 5-15s |

**Splunk DB Connect**: Add +100-200ms to PostgreSQL/ClickHouse times

### Scalability Limits

**Current Configuration**:
- Dataset: 300K security events + 20K network logs
- Time range: 30-60 days
- Users: ~1000 unique
- Hosts: ~100 unique

**Scaling Considerations**:
- 1M+ events: Increase PostgreSQL/StarRocks memory
- 10M+ events: Consider data retention policies
- Real-time ingestion: Add Kafka/streaming layer (future)

## Security Architecture

**Credential Management**:
- All credentials in `.env` file (gitignored)
- No hardcoded passwords in configs/scripts
- `.env.example` provides template

**Network Security**:
- All services isolated in Docker network
- External access via published ports only
- Splunk uses self-signed certificates (development)

**Data Security**:
- No PII in sample data
- Synthetic usernames/IPs
- Safe for development/testing

## Monitoring and Observability

**Health Checks**:
- All services have Docker health checks
- `validate_environment.py` tests connectivity
- Session hook displays service status

**Logs**:
- Docker logs for each service
- Benchmark results in `results/`
- Application logs in `logs/`

**Metrics**:
- Docker stats for resource usage
- Query timing in benchmark scripts
- MinIO metrics via console

## Future Architecture Enhancements

**Potential Additions**:
1. Grafana + Prometheus for monitoring
2. Kafka for real-time event streaming
3. Jupyter notebooks for analysis
4. Superset for visualization
5. Additional databases (TimescaleDB, DuckDB)
6. Kubernetes deployment option

**Not Planned** (out of scope):
- Production-scale data (10M+ events)
- High availability / replication
- Security hardening for production
- Multi-node clusters
