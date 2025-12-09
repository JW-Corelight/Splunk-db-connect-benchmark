# Splunk Analytics Queries - Event Traffic and Ingest Analysis

## Overview

This document provides production-ready Splunk queries for analyzing event traffic patterns, data ingest volumes, and retention periods across your Splunk deployment. These queries are designed for capacity planning, performance monitoring, and identifying high-volume data sources.

**Last Updated:** December 8, 2024
**Time Range:** Last 90 days
**Timeseries Span:** Daily aggregation (span=1d)
**Applies To:** Splunk Enterprise and Splunk Cloud Platform

---

## Executive Summary

Three complementary queries for comprehensive Splunk data analysis:

1. **Event Traffic Count Analysis** - Uses `tstats` to count events by index and sourcetype with sub-second performance
2. **Data Ingest Volume Analysis** - Calculates actual MB ingested from Splunk's internal license usage logs
3. **Data Retention Analysis** - Provides both current retention status and historical retention patterns visualization

All queries create a concatenated `index_sourcetype` field for clear visualization and comparison across data sources.

---

## 1. Event Traffic Count Analysis (tstats)

### Query

```spl
| tstats count WHERE index=* earliest=-90d latest=now
  BY _time index sourcetype span=1d
| eval index_sourcetype = index . "_" . sourcetype
| timechart span=1d sum(count) BY index_sourcetype
```

### How It Works

**Key Components:**
- `tstats count` - Leverages Splunk's accelerated indexed data for fast event counting without full text search
- `WHERE index=*` - Searches across all indexes (can be filtered to specific indexes if needed)
- `BY _time index sourcetype span=1d` - Groups results by time, index, and sourcetype with 1-day buckets
- `eval index_sourcetype = index . "_" . sourcetype` - Concatenates index and sourcetype using the `.` string operator
- `timechart span=1d sum(count) BY index_sourcetype` - Transforms data into timeseries format with daily aggregation

**Performance Characteristics:**
- Extremely fast execution (typically <1 second) due to tstats acceleration
- Does not read raw event data, only metadata
- Scales well to billions of events

### Use Cases

- **Capacity Planning** - Identify growing data sources before they impact performance
- **Anomaly Detection** - Spot unusual spikes or drops in event volume
- **Data Source Monitoring** - Track which indexes/sourcetypes are most active
- **Troubleshooting** - Verify data is being indexed as expected

### Customization Options

**Filter Specific Indexes:**
```spl
| tstats count WHERE (index=main OR index=security) earliest=-90d latest=now
  BY _time index sourcetype span=1d
```

**Change Time Range (30 days):**
```spl
| tstats count WHERE index=* earliest=-30d latest=now
  BY _time index sourcetype span=1d
```

**Hourly Granularity:**
```spl
| tstats count WHERE index=* earliest=-7d latest=now
  BY _time index sourcetype span=1h
| eval index_sourcetype = index . "_" . sourcetype
| timechart span=1h sum(count) BY index_sourcetype
```

---

## 2. Data Ingest Volume Analysis (_internal)

### Query

```spl
index=_internal source=*license_usage.log* type="Usage" earliest=-90d latest=now
| eval mb = b/1024/1024
| eval index_sourcetype = idx . "_" . st
| timechart span=1d sum(mb) BY index_sourcetype
```

### How It Works

**Key Components:**
- `index=_internal source=*license_usage.log*` - Targets Splunk's internal license usage logs
- `type="Usage"` - Filters for actual data usage events (excludes license pool information)
- `eval mb = b/1024/1024` - Converts the `b` field (bytes) to megabytes for readability
- `eval index_sourcetype = idx . "_" . st` - Concatenates using license log field names (`idx` and `st` instead of `index` and `sourcetype`)
- `timechart span=1d sum(mb) BY index_sourcetype` - Aggregates MB ingested per day by the concatenated field

**Important Field Mapping:**
- License usage logs use **`idx`** instead of `index`
- License usage logs use **`st`** instead of `sourcetype`
- The **`b`** field contains bytes ingested
- The **`h`** field contains the indexer hostname

