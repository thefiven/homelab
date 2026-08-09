---
status: accepted
date: 2026-08-09
tags: [orchestration, kubernetes, scheduling]
---

# k3s, single server, SQLite datastore

What schedules and reconciles the workloads was framed against agnosticity,
horizontal growth and GitOps fit, not ease of first install: the realistic
growth path is heterogeneous x86 mini-PCs joining one at a time over several
years, funded ahead of any upgrade to this machine, so the second-node cost is
a first-class criterion. Whatever wins must also justify its annual
maintenance cost: upgrades, breaking changes, and debugging at 22:00 by one
person. #13's research settled the memory question before this decision even
started: the largest published control-plane figure among the five candidates
researched is ~5% of the 32 GB ceiling, so **memory is not the discriminator**
here.

## Kubernetes-shaped, not Nomad or Compose

#28 already decided the GPU stays "a platform resource any workload may
request," with no passthrough and no dedicated VM. That presupposes something
can actually schedule the GPU across workloads, which rules out one candidate
before the rest are weighed.

**Docker Compose + a GitOps manager (Komodo).** There is no scheduler:
Komodo and Dockge federate independent Docker hosts, they don't place
workloads across them. GPU-as-platform-resource would mean pinning GPU
workloads to the GPU host by hand, forever, the exact opposite of #28. Komodo
also requires a MongoDB or FerretDB dependency with a documented
memory-default hazard: the unpinned WiredTiger cache defaults to 50% of
(RAM − 1 GB), about 15.5 GB on this machine. It publishes no support window
and ships under a "no warranties" GPL-3.0 README. Rejected.

**HashiCorp Nomad.** The genuinely simplest architecture of the five (one
self-contained binary, no etcd, no CNI to operate), but it fails the
repository's own hard constraint that no cluster credential may exist as a CI
secret, which forces a pull-based reconciler living inside the network. Nomad
has none, documented or otherwise: the only path is push (CLI/API), so a
GitOps loop would have to be built and maintained from scratch, a second
system for a single operator to own. It is now BUSL-1.1 licensed under IBM,
not open source, and carries the heaviest two-year breaking-change record of
any candidate researched (HCLv1 removal, Vault/Consul token auth removal,
remote task drivers removed, `retry_join` deprecated, client-version floor
raised). Whether one GPU can be shared across multiple allocations is
undocumented. Rejected.

**Kubernetes-shaped (k3s / k0s / kubeadm).** Real scheduler, and the only
family paired with a mature, pull-based GitOps ecosystem (Flux) that fits the
no-CI-secret constraint. Flux is a separate ecosystem project layered on top,
not a first-party feature of any one distro, unlike Komodo's built-in
Resource Sync; but no distro-first-party reconciler exists for any candidate
here, and Flux is still the only pull-based option left once Compose+Komodo
is rejected on scheduling grounds and Nomad on having no reconciler at all.
Selected as the family; which distribution is the next question.

## k3s, not k0s or kubeadm

The ticket names the cost explicitly: "annual maintenance," "breaking
changes," "debugging at 22:00 by one person." That is an optimization target
for low-touch operation, not for staying closest to the reference
implementation.

**kubeadm.** The heaviest treadmill of the three: releases land roughly three
times a year, upgrades cannot skip a minor version even on a single-instance
cluster, and client certificates expire after one year, renewing only as a
side effect of `kubeadm upgrade apply`. **A kubeadm cluster left untouched for
twelve months breaks itself.** For a machine that may go months without being
touched, that is a self-inflicted outage waiting to happen. Its mildest
breaking-change record (no API removals across v1.33-v1.36) doesn't offset a
failure mode this severe. Rejected.

**k0s.** The lowest measured control-plane figure of the five (510 MB,
though from a v1.22-era test) and the only distribution with an explicitly
stated 14-month support window in its own docs. Set against that: the
documented default install command, `k0s install controller --single`,
permanently forecloses adding workers later, the exact growth path this
platform needs, unless the less-discoverable `--enable-worker --no-taints`
flag is used instead. A second, unrelated one-way door exists at the same
install moment: the CNI provider can only be changed via full cluster
redeployment. Whether k0s auto-renews leaf certificates before expiry is not
established in its own documentation. Two install-time traps plus an
undocumented certificate story is more operational surprise than the
alternative, not less. Rejected.

**k3s.** The only one of the three Kubernetes distributions researched with
**documented automatic certificate renewal**: certificates within 120 days of
expiring renew automatically on every k3s start, with a Kubernetes Warning
Event emitted if one is approaching. For a single operator on a 24/7 box that
may not be touched for months, this removes a whole class of self-inflicted
outage that both kubeadm and (undocumented) k0s carry. Adding a worker is one
command (`curl ... | K3S_URL=... K3S_TOKEN=... sh -`) regardless of node count
or hardware generation. Its own weaknesses, no formally published support
window (inferred from observed release cadence, not a stated commitment) and
a headline memory figure contaminated by a bundled monitoring stack in its
own published test, are the mildest of the three. Selected, on the `stable`
release channel: k3s's own docs describe `stable` as recommended for
production, having been through a period of community testing, which matches
a low-touch operator trading newest features for fewer surprises.

