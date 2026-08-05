---
status: accepted
date: 2026-08-05
tags: [resources, memory, storage, capacity, foundation]
---

# The resource budget, and the verdict on whether it fits

Every structural decision still open on this platform — the foundation, the
orchestrator, the storage layout, the observability stack — is downstream of one
number this project cannot change: **32 GiB of RAM, in four occupied slots, with
no hardware budget now or in the coming months.** This document spends that
number, and states plainly whether the intended set of services fits inside it.

**Units.** Memory figures are **GiB** — the unit the modules, the kernel and
`zfs_arc_max` actually use, and the one the storage research (#15) uses
throughout. Storage capacity and write volumes are **decimal GB/TB**, the unit
drive vendors and TBW ratings use. The two are not mixed within a table.

## The verdict

**It fits, exactly, and only under three conditions.**

The service set as it stands after #29 and #36 — Immich, two web stacks in
development, an observability stack, an orchestrator and a GitOps engine, and
room for services not yet named — sums to **32 GiB with three free standard
slots and 2.5 GiB of unallocated slack**. The conditions are not decorations:

1. Every consumer carries an **externally enforced cap**. No project in this
   design publishes a working internal memory limit.
2. The platform **refuses admission** beyond the allocation. A cap bounds one
   service; only admission bounds their sum.
3. The filesystem cache is **pinned at 5 GiB**. Left at its default it takes
   31 GiB and there is no budget at all.

One service was dropped to reach this: **local inference is allocated zero.**

Storage capacity is not the constraint and never becomes one within this
hardware's life. Daily writes are allocated, not forecast, and hold against a
**×5.5 amplification threshold** — conditional on a measurement not yet taken
(#6). IOPS requirements are met with room to spare on the local drives; the
binding disk number is **fsync latency**, not throughput, and the platform's real
IOPS ceiling is the NAS rather than the NVMe.

## Why this is an allocation and not a forecast

A forecast estimates what each service will consume, sums the estimates, and
compares the total to the ceiling. It was rejected, for a reason this project has
now found twice.

The observability research (#17) and the Nextcloud/office research (#35) reached
the same conclusion in unrelated domains: **no project here publishes an
enforceable internal memory cap.** Collabora's `memproportion` was the single
counter-example found, and it is mis-wired — its cleanup trigger divides by the
host's `MemTotal`, so under a container limit it never fires. A forecast on this
platform would rest on numbers nothing holds the software to.

An allocation inverts the question. The ceiling is divided into envelopes, each
enforced from outside the service. The sum is under the ceiling *by
construction*, so "does it fit" stops being a prediction that can be wrong, and
the interesting question becomes **what each service gives up at its envelope**.
That question has answers; the forecast's question only has hopes.

The method is not merely tidier — it is the difference between a document that
holds and one that drifts. This ADR was drafted once with the daily-write figures
forecast rather than allocated, and a single misread column moved the total by a
factor of seven. An allocation cannot move like that: it is a decision, and
decisions only change when someone changes them.

The cost is named rather than avoided: **a memory cap converts a slowdown into an
outage.** Immich's own documentation says it — "memory constraints work by
terminating the container, so this can introduce instability if set too low"
(#16). This design accepts noisy failure over silent degradation, on a single
machine with no second node to absorb the difference. Where cgroup v2's
`memory.high` is available it should be preferred to `memory.max`, since it
throttles and reclaims rather than killing; whether the chosen orchestrator
exposes it is a question for #21, not an assumption of this one.

### Caps do not bound the sum; admission does

Ten workloads capped at 2 GiB each sit perfectly inside their caps and demand
20 GiB. A cap bounds one workload in isolation. What bounds the total is a
**reservation checked at admission**: the platform adds up what has been promised
and refuses to start the workload that would exceed the allocation.

**Admission is binding on this platform.** This is a deliberate constraint on the
orchestrator decision (#21), placed here rather than discovered there: an
orchestrator that cannot refuse an admission cannot enforce this budget. Docker
Compose starts what it is given. Kubernetes-shaped orchestrators do this natively
through requests against node-allocatable capacity.

The motive is in the project's own framing of itself: a platform hosting *N
services not yet named, by construction*. A budget that holds only while the
operator remembers it is refuted by the requirement that produced it. It fails on
exactly the evening something gets deployed "just to try it".

What this costs: a mis-declared reservation blocks a deployment. The mechanism
that keeps the sum true is the same mechanism that stands in the way at an
inconvenient moment. That is the trade, and it is accepted.

## Three classes of consumer, three enforcement mechanisms

A cgroup does not see all of the machine's memory. Treating the budget as one
column of container limits would leave its largest line unenforced.

**Class A — kernel memory, invisible to cgroups.** The ZFS ARC belongs to no
container; it is kernel cache. No container limit will ever reach it. It is set
by the `zfs_arc_max` module parameter and by nothing else, as is
`zfs_dirty_data_max` — which defaults to 3.2 GiB here, *in addition to* the ARC.
Two caveats from #15 are carried into the budget rather than assumed away: the
ARC does not shrink below `zfs_arc_min`, 1 GiB by default on this machine; and on
OpenZFS 2.3.x `zfs_arc_max` **is not a hard bound** — an upstream bug showed the
ARC at roughly 4.6 GB with the parameter set to 2 GB, fixed in July 2025. The
kernel-side cap is a target, not a guarantee.

**Class B — host processes.** Kernel, systemd, `sshd`, journald, and the
orchestrator agent where it runs as a systemd unit. Bounded by systemd slices
(`MemoryMax=` / `MemoryHigh=`), not by container limits.

**Class C — workloads.** Container limits apply here and only here.

The consequence that matters: **the single largest line in the budget sits in the
class with the weakest enforcement.**

## The memory allocation

| Consumer | Envelope | Basis |
| --- | --- | --- |
| Host — kernel, systemd, `sshd`, journald | 1 GiB | estimate; to be measured |
| Filesystem cache | 5 GiB | #15 — see below |
| Control plane + node agent | 1.5 GiB | #13 |
| GitOps engine | 1 GiB | #13 — Flux ships 7 controllers at 64Mi requested, 1Gi capped each |
| Observability | 3 GiB | #17 |
| **Reserved floor** | **11.5 GiB** | |
| Immich | 8 GiB | #16 |
| Two web stacks — 2 standard slots | 4 GiB | see below |
| Three free standard slots | 6 GiB | growth capacity |
| Unallocated slack | 2.5 GiB | |
| **Total** | **32 GiB** | |

### The filesystem cache envelope — 5 GiB, and it is opposable

**4 GiB of ARC (`zfs_arc_max`) and 1 GiB of dirty data
(`zfs_dirty_data_max`, against a 3.2 GiB default).**

This envelope exists because ZFS creates a budget line that ext4 and XFS do not.
A page cache is reclaimable — the kernel gives it back under pressure, which is
why nobody budgets for it. The ARC gives its memory back more slowly and, in at
least one shipped version, not at all when told to.

The size is settled by one fact from #16: **Immich's hot working set is
150–300 GB.** No ARC that fits on this machine caches a useful fraction of it, so
sizing the ARC to the working set is not an option that exists. What remains is
sizing it to metadata, which is a different order of magnitude. It also matters
that the ARC is a *read* cache: shrinking it costs disk reads, and #15 established
that the scarce resource on these drives is write endurance, not read latency.

**This envelope is binding on the storage decision (#19).** The budget does not
choose a filesystem; it prices one. ZFS may be chosen, but it enters that decision
with 5 GiB — roughly a sixth of the machine — already spent, to be weighed against
what it buys: checksums, snapshots, and a topology reversible through `zpool
attach`. ext4 and XFS enter at zero. That comparison does not exist if this
document stays silent, and #19 would then be free to choose ZFS without ever
seeing its cost in RAM — precisely the hidden overrun this budget was written to
prevent.

The 4 GiB figure is an **assumption, not a measurement**. #15 is explicit that no
upstream source quantifies the performance cost of any given `zfs_arc_max`. It is
derived by elimination, and #31 must instrument it.

### Immich — 8 GiB, machine learning included and reserved

| Container | Cap |
| --- | --- |
| PostgreSQL + VectorChord | 2.5 GiB |
| `immich-server` + jobs | 3 GiB |
| `machine-learning` | 2 GiB |
| Redis | 0.5 GiB |

Immich documents 6 GB minimum and 8 GB recommended, 4 GB viable with machine
learning disabled, and 2 GB minimum for PostgreSQL specifically *when container
limits are in use* — which this design guarantees. Note the reading: those are
**whole-system** figures, so an 8 GiB envelope for Immich's containers alone is
deliberately conservative. Under a cap that kills, margin is not comfort; it is
the only mechanism separating a slowdown from an outage.

**The machine-learning envelope is reserved even though the workload is bursty.**
Immich sheds ML memory when idle — the worker exits on purpose, and its own FAQ
says so. Budgeting against that idle floor is exactly the move this decision
forbids: face detection on a photo that arrives on a Sunday evening would then
meet a full machine, and the cap would kill the container.

**The initial import is sequenced, not budgeted.** 1.5 TB enters once, and #16
names it the most intensive period the system will ever see. A one-off dated
operation is not a steady state: it runs before the other services exist, under a
temporarily widened envelope, and the machine returns to the nominal regime
afterwards. This is not the "they are never busy at once" assumption the budget
rejects — non-concurrency is *guaranteed by sequencing* rather than hoped for.

### The standard slot — 2 GiB

| Component | Cap |
| --- | --- |
| Application | 1 GiB |
| Database | 768 MiB |
| Margin | 256 MiB |

The two web stacks take one slot each. They were deliberately **not** sized
individually: this platform holds application repositories out of scope, on the
principle that a platform decision depending on an application's internals is
evidence of coupling to remove. Bespoke envelopes would manufacture exactly that
coupling, and would have to be re-derived for every application that follows.

The slot's real value is that it gives the budget a unit in which to answer the
"N services not yet named" requirement. The capacity statement becomes **"this
platform holds K slots"** rather than "there is some memory left" — a sentence
that can be held up against a future request, and checked.

2 GiB is an assumption, like the ARC figure, and #31 must instrument it. A
workload that does not fit a slot becomes an explicit exception that must argue
for its envelope against this budget. That is the price of remaining agnostic to
the services, and it is a feature: it makes the greedy application visible instead
of letting it help itself.

## Storage capacity is not the constraint

Computed in the **least favourable topology** — a mirror, ~1 TB usable, pool held
under 80% — so that #19 remains free to choose without this budget having
presupposed the generous arrangement:

| Consumer | GB | Basis |
| --- | --- | --- |
| OS + container images | ~50 | estimate |
| Immich derivatives (`thumbs`, `encoded-video`) | 150–300 | #16 — 10–20% of 1.5 TB |
| PostgreSQL + VectorChord | 3–20 | #16 — "1–3 GB" is a floor, not a bound |
| Observability, 30-day retention | 10–30 | #17 |
| Five slots' data | ~100 | derived from the slot |
| **Total** | **~313–500** | |
| **Available** | **~800** | |

The 1.5 TB of originals stay on the NAS over NFS; the database never touches a
network share, which Immich forbids outright (#16). Roughly 300 GB of margin
remains in the worst case on the more expensive topology.

## Daily writes are allocated too

The first draft of this document forecast this section and got it wrong by a
factor of seven, by reading #17's `Stored bytes/day` column as if it were a write
rate — #17 warns against exactly that, on the line immediately below the table:
"**Write volume ≠ stored bytes.**" The correction is not a better forecast. It is
to allocate writes the same way memory is allocated.

| Writer | Envelope | Enforced by |
| --- | --- | --- |
| Observability | 10 GB/day | scrape interval, retention, cardinality limits, log volume caps — the levers #17 inventories |
| Immich, steady state | 2 GB/day | derivative churn on new assets only |
| PostgreSQL WAL + five slots | 3 GB/day | |
| Host + system journals | 1 GB/day | journald caps |
| **Total allocated** | **16 GB/day** | |

**The endurance target is ten years: 88 GB/day per drive.** A mirror does not
split this budget — both drives take every write (#15). ZFS then multiplies the
allocated figure, and #15 is unambiguous that **the factor is measured nowhere**,
not upstream and not here. So the budget does not predict it; it sets a threshold
against it.

| Amplification | Actual writes | Life to 320 TB |
| --- | --- | --- |
| ×2 | 32 GB/day | ~27 years |
| **×5.5** | **88 GB/day** | **~10 years — the target** |
| ×10 | 160 GB/day | ~5.5 years |
| ×20 | 320 GB/day | ~2.7 years |

**The threshold opposable to #19 is ×5.5.** The ten-year target was chosen over
the five-year one because the hardware budget is zero as a standing constraint —
a five-year target schedules a purchase nothing funds — and because it converts
#15's open unknown into something #6 and #30 can test. A threshold can be refuted;
a prediction just ages.

`atime=off` follows from the ten-year target and is binding on #19: #15 costs
`relatime` at one metadata write per file read per day.

**The 10 GB/day observability envelope is binding on #31**, exactly as its 3 GiB
is. It forces a 60-second scrape interval rather than 15, a bounded retention and
a cardinality limit — the levers #17 catalogued without anything making them
mandatory. #17's own bounding exercise, stacking its worst cardinality row with a
brutal ×10 amplification and the top of its log-volume bracket, reaches ~26 GB/day;
this envelope is deliberately tighter than that bound and looser than its middle
case, and it is a decision rather than a reading.

### At peak

Two events write far more than the steady state, and neither is budgeted — both
are bounded and dated:

- **The initial import**: ~300 GB of derivatives written once. At ×5.5 that is
  ~1.65 TB, about **0.5% of the TBW budget**. Negligible.
- **A full derivative regeneration**, which #16 warns is forced by a later change
  of face model or thumbnail settings: the same ~300 GB again, so ~0.5% per
  regeneration. A handful over the hardware's life is affordable; a habit of them
  is not.

**This part of the verdict is conditional on #6.** The drives' consumed TBW has
never been recorded, so the ten-year clock may already have been running for some
time. The margin above is computed as though the counter starts now, and that
assumption is not yet checked.

## IOPS: the requirements are trivial, the latency is not

Absolute IOPS requirements on this platform are small enough that NVMe meets them
without discussion. What is not trivial is the **synchronous write latency** they
come attached to, on drives #15 established are DRAM-less.

| Consumer | Documented requirement | Source |
| --- | --- | --- |
| Kine/SQLite datastore | 10 IOPS, 500 KiB/s, **< 10 ms** | #13 |
| Embedded etcd datastore | 50 IOPS, 250 KiB/s, **< 5 ms** | #13 |
| etcd, upstream floor | "50 sequential IOPS is required"; "fast disks are the most critical factor" | #13 |
| Immich derivative reads | "small-file, high-IOPS, latency-sensitive, read-dominated, with a write burst during import" | #16 |
| Observability | not established | #17 |
| Standard slot | not established | |

Three conclusions the rest of the design must carry:

1. **The number to validate is 5 ms, not 50 IOPS.** #13 states it directly:
   the sub-5 ms requirement "is the number to validate empirically before choosing
   etcd over SQLite". On a DRAM-less consumer drive under sustained small
   synchronous writes this is not a safe assumption, and ZFS routes every `fsync`
   through the ZIL (#15). **#30 is the open ticket that measures it, and #21 must
   not choose embedded etcd before it reports.**
2. **Immich's high-IOPS path is read-dominated and already local by design.** #16
   put derivatives on NVMe precisely to remove read amplification against the NAS.
   Reads cost latency, not endurance, which is why the ARC was cut to 4 GiB
   without this becoming a write problem.
3. **The IOPS ceiling this platform actually hits is the NAS, not the NVMe.** #16
   ends on exactly that: *"The ceiling that will actually be hit is VRAM, and
   after that, NAS IOPS during the nightly scan — not system memory."* A DS412+ on
   an Atom D2700 over gigabit is the slow end of every path that touches
   originals. That belongs to #12, and this budget does not spend it.

## CPU takes a different regime

**RAM is incompressible; CPU is compressible.** Exceeding a memory envelope is
death; exceeding a share of CPU is waiting. The entire apparatus above — hard
caps, binding admission, a guaranteed sum — exists because memory cannot share
itself under pressure. CPU can, at microsecond granularity. Reproducing the memory
regime here out of symmetry would be a mistake.

Six cores and twelve threads, against what is actually documented per consumer:

| Consumer | Documented figure | Source |
| --- | --- | --- |
| Immich | minimum 2 cores, recommended 4 | #16 |
| k3s | server 2 cores, agent 1 core | #13 |
| k0s | controller 1 vCPU, worker 1 vCPU | #13 |
| etcd | 2 vCPUs — for a 50-node cluster, ceiling-shaped | #13 |
| Observability collector | 0.4 cores per **1 million** active series, clustered → ~0.01 here | #17 |
| Metrics store, log store, Grafana | not established | #17 |
| Host, GitOps engine, standard slot | not established | |

The census is deliberately incomplete rather than filled with invented numbers:
six of the eleven consumers are not documented anywhere, and #17's collector rate is
published per million series in clustered deployments, which is three orders of
magnitude above this node. What the documented rows already show is that the
**recommendations alone oversubscribe the machine on paper** — Immich's 4 plus a
control plane's 2 is already 6 of 6 cores before anything else runs. #13 records
the same tension from the other side: CPU, not RAM, was the binding constraint in
the k3s profiling it examined, at 90% CPU while memory sat near 60%.

A per-service CPU allocation built on that evidence would be more than half
invention. The regime is therefore relative weights, with two exceptions.

1. **General case: weights, not quotas.** Interactive work — Immich's web
   interface, the web stacks, ingress — outranks background work — ML,
   transcoding, backups, compaction. Under contention the kernel arbitrates, and
   everything slows in the right order rather than something dying.
2. **A guaranteed share for the host and control plane**, roughly one core
   equivalent. This is the one starvation that is unrecoverable: a saturated node
   that has lost its node agent and its `sshd` cannot be repaired without a reboot.
3. **A hard ceiling on Immich's batch queues**, through Immich's own job
   concurrency settings — the lever #16 documents — rather than a cgroup quota.
   Left at defaults, thumbnail generation, smart search, face detection and
   metadata extraction together request far more than twelve threads, and the
   initial import makes the interface unusable for hours. This is the one case
   where "it gets slow" becomes "it does not work".

## What was dropped, and what was never available

### Local inference is allocated zero

Not deferred headroom — **zero**, in the same form and for the same reason as #36:
an envelope reserved "for later" gets eaten by something else while suggesting a
decision was taken.

The reason is not RAM. It is VRAM, and it is documented. Immich's machine
learning already has a VRAM problem on this class of card, from #16:

- **Issue #11979** (on a 4 GiB card): under concurrent face detection, smart
  search and transcoding, smart search **leaks VRAM** — not released, and
  re-running the job does not help; only a container restart does.
- **Issue #23462**, still open: a **12 GB** card filled in one hour. Growth
  unbounded.
- **Immich publishes no VRAM budget anywhere.** #16 states outright that 8 GB
  cannot be checked against any requirement, only against reported behaviour.

#16's conclusion is adopted here verbatim: *"A 3070 Ti's 8 GB shared with any
other GPU consumer is squarely in the region where these reports originate."*
Local inference is by definition that other consumer. The contention is over
8 GB of VRAM, not 32 GiB of RAM, and **neither occupant publishes its
requirement** — so this cannot be arbitrated by arithmetic, because there is no
arithmetic to do.

What this gives up is real: local inference was the last use that justified the
RTX 3070 Ti as anything other than an Immich accelerator. #28 kept the card as a
schedulable platform resource after removing gaming; this budget reduces it, in
practice, to that one role. That is the honest consequence of #28 rather than a
departure from it.

**Reopening condition: a second node carrying its own GPU.** This matches the
standing constraint — growth happens by adding machines, never by modifying this
one.

### Replacing the memory modules is not an option on the table

Stated plainly rather than left as an implicit alternative: **it is excluded.**
The hardware budget is zero now and for the coming months, all four slots are
occupied so any increase means discarding the installed modules rather than
adding to them, and the project's standing preference is to grow by adding nodes
instead of modifying this machine. This is not a lever held in reserve; it is
ruled out, and every figure above is written against a ceiling that does not move.

### Levers used, and levers still held

The ticket's ordered reduction options were exercised as follows. **Footprint
reduction** was applied to observability, whose 3 GiB is already the trimmed figure
#17 argued for. **Dropping a service** was applied twice: Nextcloud and the office
server in #36, local inference here. **Adding or replacing storage** was not
needed — capacity is not the constraint. **Replacing the memory** was excluded, as
above. No option required pricing in euros, because the verdict is that it fits.

Two levers remain in reserve should the budget ever need to give memory back,
recorded so a future reader does not have to rediscover them:

- **The three free standard slots: −6 GiB.** The largest single reduction
  available, at the cost of the platform's entire growth capacity.
- **Disabling Immich's machine learning: −2 GiB**, the size of the ML container
  in the allocation above. It costs semantic search and face recognition — what
  distinguishes Immich from a folder of photographs — and #16 flags a trap: a
  later change of face model forces re-running detection over the entire corpus,
  so the choice is paid for twice if reversed.

## Consequences

**Constraints this budget places on decisions still open.** These belong on their
tickets and are recorded here as the single place they were derived:

- **#19, storage layout** — ZFS enters costed at 5 GiB of RAM; ext4 and XFS at
  zero. Write amplification threshold ×5.5 for the ten-year endurance target;
  `atime=off` is mandatory.
- **#20, foundation** — the reserved floor allows 1 GiB for the host, and the
  chosen foundation must be able to enforce systemd-slice limits on class B.
- **#21, orchestrator** — must be able to **refuse an admission**; this rules out
  a family of candidates. It must not choose embedded etcd before #30 reports on
  fsync latency. Whether it exposes cgroup v2 `memory.high` rather than only
  `memory.max` should be established from primary sources, not assumed.
- **#31, observability** — 3 GiB of memory *and* 10 GB/day of writes are both
  binding, and three assumptions in this document require instrumentation: the
  4 GiB ARC, the 2 GiB standard slot, and the ×5.5 amplification threshold.
- **#12, NAS regime** — inherits the finding that the platform's real IOPS ceiling
  is the DS412+ during the nightly scan, not the local drives.

**There is no admission gate on CPU.** The "K slots" figure is a memory number.
The platform will refuse a workload that does not fit in RAM and will **accept**
one that makes it slow. This is a deliberate hole, written down rather than left
to be discovered: nothing prevents CPU oversubscription, so #31 must make it
visible instead.

**The three enforcement mechanisms differ in strength, and the weakest guards the
largest line.** The 5 GiB filesystem envelope rests on a kernel module parameter
that a shipped OpenZFS version was observed to overrun. The 2.5 GiB of slack exists
partly for that reason and is not spare capacity.

**Two of the largest figures are assumptions rather than measurements** — the
4 GiB ARC and the 2 GiB slot — in a document whose whole method is to replace
prediction with enforcement. They are enforced from the outset and measured
afterwards, which is the right order under a hard ceiling, but it means the
allocation's internal split may need revisiting once #31 reports. The total will
not: 32 GiB does not move.

**Five of eleven rows in the CPU census are not established from primary sources**,
and the write and IOPS tables have their own gaps. Those blanks are left visible
rather than filled with plausible numbers, because a budget whose figures cannot
be traced to a source or a decision is the forecast this document rejected.

**Every envelope above is a number someone must now design against.** That is the
point — three decisions were blocked on this one precisely because they needed a
constraint rather than an estimate.

## Alternatives rejected

**A forecast rather than an allocation** — estimate each service's consumption,
sum, compare. Rejected because nothing here publishes an enforceable internal cap,
so the estimates would bind nothing, and because this document demonstrated the
failure mode on itself: one misread column moved the write total sevenfold.

**Caps without an admission gate.** Simpler, and it leaves the budget true only
while the operator remembers it — refuted by the platform's own requirement to
host services not yet named.

**Hard per-service CPU quotas.** They produce predictable numbers by wasting the
machine, leaving a workload throttled at two cores while four sit idle. On a
single node where the scarce resource is demonstrably memory, capping unused CPU
buys nothing. Five of the eleven rows in the census are also undocumented, so the
quotas would be largely invented.

**Sizing the ARC to the working set.** Not an option that exists: #16 puts
Immich's hot set at 150–300 GB, which no ARC on this machine approaches.

**Local inference resident at 4–6 GiB.** Two to three standard slots — the
machine's entire growth capacity — and it stacks two undocumented VRAM consumers
on 8 GB, one of which leaks.

**Local inference non-resident**, borrowing free slots per session as the Immich
import does. Defensible on RAM, and it assumes the GPU can be handed back cleanly;
#11979 says the failure path is exactly where VRAM is not released. It would trade
a clean memory envelope for an Immich container restart per session.

**Local inference on CPU.** Avoids the VRAM collision entirely and is unusable on
six cores shared with Immich, PostgreSQL and observability.

**A five-year endurance target** (175 GB/day per drive, threshold ×10.9). It grants
#19 more latitude and schedules a drive replacement that no budget funds.

**Setting the write threshold on #17's pessimistic bound** (~29 GB/day all in,
threshold ×3). Honest, and built by stacking two deliberately brutal assumptions — the
worst cardinality row *and* a ×10 amplification, the top of the log bracket *and*
×10 — against a note whose own conclusion is that "endurance is **not** a
criterion at this scale". Compounded pessimism would over-constrain #19.