### Use Cases

- **License Management** - Track license usage by data source to optimize allocation
- **Cost Analysis** - Identify high-volume data sources for potential filtering or sampling
- **Capacity Planning** - Project future storage needs based on ingest trends
- **Billing/Chargeback** - Attribute data ingest costs to specific teams or applications

### Customization Options

**Include Indexer Hostname:**
```spl
index=_internal source=*license_usage.log* type="Usage" earliest=-90d latest=now
| eval mb = b/1024/1024
| eval index_sourcetype_host = idx . "_" . st . "_" . h
| timechart span=1d sum(mb) BY index_sourcetype_host
```

**Filter Specific Indexes:**
```spl
index=_internal source=*license_usage.log* type="Usage" earliest=-90d latest=now
| search idx IN (main, security, firewall)
| eval mb = b/1024/1024
| eval index_sourcetype = idx . "_" . st
| timechart span=1d sum(mb) BY index_sourcetype
```

**Show Total Daily Ingest (All Sources):**
```spl
index=_internal source=*license_usage.log* type="Usage" earliest=-90d latest=now
| eval mb = b/1024/1024
| timechart span=1d sum(mb) as total_mb
```

**Convert to GB for Large Environments:**
```spl
index=_internal source=*license_usage.log* type="Usage" earliest=-90d latest=now
| eval gb = b/1024/1024/1024
| eval index_sourcetype = idx . "_" . st
| timechart span=1d sum(gb) BY index_sourcetype
```

---

## 3. Data Retention Analysis

### Overview

Data retention analysis helps you understand how far back your data goes for each index and sourcetype combination. This is critical for compliance, capacity planning, and ensuring data availability meets business requirements.

**Two approaches provided:**
- **Simple Query (3A)** - Current snapshot of retention periods for each index/sourcetype
- **Detailed Query (3B)** - Historical timeseries showing data existence patterns over time

---

### 3A. Current Retention Status (Simple)

#### Query

```spl
| tstats min(_time) as oldest_event, max(_time) as newest_event, count WHERE index=*
  BY index sourcetype
| eval index_sourcetype = index . "_" . sourcetype
| eval retention_days = round((newest_event - oldest_event) / 86400, 1)
| eval oldest_event_readable = strftime(oldest_event, "%Y-%m-%d %H:%M:%S")
| eval newest_event_readable = strftime(newest_event, "%Y-%m-%d %H:%M:%S")
| eval data_span_readable = tostring(retention_days, "duration")
| table index_sourcetype oldest_event_readable newest_event_readable retention_days count
| sort - retention_days
```

#### How It Works

**Key Components:**
- `tstats min(_time) as oldest_event` - Finds the timestamp of the oldest event for each index/sourcetype
- `max(_time) as newest_event` - Finds the timestamp of the most recent event
- `retention_days = (newest_event - oldest_event) / 86400` - Calculates the span in days (86400 seconds per day)
- `strftime()` - Converts Unix timestamps to human-readable dates
- `table` - Displays results in tabular format sorted by retention period (longest first)

**Output Columns:**
- `index_sourcetype` - Concatenated identifier
- `oldest_event_readable` - Date/time of oldest event in the index
- `newest_event_readable` - Date/time of newest event in the index
- `retention_days` - Number of days between oldest and newest events
- `count` - Total number of events for this index/sourcetype

#### Use Cases

- **Compliance Verification** - Ensure retention policies are being met (e.g., "must retain 90 days")
- **Retention Policy Planning** - Identify indexes with excessive retention that could be reduced
- **Data Availability Check** - Verify historical data is available for investigations or audits
- **Storage Optimization** - Find index/sourcetype pairs with unexpectedly long retention consuming storage

#### Interpretation

