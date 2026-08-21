---
status: accepted
date: 2026-08-21
tags: [resources, memory, storage, capacity, network, media]
---

# The allocation, revised against a machine that now exists

ADR-0002 divided 32 GiB into envelopes and declared the service set fitted, "exactly, and only
under three conditions". It was written before the node was built, against figures supplied by
tickets rather than read off hardware. The node has now been running for eight days with Immich,
observability, ingress and backup on it, and a scoped kubeconfig (ADR-0019) makes it readable
from the operator's own workstation without SSH.

This ADR is what changed once someone looked. It replaces ADR-0002's allocation tables and keeps
its method intact: the ceiling is still divided into envelopes, each enforced from outside the
consumer, so that the sum is under the ceiling by construction. Nothing here reopens the
allocation-not-forecast argument, which held. What did not hold is a load-bearing input, two of
the three conditions, and the total itself.

## What the machine actually reports

**The total is 30.26 GiB, not 32.** `MemTotal` on node1 is 31736532 KiB. ADR-0002's table sums to
exactly 32 GiB with 2.5 GiB of slack, so roughly 1.7 GiB of the slack it counted on never existed:
it was taken by firmware and kernel before `MemTotal` was computed. Every figure below is written
against 30.26 GiB.

**Two of ADR-0002's three conditions were not enforced.** Condition 2 was "the platform refuses
admission beyond the allocation". k3s runs with no `system-reserved`, no `kube-reserved` and no
`eviction-hard`, so node-allocatable equals capacity: the scheduler will admit roughly 30 GiB of
pod requests while the ARC, the host and the k3s server process already hold about 7.5 GiB that no
pod accounts for. Condition 1 was "every consumer carries an externally enforced cap". Traefik and
svclb, both k3s bundled add-ons, run in `BestEffort` with neither request nor limit.

**The filesystem cache envelope was overrun by its own role.** ADR-0002 decomposed its 5 GiB as
4 GiB of ARC plus 1 GiB of dirty data, against a 3.2 GiB default. The `zfs` role sets
`zfs_arc_max_bytes` to 5 GiB, the whole envelope, and never sets `zfs_dirty_data_max` at all, so
the default stands on top: about 8.2 GiB in practice against a 5 GiB decision. This is the largest
line in the budget sitting in the enforcement class ADR-0002 itself called the weakest, overrun in
exactly the way it predicted, with nothing checking it.

## The corpus is 48 GB, not 1.5 TB

`docs/reference/research-immich-data-classes.md` opens by stating the machine's context, including
"~1.5 TB of family photos". That figure was a ticket premise, never a measurement. Measured on
node1 on 2026-08-21, the NAS volume holding `upload/`, `library/` and the restic repository
reports 48 GB used of 5.5 TB. `state/immich-derivatives` holds 14 GB. The operator has since
confirmed the initial import is complete and that no comparably intensive event is expected.

The figure is out by a factor of about 31 and it propagated into four ADRs. What each one now
needs:

- **ADR-0002, the ARC rationale, is inverted.** "Immich's hot working set is 150-300 GB. No ARC
  that fits on this machine caches a useful fraction of it, so sizing the ARC to the working set
  is not an option that exists." Against 14 GB of derivatives, a 4 GiB ARC caches a meaningful
  share. The 4 GiB figure survives on ADR-0002's other argument, which does still hold: the scarce
  resource on these drives is write endurance, not read latency, and the ARC is a read cache.
- **ADR-0002's sequenced-not-budgeted import exception has already been spent.** There is no
  1.5 TB event ahead. The `immich-machine-learning` widening to 6 GiB, which
  `workloads/immich/ml-deployment.yaml` marks as temporary against exactly that exception, has
  nothing left to wait for.
- **ADR-0002's storage table over-counts derivatives** at 150-300 GB against 14 GB measured.
- **ADR-0010's stated reason for putting originals on the NAS is false.** "1.5 TB corpus does not
  fit two 1 TB NVMe alongside state" is untrue at 48 GB. **The decision stands anyway, for a
  reason the ADR did not give**: the originals are the sole copy, and a single unmirrored NVMe
  (risk register 4) is a worse trustee for a sole copy than the NAS's RAID. Originals are not
  moved.
