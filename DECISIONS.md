# Architecture Decision Records (ADRs)

This document captures key architectural decisions made during the development of the Splunk DB Connect Benchmark environment.

---

## ADR-001: Docker Compose over Kubernetes

**Date**: 2024-12-07
**Status**: Accepted
**Decision Makers**: Development Team

### Context
Need to orchestrate 7 different database and middleware services on a MacBook Pro M3 for benchmarking purposes.

### Decision
Use Docker Compose instead of Kubernetes.

### Rationale

**Pros of Docker Compose**:
- Simpler setup (single YAML file)
- Lower resource overhead (~2GB vs ~4GB for K8s control plane)
- Easier debugging on local machine
- Faster iteration during development
- Better suited for single-host deployment
- Native Docker Desktop integration on macOS

**Cons Considered**:
- No horizontal scaling (not needed for benchmarking)
- No load balancing (single instance per service)
- Less production-like (acceptable for research project)

### Consequences
- Quick setup time (~30 minutes)
- Services can be started/stopped independently
- Lower memory footprint leaves more for databases
- Not suitable for multi-node benchmarking (future consideration)

---

## ADR-002: PostgreSQL as Baseline Database

**Date**: 2024-12-06
**Status**: Accepted

### Context
Need a traditional RDBMS as performance baseline for comparison with columnar databases.

### Decision
Use PostgreSQL 16 as the relational database baseline.

### Rationale

**Why PostgreSQL**:
- Industry-standard RDBMS widely used in enterprises
- Excellent ARM64 support on Apple Silicon
- ACID compliance for comparison
- Strong community and documentation
- Representative of traditional row-store performance

**Alternatives Considered**:
- MySQL: Less features, comparable performance
- MariaDB: Similar to MySQL, no significant advantage
- Oracle: Licensing costs, overkill for benchmarking

### Consequences
- Well-known performance characteristics
- Easy to compare with ClickHouse columnar performance
- Good psycopg2 driver support for Python benchmarks
- ~50-300ms query times for typical security analytics

---

## ADR-003: ClickHouse as Primary Columnar Database

**Date**: 2024-12-06
**Status**: Accepted

### Context
Need a high-performance columnar database for security analytics workloads.

### Decision
Use ClickHouse 24.1 as the primary columnar OLAP database.

### Rationale

**Why ClickHouse**:
- Best-in-class performance for analytical queries
- Excellent ARM64 support (native binary)
- MergeTree engine optimized for time-series data
- 5-10x faster than PostgreSQL for aggregations
- Strong Splunk DB Connect compatibility
- Active development and security focus

**Alternatives Considered**:
- **DuckDB**: Excellent performance but in-process only, no server mode
- **Apache Druid**: More complex, requires Zookeeper, higher overhead
- **TimescaleDB**: Extension of PostgreSQL, not true columnar
- **Apache Pinot**: Optimized for real-time, heavier resource requirements

### Consequences
- 10-50ms query times for analytics (vs 50-300ms PostgreSQL)
- Need 4GB memory allocation (higher than PostgreSQL)
- Native ARM64 performance without Rosetta overhead
- Good documentation for cybersecurity use cases

---

## ADR-004: StarRocks for Additional MPP Testing

**Date**: 2024-12-06
**Status**: Accepted

### Context
Want to evaluate another columnar database with MPP architecture.

### Decision
Include StarRocks 3.2 as third database engine.

### Rationale

**Why StarRocks**:
- MPP (Massively Parallel Processing) architecture
- MySQL protocol compatibility (easy benchmarking)
- Vectorized execution engine
- Different architecture from ClickHouse (comparison value)
- Support for Apache Iceberg external tables

**Trade-offs**:
- No ARM64 native build (runs on Rosetta 2)
- ~15-20% performance overhead from Rosetta
- Higher memory requirements (2GB FE + 4GB BE)
- More complex setup (frontend + backend services)

### Consequences
- Enables MPP vs single-node columnar comparison
- Rosetta overhead documented for M3 users
- Good preparation for Iceberg multi-engine testing
- Requires 6GB total memory allocation

---

## ADR-005: Apache Iceberg for Multi-Engine Access

**Date**: 2024-12-07
**Status**: Accepted

### Context
Want to enable multiple query engines to access the same data without ETL.

### Decision
Implement Apache Iceberg table format with MinIO storage and Hive Metastore catalog.

### Rationale