**Example Output:**
```
index_sourcetype               oldest_event_readable    newest_event_readable    retention_days  count
main_access_combined          2023-09-08 00:00:15      2024-12-08 16:30:45      457.7          8500000
security_linux_secure         2024-06-15 08:22:10      2024-12-08 16:25:30      176.3          1200000
firewall_cisco_asa            2024-11-01 12:00:00      2024-12-08 16:20:15      37.2           450000
```

**Key Insights:**
- **retention_days = 0 or very small** - Data source is new or only recent data exists
- **retention_days matches policy** - Expected behavior (e.g., 90-day policy shows ~90 days)
- **retention_days exceeds policy** - Potential frozen/archived data not being deleted, or policy not applied
- **Low count with high retention_days** - Sparse data source that's been collecting for a long time

#### Customization Options

**Filter Specific Indexes:**
```spl
| tstats min(_time) as oldest_event, max(_time) as newest_event, count
  WHERE (index=main OR index=security)
  BY index sourcetype
| eval index_sourcetype = index . "_" . sourcetype
| eval retention_days = round((newest_event - oldest_event) / 86400, 1)
| eval oldest_event_readable = strftime(oldest_event, "%Y-%m-%d %H:%M:%S")
| eval newest_event_readable = strftime(newest_event, "%Y-%m-%d %H:%M:%S")
| table index_sourcetype oldest_event_readable newest_event_readable retention_days count
| sort - retention_days
```

**Show Only Indexes Exceeding 90-Day Retention:**
```spl
| tstats min(_time) as oldest_event, max(_time) as newest_event, count WHERE index=*
  BY index sourcetype
| eval index_sourcetype = index . "_" . sourcetype
| eval retention_days = round((newest_event - oldest_event) / 86400, 1)
| where retention_days > 90
| eval oldest_event_readable = strftime(oldest_event, "%Y-%m-%d %H:%M:%S")
| eval newest_event_readable = strftime(newest_event, "%Y-%m-%d %H:%M:%S")
| table index_sourcetype oldest_event_readable newest_event_readable retention_days count
| sort - retention_days
```

**Add GB Calculation:**
```spl
| tstats min(_time) as oldest_event, max(_time) as newest_event, count, sum(len) as total_bytes WHERE index=*
  BY index sourcetype
| eval index_sourcetype = index . "_" . sourcetype
| eval retention_days = round((newest_event - oldest_event) / 86400, 1)
| eval size_gb = round(total_bytes / 1024 / 1024 / 1024, 2)
| eval oldest_event_readable = strftime(oldest_event, "%Y-%m-%d %H:%M:%S")
| eval newest_event_readable = strftime(newest_event, "%Y-%m-%d %H:%M:%S")
| table index_sourcetype oldest_event_readable newest_event_readable retention_days count size_gb
| sort - retention_days
```

---

### 3B. Retention Pattern Visualization (Detailed)

#### Query

```spl
| tstats count WHERE index=* earliest=-1y latest=now
  BY _time index sourcetype span=1w
| eval index_sourcetype = index . "_" . sourcetype
| timechart span=1w sum(count) BY index_sourcetype
```

#### How It Works

**Key Components:**
- `earliest=-1y` - Looks back 1 year to visualize long-term retention patterns
- `span=1w` - Uses weekly buckets (more appropriate for year-long analysis than daily)
- `BY _time index sourcetype` - Groups by time period, index, and sourcetype
- `timechart` - Creates a multi-series timeseries visualization

**Visualization Output:**
- X-axis: Time (weekly intervals over 1 year)
- Y-axis: Event count per week
- Series: One line per `index_sourcetype` combination
- Interpretation: Lines that start mid-chart indicate when data collection began; lines that end mid-chart indicate retention cutoff

#### Use Cases

- **Visual Retention Verification** - See exactly where data drops off for each source
- **Retention Policy Changes** - Visualize the impact of retention policy adjustments over time
- **Data Collection History** - Identify when new data sources were added
- **Gap Detection** - Spot periods where data collection was interrupted
- **Retention Drift Analysis** - Compare current retention to historical patterns

#### Interpretation

**Pattern Analysis:**

