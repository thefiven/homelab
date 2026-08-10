---
status: accepted
date: 2026-08-10
tags: [storage, zfs, immich, backup]
---

# ZFS, split into a system pool and a state pool, across the two NVMe; originals stay on the NAS

#19 named three shapes for the two 1 TB NV2 NVMe drives — a mirror, two
independent volumes, or a system/data split — and left the root filesystem
technology itself unsettled, deferred here by ADR-0003 ("Rollback comes from
a snapshot-capable root filesystem instead, whichever #19 settles on"). This
ADR settles both, plus what physically lives where between the two drives and
the DS412+ NAS, using #15's ZFS-on-DRAM-less-SSD research
(`docs/reference/research-zfs-on-dramless-ssds.md`), #16's Immich data-class
research (`docs/reference/research-immich-data-classes.md`), and #18's
resource budget. A prior-art repository built on this exact hardware reached
a structurally similar answer for a different scope (gaming and Nextcloud
both in the picture then, both gone now); read as prior art, not doctrine —
re-derived below on the current facts, not inherited.

## Root filesystem: ZFS, not btrfs

Ubuntu Server's installer (subiquity) has a guided `autoinstall` layout for
ZFS but explicitly cannot configure btrfs subvolumes ("The installer cannot
configure iSCSI mounts or BTRFS subvolumes"). btrfs's own documented
degraded-mount behaviour is a real gotcha ZFS's mirror semantics don't share:
new writes in a degraded `raid1` mount silently fall back to an unreplicated
`single` profile until a manual rebalance is run. #15's entire research
scope on this map was ZFS specifically, not a comparison — this confirms
that working premise rather than reopening it.

## Topology: a system pool and a state pool, not a mirror

**System pool** (one drive): OS root, k3s, container images, the ML model
cache. Everything Ansible and GitOps reconstruct from this repository in
minutes. **State pool** (the other drive): application databases (Immich's
Postgres, and any database the two web stacks bring), Immich's generated
derivatives (`thumbs/`, `encoded-video/`), and observability's
VictoriaMetrics/VictoriaLogs storage — #18's single largest writer, 10 of the
16 GB/day budget.

A full mirror was the stronger-sounding default and is rejected here on
three grounds, all from #15's research:

- **A mirror does not split the write budget** — every logical write goes to
  both drives. #18's resource budget already spends its entire amplification
  threshold reaching the 10-year endurance line this way: 16 GB/day × 5.5 =
  88 GB/day, exactly the derived 10-year-per-drive figure. That threshold
  assumes the worst case (the full stream hitting both drives), i.e. a
  mirror — leaving zero headroom, against an amplification factor this
  hardware has never measured (`nvme endurance-log`'s MUW/DUW fields are
  unread).
- **A mirror doubles metadata writes on its own**, independent of the write
  budget: `redundant_metadata=all` at defaults means 4 physical writes per
  metadata block on a 2-way mirror (2 ditto copies × 2 members) against 2 on
  a single-disk pool.
- **Correlated wear-out.** Two identical drives, same batch, same full write
  stream, age identically — a mirror protects against one drive failing
  early, not against both reaching 320 TBW together. Kingston states the NV2
  "is not intended for Server environments."

A mirror is a device for availability, never a backup — the prior-art
repository's own phrase, still true here: repair is not the same axis as
recovery, and #23 owns recovery regardless of which topology wins this
ticket. `zpool attach` can still widen either pool into a mirror later if the
endurance picture proves better than feared; going the other way costs a
rebuild, so this stays the reversible choice.

Two independent volumes with no role split (#19's second option) was also on
the table and rejected for giving up the reconstructible/irreplaceable
framing for no offsetting gain — an even split buys nothing a role split
doesn't, and a role split additionally keeps a system reinstall from
touching the drive backup and recovery actually cares about.

## What lives where

Confirming and sharpening #16's hypothesis, which holds:

| Data | Location | Why |
| --- | --- | --- |
| Immich Postgres (+ VectorChord) | State pool, own dataset, `copies=2` | Never on NFS — three independent Immich sources call this out, one names it a corruption cause; not derivable from the files or from Git (see below) |
| Other app databases (two web stacks) | State pool, own dataset | Same reasoning; no repository-level regeneration path for user-generated state |
| Immich derivatives (`thumbs/`, `encoded-video/`) | State pool | ML reads the derivative, never the original (#16) — pinning these local removes NAS read traffic from the entire hot path |
| Immich `profile/`, `backups/` (dump output) | State pool | Small; `backups/`' final resting place is #23's call, not this ticket's |
| VictoriaMetrics / VictoriaLogs | State pool | #18's dominant writer; wants fast local disk, not NFS |
| ML model cache (Docker named volume) | System pool | Read-mostly, cold-start only, redownloadable from Hugging Face |
| Immich originals (`upload/`, `library/`) | NAS, over NFS | 1.5 TB corpus does not fit two 1 TB NVMe alongside state, without giving up all local redundancy for bulk that doesn't need NVMe speed |

**Ingestion route: normal Upload, not External Library.** `UPLOAD_LOCATION`'s
`upload/` and `library/` subfolders are NFS-mounted onto the NAS as a mount
over a subpath — the pattern Immich's own docs gesture at ("moved some of
these folders onto a different storage device") — while `thumbs/`,
`encoded-video/`, `profile/`, `backups/` stay on the state pool. External
Library was rejected: it restricts a library to a single owner, which
directly contradicts multi-user family access, and its automatic watcher is
documented and field-confirmed unreliable over NFS/Synology (upstream
#20858, #27676) — its own fallback is the same nightly periodic scan that
Upload doesn't even need, since Upload never depends on filesystem watching.
#11 already establishes ingestion as a phone-backup trickle, never bulk, so
there's no one-time mass-import event that would make External Library's
in-place indexing (avoiding a copy) worth its restrictions.

**Postgres gets `copies=2`; nothing else on the state pool does.** Without a
mirror, ZFS still detects corruption via checksums but can no longer repair
it — no second copy to heal from. `copies=2` on a single dataset restores
that repair capability at the cost of writing that dataset's blocks twice.
Scoped to Postgres alone, the cost is cheap: the database is small against
the 10 GB/day observability writer that dominates the state pool's budget,
and the benefit lands exactly on the one slice that turned out to be
genuinely irreplaceable (next section) rather than spread thin across
everything.

**Correcting #11's classification.** #11 filed "application databases" under
its *regenerable* tier (7-day RPO/RTO, "reconstructible from Git"). That's
wrong for Immich's Postgres database specifically: Immich's own docs state
plainly that it "does not scan the library folder, so database backups are
essential" — named faces, albums and user metadata exist nowhere else, not
in Git, not in the original files. The prior-art repository reached the same
conclusion independently, on the same hardware: of the whole 2 TB, the only
truly irreplaceable slice was the ~20 GB Immich database, smaller than the
photo corpus and more fragile, not less. **Immich's Postgres DB, and any
other app database holding user-generated state, is irreplaceable-tier, not
regenerable-tier.** #11's Decisions-so-far entry is amended accordingly, not
reopened — #23 designs the DB's backup cadence against the 24h RPO / 72h RTO
line, not the 7-day one.

## Tiering: static by data class, no cache layer

No dynamic tiering — no L2ARC over NFS (that combination doesn't make
sense), no dm-cache or bcache in front of the NAS mount. #16's own finding is
that the working set doesn't shift with access recency: derivatives and
databases are unconditionally local, originals are unconditionally on the
NAS, decided once by data class. There's no hot/cold boundary that moves.

## Every-option measures, from #15's research

Independent of the topology decision, all sourced from primary OpenZFS
documentation:

- `ashift=12` at pool creation, after low-level formatting both drives to
  4096-byte sectors — the one irreversible knob, decided now because it
  cannot be changed later, not even on disk replacement.
- `atime=off` on the state pool's database and derivative datasets;
  `relatime=on` elsewhere. A photo library walked daily by a scan job turns
  the default `atime=on` into one metadata write per file per day.
- Matched `recordsize` on database datasets — PostgreSQL at `32K` per
  OpenZFS's own workload-tuning guidance — left at the 128 KiB default on
  blob/derivative datasets.
- An explicit `zfs_arc_max`, not the OpenZFS ≥2.3.0 default (31 GiB on this
  32 GiB machine) — #18's resource budget already pins the filesystem cache
  at 5 GiB as a condition of the platform fitting at all.
- **No `log` vdev and no `cache` vdev.** A SLOG on a consumer SSD without
  power-loss protection is documented as unsafe; an L2ARC on a RAM-constrained
  system is documented as counterproductive, and would fight the same 5 GiB
  cap #18 just pinned.
- Scheduled `zpool trim`, not `autotrim=on` — upstream's own guidance for
  "lower-end devices."
- Baseline `data_units_written` on both drives now, and check whether
  `nvme endurance-log` reports `media_units_written` — the only available
  measurement of this hardware's actual write amplification, which the
  ×5.5 threshold above is currently unverified against.

Exact recordsize for the observability datasets and exact dataset boundaries
are left to whichever ticket installs the pools, per the map's standing rule
against configuration before the ADR it derives from is accepted.

## Second node

Deliberately not solved here. The map's "Not yet specified" already carries
the multi-node trajectory as fog; this arrangement is node-local, and
whether it generalizes or needs redesign is that fog item's question to
answer once a second node — and the storage abstraction question it also
waits on — actually exists.

## Decision

**ZFS**, two pools: a **system pool** on one NVMe (OS, k3s, images, model
cache — Ansible/GitOps-reconstructible) and a **state pool** on the other
(app databases, Immich derivatives, observability), no mirror. Immich
originals stay on the NAS over NFS, reached through the normal per-user
Upload route with `upload/`/`library/` mounted onto the NAS and everything
else local. Postgres gets `copies=2`; the rest of the state pool stays at
`copies=1`. Tiering is static, by data class — no cache layer. `ashift=12`,
explicit `zfs_arc_max`, matched `recordsize` on database datasets, no
log/cache vdev, scheduled trim. #11's database classification is corrected:
application databases holding user-generated state are irreplaceable-tier.

## Alternatives rejected

**A full 2-way mirror.** The default-sounding choice; rejected on
endurance (zero headroom against an unmeasured amplification factor,
plus the mirror's own metadata-doubling) and on correlated wear-out between
two identical drives Kingston does not rate for server duty. Reversible
later via `zpool attach` if the endurance picture improves.

**Two independent volumes with no role split.** Gives up the
reconstructible/irreplaceable framing for no gain over a role split, and
loses the property that a system reinstall never touches the drive backup
and recovery care about.

**btrfs as root filesystem.** In-tree, GPLv2, no DKMS or ARC to size — real
advantages that would have mattered more under a mirror. Without one, the
comparison turns on installer support, and subiquity has no guided path for
btrfs subvolumes where it does for ZFS.

**External Library for originals.** Avoids copying 1.5 TB across NFS, but
its single-owner-per-library restriction directly contradicts multi-user
family access, and its watcher is documented and field-confirmed unreliable
on NFS-mounted Synology shares. Upload doesn't need the copy avoided badly
enough to take either cost, especially with ingestion already established as
trickle, not bulk.

**Dynamic tiering (L2ARC, dm-cache/bcache) between NVMe and NAS.** No hot/cold
boundary actually moves here — the split is intrinsic to data class, not
access recency — so a cache layer would add complexity to track something
that's already static.

**`copies=2` across the whole state pool.** Considered as the simple version
of the repair mechanism; rejected for spending the doubling cost on
observability's dominant, genuinely regenerable write stream instead of
targeting the one dataset that turned out to be irreplaceable.

## Consequences

- **A reinstall is required before this can be built.** #30's write-latency
  measurement destroyed the machine's existing installation (EFI, ZFS,
  swap); this ADR describes the target layout for that reinstall, not a
  live system.
- **Booting depends on an out-of-tree module.** A kernel update that outpaces
  the OpenZFS package can leave the machine unable to boot — on a headless
  box with no iGPU, recovery means a screen plugged into the GPU. Accepted,
  not mitigated further here.
- **The state pool's exact dataset boundaries and non-database `recordsize`
  values are not fixed by this ADR** — left to the installing ticket, along
  with `backups/`'s final resting place, which is #23's decision.
- **#11's map entry needs a one-line amendment**, not a reopening: application
  databases holding user-generated state move from its regenerable tier to
  its irreplaceable tier.
- **Two fog items graduate**: the storage abstraction offered to workloads and
  the BIOS reference table both had this decision as their last open
  prerequisite.