- **ADR-0012's price is out by the same factor**, but its rejection was never a price. It refused
  "even the ≈$0.14/month it would cost to send only the ~20 GB Postgres dump off-site ... the
  budget for a recurring payment is zero, not merely small." The correction therefore does not
  invalidate ADR-0012. It is reopened separately, on the principle rather than the price, by
  ADR-0021.
- **ADR-0017's "1.5 TB photo archive" is cosmetic** and needs no action beyond not being copied
  forward.

## The memory allocation

The floor now splits in two, because it is enforced by two different mechanisms and only one of
them is visible to the scheduler. ADR-0002 listed a single "reserved floor" of 11.5 GiB, which
made it impossible to tell which part the admission gate was supposed to subtract.

**Reserved outside Kubernetes, through `system-reserved` on the kubelet:**

| Consumer | Envelope | Enforced by |
| --- | --- | --- |
| Host: kernel, systemd, `sshd`, journald | 1 GiB | systemd slices |
| Filesystem cache: ARC 4 GiB + dirty data 1 GiB | 5 GiB | `zfs_arc_max`, `zfs_dirty_data_max` |
| k3s server process | 1.5 GiB | systemd slice |
| **Reserved, invisible to the scheduler** | **7.5 GiB** | `--kubelet-arg=system-reserved` |
| **Node-allocatable** | **22.76 GiB** | |

**Reserved inside Kubernetes, as pod requests:**

| Consumer | Envelope |
| --- | --- |
| GitOps engine (Flux) | 1 GiB |
| Observability | 3.75 GiB |
| Platform pods: coredns, metrics-server, traefik, svclb, cloudflared, backup CronJobs | 1 GiB |
| **Pod-side floor** | **5.75 GiB** |
| **Workload space** | **17.01 GiB** |

**Workloads:**

| Consumer | Envelope |
| --- | --- |
| Immich | 8 GiB |
| Showcase web stack (one, see below) | 2 GiB |
| Media stack | 4.25 GiB |
| Plex transcode scratch (tmpfs) | 1 GiB |
| Slack | 1.76 GiB |
| **Total** | **17.01 GiB** |

Observability rises from 3 GiB to 3.75 GiB. It is exactly full today (3072 MiB requested against
3 GiB allocated) and the platform is currently blind to everything between "the node answers" and
"a disk is full": VictoriaMetrics scrapes two jobs, `node-exporter` and `traefik`, and vmalert
carries five rules. Two live failures were running unnoticed when this ADR was written, a
`cloudflared` pod in `CreateContainerConfigError` for over two days and eleven restarts on
`immich-server`. Closing that gap costs exporters, and exporters cost memory.

The platform-pods line is new. cloudflared, the smoke target, the backup CronJobs, coredns and
metrics-server appear nowhere in ADR-0002's table. They are platform machinery, on the same side
of the boundary as Flux and observability, not workloads in `CONTEXT.md`'s sense, so they get one
line rather than a standard slot each.

### Immich keeps 8 GiB and is re-split

ADR-0002 anticipated this: "the allocation's internal split may need revisiting once #31 reports.
The total will not."

| Container | ADR-0002 | Here | Why |
| --- | --- | --- | --- |
| PostgreSQL + VectorChord | 2.5 GiB | 2 GiB | Immich's own documented minimum under container limits; 79 MiB observed |
| `immich-server` + jobs | 3 GiB | 2.5 GiB | 765 MiB observed |
| `machine-learning` | 2 GiB | **3 GiB** | OOMKilled three times at 2 GiB |
| Redis | 0.5 GiB | 0.5 GiB | |

The machine-learning line is the only one that has actually failed. `ml-deployment.yaml` records
it: a real import had queued OCR, SmartSearch and AssetDetectFaces before the pod finished its
first image pull, so three model loads landed concurrently in one `MACHINE_LEARNING_WORKERS=1`
process, and 2 GiB died three times in a row. The model cache is now warm on disk, which removes
the download half of that cost but not the load half. Postgres and the server are oversized for a
48 GB corpus in a way they were not for a 1.5 TB one, so the gigabyte comes from them. The
temporary 6 GiB widening is retired.

