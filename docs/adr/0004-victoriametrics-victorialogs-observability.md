---
status: accepted
date: 2026-08-07
tags: [observability, memory, alerting]
---

# VictoriaMetrics and VictoriaLogs under a 3 GiB cap, with standalone Alertmanager

The cap holds: ADR-0002 already fixed observability's envelope at 3 GiB, roughly
9% of the 32 GiB ceiling, and nothing found while resolving this ticket disturbs
it. The research this ADR draws from defends that figure on its own terms, not
just by inheritance: the cap is cheap because the risk it guards against is
asymmetric (a cardinality mistake in a TSDB is unbounded, and this machine has
no swap-in-more-RAM escape), and it is sized with margin rather than to
observed steady state, since nothing surveyed publishes a number to size to
exactly. What remains to decide is which stack runs inside that envelope, how
the envelope splits between its parts, and which few alerts are worth waking
someone for. Findings throughout are from
`docs/reference/research-observability-memory-footprint.md` (#17), which surveyed
Prometheus, Grafana, Loki, VictoriaMetrics, VictoriaLogs, Alloy and Netdata
against official documentation only.

## The stack

**VictoriaMetrics single-node plus VictoriaLogs, with Grafana for dashboards.**

Three candidates were compared. Prometheus with Grafana and Loki carries the
largest ecosystem and the most transferable query language, but the research
found no memory figure or formula for either its metrics or its log store at
this scale, and Loki's own sizing guidance starts three orders of magnitude
above this workload. Promtail, its log shipper, reached end of life on
2026-03-02, so the stack now needs a fourth process (Alloy) just to keep
shipping logs, and Loki's filesystem storage is documented as unsupported for
production, with the supported alternative (an object store such as MinIO)
adding a fifth.

Netdata is the only option whose memory a reader can compute in advance from
official documentation (`UNIQUE_METRICS x 16 KiB + 32 MiB`, roughly 423 to
668 MB at 25,000 metrics), and it assumes no orchestrator at all. It was set
aside because it leaves the Prometheus data model entirely: dashboards,
alerting and querying follow Netdata's own model instead, machine learning
runs by default at a further 5 KiB per metric, and nothing else in this
project's architecture points away from Prometheus-compatible tooling.

VictoriaMetrics and VictoriaLogs publish no memory formula either, and say so
directly rather than leaving a gap: both name "set up a test instance and
scale iteratively" as the sizing method, and both publish an actionable
margin rule (50% of free RAM as the OOM-avoidance buffer). Against Prometheus
and Loki, they remove two processes rather than add one: VictoriaMetrics
scrapes Prometheus-format targets on its own (`-promscrape.config`), and
VictoriaLogs ingests journald and syslog natively, so neither metrics nor logs
need a separate agent. VictoriaLogs also enforces disk-bounded retention as a
first-class flag (`-retention.maxDiskSpaceUsageBytes`), the single most useful
safety property for a fixed-size SSD that nothing in the Prometheus stack
offers natively. Both remain PromQL-compatible for querying and
remote-write-compatible for ingestion, so the query knowledge this project
already leans on is not discarded.

The write-budget side is a check, not a driver: ADR-0002 allocated
observability 10 GB/day of writes. The research's own worst-case arithmetic
(50,000 series at 15 s scrape, 10x write amplification) lands near 2 TB/year,
about 150 years against the drives' 320 TBW rating; logs at 2 GB/day raw with
10x amplification land near 45 years. Neither writer binds in practice; the
flash-lifetime concern that does apply is flush *frequency*, for which
VictoriaMetrics and VictoriaLogs both document `-inmemoryDataFlushInterval` as
the explicit knob.

## Alerting

**Standalone Alertmanager, paired with vmalert for rule evaluation** (vmalert
evaluates Prometheus-compatible alerting rules against VictoriaMetrics;
Alertmanager groups, deduplicates and routes the resulting notifications).

Grafana-managed alerting was the alternative. Its own documentation describes
inhibition as available only "in Grafana 13 or higher," intended for
"compatibility with configurations imported from Prometheus Alertmanager or
Mimir," with "no dedicated management UI in Grafana by design," managed only
through a beta (v1beta1) API. This platform is one physical machine: a single
node going down takes every service with it, so muting the resulting flood
behind one root-cause alert is not an edge case here, it is the normal failure
mode. Alertmanager treats that as a first-class, file-configured feature;
Grafana-managed alerting treats it as an import-compatibility escape hatch.

Four alert categories, chosen to stay small and symptom-based rather than
exhaustive, per Prometheus's own alerting guidance to "aim to have as few
alerts as possible" and "avoid having pages where there is nothing to do":

1. **Node unreachable.** The root cause. Every other alert is inhibited when
   this one fires, since one machine failing takes everything down at once.
2. **Disk space near full**, NVMe or NAS.
3. **Backup has not succeeded within its RPO window.** 24 hours for Immich
   originals, 7 days for everything regenerable from Git, per #11.
4. **Certificate expiring soon.**

The exact expressions and thresholds are implementation, written when the
platform is built, not decided here.

## The cap, split

| Component | Cap |
| --- | --- |
| VictoriaMetrics | 1.25 GiB |
| VictoriaLogs | 768 MiB |
| Grafana | 768 MiB |
| vmalert + Alertmanager | 256 MiB |

The four rows sum to exactly 3 GiB (3072 MiB): removing the separate collector
that a Prometheus-based stack would have needed freed the room this split
spends instead on vmalert and Alertmanager, with nothing left over. Every
figure is a cgroup limit (`systemd` `MemoryMax=` or a container memory limit),
not an internal setting: VictoriaMetrics states plainly that
`-memory.allowedPercent` and `-memory.allowedBytes` bound only internal
caches, "since these flags don't limit additional memory, which may be needed
on a per-query basis." Neither Prometheus, Loki, nor VictoriaLogs document an
internal cap at all. Without an external cap, none of these projects honour a
budget.

Cardinality guards are set from the start, not after a first incident:
`-maxIngestionRate` and `-search.maxUniqueTimeseries` on the VictoriaMetrics
side, `max_global_streams_per_user` on the VictoriaLogs side. A cardinality
mistake in a TSDB is unbounded, and this machine has no swap-in-more-RAM
escape; the cap converts "the photo library gets OOM-killed" into "the
monitoring gets OOM-killed," which is the correct failure ordering on a named
SPOF.

## Decision

VictoriaMetrics and VictoriaLogs, both self-scraping and self-ingesting with
no separate agent, Grafana for dashboards, vmalert plus standalone Alertmanager
for alerting with inhibition on node-down as the root-cause alert. Total
budget 3 GiB, split as above, every limit enforced externally by cgroup.

## Alternatives rejected

**Prometheus, Grafana, Loki, Alloy.** The largest ecosystem, and the only
candidate where the research found no usable memory sizing for either store at
this scale. Promtail's 2026-03-02 end of life forces a fourth process; Loki's
supported storage path forces a fifth. Kept in mind only as the option to
revisit if PromQL/LogQL familiarity or ecosystem breadth ever outweighs the
process count.

**Netdata.** The only stack with a computable memory formula in advance and no
orchestrator assumption, set aside because it replaces the Prometheus data
model wholesale, a change nothing else in this project's architecture asks
for, and runs machine learning by default at a further cost per metric that
would need disabling on day one anyway.

**Grafana-managed alerting.** Simpler by one fewer process, and rejected
because inhibition, the one mechanism that matches a single-node platform's
failure mode, is documented as an import-compatibility feature with no UI,
gated on a recent Grafana version, and driven only by a beta API.

## Consequences

- Every observability component runs under an external cgroup memory limit
  from the day it is deployed; none of the software's own internal settings
  are trusted as a cap.
- vmalert and Alertmanager both enter the configuration surface as processes
  in their own right, budgeted for above, not assumed to be free riders on
  Grafana.
- Cardinality guards (`-maxIngestionRate`, `-search.maxUniqueTimeseries`,
  `max_global_streams_per_user`) are set at first deployment, not added
  reactively after an incident.
- The alert set stays at four categories until a real gap shows up in
  operation; adding alerts is a deliberate decision against the "as few
  alerts as possible" guidance, not a default.
- Endurance is closed as a concern for this consumer: both the metrics and log
  writers land one to two orders of magnitude under the drives' rated
  lifetime, even at pessimistic write-amplification assumptions.
