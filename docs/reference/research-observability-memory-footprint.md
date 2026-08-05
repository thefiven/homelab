# Observability stacks: memory, disk and write footprint on one 32 GB node

**Date:** 2026-08-05
**Status:** research note, no decision taken
**Sources:** primary only — official documentation, official release/EOL notices,
upstream configuration reference, upstream source repositories. Vendor benchmarks
are used only where labelled as such. Every claim carries its URL inline.

---

## 1. Scope and the assumptions this note is written against

The target is a single machine: Ryzen 5 5600X, **32 GB RAM as a hard ceiling**,
running 24/7, one operator, no HA. Workloads observed: a photo library, a file
store, two small web stacks, databases, host and GPU metrics. **Roughly 10–20
scrape targets.** The orchestrator is not chosen yet, so every place where an
option assumes Kubernetes is flagged.

Three numbers are used throughout as the working envelope. They are *assumptions
of this note*, not documented figures:

| Parameter | Value used | Why |
| --- | --- | --- |
| Active time series | 10,000 / 25,000 / 50,000 (bracket) | No project documents typical exporter cardinality; see §8 |
| Scrape interval | 15 s and 60 s (both shown) | The single biggest lever on ingestion rate |
| Retention (metrics) | 30 days | "Modest window" |
| Log volume | 0.5–2 GB/day raw | Small stack, few services |
| Log retention | 7–30 days | VictoriaLogs defaults to 7 days |

### 1.1 The rule this note enforces

**A memory figure without its cardinality assumption is worthless.** Memory in
every one of these systems is dominated by the number of *active series* (metrics)
or *active streams* (logs) held in RAM, not by retention or by disk size. Where a
project publishes a memory number without stating the series count it was measured
at, this note records it as **not established**. That happens more often than not.

---

## 2. Option A — Prometheus + Grafana + Loki

### 2.1 Prometheus: resident memory