### The standard slot, and one showcase stack instead of two

The slot stays at 2 GiB. ADR-0002 allocated two web stacks; one has been abandoned, so the
allocation carries one. The other 2 GiB returns to workload space rather than being held as a
named envelope for something nobody is building, which is the "reserved for later" pattern
ADR-0002 forbids elsewhere.

### The media stack is an exception, not a slot

ADR-0002: "A workload that does not fit a slot becomes an explicit exception that must argue for
its envelope against this budget." The media stack is eight containers and does not pretend to be
a slot.

| Container | Cap |
| --- | --- |
| Plex | 1536 MiB |
| qBittorrent | 512 MiB |
| Overseerr | 512 MiB |
| Sonarr | 384 MiB |
| Radarr | 384 MiB |
| Maintainerr | 384 MiB |
| Prowlarr | 256 MiB |
| `cross-seed` | 256 MiB |
| gluetun | 128 MiB |
| **Total** | **4.25 GiB** |

Recyclarr runs as a CronJob, not a resident service, and draws its 64 MiB from slack the same way
the backup CronJobs do. Autobrr and Tautulli are deliberately out: Autobrr's speed advantage
depends on an IRC announce definition, and of the operator's six trackers exactly one
(`theoldschool`) has one upstream, leaving it to fall back on the RSS and torznab paths Prowlarr
already covers; Tautulli is an optional rule source for Maintainerr and Overseerr, both of which
read Plex directly, and the Grafana dashboards that would replace it are themselves fed by
Tautulli's API. Both are one kustomization line away if a measured gap appears.

The 1 GiB tmpfs for Plex's transcode scratch is a memory line on purpose. On NVMe it would be a
write line instead, and a habit of two transcoded viewings a day would consume a large share of
the 16 GB/day write allocation once ZFS amplification is applied. Plex needs the lookahead buffer,
not the whole film.

## The NAS is allocated too

5.5 TB has never been divided anywhere. ADR-0002's storage table is computed against the local
NVMe. The method is the same as for memory: envelopes, each held by a mechanism outside the
consumer.

| Consumer | Envelope | Held by |
| --- | --- | --- |
| Immich originals | 500 GB | 48 GB today |
| restic repository | 300 GB | ADR-0012, plus whatever ADR-0021 settles |
| Plex media library | 3 TB | **Maintainerr** |
| Downloads in flight and seeding | 500 GB | qBittorrent's own limits |
| Unallocated | ~1.2 TB | |

Maintainerr earns its 384 MiB here rather than as a convenience: it is the external enforcement for
the Plex line, structurally the same role a cgroup cap plays for a memory line. Without it the
library is bounded only by the operator remembering, which is the failure mode this whole method
exists to remove.

The unallocated 1.2 TB is not only growth room. Rebuild time after a disk failure rises with how
full the volume is, on four disks that #7 measured at 42,000 to 43,000 power-on hours within 3% of
each other, holding the only copy of the photo corpus (risk register 3).

## Bandwidth: risk register 6, finally priced

Measured from node1 on 2026-08-21, against a subscription of 1 Gbit/s down and 700 Mbit/s up:

| | Subscribed | Measured | Lost |
| --- | --- | --- | --- |
| Down | 1000 Mbit/s | 116.5 Mbit/s | 88% |
| Up | 700 Mbit/s | ~103 Mbit/s | 85% |

Download is a 60-second sustained transfer (874 MB from `proof.ovh.net`); upload is two 100 MB
passes against Cloudflare's `__up` endpoint, at 99.4 and 106.8 Mbit/s. `enp5s0` negotiates
1000 Mbit/s, so the loss is not on the node. The near-symmetry is the signature of a shared
bottleneck on the path rather than an asymmetric subscription profile, and it matches #8's
`iperf3` bisection exactly: about 940 Mbit/s on the LAN side, about 100 Mbit/s once the powerline
segment is crossed.

