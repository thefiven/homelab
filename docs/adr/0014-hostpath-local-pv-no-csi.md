---
status: accepted
date: 2026-08-10
tags: [storage, kubernetes, csi]
---

# Static `local` PersistentVolumes for workloads; no CSI driver, k3s's bundled provisioner disabled

#52 asked which storage abstraction workloads get on top of ADR-0010's system/state pool split —
bare local paths, a CSI driver, or replicated block storage — given the RAM cost #51's research
establishes (`docs/reference/research-storage-abstraction-memory-footprint.md`). Grilled with
`/grill-with-docs`.

## Scope: one node, so replication is worth zero

ADR-0007 settled one control plane, forever. Any value a distributed block-storage driver gets
from replicating across nodes has no second node to distribute to — what's actually being
compared is what each option buys *beyond* that, against RAM inside ADR-0002's genuinely free
room (three standard slots plus slack, roughly 6-8.5 GiB).

## What was compared

`local-path-provisioner`, k3s's own bundled default, turned out not to be a CSI driver at all
(its `go.mod` depends on the pre-CSI external-provisioner library, confirmed by its own issue
tracker) — it buys only dynamic provisioning over a plain `hostPath`/`local` PV, and its own
README states plainly that it ignores capacity limits, a real trap against a fixed, two-drive ZFS
pool. Longhorn is the only option offering RWX, but its default replica count assumes at least
two nodes; at one, SUSE's own Harvester docs name the exact failure this platform would hit —
volumes stuck permanently `Degraded` — and its RAM cost is the least quantified of anything
compared (one 3-node-assuming ceiling figure, no memory cap setting at all, several open upstream
issues reporting multi-GiB unexplained growth). OpenEBS Local PV ZFS is the architecturally
closest fit to ADR-0010 — a CSI control plane with no dataplane of its own, running directly over
the state pool ADR-0010 already built — but its RAM cost is exactly as unpublished as
Longhorn's, and it only offers RWO.

Every workload named on this map today (Immich's Postgres, the two web stacks' databases,
observability's two stores, each future standard slot) needs none of dynamic provisioning,
`kubectl`-native resize, or `kubectl`-native snapshot badly enough to pay an unmeasured,
uncapped RAM cost for it — confirmed directly at the grilling stage, not assumed. RWX is the one
open edge: not needed by anything named today, but the platform is explicitly built for **N
unknown services by construction** (the map's own words), so a future one might ask for it.

## Decision

Plain `local` PersistentVolumes, one static, GitOps-committed manifest per workload or standard
slot, over the state pool ADR-0010 already built. No provisioner, no controller, no CSI driver —
the kubelet mounts a path that already exists, at zero marginal RAM, already inside ADR-0002's
1.5 GiB control-plane envelope.

k3s's bundled `local-path-provisioner` is disabled at install (`--disable=local-storage`), so a
PVC declared with no explicit `storageClassName` fails to bind (`Pending`) instead of silently
landing on a capacity-blind, unmeasured default.

## Alternatives rejected

**`local-path-provisioner`** (k3s's own default). Buys exactly one thing over a static `local`
PV — automatic per-PVC directory creation — for a RAM cost nobody, including k3s's own bundled
manifest, measures or caps, and for a provisioner whose own README admits it ignores the volume
capacity limit entirely. Leaving it enabled would keep exactly the failure mode this ADR exists
to avoid reachable by accident.

**Longhorn.** The only option offering RWX and `kubectl`-native online resize, and rejected
anyway: at one node its default settings cannot deliver its own headline feature — replica
anti-affinity leaves volumes `Degraded`, per SUSE's own documentation of the identical
single-node case — and its RAM appetite carries the most open, unresolved risk of anything
compared, against a free budget with no room to absorb a surprise. What's left once replication
is priced at zero (resize, snapshot/backup convenience) mostly overlaps ZFS's own snapshots and
restic's already-decided backup path (ADR-0010, ADR-0012).

**OpenEBS Local PV ZFS.** The architecturally honest choice — a CSI control plane with no
dataplane, over the exact ZFS pool ADR-0010 already built — but its RAM cost is exactly as
undocumented as Longhorn's, and nothing on this map needs the resize/snapshot/clone it would add
badly enough to accept that unknown against a tight budget. Kept as the natural fallback if a
real need for those features ever proves itself, ahead of Longhorn.

## Consequences

- **No dynamic provisioning.** Every new PV is a manual, GitOps-committed manifest — a one-time
  cost per workload or slot, confirmed a non-issue against the review flow every other workload
  change already goes through, not an ongoing operational burden.
- **No PVC-native resize.** Growing a volume means editing the ZFS dataset's quota and the PV's
  declared `capacity` by hand, in the same PR — consistent with ADR-0002's envelope model already
  sizing workloads at the manifest level, not at runtime.
- **No `kubectl`-native `VolumeSnapshot`.** `zfs snapshot`, run directly by the operator, remains
  the only free, dataset-level restore point; ADR-0012 already owns backup/restore for the tier
  that actually matters (application databases), so this is not a gap, just an unclaimed
  convenience.
- **No RWX today. This reopens** if a future, currently-unknown service genuinely needs one
  volume mounted read-write from more than one pod at once — but reopening it means re-solving
  Longhorn's single-node replica-anti-affinity problem (a second node, or a different mechanism
  entirely, such as an NFS export off the ZFS pool), not simply installing Longhorn: that
  structural block does not resolve itself by waiting.
- **A new requirement on ADR-0013's still-unwritten k3s Ansible role**: it must pass
  `--disable=local-storage` at install. This does not reopen ADR-0013 — the role was already
  deferred there to build time, and this is one more install-time detail for it, not a change to
  the manual-gesture count or role set it settled.
- **Every workload's PV carries the node's own `nodeAffinity`**, consistent with ADR-0013's
  single-node assumption; a heterogeneous second node stays exactly the open fog ADR-0013 already
  left it as.
