# Run Benchmark Suite

## Overview
Executes the complete benchmark suite that measures query performance across three different access patterns: native database access (baseline), Splunk DB Connect proxy overhead, and Apache Iceberg multi-engine access. This comprehensive test suite provides quantitative performance data for comparing different architectural approaches to security analytics.

## What This Command Does

When you run `/benchmark`, it executes `benchmarks/run_all.sh` which sequentially runs:

1. **Benchmark 01: Native Baseline** (`01_native_baseline.py`)
   - Direct queries to PostgreSQL and ClickHouse
   - Measures optimal performance without middleware
   - Tests: SELECT, aggregations, GROUP BY, JOINs, time-series queries
   - Duration: ~5-10 minutes

2. **Benchmark 02: Splunk DB Connect Overhead** (`02_splunk_dbxquery_overhead.py`)
   - Same queries routed through Splunk's `dbxquery` command
   - Measures proxy/serialization overhead
   - Compares against native baseline
   - Duration: ~5-10 minutes
   - *Requires*: Splunk DB Connect configured (see setup docs)

3. **Benchmark 03: Iceberg Multi-Engine** (`03_iceberg_multi_engine.py`)
   - Queries against shared Iceberg tables via Trino
   - Measures cost of multi-engine flexibility
   - Tests Parquet file scanning performance
   - Duration: ~10-15 minutes
   - *Requires*: Iceberg tables created in MinIO

All results are saved to `results/` directory with timestamps for historical comparison.

## When to Use This Command

- **After environment setup**: Establish baseline performance metrics
- **After configuration changes**: Measure impact of tuning parameters
- **Before/after hardware changes**: Compare M3 vs M3 Pro vs M3 Max
- **Periodic validation**: Ensure performance hasn't degraded
- **Research and comparison**: Generate data for architecture decisions

## Prerequisites

**Required**:
- All services healthy (`/status` shows all containers up)
- Databases populated with data (`scripts/load_zeek_data.py` completed)
- Python packages installed: `psycopg2-binary`, `clickhouse-driver`, `trino-python-client`, `requests`

**Optional** (for full suite):
- Splunk DB Connect configured (for benchmark 02)
- Iceberg tables created (for benchmark 03)
- At least 2GB free memory for query execution

**Recommended**:
- Close other applications to minimize resource contention
- Disable macOS power saving features during benchmarking
- Run benchmarks 2-3 times and average results for consistency

## Output Format

Each benchmark outputs:
```
=================================================
Benchmark: Failed Login Attempts by User
Database: ClickHouse
=================================================
Iteration 1: 45.2ms
Iteration 2: 42.8ms
Iteration 3: 43.5ms
Iteration 4: 44.1ms
Iteration 5: 43.9ms

Results:
  Min: 42.8ms
  Max: 45.2ms
  Avg: 43.9ms
  Median: 43.9ms
  p95: 45.0ms
  p99: 45.2ms
```

Final summary saved to `results/benchmark_YYYYMMDD_HHMMSS.json`

## Expected Performance (M3 Mac)

### Native Baseline
- **PostgreSQL**: 50-100ms (simple), 150-300ms (aggregation)
- **ClickHouse**: 10-20ms (simple), 30-50ms (aggregation)
- **Speedup**: ClickHouse 3-6x faster than PostgreSQL

### Splunk DB Connect Overhead
- **Additional latency**: +100-200ms per query
- **Total time**: PostgreSQL+proxy = 150-500ms
- **Use case**: Acceptable for ad-hoc analytics, not real-time

### Iceberg Multi-Engine
- **Trino via Iceberg**: 200-400ms (simple), 800-1500ms (aggregation)
- **Overhead vs native**: 4-25x slower
- **Trade-off**: Flexibility for performance

## Benchmark Options

### Run Individual Benchmarks

Instead of running all benchmarks, you can run specific ones:

```bash
cd benchmarks
python3 01_native_baseline.py              # Native only (~10 min)
python3 02_splunk_dbxquery_overhead.py     # Splunk proxy (~10 min)
python3 03_iceberg_multi_engine.py         # Iceberg (~15 min)
```

### Customize Benchmark Parameters

Edit benchmark scripts to modify:
- **Iterations**: Change `ITERATIONS = 5` to run more/fewer times
- **Warmup**: Change `WARMUP_ITERATIONS = 2` to adjust cache warmup
- **Timeout**: Change `QUERY_TIMEOUT = 300` for slower queries
- **Queries**: Comment out specific queries to focus testing

## Results Analysis

Results are saved to:
- **JSON**: `results/benchmark_YYYYMMDD_HHMMSS.json` (machine-readable)
- **CSV**: `results/benchmark_YYYYMMDD_HHMMSS.csv` (spreadsheet import)
- **Summary**: `results/latest_summary.txt` (human-readable)

Use results to:
- Compare database engines for specific query patterns
- Quantify overhead of middleware layers
- Make architecture decisions with data
- Track performance trends over time

## Common Issues

**Issue**: "Connection refused to database"
- **Solution**: Run `/validate` first to ensure services are healthy
- **Check**: Services may need 1-2 minutes after startup

**Issue**: "Splunk benchmarks failing with 401"
- **Solution**: Configure DB Connect first via `/configure_dbconnect.py`
- **Skip**: Run only `01_native_baseline.py` if Splunk not needed

**Issue**: "Iceberg benchmarks failing - table not found"
- **Solution**: Create Iceberg tables first using Iceberg setup scripts
- **Skip**: Comment out benchmark 03 if Iceberg not needed

**Issue**: "Benchmarks inconsistent between runs"
- **Solution**: Close other applications, disable Spotlight indexing
- **Improvement**: Run 10 iterations instead of 5, drop outliers

**Issue**: "Out of memory during benchmarks"
- **Solution**: Run benchmarks sequentially, not in parallel
- **Check**: `docker stats` to see memory usage per container

## Performance Tuning Tips

**For Faster Benchmarks**:
- Increase warmup iterations (improves cache hit rate)
- Run on AC power (prevents CPU throttling)
- Close Docker Desktop dashboard (reduces observer overhead)

**For More Accurate Results**:
- Run during off-peak hours (fewer background processes)
- Increase iterations to 10-20 (statistical significance)
- Use multiple runs and average (reduces variance)
- Monitor system resources with `docker stats` in parallel

## Related Commands

- `/validate` - Verify environment before benchmarking
- `/status` - Check service health during benchmark runs
- `/cleanup` - Reset environment if benchmarks corrupt state

## Technical Details

Benchmark scripts use:
- **Time measurement**: Python `time.perf_counter()` (nanosecond precision)
- **Statistics**: NumPy for percentile calculations
- **Connection pooling**: Reuses database connections across iterations
- **Result format**: JSON Schema v1.0 for compatibility

Total disk space for results: ~50MB per complete run

## Exit Codes

- **0**: All benchmarks completed successfully
- **1**: One or more benchmarks failed (partial results saved)
- **2**: Critical error (no results generated)