1. **Full-span line (Jan → Dec)** - Data source has been collecting for entire year and retention keeps full year
   ```
   Count
   |     ________________
   |    /                \
   |___/                  \___
   Jan                      Dec
   ```

2. **Line starts mid-year** - New data source added partway through the year
   ```
   Count
   |              ________
   |             /        \
   |____________/          \___
   Jan         Jun          Dec
   ```

3. **Line ends abruptly** - Retention cutoff point or data source stopped collecting
   ```
   Count
   |     ________
   |    /        \
   |___/          \___________
   Jan           Jun          Dec
   ```

4. **Line with gap** - Data collection interrupted (forwarder down, network issue, etc.)
   ```
   Count
   |     ____    ____
   |    /    \  /    \
   |___/      \/      \___
   Jan    Mar  May      Dec
   ```

5. **Declining line** - Progressive retention window (older data rolling off)
   ```
   Count
   |     ___
   |    /   \___
   |___/        \___________
   Jan                     Dec
   ```

#### Customization Options

**Daily Granularity (Shorter Time Range):**
```spl
| tstats count WHERE index=* earliest=-90d latest=now
  BY _time index sourcetype span=1d
| eval index_sourcetype = index . "_" . sourcetype
| timechart span=1d sum(count) BY index_sourcetype
```

**2-Year Historical View:**
```spl
| tstats count WHERE index=* earliest=-2y latest=now
  BY _time index sourcetype span=1mon
| eval index_sourcetype = index . "_" . sourcetype
| timechart span=1mon sum(count) BY index_sourcetype
```

**Filter to Specific Indexes:**
```spl
| tstats count WHERE (index=main OR index=security) earliest=-1y latest=now
  BY _time index sourcetype span=1w
| eval index_sourcetype = index . "_" . sourcetype
| timechart span=1w sum(count) BY index_sourcetype
```

**Show Data Presence (Binary Yes/No Instead of Count):**
```spl
| tstats count WHERE index=* earliest=-1y latest=now
  BY _time index sourcetype span=1w
| eval index_sourcetype = index . "_" . sourcetype
| eval has_data = if(count > 0, 1, 0)
| timechart span=1w max(has_data) BY index_sourcetype
```
This creates a binary view where 1 = data exists, 0 = no data (useful for seeing gaps more clearly)

#### Performance Considerations

- **1-year lookback with weekly span** - Generally fast (<5 seconds) due to tstats acceleration
- **Daily span over 1 year** - May be slower (10-30 seconds) due to higher granularity
- **2+ year lookbacks** - Use monthly span to keep query performant
- **Recommendation** - Start with weekly/monthly spans and only increase granularity if needed

---

## Visualization Notes

### Chart Interpretation

**Timeseries Display:**
- Queries 1, 2, and 3B produce multi-series timechart visualizations
- Each line represents one `index_sourcetype` combination
- The X-axis shows time buckets (daily for Queries 1/2, weekly for Query 3B)
- The Y-axis shows event count (Query 1/3B) or MB ingested (Query 2)
- Query 3A produces a table view rather than a timechart

**Legend Format:**
- Format: `{index}_{sourcetype}` (e.g., `main_access_combined`, `security_linux_secure`)
- Concatenation provides clear identification of data sources
- Useful for comparing multiple data sources simultaneously

**Common Patterns:**
- **Steady baseline** - Normal, consistent data flow
- **Daily/weekly cycles** - Business hour patterns
- **Sharp spikes** - Potential issues or batch data loads
- **Dropouts (zeros)** - Forwarding failures or gaps in data collection
- **Gradual increases** - Organic growth or new data sources

### Performance Considerations

**Query 1 (tstats):**
- Very fast execution (<1 second typically)
- Minimal resource consumption
- Safe to run frequently or schedule as an alert

**Query 2 (_internal logs):**
- Moderate execution time (5-30 seconds depending on deployment size)
- Scans license usage logs across all indexers
- Recommended for scheduled reports rather than ad-hoc searches
- May show slight discrepancies from actual event counts due to licensing calculations

