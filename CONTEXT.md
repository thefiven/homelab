# homelab

A single-operator, self-hosted execution platform, agnostic to the services it
runs. This glossary fixes the terms whose everyday synonyms are misleading here.

## Language

### The platform and what it runs

**Platform**:
The execution substrate this repository designs and operates. It is the product;
what runs on it is interchangeable.

**Workload**:
Anything the platform runs on behalf of a consumer, as opposed to the platform's
own machinery. Use this word when the distinction from the platform is what
matters — a workload's internals are out of scope for a platform decision.

**Service set**:
The named workloads this platform has committed to running. Membership is decided,
not discovered: a service enters or leaves it by an ADR.

### Verification

**Hardware-free check**:
A check that runs without touching the physical node or NAS: what
`scripts/check.py` runs, and the only kind of check CI is capable of running.
_Avoid_: test, test suite. This repository doesn't use those words for it.

**Platform verify**:
An `ansible` `--tags verify` task, run against the real node to prove one of
the platform's invariants already holds (a ZFS pool is ONLINE, the k3s node
is Ready, Flux's controllers are healthy...) rather than to mutate anything.
See [docs/reference/platform-state.md](./docs/reference/platform-state.md).
Human-in-the-loop by nature: it needs the real machine, so CI can never run
it. "CI is green" and "the platform verify passed on node1" are never the
same claim.

### Alerting

The first two are routinely used as two intensities of one word. They are not:
the boundary is action, not severity. See
[ADR-0004](./docs/adr/0004-victoriametrics-victorialogs-observability.md) and
[ADR-0018](./docs/adr/0018-ntfy-receiver-healthchecks-witness.md).

**Alert**:
A notification that demands a human gesture, costs something if ignored, and
will not resolve itself. It pushes to the phone. The set is closed at five
categories and grows only by an ADR.
_Avoid_: warning, notification

**Signal**:
Everything else the observability stack produces. It lives in Grafana and never
notifies. A signal is read when someone thinks to look, which is why no failure
that needs a gesture is left as one.
_Avoid_: low-priority alert, soft alert

**Witness**:
The external service that notices this platform's silence. It is not a probe:
nothing is asked of the platform, the platform speaks on a schedule and the
**absence** of speech is the alarm. Its whole value is being somewhere that
does not die with the machine it watches.
_Avoid_: monitor, uptime check

### The resource budget

The first three terms below are routinely conflated and mean different things.
See [ADR-0002](./docs/adr/0002-resource-budget-and-feasibility-verdict.md).

**Envelope**:
The share of a finite machine resource allocated to one consumer by the resource
budget — of memory, of daily writes, or of stored capacity. It is a decision, not
an observation.
_Avoid_: Quota, allowance

**Reservation**:
What a consumer declares it needs, checked at admission. This is what makes the
sum of all envelopes true.
_Avoid_: Request — except when naming an orchestrator's own field

**Cap**:
The point beyond which a consumer is throttled or killed. This is what makes one
consumer's overrun someone else's non-problem.
_Avoid_: Limit, ceiling, max

**Resource budget**:
The document that divides a machine resource into envelopes and states whether
the service set fits. It allocates; it does not forecast.

**Standard slot**:
The unit envelope an ordinary workload receives without arguing for one — an
application plus its database. Platform capacity is stated in slots.

**Reserved floor**:
The part of the machine consumed before any workload sees it. Its two halves are
not interchangeable, and
[ADR-0020](./docs/adr/0020-revised-allocation-after-measurement.md) separates
them for that reason: one half is invisible to the admission gate (host,
filesystem cache, the control plane's own process) and has to be subtracted from
the machine before the gate counts anything; the other declares itself as an
ordinary reservation and the gate sees it for free (GitOps engine, observability,
platform services). Stating the floor as one number is what lets the first half
be handed out twice.

**Slack**:
Machine resource deliberately left unallocated at the platform level. It is not
spare capacity and is not available to a workload.
_Avoid_: Headroom, spare capacity

**Amplification threshold**:
The multiplier a storage layer may apply to the allocated write budget before the
endurance target is missed. It is opposable to a storage decision, and refutable
by measurement.

### Storage

See [ADR-0010](./docs/adr/0010-zfs-system-state-split-storage-layout.md).

**System pool**:
The ZFS pool holding everything Ansible and GitOps reconstruct from this
repository — OS root, k3s, container images, the ML model cache. Disposable by
construction; a lost drive is a reinstall, not a restore.
Subiquity's ZFS-guided autoinstall names it `bpool` (boot) and `rpool`
(root) on disk, not literally `system` — "system pool" is this glossary's
name for the pair, not a `zpool list` name to grep for.

**State pool**:
The ZFS pool holding what no rebuild recreates — application databases and
Immich's generated derivatives. Of these, only the application databases are
what #23's backup and recovery strategy targets (ADR-0012); the derivatives
are excluded as regenerable from the originals.
_Avoid_: data disk, data pool