**Why Apache Iceberg**:
- Open table format (no vendor lock-in)
- Schema evolution without rewriting data
- Time travel and versioning support
- Supported by Trino, ClickHouse, StarRocks
- Industry momentum (Snowflake, Databricks support)

**Alternatives Considered**:
- **Delta Lake**: Databricks-centric, less multi-engine support
- **Apache Hudi**: More complex, streaming-focused
- **Direct Parquet**: No metadata layer, manual partition management

**Trade-offs**:
- ✅ Multi-engine flexibility
- ✅ Schema evolution
- ✅ ACID transactions
- ❌ 4-25x slower than native formats
- ❌ Additional infrastructure (MinIO, Hive Metastore)
- ❌ ~2GB additional memory overhead

### Consequences
- Demonstrates trade-offs between flexibility and performance
- Enables realistic multi-engine access patterns
- Prepares for future lakehouse architectures
- Valuable for organizations considering data lake platforms

---

## ADR-006: MinIO for S3-Compatible Storage

**Date**: 2024-12-07
**Status**: Accepted

### Context
Iceberg requires S3-compatible object storage for Parquet files.

### Decision
Use MinIO as local S3-compatible storage instead of AWS S3.

### Rationale

**Why MinIO**:
- True S3 API compatibility
- Runs locally (no cloud costs)
- Excellent ARM64 support
- Lightweight (512MB memory)
- Web console for debugging
- Industry-standard for local S3 testing

**Alternatives Considered**:
- **AWS S3**: Requires internet, costs money, latency
- **LocalStack**: More complex, heavier, less stable
- **Direct filesystem**: No S3 API, limits Iceberg functionality

### Consequences
- Zero cloud costs
- Fast local I/O performance
- Easy debugging via web console (port 9001)
- Realistic S3 API testing for production readiness

---

## ADR-007: Trino as Iceberg Query Coordinator

**Date**: 2024-12-07
**Status**: Accepted

### Context
Need a distributed SQL query engine for Iceberg tables.

### Decision
Use Trino as the primary query engine for Iceberg tables.

### Rationale

**Why Trino**:
- Best-in-class Iceberg support (contributed by Facebook)
- ARM64 native support
- Distributed query execution
- SQL-standard compliant
- Good Python client (trino-python-client)
- Active development

**Alternatives Considered**:
- **Presto**: Original project, less active than Trino
- **Apache Spark**: Heavy JVM footprint, complex setup
- **Dremio**: Commercial, resource-intensive

### Consequences
- 2GB memory footprint (acceptable)
- Native ARM64 performance
- Standard SQL interface for benchmarks
- Single-node deployment (coordinator + worker combined)

---

## ADR-008: Splunk DB Connect for Proxy Overhead Testing

**Date**: 2024-12-07
**Status**: Accepted

### Context
Want to measure overhead of Splunk's database proxy layer for analytics.

### Decision
Deploy Splunk Enterprise with DB Connect app to test `dbxquery` performance.

### Rationale

**Why Test DB Connect**:
- Common pattern: Splunk as SIEM + analytics hub
- Organizations want to know cost of using Splunk as query layer
- Measures serialization and network overhead
- Real-world use case validation

**Trade-offs**:
- Splunk requires 4GB memory
- Runs on Rosetta 2 (no ARM64 build)
- Adds ~30-40% Rosetta overhead on top of proxy overhead
- Complex setup (license, DB Connect configuration)

**Expected Overhead**: +100-200ms per query

### Consequences
- Realistic measurement of Splunk proxy costs
- Demonstrates trade-off between unified interface and performance
- Validates direct database access for latency-sensitive queries
- Useful for organizations planning Splunk DB Connect deployments

---

## ADR-009: ARM64 Native vs Rosetta 2 Trade-offs

**Date**: 2024-12-06
**Status**: Accepted

### Context
Not all database software has ARM64 native builds for Apple Silicon.

### Decision
Use ARM64 native where available, accept Rosetta 2 for others, document overhead.

### ARM64 Native Services (Optimal):
- PostgreSQL 16
- ClickHouse 24.1
- Trino
- MinIO

### Rosetta 2 Services (Acceptable Overhead):
- Splunk Enterprise (~30-40% overhead)
- StarRocks (~15-20% overhead)
- Hive Metastore (~10-15% overhead, metadata-only)

### Rationale
- Maximize performance where possible
- Accept Rosetta overhead for unique capabilities
- Document performance impact for users
- M3 Rosetta performance is acceptable for development