**Query 3A (retention snapshot):**
- Very fast execution (<1 second typically)
- Leverages tstats acceleration
- Safe to run frequently
- Useful for scheduled reports or dashboards

**Query 3B (retention visualization):**
- Fast to moderate execution (2-10 seconds depending on time range)
- 1-year lookback with weekly span typically completes quickly
- Longer time ranges (2+ years) should use monthly span
- Consider scheduling for recurring retention audits

---

## Customization Guide

### Adjusting Time Ranges

**Common Time Range Options:**
```spl
earliest=-24h latest=now     # Last 24 hours
earliest=-7d latest=now      # Last 7 days
earliest=-30d latest=now     # Last 30 days (1 month)
earliest=-90d latest=now     # Last 90 days (3 months)
earliest=-1y latest=now      # Last year
```

**Specific Date Ranges:**
```spl
earliest="11/01/2024:00:00:00" latest="12/01/2024:00:00:00"  # November 2024
```

### Changing Span Intervals

**Span determines the time bucket size for aggregation:**
```spl
span=15m    # 15-minute intervals (good for last 24 hours)
span=1h     # Hourly intervals (good for last 7 days)
span=1d     # Daily intervals (good for 30-90 days) - DEFAULT
span=1w     # Weekly intervals (good for 6+ months)
span=1mon   # Monthly intervals (good for multi-year analysis)
```

**Match span to time range for optimal visualization:**
- 24 hours → `span=15m` or `span=1h`
- 7 days → `span=1h` or `span=6h`
- 30 days → `span=1d`
- 90 days → `span=1d` - **CURRENT DEFAULT**
- 1 year → `span=1w` or `span=1mon`

### Filtering Specific Indexes

**Query 1 (tstats) - Multiple Indexes:**
```spl
| tstats count WHERE (index=main OR index=security OR index=firewall) earliest=-90d latest=now
  BY _time index sourcetype span=1d
| eval index_sourcetype = index . "_" . sourcetype
| timechart span=1d sum(count) BY index_sourcetype
```

**Query 2 (_internal) - Filter by idx:**
```spl
index=_internal source=*license_usage.log* type="Usage" earliest=-90d latest=now
| search idx IN (main, security, firewall)
| eval mb = b/1024/1024
| eval index_sourcetype = idx . "_" . st
| timechart span=1d sum(mb) BY index_sourcetype
```

### Adding Additional Fields

**Include Indexer Host (Query 2):**
```spl
index=_internal source=*license_usage.log* type="Usage" earliest=-90d latest=now
| eval mb = b/1024/1024
| eval index_sourcetype_host = idx . "_" . st . " (" . h . ")"
| timechart span=1d sum(mb) BY index_sourcetype_host
```

**Add Splunk Pool Information:**
```spl
index=_internal source=*license_usage.log* type="Usage" earliest=-90d latest=now
| eval mb = b/1024/1024
| eval index_sourcetype = idx . "_" . st
| eval pool = if(isnull(pool), "default", pool)
| timechart span=1d sum(mb) BY index_sourcetype pool
```

---

## Comparison and Analysis

### Query Comparison Matrix

| Aspect | Query 1 (tstats) | Query 2 (_internal) | Query 3A (retention) | Query 3B (retention viz) |
|--------|------------------|---------------------|----------------------|--------------------------|
| **Data Source** | Index metadata | License usage logs | Index metadata | Index metadata |
| **Metric** | Event count | MB ingested | Retention days | Event count over time |
| **Output Format** | Timechart | Timechart | Table | Timechart |
| **Time Range** | 90 days (default) | 90 days (default) | All time | 1 year (default) |
| **Speed** | Very fast (<1s) | Moderate (5-30s) | Very fast (<1s) | Fast (2-10s) |
| **Accuracy** | Exact event count | Approximate | Exact timestamps | Exact event count |
| **Field Names** | `index`, `sourcetype` | `idx`, `st` | `index`, `sourcetype` | `index`, `sourcetype` |
| **Use Case** | Event volume analysis | License/cost tracking | Compliance verification | Pattern visualization |