## SQLite, not embedded etcd

#13 found that every quorum-based option shares the same arithmetic trap:
two control-plane members are strictly worse than one (either one failing
stops the control plane), and the benefit only arrives at three. Against a
platform whose standing constraint is "one physical machine, name the SPOF,
never design or claim HA," that means **one server forever**: additional
machines join as workers, which is a single command regardless of the
server's own datastore. The datastore choice therefore has no bearing on the
stated growth path ("N unknown services" means more workers, never more
servers), so it fell to a genuine trade-off with no growth-path stake either
way.

etcd's own case wasn't free: #30 was run specifically to validate embedded
etcd's <5 ms p99 fsync requirement against the DRAM-less NV2 drives before
this ticket could close, and it cleared with 5-8x margin, so hardware doubt
doesn't disqualify it. But etcd's redundancy is a property of replicating
across separate physical machines. On a single box, a single-member etcd is
exactly as exposed to that box dying as SQLite is, and this platform will
never run a second server to make that redundancy real. What actually
protects against "the one machine dies" is a tested backup-and-restore
procedure (#23), already scoped for it, with the control-plane state
classified `regenerable` and given a 7-day RPO/RTO by #11 on the basis that
the platform rebuilds from Git. SQLite is the simpler side of that: a file to
copy, versus a dedicated snapshot mechanism, for identical protection against
the only failure this machine can actually have. Embedded etcd's IOPS
profile (50 IOPS, <5 ms) is also needlessly tighter than SQLite's (10 IOPS,
<10 ms) against drives already carrying ZFS write-amplification scrutiny
(#15).

k3s selects SQLite automatically whenever no other datastore is configured
and no embedded-etcd files exist on disk, so this is a decision to not
override that default, not new configuration. If the growth plan ever
changes toward wanting real control-plane redundancy across multiple
physical machines, the conversion is documented as a single restart with
`--cluster-init`, and #30's validation is banked, unused, as a ready escape
hatch.

## Decision

**k3s**, installed as a single server, on its **default SQLite** datastore,
tracking the `stable` release channel. Additional machines join as k3s agents
(workers) as the service set grows; the server role is not replicated.

## Alternatives rejected

**Docker Compose + Komodo/Dockge.** No real scheduler, contradicting #28's
GPU-as-platform-resource decision. Komodo's own documented Mongo
memory-default hazard is a standing risk on a 32 GB machine; Dockge has no
git story at all.

**HashiCorp Nomad.** Requires hand-building the pull-based GitOps reconciler
the no-CI-secret constraint demands. BUSL-1.1/IBM licensing and the heaviest
breaking-change record researched. GPU-sharing across allocations
undocumented.

**kubeadm.** Reference implementation, most portable knowledge, mildest API
churn, but a cluster left untouched for a year breaks its own certificates,
and the no-skip minor-upgrade rule means roughly three forced sequential
upgrades a year forever.

**k0s.** Lowest measured control-plane memory and the only explicit support
window statement, undercut by two install-time one-way doors (`--single`,
CNI provider) and undocumented certificate renewal.

**Embedded etcd (with k3s).** Its redundancy only pays off across multiple
physical machines, which this platform will never run per #13 and the
single-machine standing constraint. Offers no real protection SQLite lacks
here, at a tighter IOPS/latency budget. Kept as a validated (#30), unused
escape hatch.

## Consequences

- **The GitOps engine question graduates from the map's fog** into its own
  ticket now that the answer is Kubernetes-shaped: Flux vs. Argo CD, and
  their resident cost against ADR-0002's 1 GiB GitOps envelope.
- **GPU exposure under k8s** still needs the NVIDIA k8s device plugin (or GPU
  Operator) at build time, layered on the `nvidia-container-toolkit` already
  installed at the host level per ADR-0003. Not decided here; an
  implementation detail, not an architectural trade-off.
- **k3s ships bundled components by default**, each independently
  controllable: CoreDNS, Traefik (ingress), local-path storage and
  metrics-server are AddOns disabled with `--disable=<name>`
  ([docs.k3s.io/installation/packaged-components](https://docs.k3s.io/installation/packaged-components)),
  ServiceLB the same way despite having no manifest of its own, and Flannel
  (CNI) is controlled separately via `--flannel-backend`, set to `none` to
  run an alternative CNI
  ([docs.k3s.io/networking/basic-network-options](https://docs.k3s.io/networking/basic-network-options)).
  #19 (storage layout) and #22 (public exposure and ingress) each decide,
  independently, whether to keep or disable the ones in their domain.
- **Backup and recovery of the SQLite datastore is #23's job**, not this
  ADR's: the control-plane state is classified `regenerable` with a 7-day
  RPO/RTO per #11, on the premise that the platform rebuilds from Git plus a
  restored datastore file.
- **#19 and #22 are not newly unblocked by this ADR.** Their tracker
  dependencies are on hardware measurements (#5, #8), not on this decision,
  though both were written assuming a Kubernetes-shaped answer.
- If the growth plan ever calls for real control-plane redundancy across
  multiple physical machines, a reversal of #13's "one control plane
  forever" finding, converting to embedded etcd is a single `--cluster-init`
  restart, with feasibility already validated by #30.