Risk register 6 recorded this ceiling as "a given, not a target to raise" without ever costing it.
It costs 88% of downstream and 85% of upstream on a subscription already paid for.

**The powerline segment is not only on the internet path.** node1 and the NAS stay together in the
upstairs office, so their link remains gigabit on the local switch, which is the adjacency Immich's
NFS mounts and the media library depend on. Everything reaching the ground floor crosses the
~110 Mbit/s segment, and four consumers now share it: Plex to the living-room television (10-20
Mbit/s at 1080p, 50-80 for a 4K remux), torrent seeding, the Cloudflare tunnel carrying the
showcase site, and the household's own use. A single 1080p stream is comfortable; a 4K remux
alongside unthrottled seeding is not. qBittorrent's scheduled alternative rate limits, throttled
during viewing hours and open overnight, are what keeps the operator's own seeding from being the
cause of a stuttering film.

Household constraints close the obvious repairs: node1 and the NAS stay in the upstairs office,
the box will be on the ground floor after the move on 2026-09-26, and running a cable is vetoed.
Powerline does not deliver 700 Mbit/s even when new and well placed. Checking for coaxial outlets
at both ends, which would allow MoCA over cabling already in the walls, is the one non-cable
option left and costs nothing to look for during the move.

## The personal AI assistant is allocated zero

Same form and same reason as ADR-0002's zero for local inference: an envelope reserved for later
gets eaten by something else while suggesting a decision was taken.

`docs/reference/research-personal-ai-assistant-hermes-openclaw.md` concluded "neither, for now",
with one named reopening condition: a concrete, operator-stated use case. The operator has since
stated twenty-one. Tested against what the platform actually lacks, twenty of them resolve to an
exporter, an alert rule, a CronJob or a tool that already exists: kube-state-metrics for
crashloops and full PVCs, a DCGM exporter for the GPU, a Synology SNMP exporter for the NAS,
blackbox for tailnet probes, `ansible-playbook --tags verify` for post-upgrade checking, Trivy for
CVE scanning, Immich's own duplicate detection. The twenty-first, a weekly report on Claude Code
model and effort routing, reads transcripts on the operator's workstation and is not a homelab
workload at all. None of the twenty-one is conversational: every one fires on a clock or a
threshold.

Routing them through an agent would build a second alerting path in parallel with the one ADR-0004
and ADR-0018 already built, with a language model on the critical path of "the NAS is full", and
the research measured a 15.5 GB RSS crash report and a degraded-but-alive failure mode at 1.8 GiB
for OpenClaw. An agent that dies quietly stops alerting, and nothing watches the agent.

**Reopening condition:** a use case that is conversational rather than scheduled, or a judgement
task that no exporter answers. Adopting an agent as a learning objective in its own right is a
legitimate reason and a different argument; it would still arrive after the exporters, in
scheduled rather than resident form.

## The media stack ships here, with a named exit

Deploying it on the platform is reversible in a way most decisions are not:
`clusters/homelab/workloads.yaml` already sets `prune: true`, so deleting `workloads/media/` from
the repository removes all eight containers in one commit. Every PV is `Retain`, so the data
survives and cleanup stays deliberate.

What is not reversible is torrent state. Seeding from home for three months and then moving to a
shared seedbox means reintroducing the torrents there, with each tracker's seeding clock restarting.
The infrastructure is disposable; the ratio is not.

**Exit condition, reviewed at the end of December 2026, three months after the move.** Two facts
decide it: whether any hit-and-run strike has been received on any tracker, and whether Plex
playback to the ground-floor television is reliable. If either fails, `workloads/media/` is removed
and media moves wholesale to a shared seedbox, accepting the incomplete `*arr` suite that comes
with it. Recorded now so the review is a reading rather than a fresh argument.

## Consequences

- **`system-reserved` makes the gate real and will refuse things.** Allocatable drops from
  30.26 GiB to 22.76 GiB the day it is set. That is the point, and it is also how a deployment
  gets blocked at an inconvenient moment. Current requests are 15.46 GiB, so nothing running today
  is affected.
- **Traefik and svclb need caps.** They ship from k3s's bundled add-ons, outside GitOps, and
  currently run `BestEffort`. Until they carry requests and limits, ADR-0002's first condition is
  false for them specifically.