### When to Use Each Query

**Use Query 1 (Event Traffic) when:**
- You need fast, real-time visibility into event counts
- You're troubleshooting data flow issues
- You want to identify anomalies in event volume over the past 90 days
- Performance is critical

**Use Query 2 (Ingest Volume) when:**
- You need to track license consumption
- You're doing cost analysis or chargeback
- You want to measure actual data size (MB/GB) ingested
- You need to align with Splunk licensing metrics

**Use Query 3A (Current Retention) when:**
- You need a snapshot of current retention periods
- You're verifying compliance with retention policies
- You want to identify indexes with excessive or insufficient retention
- You need to calculate storage requirements based on retention

**Use Query 3B (Retention Patterns) when:**
- You want to visualize retention patterns over time
- You need to identify when data collection started/stopped
- You're investigating gaps in data collection
- You want to see the impact of retention policy changes
- You need to verify progressive retention windows

### Running Multiple Queries Together

**Comprehensive Data Health Analysis:**
Combine all queries for complete visibility:
1. **Query 1** - Current event volume trends (Are events flowing correctly?)
2. **Query 2** - Actual data size (What's the cost/license impact?)
3. **Query 3A** - Retention status (How far back can we search?)
4. **Query 3B** - Historical patterns (Are there gaps or anomalies?)

**Example Insights from Combined Analysis:**
- **High event count + Low MB + Short retention** = Efficient, recent data source
- **Low event count + High MB + Long retention** = Large events or bloated logs consuming storage
- **Query 3B shows gaps + Query 1 shows steady flow** = Recent recovery from outage
- **Query 3A shows excessive retention + Query 2 shows high MB** = Optimization opportunity (reduce retention to save storage)

---

## Related Documentation

- [Splunk DB Connect - dbxquery Command Limitations](./SPLUNK_DBXQUERY_LIMITATIONS.md)
- [Iceberg Multi-Engine Architecture](./ICEBERG_MULTI_ENGINE.md)
- [Project Specification](../SPECIFICATION.md)
- [Implementation Summary](../IMPLEMENTATION_SUMMARY.md)

---

## Support and Troubleshooting

### Common Issues

**Query 1 returns no results:**
- Verify tstats is enabled for your indexes (`tstats` works on indexed data only)
- Check that you have search permissions for the indexes
- Ensure the time range contains data

**Query 2 returns no results:**
- Verify you have access to the `_internal` index
- Check that license usage logging is enabled (it is by default)
- Confirm the time range is correct (license logs are written daily)

**Query 3A shows 0 or very small retention_days:**
- This is expected for newly created indexes or recently added data sources
- Check if data is actually flowing using Query 1
- Verify that older data hasn't been deleted due to retention policies

**Query 3B shows no historical data:**
- Increase the time range if the index is older than the query window
- Check that tstats is enabled for the indexes
- Verify the index has been collecting data for the full time range

**Too many series in the chart:**
- Apply index filters to reduce the number of index_sourcetype combinations
- Consider aggregating at the index level only (remove sourcetype from concatenation)
- Use `| head` or `| tail` to limit results to top/bottom data sources
- For Query 3B, consider filtering to only critical indexes

**Performance is slow:**
- For Query 1: tstats should always be fast; check for summary indexing issues
- For Query 2: Reduce time range or add more specific filters
- For Query 3A: Should always be fast; check index permissions if slow
- For Query 3B: Use weekly/monthly span for time ranges over 1 year
- Consider scheduling as a report rather than running ad-hoc

**Query 3A retention_days exceeds expected policy:**
- Verify frozen/archived data isn't being counted
- Check if retention policies are actually being applied to the indexes
- Review indexes.conf settings for frozenTimePeriodInSecs
- Confirm Splunk's data model acceleration isn't affecting results

---

**Generated for:** Splunk DB Connect Benchmark Project
**Repository:** [Splunk-db-connect-benchmark](https://github.com)
