# Database Benchmark: Multi-Engine Analytics with Apache Iceberg

[![Platform](https://img.shields.io/badge/platform-macOS_14+-blue.svg)](https://www.apple.com/macos/)
[![Architecture](https://img.shields.io/badge/architecture-ARM64-green.svg)](https://developer.apple.com/documentation/apple-silicon)
[![Docker](https://img.shields.io/badge/docker-24.0+-blue.svg)](https://www.docker.com/products/docker-desktop/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A comprehensive benchmarking environment for cybersecurity analytics, featuring **native database formats**, **Splunk DB Connect overhead testing**, and **Apache Iceberg multi-engine architecture**. Designed for Apple Silicon (M3/M3 Pro/M3 Max) with AWS deployment options for fair production comparisons.

---

## 🎯 Purpose

This project benchmarks three key architectural patterns for cybersecurity log analysis:

### 1. **Native Performance Baseline**
Compare raw query performance across database engines on their native formats:
- **PostgreSQL 16** - Traditional relational (ARM64 native)
- **ClickHouse 24.1** - Columnar OLAP with NEON SIMD (ARM64 native)
- **StarRocks 3.2** - MPP analytics (Rosetta 2)

### 2. **Splunk DB Connect Overhead**
Measure performance impact when querying databases **via Splunk's dbxquery** command:
- Direct query: Database → Application (baseline)
- Proxy query: Database → Splunk → Application (measure overhead)
- Expected overhead: **100-200ms added latency**

### 3. **Apache Iceberg Multi-Engine**
Test open lakehouse pattern where multiple engines query shared data:
- **Trino** - Create and manage Iceberg tables (full read/write)
- **ClickHouse** - Query Iceberg tables (read-only, ~20x slower than native)
- **StarRocks** - Query and modify Iceberg tables (read/write, ~4x slower)
- Trade-off: **Flexibility vs Performance**

---

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                          Query Engines                              │
├────────────┬────────────┬────────────┬────────────┬─────────────────┤
│ PostgreSQL │ ClickHouse │ StarRocks  │   Trino    │     Splunk      │
│  (Native)  │  (Native)  │  (Native)  │ (Iceberg)  │  (DB Connect)   │
└──────┬─────┴─────┬──────┴──────┬─────┴──────┬─────┴─────────┬───────┘
       │           │             │            │               │
       │           └─────────────┼────────────┘               │
       │                         │                            │
       │           ┌─────────────▼──────────────┐             │
       │           │   Hive Metastore Catalog   │             │
       │           │ (Iceberg metadata: schemas,│             │
       │           │  snapshots, partitions)    │             │
       │           └─────────────┬──────────────┘             │
       │                         │                            │
       │           ┌─────────────▼──────────────┐             │
       │           │  MinIO (S3-compatible)     │             │
       │           │  /warehouse/cybersecurity/ │             │
       │           │    - Parquet data files    │             │
       │           │    - Avro metadata files   │             │
       │           └────────────────────────────┘             │
       │                                                      │
       └──────────────────────────────────────────────────────┘
                   Native Table Storage + Splunk DB Connect
```

### Key Components

| Component | Role | Port | Architecture |
|-----------|------|------|--------------|
| **PostgreSQL** | Relational database | 5432 | ARM64 native |
| **ClickHouse** | Columnar OLAP + Iceberg engine | 8123 | ARM64 native |
| **StarRocks** | MPP analytics + Iceberg catalog | 9030 | Rosetta 2 |
| **Splunk** | SIEM + DB Connect proxy | 8000 | Rosetta 2 |
| **Trino** | Federated SQL + Iceberg coordinator | 8080 | ARM64 native |
| **MinIO** | S3-compatible object storage | 9000/9001 | ARM64 native |
| **Hive Metastore** | Iceberg catalog backend | 9083 | Rosetta 2 |

---

## 🚀 Quick Start

### Prerequisites

- **Hardware:** MacBook Pro M3/M3 Pro/M3 Max
- **Memory:** 24GB recommended (18GB minimum)
- **Storage:** 150GB free space
- **macOS:** 14.0 Sonoma or later
- **Docker Desktop:** 24.0+ with Rosetta 2 enabled
- **Python:** 3.10+ with pip

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/splunk-db-connect-benchmark.git
cd splunk-db-connect-benchmark

# Copy environment template
cp .env.example .env

# Start all services
docker-compose -f docker-compose.m3.yml up -d

# Wait for all services to be healthy (5-10 minutes)
docker-compose -f docker-compose.m3.yml ps
```

### Initialize Data and Iceberg Tables

```bash
# Step 1: Load data into native databases (PostgreSQL, ClickHouse, StarRocks)
bash scripts/phase4_load_data.sh

# Step 2: Initialize MinIO and create Iceberg tables
bash scripts/setup_iceberg.sh

# Step 3: Configure ClickHouse Iceberg engine
bash scripts/configure_clickhouse_iceberg.sh

# Step 4: Configure StarRocks Iceberg catalog
bash scripts/configure_starrocks_iceberg.sh

# Step 5: Set up Splunk DB Connect (requires manual DB Connect app installation)
bash scripts/setup_splunk_dbconnect.sh
```

### Run Benchmarks

```bash
# Install Python dependencies
pip3 install psycopg2-binary clickhouse-connect pymysql

# Run all 3 benchmarks
cd benchmarks
./run_all.sh

# Or run individually:
python3 01_native_baseline.py          # Native performance baseline
python3 02_splunk_dbxquery_overhead.py # Splunk proxy overhead
python3 03_iceberg_multi_engine.py     # Iceberg multi-engine performance

# View results
ls -lh results/
```

---

## 📊 Benchmark Suite

### Test 1: Native Performance Baseline

**Purpose:** Establish baseline query performance on native database formats

**Queries:**
- Count all records
- Aggregate by event type (GROUP BY + ORDER BY)
- Filter failed login events (WHERE + HAVING)
- Time range aggregation (last 7 days)
- Top data transfer events (ORDER BY + LIMIT)

**Expected Results:**
| Database | Simple Query | Complex Aggregation |
|----------|--------------|---------------------|
| ClickHouse | 10-20 ms | 30-50 ms |
| PostgreSQL | 50-100 ms | 150-300 ms |
| StarRocks | 30-50 ms | 70-120 ms |

**Script:** `benchmarks/01_native_baseline.py`

---

### Test 2: Splunk DB Connect Overhead

**Purpose:** Measure latency added by Splunk's dbxquery proxy layer

**Method:**
1. Query database directly (baseline)
2. Query same database via Splunk dbxquery
3. Calculate overhead: `splunk_latency - direct_latency`

**Expected Overhead:**
| Database | Direct Query | via dbxquery | Overhead |
|----------|--------------|--------------|----------|
| PostgreSQL | 50-100 ms | 150-300 ms | **+100-200 ms** |
| ClickHouse | 10-20 ms | 110-220 ms | **+100-200 ms** |
| StarRocks | 30-50 ms | 130-250 ms | **+100-200 ms** |

**Key Finding:** Splunk dbxquery adds **consistent 100-200ms overhead** regardless of database speed.

**Script:** `benchmarks/02_splunk_dbxquery_overhead.py`

**Documentation:** [docs/SPLUNK_DBXQUERY_LIMITATIONS.md](docs/SPLUNK_DBXQUERY_LIMITATIONS.md)

---

### Test 3: Iceberg Multi-Engine Performance

**Purpose:** Test Apache Iceberg table format with multiple query engines

**Architecture:**
- **Shared Data:** Iceberg tables stored in MinIO (Parquet format)
- **Metadata:** Hive Metastore catalog (tracks schemas, snapshots)
- **Engines:** Trino (read/write), ClickHouse (read-only), StarRocks (read/write)

**Comparison:** Native format vs Iceberg format for same query

**Expected Results:**
| Engine | Native Format | Iceberg Format | Slowdown |
|--------|---------------|----------------|----------|
| ClickHouse | 10-20 ms | 200-500 ms | **20-25x slower** |
| StarRocks | 30-50 ms | 120-200 ms | **4-6x slower** |

**Trade-off:**
- ✅ **Benefit:** Multi-engine access, ACID transactions, schema evolution, time travel
- ❌ **Cost:** 4-20x slower query performance

**Script:** `benchmarks/03_iceberg_multi_engine.py`

**Documentation:** [docs/ICEBERG_MULTI_ENGINE.md](docs/ICEBERG_MULTI_ENGINE.md)

---

## 📁 Project Structure

```
splunk-db-connect-benchmark/
├── README.md                        # This file
├── docker-compose.m3.yml            # Complete M3 deployment
├── .env.example                     # Environment variables
│
├── configs/                         # Database configurations
│   ├── postgresql/                  # PostgreSQL configs
│   ├── clickhouse/                  # ClickHouse configs
│   ├── starrocks/                   # StarRocks FE/BE configs
│   ├── splunk/                      # Splunk configs
│   └── trino/                       # Trino configs (NEW)
│       ├── config.properties        # Trino coordinator settings
│       ├── jvm.config               # JVM tuning for M3
│       ├── node.properties          # Node identification
│       ├── log.properties           # Logging configuration
│       └── catalog/
│           └── iceberg.properties   # Iceberg catalog connector
│
├── sql/                             # Schema definitions
│   ├── postgresql_schema.sql        # PostgreSQL tables
│   ├── clickhouse_schema.sql        # ClickHouse tables
│   ├── starrocks_schema.sql         # StarRocks tables
│   └── iceberg_schema.sql           # Iceberg tables (NEW)
│
├── scripts/                         # Setup and utility scripts
│   ├── setup_all.sh                 # Master setup script
│   ├── setup_iceberg.sh             # Initialize Iceberg (NEW)
│   ├── configure_clickhouse_iceberg.sh  # ClickHouse Iceberg engine (NEW)
│   ├── configure_starrocks_iceberg.sh   # StarRocks Iceberg catalog (NEW)
│   ├── setup_splunk_dbconnect.sh    # Splunk DB Connect (NEW)
│   ├── phase1_verify_system.sh      # System verification
│   ├── phase2_configure_docker.sh   # Docker configuration
│   ├── phase3_deploy_containers.sh  # Container deployment
│   ├── phase4_load_data.sh          # Data loading
│   └── cleanup.sh                   # Environment cleanup
│
├── benchmarks/                      # Benchmark scripts (NEW)
│   ├── 01_native_baseline.py        # Native performance baseline
│   ├── 02_splunk_dbxquery_overhead.py  # Splunk proxy overhead
│   ├── 03_iceberg_multi_engine.py   # Iceberg multi-engine
│   ├── run_all.sh                   # Execute all benchmarks
│   └── results/                     # Benchmark results (JSON)
│
├── docs/                            # Documentation
│   ├── SPLUNK_DBXQUERY_LIMITATIONS.md  # Splunk dbxquery analysis (NEW)
│   ├── ICEBERG_MULTI_ENGINE.md      # Iceberg architecture guide (NEW)
│   ├── TROUBLESHOOTING.md           # Common issues
│   └── ARCHITECTURE.md              # System architecture
│
└── data/                            # Persistent data (gitignored)
    ├── postgresql/                  # PostgreSQL data
    ├── clickhouse/                  # ClickHouse data
    ├── starrocks-fe/                # StarRocks frontend
    ├── starrocks-be/                # StarRocks backend
    ├── splunk/                      # Splunk data
    ├── minio/                       # MinIO object storage (NEW)
    └── hive-metastore/              # Hive Metastore metadata (NEW)
```

---

## 🎮 Using the Environment

### Access Services

| Service | Endpoint | Credentials | Purpose |
|---------|----------|-------------|---------|
| **PostgreSQL** | `localhost:5432` | postgres / postgres123 | Relational database |
| **ClickHouse HTTP** | `http://localhost:8123` | default / (none) | Columnar OLAP |
| **ClickHouse Native** | `localhost:9000` | default / (none) | Native protocol |
| **StarRocks FE** | `http://localhost:8030` | root / (none) | Web UI |
| **StarRocks MySQL** | `localhost:9030` | root / (none) | Query interface |
| **Splunk Web** | `http://localhost:8000` | admin / changeme | SIEM UI |
| **Splunk API** | `https://localhost:8089` | admin / changeme | Management API |
| **Trino Web** | `http://localhost:8080` | (none) | Query UI |
| **MinIO Console** | `http://localhost:9001` | admin / password123 | Object storage UI |
| **MinIO API** | `http://localhost:9000` | admin / password123 | S3-compatible API |

### Query Examples

#### PostgreSQL (Native)
```bash
docker exec -it benchmark-postgres psql -U postgres -d cybersecurity -c \
  "SELECT event_type, COUNT(*) FROM security_logs GROUP BY event_type ORDER BY COUNT(*) DESC LIMIT 10;"
```

#### ClickHouse (Native MergeTree)
```bash
curl 'http://localhost:8123/' --data-binary \
  "SELECT event_type, COUNT() as count FROM cybersecurity.security_logs GROUP BY event_type ORDER BY count DESC LIMIT 10 FORMAT Pretty"
```

#### ClickHouse (Iceberg Table Engine)
```bash
docker exec -it benchmark-clickhouse clickhouse-client --query \
  "SELECT event_type, COUNT() as count FROM iceberg_db.security_logs GROUP BY event_type ORDER BY count DESC LIMIT 10"
```

#### StarRocks (Native)
```bash
docker exec -it benchmark-starrocks-fe mysql -h127.0.0.1 -P9030 -uroot -D cybersecurity -e \
  "SELECT event_type, COUNT(*) as count FROM security_logs GROUP BY event_type ORDER BY count DESC LIMIT 10;"
```

#### StarRocks (Iceberg External Catalog)
```bash
docker exec -it benchmark-starrocks-fe mysql -h127.0.0.1 -P9030 -uroot -e \
  "SELECT event_type, COUNT(*) as count FROM iceberg_catalog.cybersecurity.security_logs GROUP BY event_type ORDER BY count DESC LIMIT 10;"
```

#### Trino (Iceberg)
```bash
docker exec -it benchmark-trino trino --server localhost:8080 --catalog iceberg --schema cybersecurity --execute \
  "SELECT event_type, COUNT(*) as count FROM security_logs GROUP BY event_type ORDER BY count DESC LIMIT 10"
```

#### Splunk DB Connect (dbxquery)
```bash
docker exec benchmark-splunk /opt/splunk/bin/splunk search \
  '| dbxquery connection="postgresql_conn" query="SELECT event_type, COUNT(*) as count FROM security_logs GROUP BY event_type ORDER BY count DESC LIMIT 10"' \
  -auth admin:changeme
```

---

## 📈 Performance Expectations

### Native Database Performance (M3 Platform)

| Database | Simple Query | Aggregation | Join Query | Architecture |
|----------|--------------|-------------|------------|--------------|
| **ClickHouse** | 10-20 ms | 30-50 ms | 50-100 ms | ARM64 native (optimal) |
| **PostgreSQL** | 50-100 ms | 150-300 ms | 300-500 ms | ARM64 native (optimal) |
| **StarRocks** | 40-60 ms | 80-150 ms | 150-250 ms | Rosetta 2 (15-20% overhead) |
| **Splunk** | 200-500 ms | 500-2000 ms | 1000-5000 ms | Rosetta 2 (30-40% overhead) |

### Splunk DB Connect Overhead

- **Additional Latency:** +100-200 ms per query
- **Reason:** Splunk search pipeline + JDBC driver + data serialization
- **Acceptable For:** Ad-hoc queries, dashboards (< 100 queries/hour)
- **Not Suitable For:** Real-time analytics (> 1000 queries/hour)

### Iceberg Multi-Engine Performance

| Engine | Native | Iceberg | Slowdown | Notes |
|--------|--------|---------|----------|-------|
| **ClickHouse** | 10-20 ms | 200-500 ms | **20-25x** | Read-only, high overhead |
| **StarRocks** | 30-50 ms | 120-200 ms | **4-6x** | Read-write, moderate overhead |
| **Trino** | - | 300-800 ms | (baseline) | Full Iceberg control |

**Trade-offs:**
- ✅ **Benefits:** Multi-engine access, ACID transactions, schema evolution, time travel, unified governance
- ❌ **Costs:** 4-25x slower than native formats, more complex infrastructure

---

## 🔄 Iceberg Use Cases

### When to Use Iceberg

✅ **Good Use Cases:**
1. **Data Governance:** Centralized access control across multiple query engines
2. **Schema Evolution:** Frequent schema changes without data rewrites
3. **Time Travel:** Audit trails, debugging, regulatory compliance
4. **Multi-Engine Federation:** Trino for ETL, ClickHouse for dashboards, StarRocks for analytics
5. **Open Architecture:** Avoid vendor lock-in, switch engines without data migration

❌ **Not Suitable For:**
1. **Real-Time Dashboards:** Sub-second query latency required
2. **High-Frequency Queries:** > 1000 queries/second
3. **OLTP Workloads:** Transactional applications with frequent updates
4. **Single Engine:** If only using one query engine, native format is faster

### Decision Matrix

| Requirement | Native Format | Iceberg Format |
|-------------|---------------|----------------|
| Performance | ✅ Best | ❌ 4-25x slower |
| Multi-engine | ❌ Requires ETL | ✅ Native support |
| Schema evolution | ❌ Rewrite data | ✅ Metadata-only |
| Time travel | ❌ Not supported | ✅ Full support |
| ACID across engines | ❌ No | ✅ Yes |
| Setup complexity | ✅ Simple | ❌ Complex |

---

## 📚 Documentation

### Core Documentation
- **[docs/SPLUNK_DBXQUERY_LIMITATIONS.md](docs/SPLUNK_DBXQUERY_LIMITATIONS.md)** - Comprehensive analysis of Splunk DB Connect dbxquery limitations, overhead measurements, and best practices
- **[docs/ICEBERG_MULTI_ENGINE.md](docs/ICEBERG_MULTI_ENGINE.md)** - Apache Iceberg multi-engine architecture guide, performance characteristics, use cases
- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** - Overall system architecture and design decisions
- **[docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)** - Common issues and solutions

### Benchmark Scripts
- **[benchmarks/01_native_baseline.py](benchmarks/01_native_baseline.py)** - Native database performance baseline
- **[benchmarks/02_splunk_dbxquery_overhead.py](benchmarks/02_splunk_dbxquery_overhead.py)** - Splunk DB Connect overhead measurement
- **[benchmarks/03_iceberg_multi_engine.py](benchmarks/03_iceberg_multi_engine.py)** - Iceberg multi-engine performance comparison
- **[benchmarks/run_all.sh](benchmarks/run_all.sh)** - Execute all benchmarks and generate report

---

## 🛠️ Advanced Configuration

### Increase Iceberg Query Performance

```sql
-- Trino: Compact small files (reduces metadata overhead)
ALTER TABLE iceberg.cybersecurity.security_logs EXECUTE optimize;

-- Trino: Expire old snapshots (cleanup history)
ALTER TABLE iceberg.cybersecurity.security_logs EXECUTE expire_snapshots(retention_threshold => '7d');

-- Trino: Remove orphan files (cleanup unused data)
ALTER TABLE iceberg.cybersecurity.security_logs EXECUTE remove_orphan_files(older_than => '30d');
```

### Configure Splunk DB Connect Connections

See [scripts/setup_splunk_dbconnect.sh](scripts/setup_splunk_dbconnect.sh) for automated configuration.

**Manual Configuration:**
1. Install Splunk DB Connect app from Splunkbase
2. Create database identities (credentials)
3. Create database connections (PostgreSQL, ClickHouse, StarRocks)
4. Test connections via Splunk UI

### Tune Database Memory (M3)

**docker-compose.m3.yml:**
```yaml
services:
  postgresql:
    deploy:
      resources:
        limits:
          memory: 4G    # Increase if needed

  clickhouse:
    deploy:
      resources:
        limits:
          memory: 8G    # High memory for fast queries

  trino:
    deploy:
      resources:
        limits:
          memory: 6G    # JVM heap for Iceberg metadata
```

---

## 🌐 AWS Deployment (Fair Comparison)

### Why AWS?

**Problem on M3:**
- StarRocks (Rosetta 2): 15-20% slower than native
- Splunk (Rosetta 2): 30-40% slower than native
- **Unfair comparison** between ARM64-native (ClickHouse) and Rosetta (others)

**Solution:**
- Deploy on AWS with **native architectures** for all databases
- ClickHouse: c7g.4xlarge (ARM64 Graviton3)
- StarRocks: m6i.4xlarge (x86_64 Intel)
- Splunk: m6i.4xlarge (x86_64 Intel)
- **Fair apples-to-apples comparison**

### Cost-Optimized AWS Deployment

**Use spot instances for short-term benchmarking:**

| Component | Instance | Spot Cost/Day |
|-----------|----------|---------------|
| PostgreSQL | r7g.xlarge | $3.84 |
| ClickHouse | c7g.2xlarge | $5.02 |
| StarRocks | m6i.2xlarge | $6.67 |
| Splunk | m6i.2xlarge | $6.67 |
| Trino | m7g.2xlarge | $4.70 |
| MinIO | t4g.large | $0.54 |
| Hive Metastore | t3a.medium | $0.27 |
| **Total** | | **~$28/day** |

**Run for 3 days:** ~$85 total for comprehensive benchmarking

**Terraform Deployment:** Coming soon (see GitHub Issues)

---

## ⚠️ Troubleshooting

### Iceberg Tables Not Visible

**ClickHouse:**
```bash
# Verify MinIO connectivity
curl http://localhost:9000/minio/health/live

# Check Iceberg table engine
docker exec -it benchmark-clickhouse clickhouse-client --query \
  "SHOW TABLES FROM iceberg_db"
```

**StarRocks:**
```bash
# Refresh Iceberg catalog
docker exec -it benchmark-starrocks-fe mysql -h127.0.0.1 -P9030 -uroot -e \
  "REFRESH EXTERNAL TABLE iceberg_catalog.cybersecurity.security_logs;"

# Verify catalog
docker exec -it benchmark-starrocks-fe mysql -h127.0.0.1 -P9030 -uroot -e \
  "SHOW CATALOGS;"
```

### Splunk DB Connect Not Working

**Error:** "dbxquery command not found"

**Solution:**
1. Install DB Connect app from Splunkbase: https://splunkbase.splunk.com/app/2686
2. Place .spl file in `./data/splunk/dbconnect/`
3. Restart Splunk: `docker-compose -f docker-compose.m3.yml restart splunk`
4. Run setup script: `bash scripts/setup_splunk_dbconnect.sh`

### Trino Queries Timeout

**Error:** "Query exceeded maximum time limit"

**Solution:**
```properties
# configs/trino/config.properties
query.max-execution-time=30m
query.max-memory-per-node=4GB
```

### Out of Memory on M3

**Symptom:** Docker containers crash, system freezes

**Solution:**
1. Increase Docker Desktop memory: Settings → Resources → Memory → 20GB (for 24GB Mac)
2. Reduce concurrent services: Stop Splunk/Trino if not actively testing
3. Lower database memory limits in docker-compose.m3.yml

---

## 🤝 Contributing

Contributions are welcome! Areas for improvement:

1. **Benchmark Enhancements:**
   - Add more query types (window functions, CTEs, subqueries)
   - Test with larger datasets (1M, 10M, 100M rows)
   - Measure concurrent query performance

2. **Iceberg Features:**
   - Time travel query benchmarks
   - Schema evolution performance
   - ACID transaction testing

3. **AWS Deployment:**
   - Terraform scripts for automated deployment
   - CloudWatch monitoring dashboards
   - Cost optimization strategies

4. **Documentation:**
   - Video tutorials
   - Best practices guide
   - Case studies

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- **PostgreSQL, ClickHouse, StarRocks, Splunk, Trino** teams for excellent database systems
- **Apache Iceberg** community for open table format
- **Docker** for consistent cross-platform development
- **Apple** for M-series ARM64 architecture
- **AWS** for Graviton processors

---

## 📞 Support

- **Issues:** [GitHub Issues](https://github.com/yourusername/splunk-db-connect-benchmark/issues)
- **Discussions:** [GitHub Discussions](https://github.com/yourusername/splunk-db-connect-benchmark/discussions)
- **Documentation:** [docs/](docs/)

---

**Built for the cybersecurity and database communities**

**Tested on:** MacBook Pro M3 Pro (24GB) | macOS 15.0 Sequoia | Docker Desktop 4.26
