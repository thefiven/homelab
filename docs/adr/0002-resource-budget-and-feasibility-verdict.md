---
status: accepted
date: 2026-08-05
tags: [resources, memory, storage, capacity, foundation]
---

# The resource budget, and the verdict on whether it fits

Every structural decision still open on this platform — the foundation, the
orchestrator, the storage layout, the observability stack — is downstream of one
number this project cannot change: **32 GB of RAM, in four occupied slots, with
no hardware budget now or in the coming months.** This document spends that
number, and states plainly whether the intended set of services fits inside it.

## The verdict

**It fits, exactly, and only under three conditions.**

The service set as it stands after ADR-supporting decisions #29 and #36 — Immich,
two web stacks in development, an observability stack, an orchestrator and a
GitOps engine, and room for services not yet named — sums to **32 GB with three
free standard slots and 2.5 GB of unallocated slack**. The conditions are not
decorations:

1. Every consumer carries an **externally enforced cap**. No project in this
   design publishes a working internal memory limit.
2. The platform **refuses admission** beyond the allocation. A cap bounds one
   service; only admission bounds their sum.
3. The filesystem cache is **pinned at 5 GB**. Left at its default it takes
   31 GiB and there is no budget at all.

One service was dropped to reach this: **local inference is allocated zero.**