**Not established from primary sources.** The Prometheus storage documentation
covers disk capacity, retention flags, WAL and compaction, but contains **no
memory sizing statement, no memory-per-active-series figure, and no memory
formula** — <https://prometheus.io/docs/prometheus/latest/storage/>. The
Prometheus FAQ does not address RAM either
(<https://prometheus.io/docs/introduction/faq/>).

What the docs *do* establish about where memory goes:

- "The current block for incoming samples is kept in memory and is not fully
  persisted. It is secured against crashes by a write-ahead log (WAL)…
  Write-ahead log files are stored in the `wal` directory in 128MB segments…
  Prometheus will retain a minimum of three write-ahead log files. High-traffic
  servers may retain more than three WAL files in order to keep at least two
  hours of raw data." — <https://prometheus.io/docs/prometheus/latest/storage/>
- Head chunks are written out to disk and m-mapped via a queue controlled by
  `--storage.tsdb.head-chunks-write-queue-size` ("Experimental. Use with server
  mode only.") —
  <https://prometheus.io/docs/prometheus/latest/command-line/prometheus/>
- `--enable-feature=memory-snapshot-on-shutdown` "takes a snapshot of the chunks
  that are in memory along with the series information when shutting down…
  This will reduce the startup time" —
  <https://prometheus.io/docs/prometheus/latest/feature_flags/>. This addresses
  the WAL-replay memory/time spike at restart, not steady state.
- `--enable-feature=use-uncached-io` (Linux, experimental) "makes chunks writing
  bypass the page cache. Its primary goal is to reduce confusion around
  page-cache behavior and to prevent over-allocation of memory in response to
  misleading cache growth." — same page. Relevant here: on a 32 GB box, page
  cache growth from a TSDB is easily mistaken for a leak.

**Trap to avoid.** The widely-quoted rule "you should have at least three times
more RAM available than needed by the memory chunks alone" and the
`storage.local.memory-chunks` / `storage.local.target-heap-size` flags come from
the **Prometheus 1.x storage engine**
(<https://prometheus.io/docs/prometheus/1.8/storage/>). That engine was replaced
in Prometheus 2.0; those flags do not exist in current Prometheus. Any sizing
advice referencing them is not applicable.

### 2.2 Prometheus: disk and the documented formula

The only published capacity formula:

> "Prometheus stores an average of only 1-2 bytes per sample. Thus, to plan the
> capacity of a Prometheus server, you can use the rough formula:
> `needed_disk_space = retention_time_seconds * ingested_samples_per_second * bytes_per_sample`"
> — <https://prometheus.io/docs/prometheus/latest/storage/>

Also documented on that page:

- `--storage.tsdb.retention.time` defaults to `15d` if neither time nor size
  retention is set.
- `--storage.tsdb.retention.size`: "Only the persistent blocks are deleted to
  honor this retention although WAL and m-mapped chunks are counted in the total
  size. So the minimum requirement for the disk is the peak space taken by the
  wal (the WAL and Checkpoint) and `chunks_head` (m-mapped Head chunks) directory
  combined (peaks every 2 hours)."
- "We recommend setting the retention size to, at most, 80-85% of your allocated
  Prometheus disk space."
- `--storage.tsdb.wal-compression`: "you can expect the WAL size to be halved with
  little extra CPU load" (enabled by default since 2.20.0).
- "Compaction will create larger blocks containing data spanning up to 10% of the
  retention time, or 31 days, whichever is smaller."
- Official advice to reduce ingestion: "To lower the rate of ingested samples, you
  can either reduce the number of time series you scrape (fewer targets or fewer
  series per target), or you can increase the scrape interval. However, reducing
  the number of series is likely more effective, due to compression of samples
  within a series."

### 2.3 Prometheus: documented knobs that cap cardinality

From <https://prometheus.io/docs/prometheus/latest/configuration/configuration/>
(per `scrape_config`, all default to `0` = no limit):

- `sample_limit` — "Per-scrape limit on the number of scraped samples that will
  be accepted. If more than this number of samples are present after metric
  relabeling the entire scrape will be treated as failed."
- `label_limit` — limit on labels per sample.
- `target_limit` — limit on targets per scrape config (documented as
  "an experimental feature, this behaviour could change in the future").
- `keep_dropped_targets` — "Limit per scrape config on the number of targets
  dropped by relabeling that will be kept in memory."
- `extra_scrape_metrics` exposes `scrape_sample_limit` so you can alert on
  approaching the limit.

These are the only officially documented hard guards against a cardinality
explosion eating the box.

### 2.4 Grafana: the one option with a published memory floor

- "Grafana requires the following minimum system resources: **Minimum recommended
  memory: 512 MB. Minimum recommended CPU: 1 core.**" —
  <https://grafana.com/docs/grafana/latest/setup-grafana/installation/>
- Sizing tiers on the same page. **Small** = "< 25 concurrent users, < 100 alert
  rules, < 5 data sources, < 200 dashboards" → **CPU 2 cores, Memory 2–4 GB, Disk
  10–20 GB SSD**. A single operator sits at the extreme bottom of that tier, so
  the 512 MB floor is the more honest anchor and 2–4 GB is the "don't be surprised"
  ceiling.
- Important caveat quoted verbatim, because it also matters for §7: "This sizing
  guidance covers the Grafana server process only… It does not account for the
  resources required by your data sources." And: "In Grafana OSS, the alert engine
  runs in the same process as the UI and data source proxy, so alert CPU saturation
  directly competes with dashboard query performance."

### 2.5 Loki: what the official sizing guide actually covers

This is the sharpest finding in the whole note.

Loki's official sizing page — <https://grafana.com/docs/loki/latest/setup/size/> —
states: "This is only documented for **microservices/distributed mode** at this
time." Its **smallest documented tier is "Less than 100TB/month (3TB/day)"**, and
even that tier lists an Ingester at 4 Gi memory request, a Compactor at 10 Gi, and
30 base replicas totalling ~59 Gi of memory requests.

**There is no official Loki sizing guidance for single-binary, single-node, low
volume.** The Loki Helm chart confirms this: every `resources:` block in
`production/helm/loki/values.yaml`, including `singleBinary`, ships as `{}` — no
default memory request or limit —
<https://raw.githubusercontent.com/grafana/loki/main/production/helm/loki/values.yaml>.
The local install guide states no hardware requirement at all —
<https://grafana.com/docs/loki/latest/setup/install/local/>.

What *is* documented for small deployments:

- "Monolithic mode is useful for getting started quickly to experiment with Loki,
  as well as for **small read/write volumes of up to approximately 20GB per
  day**." — <https://grafana.com/docs/loki/latest/get-started/deployment-modes/>
  (`-target=all`). Our 0.5–2 GB/day is well inside this.
- The memory mechanism, from
  <https://grafana.com/docs/loki/latest/configure/bp-configure/>: "Using
  `chunk_target_size` instructs Loki to try to fill all chunks to a target
  *compressed* size of 1.5MB… Loki has a default `max_chunk_age` of 2h and
  `chunk_idle_period` of 30m **to limit the amount of memory used** as well as
  the exposure of lost logs if the process crashes… **Remembering that a chunk is
  per stream, the more streams you break up your log files into, the more chunks
  that sit in memory**, and the higher likelihood they get flushed by hitting one
  of those timeouts."
- Defaults confirmed in the configuration reference
  (<https://grafana.com/docs/loki/latest/configure/>): `chunk_target_size`
  = 1572864 (1.5 MB), `chunk_block_size` = 262144, `chunk_idle_period` = 30m,
  `max_chunk_age` = 2h, `chunk_encoding` = gzip, `flush_check_period` = 30s.
- Stream limits and their memory link, from
  <https://grafana.com/docs/loki/latest/operations/troubleshooting/troubleshoot-ingest/>:
  "**Active streams are held in memory on ingesters, and excessive streams can
  cause out-of-memory errors.**" Defaults: `max_global_streams_per_user` = 5000,
  `max_streams_per_user` = 0, "Active stream window: `chunk_idle_period`
  (default: 30 minutes)". The recommended production limits block in
  bp-configure sets `max_global_streams_per_user: 10000`.
- Cardinality guidance: "keep any single tenant in Loki to less than **100,000
  active streams**… These values are for HUGE tenants, sending more than **10 TB**
  a day. If your tenant is 10x smaller, you should have at least 10x fewer
  labels." — <https://grafana.com/docs/loki/latest/get-started/labels/bp-labels/>

**Derived, not documented:** at a homelab scale of, say, 50–200 active streams,
the in-memory chunk working set is on the order of 200 × 1.5 MB ≈ 300 MB *at
worst* (chunks are usually far from full at low volume, and are cut at
`chunk_idle_period` = 30m). Loki's real resident memory also includes the index,
query paths and Go runtime overhead, none of which are quantified anywhere
official. **Treat any single number for "Loki at 1 GB/day" as unestablished.**

### 2.6 Loki: storage on a single node

- Filesystem object store: "Great for low volume applications, proof of concepts,
  and just playing around with Loki." Cons: "**The filesystem is not supported by
  Grafana Labs for production environments**"; durability "is at the mercy of the
  filesystem itself"; a user hit problems at ~5.5 million chunk files in one
  directory — <https://grafana.com/docs/loki/latest/operations/storage/filesystem/>.
  The storage overview lists Filesystem and S3-compatible (MinIO) under
  "⚠️ Supported chunks stores, **not typically recommended for production use**" —
  <https://grafana.com/docs/loki/latest/operations/storage/>.
- The same filesystem page notes the memory trade directly: raising
  `max_chunk_age` / `chunk_idle_period` reduces the number of chunk files
  "(although they will trade for more memory consumption)".

### 2.7 Loki: the agent is no longer optional

**Promtail is end of life.** "Promtail is end of life (EOL) as of March 2, 2026.
Commercial support has ended. No future support or updates will be provided. All
future feature development will occur in Grafana Alloy… If you are currently using
Promtail, you must migrate to Alloy or another supported client." —
<https://grafana.com/docs/loki/latest/send-data/promtail/>

So option A in 2026 is **four** processes (Prometheus, Grafana, Loki, Alloy), not
three. Alloy's memory is the one figure Grafana does publish — see §4.2.

---

## 3. Option B — VictoriaMetrics single-node + Grafana + VictoriaLogs

### 3.1 VictoriaMetrics: resident memory

**No memory-per-active-series figure and no memory formula are published.** The
capacity planning section is explicit that sizing is empirical:

> "VictoriaMetrics capacity scales linearly with the available resources. The
> needed amounts of CPU and RAM highly depends on the workload - the number of
> active time series, series churn rate, query types, query qps, etc. **It is
> recommended setting up a test VictoriaMetrics for your production workload and
> iteratively scaling CPU and RAM resources until it becomes stable**"
> — <https://docs.victoriametrics.com/victoriametrics/single-server-victoriametrics/#capacity-planning>

The same section publishes a headroom rule that is directly actionable for a
memory cap:

> "It is recommended leaving the following amounts of spare resources: **50% of
> free RAM** for reducing the probability of OOM (out of memory) crashes.
> Exceeding 50% of free RAM may cause cache evictions, excessive I/O and overall
> slowdown… **50% of spare CPU**… **At least 20% of free storage space** at the
> directory pointed by `-storageDataPath`."

The cluster documentation repeats the same "no formula, run a test" position —
<https://docs.victoriametrics.com/victoriametrics/cluster-victoriametrics/#capacity-planning>.

The workload figures VictoriaMetrics *does* publish ("1.5+ million samples per
second, 50+ million active time series") are case studies at four to five orders
of magnitude above this homelab and are useless for sizing here.

### 3.2 VictoriaMetrics: memory knobs, and what they do *not* do

From the resource usage limits section of the single-server docs
(<https://docs.victoriametrics.com/victoriametrics/single-server-victoriametrics/#resource-usage-limits>)
and the flag list on the same page:

- `-memory.allowedPercent` — "Allowed percent of system memory VictoriaMetrics
  caches may occupy… **(default 60)**". `-memory.allowedBytes` overrides it.
- **Critical caveat, quoted:** "`-memory.allowedPercent` and `-memory.allowedBytes`
  limit the amounts of memory, which may be used for various internal caches at
  VictoriaMetrics. **Note that VictoriaMetrics may use more memory, since these
  flags don't limit additional memory, which may be needed on a per-query basis.**"
  → these are *not* a memory cap. An external cap (cgroup / container limit) is
  still required.
- `-search.maxMemoryPerQuery`, `-search.maxConcurrentRequests`,
  `-search.maxUniqueTimeseries`, `-search.maxSamplesPerSeries`,
  `-search.maxQueryDuration`, `-maxIngestionRate` are the documented per-query
  guards.
- Troubleshooting is emphatic that tuning caches is the wrong move: "it isn't
  recommended to change cache sizes in VictoriaMetrics, as this frequently leads
  to OOM exceptions… **it is better to migrate to a host with more memory instead
  of trying to tune cache sizes manually**" —
  <https://docs.victoriametrics.com/victoriametrics/troubleshooting/#out-of-memory-errors>.
  On a box where 32 GB is a hard ceiling, "buy more RAM" is not available; that
  makes cardinality control, not tuning, the only lever.

### 3.3 VictoriaMetrics: it scrapes on its own

Single-node VictoriaMetrics can replace the scraper entirely: "Just set
`-promscrape.config` command-line flag to the path to `prometheus.yml` config -
and VictoriaMetrics should start scraping the configured targets." —
<https://docs.victoriametrics.com/victoriametrics/single-server-victoriametrics/#how-to-scrape-prometheus-exporters-such-as-node-exporter>.
That removes one process from the stack relative to option A.

### 3.4 VictoriaMetrics: disk, retention and flash wear

- Retention: "`-retentionPeriod` - retention for stored data. Older data is
  automatically deleted. **Default retention is 1 month (31 days).** The minimum
  retention period is 24h or 1d." Also: "The maximum disk space usage for a given
  `-retentionPeriod` is going to be (`-retentionPeriod` + 1) months."
  Per-series retention filters (`-retentionFilter`) exist too. Same page, §Retention.
- Sizing method is again empirical: "if `-storageDataPath` directory size becomes
  10GB after a day-long test run on a production workload, then it will need at
  least 10GB*100=1TB of disk space for `-retentionPeriod=100d`."
- Storage engine, which is what generates write amplification: "VictoriaMetrics
  buffers the ingested data in memory for up to a second. Then the buffered data
  is written to in-memory parts… The in-memory parts are periodically persisted to
  disk… **Parts are periodically merged into bigger parts in background.**" —
  same page, §Storage. The amplification factor is **not quantified**.
- **Directly relevant to consumer SSD endurance**, quoted from the flag
  description of `-inmemoryDataFlushInterval`: "The interval for guaranteed saving
  of in-memory data to disk. The saved data survives unclean shutdowns such as OOM
  crash, hardware reset, SIGKILL, etc. **Bigger intervals may help increase the
  lifetime of flash storage with limited write cycles (e.g. Raspberry PI).**
  Smaller intervals increase disk IO load. Minimum supported value is 1s
  (default 5s)." This is the only *explicit, official* flash-endurance knob found
  in any of the projects surveyed. The identical flag exists in VictoriaLogs.

### 3.5 VictoriaLogs

- **Memory: not established.** The FAQ's "How to estimate the needed compute
  resources for the given workload?" gives no numbers and ends with the same
  empirical instruction: "The best approach to estimate the needed compute
  resources for the given workload is to start a VictoriaLogs, to ingest a share
  (1%-10%) of your production logs into it, and to execute typical queries on it,
  while measuring the consumed compute resources." —
  <https://docs.victoriametrics.com/victorialogs/faq/>
- What it does say about small hardware: "It is resource-efficient and fast. It
  uses up to **30x less RAM** and up to **15x less disk space** than other
  solutions such as Elasticsearch and Grafana Loki… **It runs smoothly on
  Raspberry PI** and on servers with hundreds of CPU cores and terabytes of RAM."
  and "**No need in tuning for VictoriaLogs** - it uses reasonable defaults for
  command-line flags, which are automatically adjusted for the available CPU and
  RAM resources." — <https://docs.victoriametrics.com/victorialogs/>
  **Label this honestly:** the 30x/15x claims are vendor comparisons; the docs
  back them with blog articles and a user report, **not with a stated
  methodology, workload, or hardware**. They are not usable as sizing input.
- Same 50%-headroom rule as VictoriaMetrics: "50% of free RAM for reducing the
  probability of OOM (out of memory) crashes and slowdowns during temporary spikes
  in workload."
- `-memory.allowedPercent` default 60, with the same "caches only, not a cap"
  semantics as VictoriaMetrics.
- Bounded by design against the classic logging blowup: max 2000 fields per log
  entry, hardcoded, "since this may increase RAM and CPU usage"; field-name length
  also hardcoded — <https://docs.victoriametrics.com/victorialogs/faq/>.
- Retention: "By default, VictoriaLogs stores log entries with timestamps in the
  time range `[now-7d, now]`… **E.g. it uses the retention of 7 days.**"
  Disk-bounded retention is first-class: `-retention.maxDiskSpaceUsageBytes` and
  `-retention.maxDiskUsagePercent` (mutually exclusive) drop old per-day
  partitions. "**VictoriaLogs usually compresses logs by 10x or more times.**"
  Caveat: "VictoriaLogs keeps at least two last days of data", so the disk cap can
  be exceeded, and disk usage "is checked periodically", so it can overshoot
  between checks — <https://docs.victoriametrics.com/victorialogs/#retention>.
- **No separate shipper needed**: VictoriaLogs ingests journald and syslog
  natively (`-journald.*`, `-syslog.listenAddr.*` flags on the same page), as well
  as Filebeat / Fluentbit / Vector. This is the second process removed relative to
  option A.

---

## 4. Option C — the lighter alternatives the projects themselves document

### 4.1 Prometheus agent mode

Stable, top-level flag: `--agent` "Run Prometheus in 'Agent mode'" —
<https://prometheus.io/docs/prometheus/latest/command-line/prometheus/>. Dedicated
flags: `--storage.agent.path`, `--storage.agent.wal-compression` (default true),
`--storage.agent.retention.min-time` 5m, `--storage.agent.retention.max-time` 4h.

The project's own description of the mechanism and the trade —
<https://prometheus.io/blog/2021/11/16/agent/> (Prometheus project blog, first
party):

> "The Agent mode optimizes Prometheus for the remote write use case. **It
> disables querying, alerting, and local storage**, and replaces it with a
> customized TSDB WAL… Our customized Agent TSDB WAL removes the data immediately
> after successful writes… **This means that we don't need to build chunks of data
> in memory. We don't need to maintain a full index for querying purposes.
> Essentially the Agent mode uses a fraction of the resources that a normal
> Prometheus server would use in a similar situation.**"

And the caveat, from the same post: "**With the introduction of the Agent mode, the
original Prometheus server mode still stays as the recommended, stable and
maintained mode. Agent mode with remote storage brings additional complexity. Use
with care.**"

**No quantitative figure is given.** More importantly for this node: agent mode
does not remove the storage problem, it *relocates* it. On a single machine you
still need a remote-write receiver, so agent mode only makes sense here as the
scraper in front of VictoriaMetrics — and VictoriaMetrics can scrape by itself
(§3.3), so this is usually a process you do not need.

### 4.2 Grafana Alloy — the only published per-series memory rule of thumb

<https://grafana.com/docs/alloy/latest/introduction/estimate-resource-usage/>,
labelled by Grafana as "based on operational experience of some of the Alloy
maintainers", with the disclaimer "The resource usage depends on the workload,
hardware, and the configuration used."

> Prometheus metrics — "As a rule of thumb, **per each 1 million active series**
> and with the default scrape interval, you can expect to use approximately:
> **0.4 CPU cores, 11 GiB of memory**, 1.5 MiB/s of total network bandwidth…
> These recommendations are based on deployments that use **clustering**".
>
> Loki logs — "As a rule of thumb, **per each 1 MiB/second of logs ingested**, you
> can expect to use approximately: **1 CPU core, 120 MiB of memory**… These
> recommendations are based on **Kubernetes DaemonSet deployments**".

**Derived from those documented rates, with our assumptions stated:**

| Workload | Documented rate | This node |
| --- | --- | --- |
| 25,000 active series scraped+forwarded | 11 GiB / 1 M series ≈ 0.4 KiB/series | ≈ **11 MiB** |
| 2 GB/day logs = 0.023 MiB/s | 120 MiB per 1 MiB/s | ≈ **3 MiB** |

Both round to "noise plus Go runtime floor" — realistically **50–150 MB resident**
for the process. The load-bearing conclusion: **collection is cheap; storage is
where the 32 GB goes.** Any plan that saves memory by swapping agents is
optimising the wrong component.

Kubernetes caveat: both Alloy figures were measured in Kubernetes (clustering /
DaemonSet). Alloy itself runs fine standalone, but the numbers carry that
provenance.

### 4.3 Netdata — the only project that publishes a complete memory formula

<https://learn.netdata.cloud/docs/netdata-agent/resource-utilization/> ("Netdata's
measured resource usage"):

| Resource | Netdata's footprint |
| --- | --- |
| CPU | 1%–5% of a single core with default settings; up to 5%–20% in production |
| RAM | **100–200 MB on an empty system; 250–350 MB in typical production** |
| Disk | **~4 GiB by default** (3 GiB metrics plus metadata), configurable per tier |

And the formula, from
<https://learn.netdata.cloud/docs/netdata-agent/resource-utilization/ram>:

> "Using the default Database Tier configuration, Netdata needs about **16KiB per
> unique metric collected**, independently of the data collection frequency."
>
> "`memory = UNIQUE_METRICS x 16KiB + CONFIGURED_CACHES`. The default
> `CONFIGURED_CACHES` is 32MiB."

Per-entry breakdown for centralisation ("Parent") nodes on the same page: 1 KiB
per metric with retention (index), **20 KiB per metric currently collected**
(16 KiB db + 4 KiB collection structures), **5 KiB per metric with ML models**,
10 KiB per node with retention, 512 KiB per node received, 512 KiB per node sent.
"Each metric currently being collected needs (1 index + 20 collection + 5 ml) =
**26 KiB**."

**Derived with our assumptions:** at 25,000 unique metrics, `25000 × 16 KiB +
32 MiB` ≈ **423 MiB**; using the 26 KiB "currently collected" figure instead,
≈ 668 MiB. This is the *only* option in this note where a defensible memory number
can be computed in advance from official documentation.

Documented memory knobs, same pages: number of database tiers ("The number of
database tiers directly affects memory consumption. More tiers mean higher memory
usage"), database mode (`ram` vs `dbengine`), disabling unnecessary collectors,
disabling machine learning, lowering sample frequency ("Lowering the sampling
frequency (e.g., 1-second to 2-second intervals) can halve CPU usage"), and since
2.1 `[db].dbengine use all ram for caches` plus `[db].dbengine out of memory
protection` ("by default 10% of total system RAM, but not more than 5GiB. When the
amount of free memory is less than this, Netdata automatically starts releasing
memory from its caches to avoid getting out of memory").

Disk, from
<https://learn.netdata.cloud/docs/netdata-agent/resource-utilization/disk-&-retention>:
default 3 tiers, 1 GiB each, "**expect about 4 GiB of disk usage under normal
conditions**"; tier0 per-second at **0.6 bytes on disk per sample**, tier1
per-minute at 6 bytes, tier2 per-hour at 18 bytes; "with default settings and an
ingestion rate of about 4,000 metrics per second, Netdata provides about 14 days
of high resolution (per-second) data, 3 months of medium resolution (per-minute)
data, and more than 1 year of low resolution (per-hour) data."

Netdata assumes no orchestrator. It is a standalone agent with a built-in database
and UI.

---

## 5. Disk usage and write volume per day, against ~320 TBW

### 5.1 Metrics — computed from the documented Prometheus formula

Inputs: the documented `1–2 bytes per sample`
(<https://prometheus.io/docs/prometheus/latest/storage/>) and our own series /
interval assumptions. **The arithmetic below is derived by this note, not
published by any project.** 2 bytes/sample is used (the pessimistic end).

| Active series | Scrape interval | Samples/s | Stored bytes/day | 30-day retention |
| --- | --- | --- | --- | --- |
| 10,000 | 15 s | 667 | ~115 MB | ~3.5 GB |
| 10,000 | 60 s | 167 | ~29 MB | ~0.9 GB |
| 25,000 | 15 s | 1,667 | ~288 MB | ~8.6 GB |
| 25,000 | 60 s | 417 | ~72 MB | ~2.2 GB |
| 50,000 | 15 s | 3,333 | ~576 MB | ~17.3 GB |
| 50,000 | 60 s | 833 | ~144 MB | ~4.3 GB |

**Write volume ≠ stored bytes.** Every sample is first written to the WAL, head
chunks are m-mapped to disk, and blocks are rewritten by compaction "up to 10% of
the retention time, or 31 days, whichever is smaller" (Prometheus storage docs).
VictoriaMetrics does the equivalent via background part merges (§3.4). **Neither
project publishes a write-amplification factor — that is not established from
primary sources.**

Bounding it anyway, since the SSD question needs an answer: take the worst row
above (576 MB/day of *stored* data) and assume a brutal **10× total write
amplification** across WAL + head chunks + compaction/merge:

- ≈ 5.8 GB written/day → ≈ **2.1 TB/year**
- Against a **320 TBW** rating: ≈ **150 years**.

Even at 50× amplification it is ~30 years. **Conclusion: at 10–20 targets, a
metrics stack does not meaningfully threaten a 320 TBW consumer SSD.** The
endurance concern is real in principle and misplaced at this scale — RAM is the
binding constraint, not TBW. (Netdata is the same order: ~4,000 metrics/s × 0.6
bytes tier0 ≈ 0.2 GB/day.)

The one place the SSD argument still bites is **flush frequency**, not volume:
VictoriaMetrics/VictoriaLogs `-inmemoryDataFlushInterval` defaults to 5s and the
docs explicitly tie longer intervals to "increase the lifetime of flash storage
with limited write cycles" (§3.4). That is a small-write / erase-block concern,
and it is the documented knob for it.

### 5.2 Logs

- Loki monolithic is documented up to "**approximately 20GB per day**"
  (<https://grafana.com/docs/loki/latest/get-started/deployment-modes/>), which is
  10–40× our assumed volume. No bytes-on-disk-per-GB-ingested figure is published.
- VictoriaLogs: "usually compresses logs by 10x or more times"
  (<https://docs.victoriametrics.com/victorialogs/#retention>). Derived: 2 GB/day
  raw → ~200 MB/day stored → ~6 GB for 30 days, and disk-capped retention is a
  first-class flag.
- At 2 GB/day raw with 10× amplification: ~7 TB/year, ~45 years against 320 TBW.
  Logs are the larger of the two writers, and still not the binding constraint.

---

## 6. What each project documents about constrained hardware

| Project | Explicit constrained-hardware statement | Documented memory-reducing knobs |
| --- | --- | --- |
| Prometheus | None found. Agent mode blog acknowledges "every GB of memory and every CPU core used on edge clusters matters" but publishes no figures | Longer scrape interval; fewer series (docs say this is more effective); `sample_limit` / `label_limit` / `target_limit` / `keep_dropped_targets`; `--storage.tsdb.retention.time` / `.size`; `--enable-feature=use-uncached-io`; agent mode (drops querying, alerting, local storage) |
| Grafana | 512 MB minimum documented | Fewer alert rules and dashboards, longer dashboard refresh intervals (the sizing page names alert rules and short refresh intervals as "the two most common reasons a deployment outgrows its initial sizing") |
| Loki | None for single-node. Filesystem store is "Great for low volume applications, proof of concepts" but "not supported… for production environments" | `max_global_streams_per_user`; fewer labels / lower stream cardinality; `chunk_target_size`, `max_chunk_age`, `chunk_idle_period` (raising them cuts file count but "trade for more memory consumption"); `chunk_encoding: snappy`; ingestion rate limits |
| VictoriaMetrics | ARM build "may run on Raspberry Pi or on energy-efficient ARM servers"; `-inmemoryDataFlushInterval` explicitly targets flash lifetime | `-retentionPeriod` (default 31d), `-retentionFilter`, `-maxIngestionRate`, `-search.max*` family, `-memory.allowedPercent` (caches only). Docs advise *against* cache tuning |
| VictoriaLogs | "**It runs smoothly on Raspberry PI**"; "No need in tuning" | `-retentionPeriod` (default 7d), `-retention.maxDiskSpaceUsageBytes` / `-retention.maxDiskUsagePercent`, `-insert.maxFieldsPerLine`, `-internStringDisableCache` ("may reduce memory usage at the cost of higher CPU usage"), `-inmemoryDataFlushInterval` |
| Grafana Alloy | Publishes per-series and per-MiB/s rates (§4.2) | Scrape fewer series; filter/relabel before forwarding |
| Netdata | "A standalone Netdata Agent has a small footprint and runs comfortably on a minimal system" | Fewer database tiers; `ram` database mode; disable collectors; disable ML (5 KiB/metric); lower sample frequency; `out of memory protection` |

---

## 7. Alerting: inhibition, grouping, and keeping the set small

### 7.1 The primary statement on alert-set size

From the Prometheus project's own alerting practices page —
<https://prometheus.io/docs/practices/alerting/>:

> "We recommend that you read *My Philosophy on Alerting* based on Rob Ewaschuk's
> observations at Google. To summarize: **keep alerting simple, alert on symptoms,
> have good consoles to allow pinpointing causes, and avoid having pages where
> there is nothing to do.**"
>
> "**Aim to have as few alerts as possible, by alerting on symptoms that are
> associated with end-user pain rather than trying to catch every possible way
> that pain could be caused.** Alerts should link to relevant consoles and make it
> easy to figure out which component is at fault."
>
> "**Allow for slack in alerting to accommodate small blips.**"
>
> "Only page on latency at one point in a stack. If a lower-level component is
> slower than it should be, but the overall user latency is fine, then there is no
> need to page."
>
> Metamonitoring: "It is important to have confidence that monitoring is working.
> Accordingly, have alerts to ensure that Prometheus servers, Alertmanagers,
> PushGateways, and other monitoring infrastructure are available and running
> correctly… **a blackbox test that alerts are getting from PushGateway to
> Prometheus to Alertmanager to email is better than individual alerts on each.**"

That is the closest thing to an official "keep the set actionable" rule any of
these projects publish. There is **no documented numeric cap** on alert count.
The nearest quantitative anchor is Grafana's own sizing tier — "Small: < 100 alert
rules" — plus its warning that in Grafana OSS "the alert engine runs in the same
process as the UI and data source proxy"
(<https://grafana.com/docs/grafana/latest/setup-grafana/installation/>).

### 7.2 Alertmanager: grouping and inhibition

From <https://prometheus.io/docs/alerting/latest/alertmanager/>:

> **Grouping** — "Grouping categorizes alerts of similar nature into a single
> notification. This is especially useful during larger outages when many systems
> fail at once and hundreds to thousands of alerts may be firing simultaneously."
>
> **Inhibition** — "Inhibition is a concept of suppressing notifications for
> certain alerts if certain other alerts are already firing. Example: An alert is
> firing that informs that an entire cluster is not reachable. Alertmanager can be
> configured to mute all other alerts concerning this cluster if that particular
> alert is firing. **This prevents notifications for hundreds or thousands of
> firing alerts that are unrelated to the actual issue.**"

Configuration semantics, from
<https://prometheus.io/docs/alerting/latest/configuration/>:

- `<inhibit_rule>`: "An inhibition rule mutes an alert (target) matching a set of
  matchers when an alert (source) exists that matches another set of matchers.
  **Both target and source alerts must have the same label values for the label
  names in the `equal` list.**" Also: "a missing label and a label with an empty
  value are the same thing"; and self-inhibition is prevented, but "we recommend
  to choose target and source matchers in a way that alerts never match both
  sides."
- `group_by` — "The labels by which incoming alerts are grouped together."
  `group_by: ['...']` "effectively disables aggregation entirely… **This is
  unlikely to be what you want, unless you have a very low alert volume**".
  (A one-operator homelab is arguably exactly that case — worth noting.)
- Timing defaults: `group_wait` **30s**, `group_interval` **5m**,
  `repeat_interval` **4h**.
- Documented interaction that matters for a small stack: "**if `group_wait` is too
  short then the first notification might not contain the complete set of expected
  alerts, and alerts that should be inhibited might not be inhibited if the
  inhibiting alerts have not arrived in time**." Inhibition correctness depends on
  `group_wait`.
- "If an alert is resolved before `group_wait` has elapsed, no notification will be
  sent for that alert. **This reduces noise of flapping alerts.**"

### 7.3 If Grafana-managed alerting is used instead

- Grouping defaults: "By default, notification policies in Grafana group alerts by
  the alert rule… using the `alertname` and `grafana_folder` labels." Group wait
  default **30 seconds**, group interval default **5 minutes** —
  <https://grafana.com/docs/grafana/latest/alerting/fundamentals/notifications/group-alert-notifications/>
- Inhibition: "**Available in Grafana 13 or higher.**" And the design caveat,
  quoted: "**Inhibition rules are intended for compatibility with configurations
  imported from Prometheus Alertmanager or Mimir. They have no dedicated
  management UI in Grafana by design.** If not carefully configured, inhibition
  rules can silently suppress alerts and make issues harder to detect. Consider
  silences or mute timings for most suppression use cases." Management is via the
  Grafana App Platform API only, and that API is beta (v1beta1) —
  <https://grafana.com/docs/grafana/latest/alerting/configure-notifications/inhibition-rules/>

**Practical consequence:** if inhibition matters, standalone Alertmanager (or
vmalert + Alertmanager) gives it as a first-class, file-configurable, GitOps-able
feature; Grafana-managed alerting treats it as an import-compatibility escape
hatch with no UI.

---

## 8. Not established from primary sources

These gaps are findings, not omissions:

1. **Prometheus resident memory per active series.** No figure, no formula, in any
   current Prometheus documentation. The only Prometheus-published memory sizing
   rule belongs to the removed 1.x storage engine.
2. **VictoriaMetrics memory per active series.** Explicitly replaced by "set up a
   test instance and scale iteratively".
3. **VictoriaLogs memory at any volume.** Explicitly replaced by "ingest 1%–10% of
   production and measure".
4. **Loki memory for single-binary / low volume.** The official sizing page covers
   microservices only, starting three orders of magnitude above this workload; the
   Helm chart ships no default memory requests.
5. **Write amplification factor** for Prometheus TSDB, VictoriaMetrics parts
   merging, or Loki chunk flushing. The mechanisms are documented; the multipliers
   are not.
6. **Typical exporter cardinality.** Neither Prometheus, node_exporter, nor any
   GPU exporter publishes an expected series count, so the single most important
   input to every memory estimate above must be measured on this machine.
7. **Any documented numeric limit on "how many alerts is too many."** Only
   qualitative guidance exists.
8. **The VictoriaLogs "30x less RAM than Elasticsearch and Grafana Loki" and "15x
   less disk" claims.** Vendor comparisons with no stated methodology, workload or
   hardware in the documentation.

## 9. Where an option assumes Kubernetes

- **Loki's official sizing guidance** is expressed as CPU/memory *requests* and
  *replicas* — Kubernetes-native, microservices-only.
- **Loki Simple Scalable Deployment** is "the default configuration installed by
  the Loki Helm Chart" and is "being deprecated and will be removed with the Loki
  4.0 release" — <https://grafana.com/docs/loki/latest/get-started/deployment-modes/>.
  Monolithic (`-target=all`) remains valid and is the non-Kubernetes path.
- **Loki `stream_limit` rebalancing behaviour** in the troubleshooting docs is
  described entirely in terms of ingester autoscaling and ring changes — not
  applicable to a single binary.
- **Alloy's published resource rates** were measured with clustering and
  Kubernetes DaemonSets.
- **Prometheus, VictoriaMetrics, VictoriaLogs and Netdata** publish no
  Kubernetes-dependent guidance for the single-node case.

---

## 10. What the evidence supports

Not a decision — the reasoning a decision can be built on.

### 10.1 A defensible memory cap for this machine

The evidence supports **a hard external cap of 3 GB total for the observability
stack on this node (~9% of 32 GB)**, allocated roughly:

| Component | Cap | Basis |
| --- | --- | --- |
| Grafana | 512 MB–1 GB | Documented 512 MB minimum; Small tier is 2–4 GB but sized for < 25 concurrent users, and this node has one |
| Metrics store | 1–1.5 GB | Nothing documented; must be measured. Set the cap, then measure against it |
| Log store | 512 MB–1 GB | Nothing documented for either candidate at this volume |
| Collector(s) | 128–256 MB | Alloy's documented rates give ~11 MiB at 25k series; the floor is Go runtime, not workload |

The reasoning:

1. **The cap must be external.** VictoriaMetrics documents plainly that
   `-memory.allowedPercent` / `-memory.allowedBytes` "don't limit additional
   memory, which may be needed on a per-query basis". Prometheus and Loki document
   no internal cap at all. Therefore the only enforceable cap is a cgroup limit
   (`systemd` `MemoryMax=` or a container memory limit). **Without it, none of
   these projects will honour a budget.**
2. **The cap must be sized with headroom, not to observed steady state.** Both
   VictoriaMetrics and VictoriaLogs state "50% of free RAM" as the OOM-avoidance
   margin. Applied here: a 1.5 GB cap means the design target for steady-state
   resident memory is ~750 MB.
3. **The cap is cheap because the risk is asymmetric.** A cardinality mistake in a
   metrics TSDB is unbounded; the machine has no swap-in-more-RAM escape and is a
   named SPOF. A cap converts "the photo library gets OOM-killed" into "the
   monitoring gets OOM-killed", which is the correct failure ordering.
4. **Cardinality limits should be set on day one, not after the first incident.**
   `sample_limit` / `label_limit` on the Prometheus side, or
   `-maxIngestionRate` / `-search.maxUniqueTimeseries` on the VictoriaMetrics side,
   and `max_global_streams_per_user` on the Loki side. These are the only
   documented guards against the failure mode that actually kills small stacks.
5. **The SSD endurance argument does not constrain this decision.** Derived from
   the documented 1–2 bytes/sample, even 50k series at 15s with 10× write
   amplification lands around 2 TB/year against a 320 TBW rating. Scrape interval
   and retention should be chosen for memory and usefulness, not for TBW. The one
   real flash consideration is flush *frequency*, for which VictoriaMetrics and
   VictoriaLogs document `-inmemoryDataFlushInterval`.
6. **Do not spend the budget on collectors.** Alloy's documented ~0.4 KiB/active
   series means the entire scrape path for this workload costs single-digit MB of
   actual data structures. Swapping agents to save memory is optimising the wrong
   component.

### 10.2 What each option gives up

**Prometheus + Grafana + Loki**
- Gives up: *predictability*. This is the only option where the primary sources
  provide neither a memory figure nor a formula for either the metrics store or
  the log store at this scale, and Loki's official sizing guidance starts at
  3 TB/day.
- Gives up: *process count*. Promtail is EOL as of 2026-03-02, so the stack is
  Prometheus + Grafana + Loki + Alloy — four processes, four Go runtimes.
- Gives up: *a supported storage path*. Filesystem chunk storage is documented as
  not supported for production; the alternative is running MinIO, which adds
  another process and more RAM.
- Keeps: the largest ecosystem, PromQL/LogQL, and the most transferable knowledge.

**VictoriaMetrics single-node + Grafana + VictoriaLogs**
- Gives up: *published sizing* as well — both projects explicitly replace formulas
  with "run a test and extrapolate". The difference from option A is that they say
  so plainly, and they publish an actionable headroom rule (50% free RAM) and a
  hard disk-bounded retention mechanism.
- Gives up: *vendor diversity*. Metrics and logs both come from one vendor, and
  the comparative claims that make the option attractive (30x RAM, 15x disk) are
  unmethodologised marketing.
- Gives up: *Loki/LogQL familiarity* — LogsQL is a different query language.
- Keeps: fewer processes (VictoriaMetrics scrapes via `-promscrape.config`;
  VictoriaLogs ingests journald/syslog natively — no separate agent required for
  either), Prometheus-compatible remote-write and PromQL-compatible querying, an
  explicit flash-lifetime knob, and disk-capped log retention which is the single
  most useful safety feature for a fixed-size SSD.

**Netdata**
- Gives up: *the Prometheus data model as the centre of gravity* — dashboards,
  alerting and long-term querying follow Netdata's model, and integrating with
  Grafana/PromQL becomes a secondary path.
- Gives up: *CPU headroom* — per-second collection by default, plus ML model
  training on by default at 5 KiB/metric.
- Keeps: **the only option whose memory can be computed in advance from official
  documentation** (`UNIQUE_METRICS × 16 KiB + 32 MiB`), a documented ~4 GiB disk
  ceiling with automatic multi-tier downsampling, documented OOM self-protection,
  and no orchestrator assumption anywhere.

**Prometheus agent mode / Alloy as a "lighter" answer**
- Gives up: *the premise*. Agent mode "disables querying, alerting, and local
  storage"; it relocates storage rather than shrinking it. On a single node with
  no remote backend, it buys nothing that VictoriaMetrics' built-in scraper does
  not already provide. Its real use here would be as the collector in front of a
  local store — an extra process for no documented memory saving.

### 10.3 On alerting

The evidence supports treating the alert set as a design constraint from the
start, on the project's own terms: "**Aim to have as few alerts as possible**",
alert on symptoms, "avoid having pages where there is nothing to do", and add
metamonitoring as a single blackbox path rather than per-component alerts
(<https://prometheus.io/docs/practices/alerting/>). Grouping (`group_by`,
`group_wait` 30s / `group_interval` 5m / `repeat_interval` 4h) and inhibition are
the two documented mechanisms for collapsing a correlated failure into one
notification — and on a single-node platform where one machine failing takes
everything with it, **inhibition on a root-cause "node down" alert is the
mechanism that matches this topology**. That is an argument for standalone
Alertmanager, where inhibition is a first-class file-configured feature, over
Grafana-managed alerting, where it is documented as an import-compatibility
mechanism with no UI, gated on Grafana 13, and managed only via a beta API.

---

## Source index

Prometheus
- <https://prometheus.io/docs/prometheus/latest/storage/>
- <https://prometheus.io/docs/prometheus/latest/configuration/configuration/>
- <https://prometheus.io/docs/prometheus/latest/command-line/prometheus/>
- <https://prometheus.io/docs/prometheus/latest/feature_flags/>
- <https://prometheus.io/docs/introduction/faq/>
- <https://prometheus.io/docs/practices/alerting/>
- <https://prometheus.io/docs/alerting/latest/alertmanager/>
- <https://prometheus.io/docs/alerting/latest/configuration/>
- <https://prometheus.io/blog/2021/11/16/agent/> (project blog, first party)
- <https://prometheus.io/docs/prometheus/1.8/storage/> (obsolete 1.x engine — cited only to mark it obsolete)

Grafana / Loki / Alloy
- <https://grafana.com/docs/grafana/latest/setup-grafana/installation/>
- <https://grafana.com/docs/grafana/latest/alerting/fundamentals/notifications/notification-policies/>
- <https://grafana.com/docs/grafana/latest/alerting/fundamentals/notifications/group-alert-notifications/>
- <https://grafana.com/docs/grafana/latest/alerting/configure-notifications/inhibition-rules/>
- <https://grafana.com/docs/loki/latest/setup/size/>
- <https://grafana.com/docs/loki/latest/setup/install/local/>
- <https://grafana.com/docs/loki/latest/get-started/deployment-modes/>
- <https://grafana.com/docs/loki/latest/get-started/labels/bp-labels/>
- <https://grafana.com/docs/loki/latest/configure/>
- <https://grafana.com/docs/loki/latest/configure/bp-configure/>
- <https://grafana.com/docs/loki/latest/operations/storage/>
- <https://grafana.com/docs/loki/latest/operations/storage/filesystem/>
- <https://grafana.com/docs/loki/latest/operations/troubleshooting/troubleshoot-ingest/>
- <https://grafana.com/docs/loki/latest/send-data/promtail/>
- <https://raw.githubusercontent.com/grafana/loki/main/production/helm/loki/values.yaml>
- <https://grafana.com/docs/alloy/latest/introduction/estimate-resource-usage/>

VictoriaMetrics / VictoriaLogs
- <https://docs.victoriametrics.com/victoriametrics/single-server-victoriametrics/>
- <https://docs.victoriametrics.com/victoriametrics/cluster-victoriametrics/>
- <https://docs.victoriametrics.com/victoriametrics/troubleshooting/>
- <https://docs.victoriametrics.com/victoriametrics/faq/>
- <https://docs.victoriametrics.com/victorialogs/>
- <https://docs.victoriametrics.com/victorialogs/faq/>

Netdata
- <https://learn.netdata.cloud/docs/netdata-agent/resource-utilization/>
- <https://learn.netdata.cloud/docs/netdata-agent/resource-utilization/ram>
- <https://learn.netdata.cloud/docs/netdata-agent/resource-utilization/disk-&-retention>
