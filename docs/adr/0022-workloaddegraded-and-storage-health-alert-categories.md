---
status: accepted
date: 2026-08-23
tags: [observability, alerting]
---

# A sixth alert category, `WorkloadDegraded`, and two existing categories broadened

#267 through #270 landed data and deliberately no alert rules, each saying so in
its own acceptance criteria: "the Alert-or-Signal decision ticket owns" whichever
of its series earns a phone notification. This ADR is that decision, for every
series those four tickets actually shipped.

`CONTEXT.md`'s test governs, unchanged: an alert demands a human gesture, costs
something if ignored, and will not resolve itself. Everything else is a signal,
read in Grafana when someone thinks to look. The set is closed at five
categories (ADR-0004, raised from four by ADR-0017) and grows only by an ADR;
the default below is signal, and the burden of argument is on anything claiming
otherwise.

## What actually shipped, checked against what was asked

Two of the operator's twenty-one stated needs, named in this ticket's own body,
have **no series behind them today**, and no exporter ticket landed one:

- **Flux reconciliation drift.** No `flux-system` controller is scraped.
  `victoriametrics-configmap.yaml` has nine jobs and none of them is Flux; the
  controllers' own `gotk_reconcile_condition` metric is never collected. Nothing
  to classify.
- **Synology cloud-sync job failures.** `snmp-exporter-configmap.yaml`'s
  `synology` module walks three OID subtrees only, `synoDisk` and `synoRaid`,
  chosen deliberately as "exactly the three signals the risk register asks for
  and nothing else the DS412+ also exposes." HyperBackup/Cloud Sync task status
  is not one of them.

Both need their own scrape source before this ticket's test can even be applied
to them. Recorded here rather than silently dropped; a follow-up ticket to add
either is not scoped by this one.

**Repeated OOMKills** is a third near-miss. `kube-state-metrics-deployment.yaml`
restricts `--resources` to four collectors and `--metric-allowlist` to exactly
the five series #268 asked for; `kube_pod_container_status_last_terminated_reason`,
the one metric that would say a restart was an OOMKill rather than any other
crash, was never on that list. `kubelet-cadvisor`'s keep list
(`container_memory_rss|container_memory_cache|container_fs_usage_bytes`) does
not carry `container_oom_events_total` either. What exists today is
`kube_pod_container_status_restarts_total`, an undifferentiated count. Widening
either allowlist is a one-line follow-up, not this ADR: without the reason
label there is nothing to test against `CONTEXT.md`'s three parts yet.

Everything below is classified against a series that is actually queryable on
node1 today.

## Signals: stays the default

**CPU saturation** (`container_cpu_usage_seconds_total`,
`node_cpu_usage_seconds_total`, `kubelet-resource`). ADR-0002 already accepted
this as a deliberate, named hole: "the platform will refuse a workload that does
not fit in RAM and will accept one that makes it slow." High CPU usually means a
legitimate transcode or ML job and resolves itself when that job ends, failing
the "will not resolve itself" test outright. Signal.

**Per-container memory** (`container_memory_rss`, `container_memory_cache`,
`container_memory_working_set_bytes`). Diagnostic context for reading the alert
below, not a trigger on its own: no number here says a container is failing,
only how much room it is using.

**GPU VRAM, utilisation, power draw, encoder sessions**
(`gpu-exporter-daemonset.yaml`'s `memory.used`, `memory.total`,
`utilization.gpu`, `power.draw`, `encoder.stats.sessionCount`,
`utilization.decoder`). ADR-0020 already accepts 8 GiB of VRAM shared with no
isolation between Immich's machine learning and Plex's hardware transcode,
"direct play is the mitigation rather than a preference." A VRAM or utilisation
number does not by itself demand a gesture; it is read when diagnosing a slow
transcode or a failed inference, which is exactly what a Grafana signal is for.

**SMART wear trend** (`smartctl_device_power_on_hours`,
`smartctl_device_percentage_used`, `smartctl_device_data_units_written_bytes`).
These move over weeks (the textfile timer itself is sized on that assumption),
not minutes. A drive nearing its wear ceiling is worth a periodic glance, not a
phone push at 3am; it is exactly the kind of weekly-digest material ADR-0020
names when it says several of the operator's twenty-one needs "are weekly
summaries, which are Signals by definition." The one SMART series that does
cross into Alert territory is below.