Storage capacity is not the constraint and never becomes one within this
hardware's life. Write endurance holds with a wide margin, against a threshold
stated below rather than a prediction, and conditional on a measurement that has
not yet been taken (#6).

## Why this is an allocation and not a forecast

A forecast estimates what each service will consume, sums the estimates, and
compares the total to 32 GB. It was rejected, for a reason this project has now
found twice independently.

The observability research (#17) and the Nextcloud/office research (#35) reached
the same conclusion in unrelated domains: **no project here publishes an
enforceable internal memory cap.** Collabora's `memproportion` was the single
counter-example found, and it is mis-wired — its cleanup trigger divides by the
host's `MemTotal`, so under a container limit it never fires. A forecast on this
platform would therefore rest on numbers that nothing holds the software to.

An allocation inverts the question. The 32 GB is divided into envelopes, each
enforced from outside the service. The sum is under the ceiling *by
construction*, so "does it fit" stops being a prediction that can be wrong, and
the interesting question becomes **what each service gives up at its envelope**.
That question has answers; the forecast's question only has hopes.

The cost is named rather than avoided: **a memory cap converts a slowdown into an
outage.** Immich's own documentation says it — "memory constraints work by
terminating the container, so this can introduce instability if set too low"
(#16). This design accepts noisy failure over silent degradation, on a single
machine with no second node to absorb the difference. Where cgroup v2's
`memory.high` is available it should be preferred to `memory.max`, since it
throttles and reclaims rather than killing; whether the chosen orchestrator
exposes it is a question for that decision, not an assumption of this one.

### Caps do not bound the sum; admission does

Ten services capped at 2 GB each sit perfectly inside their caps and demand
20 GB. A cap bounds one service in isolation. What bounds the total is a
**reservation checked at admission**: the platform adds up what has been promised
and refuses to start the service that would exceed the allocation.

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
inconvenient moment. That is the trade and it is accepted.

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
| Host — kernel, systemd, `sshd`, journald | 1 GB | estimate; to be measured |
| Filesystem cache | 5 GB | #15 — see below |
| Control plane + node agent | 1.5 GB | #13 |
| GitOps engine | 1 GB | #13 — Flux ships 7 controllers at 64Mi requested, 1Gi capped each |
| Observability | 3 GB | #17 |
| **Reserved floor** | **11.5 GB** | |
| Immich | 8 GB | #16 |
| Two web stacks — 2 standard slots | 4 GB | see below |
| Three free standard slots | 6 GB | growth capacity |
| Unallocated slack | 2.5 GB | |
| **Total** | **32 GB** | |

### The filesystem cache envelope — 5 GB, and it is opposable

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
with 5 GB — roughly a sixth of the machine — already spent, to be weighed against
what it buys: checksums, snapshots, and a topology reversible through `zpool
attach`. ext4 and XFS enter at zero. That comparison does not exist if this
document stays silent, and #19 would then be free to choose ZFS without ever
seeing its cost in RAM — which is precisely the hidden overrun this budget was
written to prevent.

The 4 GiB figure is an **assumption, not a measurement**. #15 is explicit that no
upstream source quantifies the performance cost of any given `zfs_arc_max`. It is
derived by elimination, and #31 must instrument it.

### Immich — 8 GB, machine learning included and reserved

| Container | Cap |
| --- | --- |
| PostgreSQL + VectorChord | 2.5 GB |
| `immich-server` + jobs | 3 GB |
| `machine-learning` | 2 GB |
| Redis | 0.5 GB |

Immich documents 6 GB minimum and 8 GB recommended, 4 GB viable with machine
learning disabled, and 2 GB minimum for PostgreSQL specifically *when container
limits are in use* — which this design guarantees. Note the reading: those are
**whole-system** figures, so an 8 GB envelope for Immich's containers alone is
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

### The standard slot — 2 GB

| Component | Cap |
| --- | --- |
| Application | 1 GB |
| Database | 768 MB |
| Headroom | 256 MB |

The two web stacks take one slot each. They were deliberately **not** sized
individually: this platform holds application repositories out of scope, on the
principle that a platform decision depending on an application's internals is
evidence of coupling to remove. Bespoke envelopes would manufacture exactly that
coupling, and would have to be re-derived for every application that follows.

The slot's real value is that it gives the budget a unit in which to answer the
"N services not yet named" requirement. The capacity statement becomes **"this
platform holds K slots"** rather than "there is some memory left" — a sentence
that can be held up against a future request, and checked.

2 GB is an assumption, like the ARC figure, and #31 must instrument it. An
application that does not fit a slot becomes an explicit exception that must
argue for its envelope against this budget. That is the price of remaining
agnostic to the services, and it is a feature: it makes the greedy application
visible instead of letting it help itself.

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
| **Total** | **~315–500** | |
| **Available** | **~800** | |

The 1.5 TB of originals stay on the NAS over NFS; the database never touches a
network share, which Immich forbids outright (#16). Roughly 300 GB of headroom
remains in the worst case on the more expensive topology.

## Write endurance: a threshold, not a prediction

Host-level writes, before any filesystem amplification:

| Writer | GB/day |
| --- | --- |
| Metrics | ~0.6 — #17, its worst row |
| Logs | ~0.2 stored — 2 GB/day raw at 10× compression |
| Immich, steady state | < 1 |
| PostgreSQL WAL + five slots | ~2 |
| **Total** | **~4 GB/day** |

ZFS then multiplies this, and #15 is unambiguous that **the factor is measured
nowhere** — not upstream, not here. So the budget does not predict it. It sets a
threshold against it.

**The endurance target is ten years: 88 GB/day per drive.** A mirror does not
split this budget — both drives take every write (#15).

| Amplification | Actual writes | Life to 320 TBW |
| --- | --- | --- |
| ×10 | 40 GB/day | ~22 years |
| **×20** | **80 GB/day** | **~11 years** |
| ×44 | 175 GB/day | 5 years |

**The threshold opposable to #19 is ×20.** The ten-year target was chosen over
the five-year one because the hardware budget is zero as a standing constraint —
a five-year target schedules a purchase nothing funds — and because at 4 GB/day
of input the stricter target still leaves a factor of twenty in hand. It tightens
a constraint that currently binds on nothing, while converting #15's open unknown
into something #6 and #30 can test. A threshold can be refuted; a prediction just
ages.

The initial import writes ~300 GB of derivatives once — about 1% of the TBW
budget even at ×10. Negligible.

`atime=off` follows from the ten-year target and is binding on #19: #15 costs
`relatime` at one metadata write per file read per day.

**This part of the verdict is conditional on #6.** The drives' consumed TBW has
never been recorded, so the ten-year clock may already have been running for some
time. The margin above is computed as though the counter starts now, and that
assumption is not yet checked.

## CPU takes a different regime

**RAM is incompressible; CPU is compressible.** Exceeding a memory envelope is
death; exceeding a share of CPU is waiting. The entire apparatus above — hard
caps, binding admission, a guaranteed sum — exists because memory cannot share
itself under pressure. CPU can, at microsecond granularity. Reproducing the memory
regime here out of symmetry would be a mistake.

Six cores and twelve threads, against recommendations that already oversubscribe
the machine on paper: 4 cores for Immich (#16), 1–2 for the control plane (#13),
~0.4 for observability (#17). #13 also records that CPU, not RAM, was the binding
constraint in the k3s profiling it examined — 90% CPU while memory sat near 60%.

**The regime is relative weights, with two exceptions.**

1. **General case: weights, not quotas.** Interactive work — Immich's web
   interface, the web stacks, ingress — outranks background work — ML,
   transcoding, backups, compaction. Under contention the kernel arbitrates, and
   everything slows in the right order rather than something dying.
2. **A reserved floor for the host and control plane**, roughly one core
   equivalent, guaranteed. This is the one starvation that is unrecoverable: a
   saturated node that has lost its node agent and its `sshd` cannot be repaired
   without a reboot.
3. **A hard ceiling on Immich's batch queues**, through Immich's own job
   concurrency settings — the lever #16 documents — rather than a cgroup quota.
   Left at defaults, thumbnail generation, smart search, face detection and
   metadata extraction together request far more than twelve threads, and the
   initial import makes the interface unusable for hours. This is the one case
   where "it gets slow" becomes "it does not work".

Hard per-service CPU quotas were rejected: they produce predictable numbers by
wasting the machine, leaving a service throttled at two cores while four sit idle.
On a single node where the scarce resource is demonstrably memory, capping unused
CPU buys nothing.

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
8 GB of VRAM, not 32 GB of RAM, and **neither occupant publishes its
requirement** — so this cannot be arbitrated by arithmetic, because there is no
arithmetic to do.

What this gives up is real: local inference was the last use that justified the
RTX 3070 Ti as anything other than an Immich accelerator. #28 kept the card as a
schedulable platform resource after removing gaming; this budget reduces it, in
practice, to that one role. That is the honest consequence of #28 rather than a
departure from it.

Two alternatives were weighed. **Resident, at 4–6 GB**: two to three standard
slots, i.e. the machine's entire growth capacity, and it stacks two undocumented
VRAM consumers on 8 GB, one of which leaks. **Non-resident, borrowing free slots
per session** like the Immich import: defensible on RAM, but it assumes the GPU
can be handed back cleanly, and #11979 says the failure path is exactly where
VRAM is not released — it would trade a clean memory envelope for an Immich
container restart per session. CPU inference avoids the VRAM collision and is
unusable on six cores shared with Immich, PostgreSQL and observability.

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
reduction** was applied to observability, whose 3 GB is already the trimmed figure
#17 argued for. **Dropping a service** was applied twice: Nextcloud and the office
server in #36, local inference here. **Adding or replacing storage** was not
needed — capacity is not the constraint. **Replacing the memory** was excluded, as
above.

Two levers remain in reserve should the budget ever need to give back memory,
recorded so that a future reader does not have to rediscover them:

- **Disabling Immich's machine learning: −4 GB.** By far the largest single
  reduction available. It costs semantic search and face recognition — what
  distinguishes Immich from a folder of photographs — and #16 flags a trap: a
  later change of face model forces re-running detection over the entire corpus,
  so the choice is paid for twice if reversed.
- **The three free standard slots: −6 GB**, at the cost of the platform's entire
  growth capacity.

## Consequences

**Constraints this budget places on decisions still open.** These belong on their
tickets and are recorded here as the single place they were derived:

- **#19, storage layout** — ZFS enters costed at 5 GB of RAM; ext4 and XFS at
  zero. Amplification threshold ×20 for the ten-year endurance target;
  `atime=off` is mandatory.
- **#20, foundation** — the reserved floor allows 1 GB for the host, and the
  chosen foundation must be able to enforce systemd-slice limits on class B.
- **#21, orchestrator** — must be able to **refuse an admission**; this rules out
  a family of candidates. Whether it exposes cgroup v2 `memory.high` rather than
  only `memory.max` should be established from primary sources, not assumed.
- **#31, observability** — the 3 GB cap is now binding, and three assumptions in
  this document require instrumentation: the 4 GiB ARC, the 2 GB standard slot,
  and the ×20 amplification threshold.

**There is no admission gate on CPU.** The "K slots" figure is a memory number.
The platform will refuse a service that does not fit in RAM and will **accept**
one that makes it slow. This is a deliberate hole, written down rather than left
to be discovered: nothing prevents CPU oversubscription, so #31 must make it
visible instead.

**The three enforcement mechanisms differ in strength, and the weakest guards the
largest line.** The 5 GB filesystem envelope rests on a kernel module parameter
that a shipped OpenZFS version was observed to overrun. The 2.5 GB of slack exists
partly for that reason and is not spare capacity.

**Two of the largest figures are assumptions rather than measurements** — the
4 GiB ARC and the 2 GB slot — in a document whose whole method is to replace
prediction with enforcement. They are enforced from the outset and measured
afterwards, which is the right order under a hard ceiling, but it means the
allocation's internal split may need revisiting once #31 reports. The total will
not: 32 GB does not move.

**The endurance verdict is conditional on a measurement not yet taken** (#6). If
the drives turn out to have consumed a significant share of their 320 TBW, the
ten-year target is already compromised and the threshold must be recomputed
rather than the target quietly relaxed.

**Every envelope above is a number someone must now design against.** That is the
point — three decisions were blocked on this one precisely because they needed a
constraint rather than an estimate.
