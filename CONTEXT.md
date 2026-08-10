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

### The resource budget

The first three terms below are routinely conflated and mean different things.
See [ADR-0002](./docs/adr/0002-resource-budget-and-feasibility-verdict.md).

**Envelope**:
The share of a finite machine resource allocated to one consumer by the resource
budget — of memory, or of daily writes. It is a decision, not an observation.
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
The part of the machine consumed before any workload sees it: host, filesystem
cache, control plane, GitOps engine, observability.

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

**State pool**:
The ZFS pool holding what no rebuild recreates — application databases and
Immich's generated derivatives. Of these, only the application databases are
what #23's backup and recovery strategy targets (ADR-0012); the derivatives
are excluded as regenerable from the originals.
_Avoid_: data disk, data pool