**Tailnet probe** (`blackbox-tailnet`, `probe_success`). #270's own manifest
comment names the gap: this probes node1's own tailnet address from a pod
scheduled on node1, proving the interface serves traffic, "not a genuine
cross-site path... Point `BLACKBOX_TARGET` at a second node's tailnet IP once
one exists." There is no second site until the move on 2026-09-26. Alerting on
a self-probe would mean paging on a failure mode indistinguishable from
`NodeUnreachable`, which already covers node1 being down. Signal until a real
second endpoint exists, at which point this is revisited, not re-argued.

**Bare restart count** (`kube_pod_container_status_restarts_total`). Noisy on
its own: a rolling deployment, a Job's normal completion cycle and a genuine
crash loop all move this number. The reason-labelled series below is the
sharper trigger; this stays a Grafana signal for context once an alert has
already fired.

## Alert: two existing categories broadened, not multiplied

**Storage degraded, extending ADR-0004's "disk space near full, NVMe or NAS".**
That category was already scoped to the NAS in its own wording; it simply had
no NAS source until #270. Three series now feed it:

- `synology_disk_temperature_celsius` and `raidFreeSize`/`raidTotalSize`
  (`snmp-synology`) are the capacity half the category already names.
- `synoRaid`'s `raidStatus` (volume/RAID health, not free space) and
  `smartctl_device_smart_passed` (NVMe's own pass/fail self-assessment) are a
  new failure mode inside the same category: not "getting full" but "failing
  outright." Both pass the three-part test cleanly on the same asset this
  category already watches: a degraded RAID on the sole copy of the photo
  corpus (risk register 3) or a failed NVMe under an unmirrored ZFS pool (risk
  register 4) demands the same gesture as a full disk: go look, and it does not
  fix itself. ADR-0017 already collapsed CPU and NVMe over-temperature into one
  category "on ADR-0004's own criterion: the two share one remedy." The same
  criterion applies here: capacity and health failures on the same storage
  layer share a remedy too.
- `kubelet_volume_stats_available_bytes` (`kubelet-volume-stats`, #267) is a
  PVC-granularity version of the same "near full" failure the category already
  names at the host-mountpoint granularity.

**Thermal, extending ADR-0017's fifth category.** `gpu-exporter-daemonset.yaml`
publishes `temperature.gpu`. Risk register 9 names exactly this decision as the
open item revisiting when this ticket lands: "the Alert-or-Signal ticket decides
whether GPU temperature joins ADR-0017's Thermal alert category." It joins, on
the same reasoning ADR-0017 used to fold CPU and NVMe into one category: a
cooling failure demands the same gesture regardless of which sensor reports it,
and risk register 9's own finding is that the case-fan curve is blind to a
GPU-bound load in exactly the way it would be blind to a third overheating
component. **The threshold is not set here.** ADR-0017 sourced 85 degrees C from
the point the `CPU_FAN` curve reaches 100% and 70 degrees C from Kingston's
datasheet; this ticket has no equivalent sourced figure for the RTX 3070 Ti, and
inventing one would repeat exactly the mistake ADR-0017's own "Alternatives
rejected" section priced and refused for the CPU (accepting a throttling point
as if it were a margin). Sourcing the number is implementation work carried to
whichever ticket wires the rule, the same way ADR-0004 and ADR-0017 left their
own exact expressions to implementation; the count decision is made here.

Neither extension changes the alert count. Both broaden which source and which
failure mode a category already covers, the same kind of amendment ADR-0018
made to category 3's mechanism without touching its count.

## Alert: a sixth category, `WorkloadDegraded`

Three series describe one failure mode none of the five accepted categories
covers: a workload that is scheduled but never becomes healthy, and stays that
way until a human intervenes.

- `kube_pod_container_status_waiting_reason` for `CreateContainerConfigError`,
  `ImagePullBackOff` and `CrashLoopBackOff` (kube-state-metrics, #268)
- `kube_deployment_status_replicas_unavailable`, sustained (kube-state-metrics)
- `kube_persistentvolumeclaim_status_phase` stuck `Pending` (kube-state-metrics)

This is not a hypothetical failure mode being pre-empted. It is the literal
motivating incident, twice: `cloudflared` sat in `CreateContainerConfigError`
for 2 days 6 hours across 1231 attempts on a missing secret (#267), and
`immich-server` reached 11 restarts, both "running unnoticed when ADR-0020 was
written," found only "by running `kubectl` by hand." Against `CONTEXT.md`'s
test: it demands a gesture (fix the manifest or the secret feeding it), it costs
something if ignored (the workload stays down for as long as nobody looks,
measured here at over two days), and Kubernetes's own retry loop guarantees it
will not resolve itself, that is precisely what "back off and retry forever"
means for a config error.

**Why this earns a sixth category rather than folding into one of the five.**
None of the existing five shares a remedy with it. `NodeUnreachable` is about
the machine, not one workload on it; `Thermal` and the now-broadened storage
category are about hardware; `CertificateExpiringSoon` and `Watchdog` are
narrower still. A misconfigured Deployment does not go away when any of those
five is fixed.

**Why the noise budget (risk register 10: one ntfy topic, two free tiers) still
holds.** This is not a routine-firing category. The two incidents that motivate
it are the only two ADR-0020 found in eight days of the platform running
unwatched, and both were genuine misconfigurations rather than transient
blips, which is exactly why `for:` durations belong on the sustained variants
(`replicas_unavailable`, `Pending`) at implementation time. A category that
fires on real breakage a handful of times over the platform's life so far does
not threaten the "sixth notification of the week" failure ADR-0018 names.

`kube_job_status_failed` (#268's fifth series) is deliberately **not** part of
this category. #268's own text scopes it "for the backup CronJobs", which
ADR-0018 already alerts on through the Healthchecks witness (daily dump, monthly
`restic check`). Routing it through `WorkloadDegraded` too would build a second,
faster detector for a failure the existing backup category already catches by
design, at the witness's slower cadence. That is a mechanism amendment to
category 3, the same shape ADR-0018 itself made there, not a new alert and not
part of this one. Left to the same follow-up as the GPU threshold: implementation,
not this decision.

## Decision

**Six alert categories.** The five ADR-0004 and ADR-0017 accepted stay, two of
them broadened in scope and mechanism rather than replaced:

1. `NodeUnreachable`, unchanged.
2. **Storage degraded** (was "disk space near full, NVMe or NAS"), now also
   reading Synology RAID/volume health, NVMe SMART pass/fail, and PVC
   fullness, alongside the host-mountpoint and NAS-capacity sources it
   already had.
3. Backup missed its RPO window, unchanged (witness-based, ADR-0018);
   `kube_job_status_failed` on the backup CronJobs may later become a faster
   trigger inside this same category, as implementation.
4. `CertificateExpiringSoon`, unchanged.
5. **Thermal**, now also reading GPU temperature, threshold to be sourced at
   implementation time.
6. **`WorkloadDegraded`**, new: sustained `CrashLoopBackOff` /
   `ImagePullBackOff` / `CreateContainerConfigError`, sustained unavailable
   replicas, and PVCs stuck `Pending`.

`CONTEXT.md`'s "closed at five categories" line is updated to six, citing this
ADR.

Every other series #267-270 shipped is a **signal**: CPU usage, per-container
memory, GPU VRAM/utilisation/power/encoder sessions, SMART wear trend, the
tailnet self-probe, and bare restart counts. They live in Grafana as ad hoc
Explore queries against the already-provisioned VictoriaMetrics datasource,
the same way ADR-0017's idle-drift signal already does; #160 scoped this
platform to deliberately carry no curated dashboard, and nothing here reopens
that. Flux reconciliation drift, Synology cloud-sync failures and
reason-labelled OOMKills stay unclassified for lack of a source, not by
decision.

Exact PromQL, `for:` durations and the GPU threshold are implementation, as
every prior alerting ADR in this set has left its own.

## Alternatives rejected

**A seventh category splitting `WorkloadDegraded`'s three series apart** (one
for restart loops, one for unavailable replicas, one for stuck PVCs). Rejected
on ADR-0017's own criterion: all three share the same remedy, going to look at
the workload, and Alertmanager groups them regardless.

**Treating GPU temperature as its own category** rather than folding it into
`Thermal`. Rejected for the same reason ADR-0017 refused a separate NVMe
category: the remedy (go check the machine's cooling) does not depend on which
sensor spoke.

**Alerting on CPU saturation.** Considered because ADR-0002 names oversubscription
as an open hole. Rejected because the hole is accepted, not a fault: a
workload getting slow under contention is the documented consequence of no CPU
admission gate, not an unresolved failure, and it resolves itself when the
contending job finishes.

**Alerting on the SMART wear trend directly** (`percentage_used` crossing a
threshold), rather than leaving it a signal and catching only outright failure
(`smart_passed`) through the broadened storage category. Rejected because wear
moves over weeks and a wear percentage alone does not demand tonight's gesture;
outright failure does, and that path is already an alert.

**Alerting on the tailnet probe now.** Rejected because it does not yet test
the cross-site path the operator asked for, per #270's own note; alerting on a
same-host self-probe would duplicate `NodeUnreachable`'s coverage under a
different name.

**Routing `kube_job_status_failed` through `WorkloadDegraded`.** Considered
because it is the fastest available signal of a backup CronJob failing.
Rejected because ADR-0018 already owns backup detection as its own category by
design (the witness); adding a second, faster path there is an amendment to
that category's mechanism, not a new alert trigger in this one.

**Leaving `WorkloadDegraded` as a Grafana signal**, on the grounds that the
operator can check dashboards periodically. Rejected because that is the exact
failure mode ADR-0020 measured directly: `cloudflared` sat broken for over two
days precisely because nothing pushed a notification and nobody thought to
look.

## Consequences

- `CONTEXT.md`'s alerting glossary entry changes from "closed at five
  categories" to six, citing this ADR alongside ADR-0004 and ADR-0017.
- Risk register 9's "Revisits when" is resolved: GPU temperature joins
  `Thermal`, pending a sourced threshold, and the entry's "Accepted by" grows
  to include this ADR.
- `vmalert-configmap.yaml` needs a new `WorkloadDegraded` alert and expanded
  expressions on `DiskSpaceNearFull` (which this ADR renames in intent to
  "storage degraded", the manifest's actual alert name is implementation) and
  `Thermal`. None of that ships in this ADR.
  **Amendment, 2026-08-24 (#299):** the OOMKilled slice of `WorkloadDegraded`
  lands. `kube_pod_container_status_last_terminated_reason` is allowlisted
  (`kube-state-metrics-deployment.yaml`), carrying upstream's own
  EXPERIMENTAL stability tier unlike the five STABLE series #268 already
  allowlists - flagged in that manifest's own comment as a metric to check
  by name at the next kube-state-metrics upgrade. Querying `cs.LastTerminationState.
  Terminated != nil` cluster-wide today (`kubectl get pods -A`, this
  workstation's read-mostly kubeconfig, ADR-0019) counts 15 containers with a
  recorded last-terminated reason against 30 containers total - one series
  per container that has restarted at least once, cheaper than
  `kube_pod_container_status_restarts_total`'s one-per-container-always. At
  that order of magnitude the write-envelope cost is negligible against the
  10 GB/day line (ADR-0020's own measured ~0.45 KiB/series/day ratio puts
  even a worst-case 30 series under 14 KiB/day). Classified **Alert**: a
  repeated OOMKill demands a memory-limit or leak investigation, costs the
  workload staying down, and Kubernetes's own backoff guarantees it will not
  resolve itself - the same three-part reasoning `WorkloadDegraded`'s other
  two series already passed. Because the metric is sticky (upstream's
  generator function only appends a series, never clears one -
  `kube-state-metrics-deployment.yaml`'s own comment cites it - so it keeps
  reporting the last reason forever, not just while the container is
  currently failing), the wired expression joins it against
  `kube_pod_container_status_waiting_reason{reason="CrashLoopBackOff"}`
  rather than firing on the reason label alone, so a container that OOM'd
  once and has been healthy since does not alert; `vmalert-configmap.yaml`'s
  own comment carries the full expression and sourcing. `ImagePullBackOff`/
  `CreateContainerConfigError` waiting reasons, sustained
  `replicas_unavailable`, and PVCs stuck `Pending` - the rest of what this
  ADR named for `WorkloadDegraded` - remain unwired, this ticket's scope was
  the OOMKilled reason label only, tracked separately as #303.
  `alertmanager-configmap.yaml`'s route,
  inhibit target and ntfy priority template are extended to carry
  `category: workload-degraded` alongside `disk`/`thermal`/`certificate`;
  without that, a fired alert would have reached the default `null` receiver
  and never notified, the exact failure this whole alert line exists to
  prevent. Real queryability and on-disk cardinality (VictoriaMetrics's own
  `/api/v1/status/tsdb`, same method as the #270 amendment above) are not
  verified from this branch: GitOps deploys the change once this merges to
  main, and the scoped kubeconfig cannot port-forward to check it directly
  today (confirmed live, `pods/portforward` is forbidden for this
  ServiceAccount) - a post-merge check is still owed.
  **Amendment, 2026-08-24 (#303):** the three remaining series land.
  `ImagePullBackOff`/`CreateContainerConfigError` join `CrashLoopBackOff`
  itself (not joined to a last-terminated reason this time) in one
  `reason=~"..."` expression: the general "container is stuck retrying"
  failure, covering `CrashLoopBackOff` regardless of cause rather than only
  the memory-kill slice #299's join already covers. Those two overlap
  whenever a container is genuinely repeat-OOMKilled - both would then
  match the same container on a plain reading, and because #299's join
  drops the `reason` label on its own result, vmalert/Alertmanager would
  treat the two as different alerts (different label sets) instead of
  deduplicating, one incident producing two ntfy notifications - caught in
  review, not shipped. `unless on(namespace, pod, container)` #299's own
  OOMKilled-join subtracts those containers out of this rule, so a
  genuinely repeated OOMKill stays solely #299's rule and this one covers
  every other `CrashLoopBackOff` cause (a bad command, a failing readiness
  probe, an app panicking on start) without double-firing.
  Same `max_over_time(...[15m:1m])` / `for: 5m` shape as the OOMKilled rule,
  for the same documented reason - kubelet's backoff cycle interrupts the
  Waiting state with brief Running/Terminated windows shorter than the 60s
  scrape interval, and `ImagePullBackOff` toggles the same reason label
  against `ErrImagePull` across its own backoff cycle, so a plain `for:`
  could keep resetting its pending timer and never fire. `replicas_unavailable`
  and `Pending` need no such join: both are read directly (`> 0` and
  `{phase="Pending"} == 1`, kube-state-metrics's own StateSet shape for the
  latter), each with `for: 15m`, reusing the duration the GPU Thermal
  expression, the OOMKilled join and the Flux rule already settled on
  (#298, #299, #300) rather than inventing a new one - the "for: durations
  belong on the sustained variants" line this ADR's own text anticipated.
  No `alertmanager-configmap.yaml` change: `category: workload-degraded` is
  already in the ntfy route's category list and priority mapping from #299,
  so these three rules reach ntfy at the same `high` priority without
  further wiring. All three series were already allowlisted
  (`kube-state-metrics-deployment.yaml`, #268) and scraped since #268; this
  ticket adds rules only, no scrape or allowlist change. Reproducing the
  `cloudflared` `CreateContainerConfigError` incident (ADR-0020) against the
  new `reason=~"..."` expression, and on-disk cardinality, are not verified
  from this branch for the same reason #299's amendment above records: the
  scoped kubeconfig cannot port-forward to VictoriaMetrics today - a
  post-merge check against the live cluster is still owed.
- The GPU thermal threshold is an open sourcing task, the same shape as
  ADR-0017's own CPU and NVMe research, before its half of the `Thermal`
  extension can actually fire.
  **Amendment, 2026-08-24 (#298):** sourced at 93 degrees C, NVIDIA's own
  published Maximum GPU Temperature for the RTX 3070 Ti, and wired into
  `vmalert-configmap.yaml`'s `Thermal` alert. Risk register 9 records the
  detail; this bullet's premise no longer holds.
- Flux reconciliation drift, Synology cloud-sync failures and reason-labelled
  OOMKills remain outside every accepted alert category, not because they
  failed this ADR's test but because nothing scrapes them yet. Each needs its
  own exporter or allowlist change before this test can be applied.
  **Amendment, 2026-08-24 (#300):** the first version of this amendment
  scraped flux-system's controllers directly for
  `gotk_reconcile_condition{type="Ready"}`. That metric does not exist on
  the Flux version this cluster runs (kustomize/source-controller v1.9.4,
  helm-controller v1.6.3, notification-controller v1.9.3) - confirmed live
  by reading every controller's raw `/metrics` output from node1 after
  merge, zero `gotk_reconcile_condition` series anywhere, `up{job="flux"}`
  green regardless since scraping itself worked fine. Upstream dropped the
  metric after Flux 2.1.1 (fluxcd/flux2#4652) and now documents
  `gotk_resource_info`, sourced from kube-state-metrics's
  `customResourceState` reader against each CRD's own `.status.conditions`,
  not something the controllers expose themselves
  (fluxcd.io/flux/monitoring/metrics/). The direct-scrape `flux` job in
  `victoriametrics-configmap.yaml` is deleted; the replacement is
  `kube-state-metrics-crs-configmap.yaml` plus the
  `--custom-resource-state-config-file` flag and RBAC added to
  `kube-state-metrics-deployment.yaml` / `kube-state-metrics-rbac.yaml` -
  the existing `kube-state-metrics` scrape job already covers the new
  metric, no new job. Classified **Alert**, folded into `WorkloadDegraded`
  rather than a seventh category: `gotk_resource_info{ready="False"} == 1`
  sustained means a Kustomization or GitRepository is not reconciling, and
  by the time that has held long enough to alert, Flux's own reconcile loop
  (`interval: 10m0s` on both `flux-system` Kustomizations, gotk-sync.yaml
  and workloads.yaml) has already retried at least once - the same "back off
  and retry forever" reasoning `WorkloadDegraded`'s other three series
  already passed, sharing the same remedy (go look at the object, fix the
  manifest or the source it points at) as `CrashLoopBackOff`/
  `ImagePullBackOff`. `ready="False"` rather than `!= "True"`: `Unknown`
  (present during startup and in the interval right after a spec change,
  before the first reconcile completes) is not the same failure as an
  object that reconciled once and then broke, and alerting on it would page
  on ordinary object creation. `for: 15m` reuses the duration Thermal's GPU
  expression and the OOMKilled join already settled on (#298, #299), longer
  than the 10-minute reconcile interval so a single attempt that would
  succeed on retry does not fire. No `alertmanager-configmap.yaml` change:
  `category: workload-degraded` is already in the ntfy route's category
  list and priority mapping from #299, so this expression's alerts reach
  ntfy at the same `high` priority without further wiring.
  Cardinality: 2 Kustomizations (`gotk-sync.yaml`, `workloads.yaml`) and 1
  GitRepository (`gotk-sync.yaml`) - 3 objects, counted from the repo
  itself: this GitOps repo is the source of truth for every Flux object,
  and no HelmRelease, HelmRepository, HelmChart, OCIRepository, Bucket,
  Alert, Provider, or Receiver manifest exists anywhere in it
  (`gotk-components.yaml` defines their CRDs but creates no instances) -
  the same "no HelmRepository source exists in this repo yet" precedent
  `nvidia-device-plugin.yaml`'s own comment already records, and why
  `kube-state-metrics-crs-configmap.yaml` only defines the two kinds that
  exist. `gotk_resource_info` is kube-state-metrics's Info metric type
  (`kube_pod_info`'s shape): one row per object regardless of state, not
  one row per condition-status value the abandoned gauge approach would
  have produced, so 3 objects is a ceiling of exactly 3 series, at
  ADR-0020's measured ~0.45 KiB/series/day under 1.5 KiB/day, negligible
  against the 10 GB/day envelope. Verified live from node1 (`ssh node1`,
  `k3s kubectl`, no `pods/portforward` restriction there unlike this
  workstation's scoped kubeconfig, ADR-0019): `up{job="flux"}` was
  initially absent from the live target list even though the mounted
  configmap already carried the job - VictoriaMetrics does not hot-reload
  `-promscrape.config` on file change without an explicit
  `-promscrape.configCheckInterval` flag (not set here), so the pod needed
  a restart (`kubectl delete pod`) before the new scrape config took
  effect; this same reload gap will apply to every future config change to
  this file, worth a flag in a later ticket. Synology cloud-sync job
  failures stay unclassified for the same reason as before: nothing scrapes
  them yet, unchanged by this ticket.
  **Amendment, 2026-08-24 (#301):** all three plausible sources were checked
  against DSM's own documentation rather than assumed; none clears the bar
  this pass, so no scrape job ships and no classification is made. SNMP: no.
  The current Synology SNMP MIB Guide (global.download.synology.com,
  updated 2026-03-25) is a different download from the raw
  `Synology_MIB_File.zip` #270's own manifest comment cites, but the same
  publisher's own enumeration of every OID subtree DSM/SRM/APM support -
  System, Disk, RAID,
  UPS, Smart, Services, StorageIO, SpaceIO, FlashCache, iSCSI LUN, Ebox,
  SHA, NFS, GPUInfo, Port, iSCSI Target, SMB Service, MailPlus - one named
  module per package that ships SNMP data, the same granularity MailPlus
  gets its own line at. A full-text read of the guide itself, not a
  summary, returns zero occurrences of "backup", "task", "job" or "cloud
  sync" anywhere in it: no module for either package is named, which is
  what would appear here if one existed, even without decoding the raw
  `.mib` files bit by bit.
  The nearest-sounding table, Services MIB (`.1.3.6.1.4.1.6574.6`), is
  login-session counts per protocol (HTTP/CIFS/AFP/NFS/FTP/SFTP/TELNET/
  SSH), not task status. Log file: no. `synobackup.log` lives under
  `/var/log/synolog/`, a system path. DSM's Shared Folder feature, the
  mechanism this platform's own NFS mounts actually run through
  (`nfs-client` role, ADR-0010), cannot export system partitions -
  Synology's own NFS documentation lists this under the feature's stated
  limitations. Reaching the log needs SSH, a manual gesture in a more
  invasive class than "Control Panel > Terminal & SNMP" (already the gap
  ADR-0020 recorded as unreachable from this platform's Ansible), and even
  with SSH the file would need a translator holding a standing SSH
  credential to the NAS just to reach node_exporter's textfile format - a
  larger surface than the API path below for the same information. DSM's
  own Web API: exists, but not zero-cost. `SYNO.Backup.Task` (Hyper Backup,
  Active Backup for Business) and a separate `SYNO.CloudSync` namespace are
  real, documented DSM Web API surfaces (n4s4/synology-api's own supported-
  APIs listing), and a working open-source Prometheus exporter
  (raph2i/synology_backup_exporter) already scrapes Hyper Backup /
  Active Backup / Hyper Backup Vault task status through them - last-
  successful timestamp, last-attempted timestamp, duration - proving the
  path is real rather than hypothetical. Three gaps stop it from being
  sized and shipped this pass, the same "size it, don't assume it" bar
  #270's own SNMP module was held to: **no anonymous or read-only
  unauthenticated tier exists at the API layer at all** - every DSM Web API
  namespace requires a session from `SYNO.API.Auth`'s login method first
  (Synology's own DSM Login Web API Guide), so "read-only" here means a DSM
  user account scoped by DSM's own per-package permission model, needing
  the same credential-siting decision under ADR-0009 every other secret in
  this repo already goes through, not a flag to flip; **DSM-version
  compatibility with this specific NAS is unverified** - the DS412+'s own
  hardware ceiling is DSM 6.2, the last version this model can run
  (Synology's own compatibility data, unchanged from #270's own dating of
  the hardware), and the one working exporter found ships a `dsm7` Docker
  tag with no documented DSM 6 support at all, a gap that can only be
  closed by live testing against this actual NAS, which this authoring
  pass cannot reach any more than #270's own SNMP-enable step could;
  **Cloud Sync is also real, but has no ready-built exporter** -
  `SYNO.CloudSync`'s own `get_tasks()` method (n4s4/synology-api's
  `cloud_sync.py`, read directly rather than trusted from its docs page's
  summary, which undersold it) documents exactly the fields needed per
  task: `sync_status`, `error`, `error_desc`, `link_status`,
  `local_sync_path`, `remote_sync_path`. Unlike Hyper Backup, no working
  open-source exporter scraping it was found, so closing this half means
  writing a small script against a documented field rather than reusing
  one, on top of the same auth/credential/DSM-6.2 gaps above. Recorded here
  rather than shipped blind. A follow-up ticket (#307) scopes both halves
  through the same DSM API session and the same ADR-0009 credential-siting
  decision, proven live against this NAS's DSM 6.2 before either ships.
- Six categories still route through risk register 10's single ntfy topic on
  two free tiers. Nothing here adds a channel; the noise-budget argument above
  is why that is judged to still hold, not a reason to revisit ADR-0018.
- No Grafana dashboard is added or curated by this ADR; every signal named
  above is read the same ad hoc way the platform's existing signals already
  are, consistent with #160.