### Consequences
- Best possible performance for PostgreSQL/ClickHouse comparisons
- Documented overhead for Splunk/StarRocks
- Clear guidance for users on M3 requirements
- Future: migrate to ARM64 when available

---

## ADR-010: Python for Benchmarking Scripts

**Date**: 2024-12-06
**Status**: Accepted

### Context
Need to write benchmark scripts to test query performance.

### Decision
Use Python 3 with native database drivers for all benchmarks.

### Rationale

**Why Python**:
- Excellent database driver ecosystem
  - `psycopg2` for PostgreSQL
  - `clickhouse-driver` for ClickHouse
  - `trino-python-client` for Trino
  - `requests` for Splunk REST API
- Easy statistical analysis (timing, percentiles)
- Simple error handling and logging
- Cross-platform compatibility
- Type hints for code quality

**Alternatives Considered**:
- **Go**: Better performance but harder driver integration
- **Bash**: Too simple for structured benchmarks
- **Java**: Heavier footprint, unnecessary complexity

### Consequences
- Consistent benchmark methodology
- Easy to add new queries
- Good documentation with docstrings
- Type hints improve maintainability
- Standard library sufficient (no external deps except drivers)

---

## ADR-011: 300K Event Dataset Size

**Date**: 2024-12-07
**Status**: Accepted

### Context
Need to choose appropriate dataset size for benchmarking.

### Decision
Use 300K security events + 20K network logs (~350MB total).

### Rationale

**Why This Size**:
- Fits in memory for ClickHouse/PostgreSQL page cache
- Large enough to show performance differences
- Small enough to setup quickly (~5-10 minutes)
- Realistic for SMB security operations (1-2 weeks of logs)
- Manageable on 16GB Mac (with 12GB Docker allocation)

**Scaling Considerations**:
- 1M events: Still manageable on 16GB Mac
- 10M events: Requires 24GB+ Mac
- 100M events: Out of scope for local benchmarking

### Consequences
- Quick data loading (<10 minutes)
- Clear performance differences visible
- Benchmark results reproducible
- Users can scale up if needed (documented in SPECIFICATION.md)

---

## ADR-012: Synthetic vs Real Security Data

**Date**: 2024-12-06
**Status**: Accepted

### Context
Need cybersecurity data for benchmarking but can't use real logs.

### Decision
Generate synthetic security event data with realistic patterns.

### Rationale

**Why Synthetic Data**:
- No PII or confidential information
- Can be shared publicly (GitHub)
- Controlled distribution (specify date ranges, event types)
- No legal/compliance concerns
- Deterministic results (reproducible benchmarks)

**Realism Requirements**:
- IP addresses in private ranges (10.x, 192.168.x)
- Typical severity distribution (5% critical, 15% high, 30% medium, 50% low)
- Temporal patterns (business hours peak, weekend valleys)
- Common event types (login, firewall, IDS, authentication)

### Consequences
- Safe to publish project openly
- Easy for others to reproduce
- Can regenerate with different parameters
- Representative query patterns and performance

---

## ADR-013: Git-Based Documentation over Wiki

**Date**: 2024-12-06
**Status**: Accepted

### Context
Need comprehensive documentation for setup, operation, and troubleshooting.

### Decision
Use Markdown files in Git repository instead of external wiki.

### Rationale

**Why Git-Based Docs**:
- Version controlled with code
- Offline access
- Easy to update with pull requests
- No separate service to maintain
- Searchable with standard tools
- Renders on GitHub automatically

**Structure**:
- `README.md`: Quick start, overview
- `SPECIFICATION.md`: Technical details
- `ARCHITECTURE.md`: System design
- `DECISIONS.md`: This file (ADRs)
- `docs/`: Detailed guides and troubleshooting
- `.claude/CLAUDE.md`: AI assistant context

### Consequences
- Single source of truth in repository
- Documentation lives with code
- Easy to keep docs in sync with changes
- No wiki maintenance overhead

---

## Future Decisions to Document

**Pending Architectural Choices**:
- Data ingestion method (batch vs streaming)
- Query result caching strategy
- Monitoring/observability framework
- CI/CD for automated benchmarks
- Multi-platform support (Linux, Windows)

Each future architectural decision should follow this ADR format:
- Context: Why is this decision needed?
- Decision: What was chosen?
- Rationale: Why this option over alternatives?
- Consequences: What are the trade-offs?
