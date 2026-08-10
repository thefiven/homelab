# Storage abstraction for workloads at one node: memory footprint and what each option buys

**Date:** 2026-08-10
**Status:** Research note for #51. No decision is made here — that is #52's job.
**Method:** Primary sources only — official documentation, official deploy manifests and
`values.yaml` files, upstream `go.mod` dependency declarations, upstream enhancement proposals,
and upstream GitHub issues/discussions. Every claim carries a direct URL. Where the primary
sources do not answer the question, this note says so rather than estimating.

---

## 1. Scope and the constraint this note is written against

One physical node, k3s single server on its default SQLite datastore, no second node planned
(ADR-0007). **32 GiB is a hard ceiling, already fully allocated** (ADR-0002): host 1 GiB,
filesystem cache 5 GiB, control plane 1.5 GiB, GitOps 1 GiB, observability 3 GiB, Immich 8 GiB,
two web stacks 4 GiB, three free 2 GiB "standard" slots (6 GiB), slack 2.5 GiB. **Any new
persistent cost for a storage abstraction has to come out of the free slots or the slack — at
most ~8.5 GiB, in practice less if any slot is later claimed by an application.** ADR-0002 also
established a standing finding this note re-tests for the storage layer specifically: "no project
in this design publishes a working internal memory limit," so every consumer needs an externally
enforced cgroup cap regardless of what it claims about itself.

The storage layout is already decided (ADR-0010): ZFS, a system pool and a state pool on the
node's two NVMe drives, **no mirror**, Immich originals on the NAS over NFS, app databases and
observability data on the state pool, Postgres given `copies=2` for in-pool bitrot repair, static
tiering by data class. ZFS itself already provides checksums, snapshots, and a reversible
`zpool attach` topology change — a fact this note weighs each CSI-shaped option against, not a
question it reopens. Backup is also already decided (ADR-0012): restic backs up the Postgres
database and the NAS-held originals, daily, to the NAS, at zero recurring cost, with no off-site
copy — a fact relevant to any option that also advertises its own backup-to-object-store feature.

**Because there is exactly one node, any value resting on replication or HA is worth zero here.**
A distributed block-storage driver's headline feature — distributing replicas across nodes — has
no second node to distribute to. What remains to weigh is only what such a driver buys *beyond*
that, against what it costs in RAM.

### 1.1 What's established, at a glance

| Option | Is it CSI? | Published idle RAM figure? | Headline finding |
| --- | --- | --- | --- |
| `hostPath` / static `local` PV | No — native kubelet volume type, no controller at all | N/A — nothing extra runs | Zero marginal RAM cost, by construction |
| local-path-provisioner (k3s default) | **No** — pre-CSI `external-provisioner` library (§3.1, §6) | Not published anywhere; no `resources:` block in k3s's own bundled manifest | Structurally tiny (one Go binary, no dataplane), but literally uncapped and unmeasured |
| Longhorn | Yes | Only a ceiling-shaped **3-node** minimum ("4 GiB per node"); a small per-process benchmark (tens of MiB) in an engineering doc; no memory cap setting exists at all; multiple open upstream issues report multi-GiB unexplained growth | The one option with a real RAM risk, and it is the least well quantified of the three |
| OpenEBS Local PV ZFS (added, §5.1) | Yes | Not established — no `resources:` block found, no figure published | Architecturally the closest fit to ADR-0010's layout (no dataplane, control-plane-only over an existing ZFS pool) but as unmeasured as everything else |

---

## 2. Plain local storage — `hostPath` or a static `local` PersistentVolume

### 2.1 What manages it, and its RAM cost