- **Two ADR-0002 assumptions remain uninstrumented and one is now measurable.** The 4 GiB ARC and
  the 2 GiB standard slot are still assumptions. The ×5.5 write amplification threshold is still
  unmeasured, and the media stack's downloads are deliberately kept off the NVMe so that it stays
  that way: downloads and library both land on the NAS, on one export with a shared root so that
  hardlinks work.
- **Hardlinks are load-bearing for more than disk space.** With `downloads/` and `media/` under one
  root, a file is seeding and imported at once as a single copy. Without them the only choices are
  two copies or deleting the torrent, and deleting the torrent is the definition of a hit and run.
  Sonarr and Radarr must therefore run with "Remove Completed Downloads" off, leaving qBittorrent's
  per-category share limits to decide when a seed stops.
- **Slack is 1.76 GiB against ADR-0002's 2.5 GiB**, and ADR-0002 wanted that margin partly to
  absorb an ARC that a shipped OpenZFS version was observed to overrun. The margin is thinner and
  the overrun it guards against is now actually enforced rather than mis-set, which is the trade.
- **Plex remote access runs through Relay, with no port forwarded.** Cloudflare's own terms
  restrict serving video through the CDN on Free, Pro and Business plans, which removes the tunnel
  as an option before it is discussed. Relay caps at 2 Mbps and forces a transcode, and because it
  only engages when no direct connection is possible, not forwarding a port is what keeps the
  residential IP unpublished, the concern ADR-0011 named.
- **GPU time-slicing has a second real consumer.** #258 raised `replicas` to 2 for a transient
  verify probe; Plex hardware transcoding (Plex Pass held) makes it a persistent claimant
  alongside Immich's machine learning. NVIDIA's own support matrix puts the RTX 3070 Ti at 12
  concurrent NVENC sessions, so session count is never the constraint. The 8 GiB of VRAM shared
  with no isolation is, and direct play is the mitigation rather than a preference.

## Tickets

Bringing the platform back in line with this document: #261 (kubelet reservation),
#262 (ARC and dirty data), #263 (Immich re-split), #264 (Traefik and svclb caps),
#265 (README), #266 (powerline segment).

Closing the visibility gap the review found: #267 (kubelet and cAdvisor), #268
(kube-state-metrics), #269 (GPU exporter), #270 (SMART, SNMP, blackbox), #271
(Alert or Signal for the rules they make possible).

The media stack: #272 (service-set decision), #273 (implementation).

Reopened separately: #274 (off-site, on its principle rather than its price).

## Alternatives rejected

**Amending ADR-0002 in place.** It would erase the trace of what drifted and why, which is the
useful part of this document. ADR-0002's method is untouched and still governs; only its tables
and two of its conditions are superseded here.

**Cutting Immich below 8 GiB to buy slack.** Available, and it contradicts ADR-0002's own argument
that this margin "is the only mechanism separating a slowdown from an outage" under a cap that
kills. The internal re-split gives the machine-learning container what it demonstrably needs
without touching the total.

**Holding both showcase web stacks at 2 GiB each.** One was abandoned. Keeping its envelope named
would be the reserved-for-later pattern ADR-0002 rejects.

**A resident personal AI assistant at 2.5 GiB.** It would require taking 1.5 GiB from Immich, and
none of the twenty-one stated use cases is conversational.

**Deploying Omniroute as the free-tier LLM path.** Both assistant candidates ship a first-party
multi-provider aggregator already, and #164 measured Omniroute at 3.7 to 8 GB RSS. A second
aggregation layer over the one already shipped buys nothing.

**A shared seedbox as the acquisition tier now.** Defensible on bandwidth and the likely outcome if
the exit condition above fires, but it rents back upstream capacity already paid for, puts a
machine outside the platform, and would be decided today on a measurement taken in a house being
left in five weeks.

**A second local NAS as the answer to the sole-copy risk.** It answers risk register 3 and not
risk register 2: a second device in the same office is taken by the same fire, flood, theft or
move. That question belongs to ADR-0021.