Both are native Kubernetes volume types handled entirely by the kubelet already running as part
of the control plane — no additional controller, DaemonSet, sidecar, or process of any kind.
`hostPath` mounts a file or directory from the host directly into a pod; it is described by
Kubernetes itself as "a powerful escape hatch for some applications" that is "rarely needed" —
[kubernetes.io/docs/concepts/storage/volumes/#hostpath](https://kubernetes.io/docs/concepts/storage/volumes/#hostpath). A `local` PersistentVolume represents "a mounted local storage device
such as a disk, partition or directory," created statically (no dynamic provisioning), with a
`nodeAffinity` field baked into the PV so the scheduler places the consuming pod on the right node
— [kubernetes.io/docs/concepts/storage/volumes/#local](https://kubernetes.io/docs/concepts/storage/volumes/#local).

**The marginal RAM cost of either is zero bytes**, and this is not a gap in the evidence — it is
the finding. Nothing new runs; the kubelet mounts a path that already exists on the ZFS state
pool. That cost, whatever it is, is already inside ADR-0002's 1.5 GiB control-plane envelope.

### 2.2 What it buys, and what it gives up

It buys exactly what ZFS and `kubectl apply` already provide: a directory or dataset on the state
pool, bind-mounted straight through. It gives up everything a provisioner or a CSI driver would
add on top:

- **No dynamic provisioning.** A human (or a GitOps manifest) must create the PV — and, for
  `local`, the backing directory — before the PVC can bind. At the scale of a handful of standard
  slots (ADR-0002's "K slots" model), this is manual toil that scales with the number of slots,
  not with anything else.
- **No PVC-native resize.** Kubernetes' own local-volume docs do not describe a resize path for
  this type; growing the backing ZFS dataset and reflecting the new size in the PV's `capacity`
  field is a manual, out-of-band operation, not a `kubectl edit pvc` one.
- **No `VolumeSnapshot` CRD.** ZFS snapshots exist and are free, but they are not exposed to
  `kubectl` — an operator (or a cron job someone writes) runs `zfs snapshot` directly against the
  dataset.
- **No backup-to-object-store integration** — restic already fills this role platform-wide
  (ADR-0012), so this is not a gap so much as a feature this platform was never going to reach for
  from the storage layer.
- **No ReadWriteMany.** Neither type supports it.

### 2.3 Gotchas

Kubernetes' own warning on `hostPath`, quoted directly: excessive disk usage on the path "will
lead to disk pressure on the node," and identical pod configurations "may behave differently on
different nodes due to different files on the nodes" —
[kubernetes.io/docs/concepts/storage/volumes/#hostpath](https://kubernetes.io/docs/concepts/storage/volumes/#hostpath). The second warning is about
multi-node drift and does not apply here. For `local`, if the node fails the volume "becomes
inaccessible," and applications "must tolerate this reduced availability, as well as potential
data loss" — [kubernetes.io/docs/concepts/storage/volumes/#local](https://kubernetes.io/docs/concepts/storage/volumes/#local). That is simply a restatement of the
platform's own already-accepted single-node SPOF (ADR-0007), not a new risk this option
introduces.

---

## 3. local-path-provisioner (k3s's bundled default)

### 3.1 What it actually is — and a correction to how this ticket framed it

**local-path-provisioner is not a CSI driver.** Its own `go.mod` declares
`sigs.k8s.io/sig-storage-lib-external-provisioner/v11`, the pre-CSI "external provisioner"
library, not `container-storage-interface/spec` —
[github.com/rancher/local-path-provisioner/blob/master/go.mod](https://github.com/rancher/local-path-provisioner/blob/master/go.mod). The practical consequence
is visible in the project's own issue tracker: a user asking "is there a way to provide a CSI
storageclass compatible with local-path?" states plainly that "the local-path StorageClass is not
a CSI-one compatible," needed specifically because CSI-only tooling (Velero's snapshot plugin) has
nothing to talk to otherwise —
[github.com/rancher/local-path-provisioner/issues/239](https://github.com/rancher/local-path-provisioner/issues/239). This matters because #51's own
framing groups it with Longhorn as "a CSI driver such as Longhorn/local-path-provisioner" — the
primary sources say only one of those two actually is one (§6).

It ships in k3s as the `local-storage` AddOn, a single-replica `Deployment` with
`priorityClassName: system-node-critical`, backing the default `StorageClass` named `local-path`
with provisioner `rancher.io/local-path` —
[github.com/k3s-io/k3s/blob/main/manifests/local-storage.yaml](https://github.com/k3s-io/k3s/blob/main/manifests/local-storage.yaml),
[docs.k3s.io/installation/packaged-components](https://docs.k3s.io/installation/packaged-components). It watches PVC creation events and
dynamically provisions a `hostPath`- or `local`-backed PV under a configured base path (default
`/opt/local-path-provisioner`), spawning short-lived "helper pods" to create or delete the backing
directory on provision/delete —
[github.com/rancher/local-path-provisioner/blob/master/README.md](https://github.com/rancher/local-path-provisioner/blob/master/README.md). It can be disabled with `--disable=local-storage`
at k3s install time — same packaged-components page.

### 3.2 RAM footprint

**No figure is published anywhere upstream — README, k3s docs, or otherwise — and k3s's own
bundled manifest sets no cap at all.** `manifests/local-storage.yaml` defines the controller
`Deployment` and the helper-pod template with no `resources:` block on either —
[github.com/k3s-io/k3s/blob/main/manifests/local-storage.yaml](https://github.com/k3s-io/k3s/blob/main/manifests/local-storage.yaml). This is the same absence
ADR-0002 already generalized for this project's software ("no project in this design publishes a
working internal memory limit"), now confirmed true of the storage layer's own default controller,
not just the workloads it hosts.

Architecturally it is a single long-running Go binary reconciling PVC events, with no dataplane —
the helper pods that do the actual `mkdir`/`rm` exit as soon as the operation completes. Nothing
in the primary sources suggests this is a meaningfully large resident cost, but "nothing suggests"
is not a measurement, so this note records the RAM figure as **not established** rather than
asserting a number.

### 3.3 What it buys over plain `hostPath`/`local`, and what it doesn't

It buys exactly one thing over §2: **dynamic provisioning**. A PVC creates its own backing
directory automatically, bound with `WaitForFirstConsumer`, removing the manual "pre-create a PV
per slot" step. Its own README states explicitly what it does not add: **"No support for the
volume capacity limit currently. The capacity limit will be ignored for now"** —
[github.com/rancher/local-path-provisioner/blob/master/README.md](https://github.com/rancher/local-path-provisioner/blob/master/README.md). Resize and snapshots are
not mentioned anywhere in its documentation — an absence this note treats as "not supported,"
corroborated directly by issue #239 above, whose author had to leave the project entirely to get
CSI-based (Velero) snapshots. `ReadWriteMany`/`ReadOnlyMany` require a shared filesystem
underneath and are not the standard configuration —
[github.com/rancher/local-path-provisioner/blob/master/README.md](https://github.com/rancher/local-path-provisioner/blob/master/README.md). In short: it inherits every limitation
named in §2.2 except the manual-provisioning one.

### 3.4 Gotchas

- **Capacity limits are ignored outright** (quoted above) — a PVC can request more space than the
  pool has free, and nothing in the provisioner stops it. On a two-drive, no-mirror ZFS state pool
  with a fixed write-endurance and capacity budget (ADR-0010), this is a real trap: the
  `local-path` StorageClass will happily bind a request the pool cannot actually satisfy.
- Custom helper-pod templates require an explicit `--allow-unsafe-helper-pod-template` opt-in,
  flagged as a safety restriction in the project's own docs — same README.
- Node-bound by design (`nodeAffinity` is written into the PV at creation) — the same
  single-node characteristic as §2, and no different from what this platform already accepts.

---

## 4. Longhorn

### 4.1 Architecture — what actually runs

- **`longhorn-manager`**: a `DaemonSet`, one pod per node, watching the Kubernetes API and
  orchestrating volume operations —
  [longhorn.io/docs/1.12.0/concepts](https://longhorn.io/docs/1.12.0/concepts/).
- **`instance-manager`**: since the 2023 consolidation, one combined "aio" `DaemonSet` pod per
  node hosts both engine and replica *processes* for every attached volume (previously two
  separate pod types) —
  [github.com/longhorn/longhorn/blob/master/enhancements/20230303-consolidate-instance-managers.md](https://github.com/longhorn/longhorn/blob/master/enhancements/20230303-consolidate-instance-managers.md),
  [github.com/longhorn/longhorn/wiki/Architecture-Overview-For-Developers](https://github.com/longhorn/longhorn/wiki/Architecture-Overview-For-Developers). "When the Longhorn
  Manager is asked to create a volume, it creates a Longhorn Engine instance on the node the
  volume is attached to," and the engine "always runs in the same node as the Pod that uses the
  Longhorn volume" — [longhorn.io/docs/1.12.0/concepts](https://longhorn.io/docs/1.12.0/concepts/).
- Plus `longhorn-driver-deployer`, the CSI plugin and its provisioner/attacher/resizer/snapshotter
  sidecars, and `longhorn-ui` — all ship in the official Helm chart's `values.yaml` with **no
  `resources:` block set for any of `longhornManager`, `longhornDriver`, `longhornUI`, or `csi`** —
  [github.com/longhorn/charts/blob/master/charts/longhorn/values.yaml](https://github.com/longhorn/charts/blob/master/charts/longhorn/values.yaml).
- **`share-manager`**: one additional pod **per attached RWX volume**, running an NFSv4.1 (Ganesha)
  server — [longhorn.io/docs/1.12.0/nodes-and-volumes/volumes/rwx-volumes](https://longhorn.io/docs/1.12.0/nodes-and-volumes/volumes/rwx-volumes/).

### 4.2 RAM footprint

**The only official whole-node figure is ceiling-shaped and assumes three nodes.** Under
"Minimum Recommended Hardware," V1 Data Engine: **"3 nodes … 4 vCPUs per node … 4 GiB per node"**
— [github.com/longhorn/website/blob/master/content/docs/1.12.0/best-practices.md](https://github.com/longhorn/website/blob/master/content/docs/1.12.0/best-practices.md). This is a
whole-node minimum for a 3-node HA deployment, not a per-component breakdown, and it is not
written for — or validated against — a single node. The separate installation-requirements page
gives no RAM figure at all for the default (V1) engine; the only memory number there is the V2
data engine's **"2 GiB of 2 MiB-sized huge pages on each node"**, reserved on top of the 4 GiB
baseline and irrelevant unless V2 is deliberately chosen —
[longhorn.io/docs/1.12.0/deploy/install](https://longhorn.io/docs/1.12.0/deploy/install/).

**No memory cap or guarantee setting exists at all — only a CPU one.** `Guaranteed Instance
Manager CPU` defaults to 12% of a node's allocatable CPU, reserved per instance-manager pod —
[longhorn.io/docs/1.12.0/references/settings](https://longhorn.io/docs/1.12.0/references/settings/). The Helm chart's `defaultSettings` block
carries `guaranteedEngineManagerCPU` and `guaranteedReplicaManagerCPU` (both null, i.e. use the
percentage default) — **there is no memory equivalent of either setting anywhere in the chart** —
[github.com/longhorn/charts/blob/master/charts/longhorn/values.yaml](https://github.com/longhorn/charts/blob/master/charts/longhorn/values.yaml). This reconfirms, for Longhorn's
own control plane and not just the workloads it would host, the same absence ADR-0002 already
found generally.

**One real measured data point exists, in Longhorn's own engineering documentation (not
user-facing docs) — a per-*process* benchmark table** from the instance-manager consolidation
proposal:

| Configuration | Engine memory | Replica memory |
| --- | --- | --- |
| No I/O, idle baseline | 24 Mi | 43 Mi |
| 512B blocks, 5 GB volume | 66 Mi | 54 Mi |
| 1 MB blocks, 10 GB volume | 65 Mi | 56 Mi |
| 5 MB blocks, 10 GB volume | 64 Mi | 54 Mi |

— [github.com/longhorn/longhorn/blob/master/enhancements/20230303-consolidate-instance-managers.md](https://github.com/longhorn/longhorn/blob/master/enhancements/20230303-consolidate-instance-managers.md). This is per volume (one engine process + one replica process each), on top of the
base `instance-manager` pod's own overhead, which is not broken out anywhere.

**Reported field behaviour departs sharply from that benchmark, in Longhorn's own, currently open,
issue tracker:**

- **#12639**, "Instance-manager memory usage grows steadily even when no volumes are attached" —
  the reporter documents growth into "multiple GiB per instance-manager pod" with all volumes
  detached — [github.com/longhorn/longhorn/issues/12639](https://github.com/longhorn/longhorn/issues/12639).
- **#12668**, "Instance Manager RAM usage keeps growing after upgrade to 1.11.0 until node RAM
  limit" — [github.com/longhorn/longhorn/issues/12668](https://github.com/longhorn/longhorn/issues/12668).
- **#12643**, "Memory leak in instance manager" —
  [github.com/longhorn/longhorn/issues/12643](https://github.com/longhorn/longhorn/issues/12643).
- **#11593**, "high memory usage on instance-managers after upgrading to v1.6.x" —
  [github.com/longhorn/longhorn/issues/11593](https://github.com/longhorn/longhorn/issues/11593).
- **#12771**, an open improvement request titled "Reduce longhorn-manager memory usage by
  optimizing cluster-wide informer caching" — the `longhorn-manager` DaemonSet itself, distinct
  from `instance-manager`, has its own unresolved memory concern —
  [github.com/longhorn/longhorn/issues/12771](https://github.com/longhorn/longhorn/issues/12771).
- Asked directly "what should I expect instance-manager memory usage to be," a Longhorn maintainer
  answered in **Discussion #7044**: "it is not easy to tell you the expected usage" — memory
  "should be scaled linearly with the number of replicas and engines" only "in steady state (no
  on-the-fly IOs)," with no number offered —
  [github.com/longhorn/longhorn/discussions/7044](https://github.com/longhorn/longhorn/discussions/7044).

**Conclusion for this section.** Longhorn publishes one ceiling-shaped whole-node figure that
assumes three nodes, one small officially-documented per-process benchmark (tens of MiB per
engine/replica pair), no memory cap of any kind, and an active trail of its own open GitHub issues
reporting multi-GiB growth on the exact process the benchmark says should cost tens of MiB. On a
budget with roughly 6–8.5 GiB of genuinely free room, this is the header risk in the whole
comparison, and it is the least quantified of the three options, not the best.

### 4.3 What it buys at exactly one node

| Capability | Longhorn source | Already covered on this platform? |
| --- | --- | --- |
| Snapshots, `kubectl`-native | `VolumeSnapshot`/`VolumeSnapshotContent` CRDs plus Longhorn's own recurring jobs — [longhorn.io/docs/1.12.0/snapshots-and-backups](https://longhorn.io/docs/1.12.0/snapshots-and-backups/scheduling-backups-and-snapshots/) | Partially — ZFS already does dataset-level snapshots for free (ADR-0010); Longhorn adds a Kubernetes-native, self-service API over the same idea plus its own retention/scheduling logic ZFS's CLI lacks |
| Backup to S3 / NFS / SMB / Azure / GCP, "entirely managed by Longhorn" | [longhorn.io/docs/1.12.0/snapshots-and-backups/backup-and-restore/set-backup-target](https://longhorn.io/docs/1.12.0/snapshots-and-backups/backup-and-restore/set-backup-target/) | Not by feature, but by role — ADR-0012 already assigned restic-to-the-NAS as the backup engine and destination for exactly the databases that would live on Longhorn volumes. Longhorn's NFS target *could* point at the same NAS without the S3 cost ADR-0012 explicitly rejected paying for, but it would be a second, differently-shaped mechanism (whole-block-device snapshot vs. `pg_dump`-consistent dump) duplicating a role already assigned |
| Restore workflow, incl. StatefulSet recovery | Documented restore-from-backup and StatefulSet-recovery paths — same doc | Restic + `pg_dump` restore already covers the same data (ADR-0012) |
| Online expansion | Attach-time resize via `spec.resources.requests.storage` + `allowVolumeExpansion: true`, automatic filesystem grow for ext4/xfs, since v1.4.0 — [longhorn.io/docs/1.12.0/nodes-and-volumes/volumes/expansion](https://longhorn.io/docs/1.12.0/nodes-and-volumes/volumes/expansion/) | No. Neither §2 nor §3 offers a `kubectl`-native resize path — this is real and uncontested |
| ReadWriteMany | `share-manager` NFSv4.1 pod per RWX volume — [longhorn.io/docs/1.12.0/nodes-and-volumes/volumes/rwx-volumes](https://longhorn.io/docs/1.12.0/nodes-and-volumes/volumes/rwx-volumes/) | No. The only one of the three options that supports it — real and uncontested, though nothing on the current map has asked for it yet |
| Replicated redundancy / HA | Distributing replicas across nodes | **Worth zero at one node** by the ticket's own framing, and — see §4.4 — structurally unable to actually function here, not merely unnecessary |
| PVC portability across nodes | — | N/A, one node |

Weighed against what is already decided, the honest summary is: **two of Longhorn's five
substantive capabilities (resize, RWX) are genuinely new here; two more (snapshots, backup/
restore) mostly re-implement, with a nicer API, something ZFS and restic already do on this
platform; and the sixth (replication) is the one the ticket already priced at zero.**

### 4.4 Known failure modes and gotchas specific to small/single-node scale

**The default replica count assumes at least two nodes, and this platform has one.** Longhorn's
own settings reference: "The recommended way of choosing the default replica count is: if you have
three or more nodes for storage, use 3; otherwise use 2" (default value: 3) —
[longhorn.io/docs/1.12.0/references/settings](https://longhorn.io/docs/1.12.0/references/settings/). Even "2" cannot be satisfied at one node,
because **`Replica Node Level Soft Anti-Affinity` defaults to `false`** — when disabled, Longhorn
"prevents scheduling new replicas on nodes containing existing healthy replicas" — same settings
page.

**This is not an inferred risk — it is documented, by name, for the identical single-node
situation**, in Harvester's own docs (SUSE's Longhorn-based HCI product): "If you use
harvester-longhorn in a single-node cluster, Longhorn is unable to create the default number of
replicas, and volumes are marked as *Degraded*," because Replica Hard Anti-Affinity "can cause
volumes to become degraded … since no other nodes are available for scheduling of new replicas."
The documented fix is to set the replica count to **1** —
[docs.harvesterhci.io/v1.6/advanced/singlenodeclusters](https://docs.harvesterhci.io/v1.6/advanced/singlenodeclusters/).

At replica count 1 — the only setting that avoids a permanently degraded volume on this node — a
Longhorn volume is by construction a single copy, the same redundancy as a plain local PV (§2),
while every write still passes through the engine/replica process indirection described in §4.1
(frontend → engine process → replica process) instead of a direct filesystem write. That
indirection is bought for zero redundancy benefit at this node count.

Two smaller, cited gotchas:

- Instance-manager pods restart every hour if the cluster's default `PriorityClass` and Longhorn's
  own `PriorityClass` setting mismatch — not size-specific, but a real single-operator trap that
  produces visible, repeated pod churn easy to mistake for the memory-growth issues in §4.2 —
  [longhorn.io/kb/troubleshooting-instance-manager-pods-are-restarted-every-hour](https://longhorn.io/kb/troubleshooting-instance-manager-pods-are-restarted-every-hour/).
- Longhorn's own best-practices doc recommends enabling only one data engine per cluster, warning
  that running both "significantly increas[es] overhead" — relevant only if V2 (with its extra
  2 GiB hugepage reservation, §4.2) is ever considered alongside V1 —
  [github.com/longhorn/website/blob/master/content/docs/1.12.0/best-practices.md](https://github.com/longhorn/website/blob/master/content/docs/1.12.0/best-practices.md).

---

## 5. Other options considered

### 5.1 OpenEBS Local PV ZFS — included because it fits ADR-0010's layout directly

Unlike Longhorn, this driver has **no dataplane of its own** — its own README describes it as
"functioning purely as a control-plane for the kernel zfs volumes," operating on a "bring your own
pool" model: "go to each node and create the ZFS Pool, which will be used for provisioning the
volumes" — [github.com/openebs/zfs-localpv/blob/develop/docs/faq.md](https://github.com/openebs/zfs-localpv/blob/develop/docs/faq.md),
[github.com/openebs/zfs-localpv/blob/develop/README.md](https://github.com/openebs/zfs-localpv/blob/develop/README.md). That pool already exists here — it is
ADR-0010's state pool. It is, unlike local-path-provisioner, a genuine CSI driver: a "CSI
Controller" `Deployment` and a "CSI Node Plugin" `DaemonSet`, with `ZFSVolume`, `ZFSSnapshot`,
`ZFSBackup`, `ZFSRestore`, and `ZFSNode` CRDs shipped in its deploy manifest —
[github.com/openebs/zfs-localpv/blob/develop/README.md](https://github.com/openebs/zfs-localpv/blob/develop/README.md).

Its own README lists snapshot create/restore, clone-from-volume, and resize as implemented
features; `ReadWriteMany` is explicitly **not** checked as supported (RWO only) —
[github.com/openebs/zfs-localpv/blob/develop/README.md](https://github.com/openebs/zfs-localpv/blob/develop/README.md).

**RAM footprint: not established from primary sources.** No `resources:` block was found in its
deploy manifest, matching the same absence pattern as local-path-provisioner and Longhorn, and no
figure is published anywhere searched.

What it would add here, specifically: it exposes ZFS's own snapshot/clone/resize primitives as
first-class, per-PVC `kubectl`-managed objects, directly against the datasets ADR-0010 already
built — architecturally the narrowest and (by design, since it runs no replication engine at all)
structurally cheapest of the CSI-shaped options, because it never attempts the one capability
already priced at zero here. It is mentioned for that structural fit; its actual memory cost
cannot be weighed against Longhorn's because neither has a measured figure, and this one has even
less documentation to go on.

### 5.2 OpenEBS Mayastor — excluded

Mayastor states its own minimum outright: **"The minimum supported worker node count is three
nodes"**, plus a reservation of "1024 such pages (i.e. 2GiB total)" of huge pages exclusively for
the Mayastor pod on every node, and an `io-engine` pod with resource requests/limits of "2 CPU and
1Gi memory" — [github.com/openebs/mayastor-docs/blob/develop/quickstart/prerequisites.md](https://github.com/openebs/mayastor-docs/blob/develop/quickstart/prerequisites.md). It is built
for NVMe-oF replicated storage and costs more up front than Longhorn's own baseline, for a
capability (replication) this ticket already establishes as worth zero at one node. Not
investigated further.

---

## 6. Cross-cutting: which of these is actually a CSI driver

| Option | CSI spec? | Evidence |
| --- | --- | --- |
| `hostPath` / static `local` PV | No controller at all — a native kubelet volume type | §2.1 |
| local-path-provisioner | **No** — depends on `sig-storage-lib-external-provisioner`, the pre-CSI dynamic-provisioning mechanism | [go.mod](https://github.com/rancher/local-path-provisioner/blob/master/go.mod), [issue #239](https://github.com/rancher/local-path-provisioner/issues/239) |
| Longhorn | Yes | CSI plugin + provisioner/attacher/resizer/snapshotter sidecars, §4.1 |
| OpenEBS Local PV ZFS | Yes | "CSI Controller" / "CSI Node Plugin," §5.1 |

This matters because #51 itself frames local-path-provisioner as "a CSI driver such as Longhorn/
local-path-provisioner." The primary sources say only one of the two actually implements the CSI
spec; the other predates it and cannot plug into CSI-only ecosystem tooling (the concrete
consequence cited in issue #239 is that Velero's CSI snapshot integration has nothing to talk to).

---

## 7. Not established from primary sources

Stated plainly, matching this project's established pattern for prior research tickets:

1. **Idle RSS of the local-path-provisioner controller pod, or of its helper pods while running.**
   No figure published anywhere upstream; not measured by this note either.
2. **Longhorn's `instance-manager` pod baseline before any engine/replica process attaches to it.**
   Only the whole-node, 3-node-assuming 4 GiB ceiling and the per-*process* LEP benchmark (§4.2)
   exist; multiple open issues report the pod itself growing unboundedly regardless.
3. **Longhorn's `longhorn-manager` DaemonSet steady-state RAM.** An open issue (#12771) exists
   specifically to investigate and reduce this, unresolved as of this research.
4. **OpenEBS Local PV ZFS's controller/node-plugin RAM.** No figure published, no `resources:`
   block in its manifest.
5. **Whether Longhorn's V1 write-path indirection (engine → replica process, even at replica
   count 1) measurably adds latency or write amplification on top of ZFS itself**, on hardware
   this project has already flagged as endurance-constrained (ADR-0002, ADR-0010). The
   architecture is documented; its cost on this specific stack is not, anywhere.

---

## 8. What the evidence supports

Not a decision — #52's job — but each option's cost stated plainly, per this project's standing
rule that no option is recorded without naming what it gives up.

- **`hostPath` / static `local` PV.** Gives up dynamic provisioning, PVC-native resize,
  `kubectl`-native snapshots, and RWX. Gets a literal zero marginal RAM cost and zero new failure
  surface beyond ZFS and the kubelet, both already inside the existing budget.
- **local-path-provisioner.** Gives up the same feature set as the option above — no resize, no
  snapshots, no RWX, and capacity limits ignored outright by its own README — for the sole benefit
  of automatic per-PVC directory provisioning, at a RAM cost that nobody, including k3s's own
  bundled manifest, measures or caps.
- **Longhorn.** Gives up a RAM appetite that is simultaneously the least well quantified of the
  three (one 3-node-assuming ceiling figure, one small per-process engineering benchmark, no
  memory cap of any kind, several open issues reporting multi-GiB unexplained growth) and, by the
  arithmetic of its own default settings, cannot deliver its own headline feature at this node
  count — default replica count assumes ≥2 nodes, and the anti-affinity mechanism meant to protect
  volume redundancy instead produces permanently degraded volumes at one node, per Harvester's
  documentation of the identical situation. What is left to weigh, once replication is set aside,
  is online resize and RWX (both real and available nowhere else on this map) against snapshot/
  backup/restore convenience that substantially overlaps what ZFS and restic already do here
  (ADR-0010, ADR-0012) — set against an unmeasured and, per its own issue tracker, sometimes
  troublesome RAM cost inside a budget with roughly 6–8.5 GiB left to spend.
- **OpenEBS Local PV ZFS.** The architectural shape that most directly matches what ADR-0010
  already built — CSI semantics over an existing ZFS pool, with no replication engine to be
  structurally wasted here — but its own RAM cost is exactly as undocumented as everything else in
  this note, so it can be weighed against the other options on architecture only, not on the axis
  this ticket asked about.

---

## Source index

Kubernetes
- <https://kubernetes.io/docs/concepts/storage/volumes/#hostpath>
- <https://kubernetes.io/docs/concepts/storage/volumes/#local>

k3s
- <https://docs.k3s.io/installation/packaged-components>
- <https://github.com/k3s-io/k3s/blob/main/manifests/local-storage.yaml>

local-path-provisioner
- <https://github.com/rancher/local-path-provisioner/blob/master/README.md>
- <https://github.com/rancher/local-path-provisioner/blob/master/go.mod>
- <https://github.com/rancher/local-path-provisioner/blob/master/deploy/local-path-storage.yaml>
- <https://github.com/rancher/local-path-provisioner/issues/239>

Longhorn
- <https://longhorn.io/docs/1.12.0/best-practices/> and source: <https://github.com/longhorn/website/blob/master/content/docs/1.12.0/best-practices.md>
- <https://longhorn.io/docs/1.12.0/deploy/install/>
- <https://longhorn.io/docs/1.12.0/concepts/>
- <https://longhorn.io/docs/1.12.0/references/settings/>
- <https://longhorn.io/docs/1.12.0/snapshots-and-backups/scheduling-backups-and-snapshots/>
- <https://longhorn.io/docs/1.12.0/snapshots-and-backups/backup-and-restore/set-backup-target/>
- <https://longhorn.io/docs/1.12.0/nodes-and-volumes/volumes/expansion/>
- <https://longhorn.io/docs/1.12.0/nodes-and-volumes/volumes/rwx-volumes/>
- <https://longhorn.io/kb/troubleshooting-instance-manager-pods-are-restarted-every-hour/>
- <https://github.com/longhorn/charts/blob/master/charts/longhorn/values.yaml>
- <https://github.com/longhorn/longhorn/blob/master/enhancements/20230303-consolidate-instance-managers.md>
- <https://github.com/longhorn/longhorn/wiki/Architecture-Overview-For-Developers>
- <https://github.com/longhorn/longhorn/discussions/7044>
- <https://github.com/longhorn/longhorn/issues/12639>
- <https://github.com/longhorn/longhorn/issues/12668>
- <https://github.com/longhorn/longhorn/issues/12643>
- <https://github.com/longhorn/longhorn/issues/11593>
- <https://github.com/longhorn/longhorn/issues/12771>
- <https://github.com/longhorn/longhorn/issues/6645>
- <https://docs.harvesterhci.io/v1.6/advanced/singlenodeclusters/> (SUSE Harvester — a Longhorn-based product documenting Longhorn's own anti-affinity behaviour directly)

OpenEBS
- <https://github.com/openebs/zfs-localpv/blob/develop/README.md>
- <https://github.com/openebs/zfs-localpv/blob/develop/docs/faq.md>
- <https://github.com/openebs/mayastor-docs/blob/develop/quickstart/prerequisites.md>

Internal (this repository)
- `docs/adr/0002-resource-budget-and-feasibility-verdict.md`
- `docs/adr/0007-orchestrator-k3s-sqlite.md`
- `docs/adr/0010-zfs-system-state-split-storage-layout.md`
- `docs/adr/0012-restic-nas-no-offsite.md`
