# Backup engines and off-site destinations for a zero/near-zero budget

**Date:** 2026-08-10
**Status:** Research note. No decision is made here — #23 ("Decide the backup and recovery
strategy") owns the decision; this feeds its grilling session.
**Method:** Primary sources only: official docs, upstream source, pricing pages, and release
notes, for restic, Kopia, Borg, OpenZFS and PostgreSQL, plus the published pricing pages of
Backblaze B2, Wasabi, Hetzner and rsync.net. Every claim carries a direct URL. Where a primary
source does not answer the question, or could not be retrieved by automated fetch, this note says
so under [§4](#4-not-established-from-primary-sources) rather than substituting an estimate.

Context this note is written against: the **state pool** (ADR-0010) holds application databases —
Immich's Postgres is irreplaceable-tier, "the only truly irreplaceable slice was the ~20 GB Immich
database" — and Immich's generated derivatives; Immich's **originals** (~1.5 TB corpus) live on the
Synology DS412+ NAS, reached over NFS, not on the platform
(`docs/adr/0010-zfs-system-state-split-storage-layout.md`). Upstream bandwidth off this LAN is a
measured ~100 Mbit/s ceiling (issue #8). #27 already accepted a comparable non-zero recurring cost
once — 27-49 EUR/year of electricity, from abandoning the nightly shutdown window — so a small paid
option for backup is not automatically disqualified here either. The seedbox and all paid hosting
for a *workload* are already ruled out as destinations (#9, #29); this note does not re-propose
them. Tailscale is already the platform's private-access mechanism — Personal/Free plan, free
indefinitely, **unlimited devices** — decided in ADR-0011 for family access to Immich, and reused
below as the reachability mechanism for an off-site device.

---

## 1. PostgreSQL's own backup contract

Every engine below either performs a **dump** or relies on an **atomic filesystem snapshot**. Both
are PostgreSQL's own documented mechanisms, and the constraints are PostgreSQL's, not the backup
tool's.

**Dump (`pg_dump` / `pg_dumpall`):**

> "Dumps created by pg_dump are internally consistent, meaning, the dump represents a snapshot of
> the database at the time pg_dump began running. pg_dump does not block other operations on the
> database while it is working."

([postgresql.org/docs/current/backup-dump.html](https://www.postgresql.org/docs/current/backup-dump.html))

The multi-database caveat is explicit: `pg_dumpall` "works by emitting commands to re-create roles,
tablespaces, and empty databases, then invoking pg_dump for each database. This means that while
each database will be internally consistent, the snapshots of different databases are not
synchronized" (same page). For a single-database Immich install this does not bind; it would if a
second database were added to the same cluster and both needed one synchronized point in time.

**Filesystem-level snapshot (LVM, ZFS, or equivalent):**

> "If your database is spread across multiple file systems, there might not be any way to obtain
> exactly-simultaneous frozen snapshots of all the volumes. [...] the snapshots *must* be
> simultaneous." "This will work even while the database server is running." "[A] backup created in
> this way saves the database files in a state as if the database server was not properly shut
> down; therefore, when you start the database server on the backed-up data, it will think the
> previous server instance crashed and will replay the WAL log. This is not a problem; just be
> aware of it (and be sure to include the WAL files in your backup)." "You can perform a CHECKPOINT
> before taking the snapshot to reduce recovery time."

([postgresql.org/docs/current/backup-file.html](https://www.postgresql.org/docs/current/backup-file.html))

Two consequences that bind directly on this platform: the snapshot must cover the *entire* data
directory (data + WAL) as one atomic unit — trivial on a single ZFS dataset, since a ZFS snapshot is
atomic per-dataset by construction, but a real constraint if Postgres's data and WAL ever end up on
separate datasets. And restore is **whole-cluster only** — this mechanism cannot restore a single
table or a single database, only the entire Postgres instance the snapshot was taken of.

---

## 2. The four engines

### 2.1 restic

**What it needs from a destination.** restic's repository is a directory structure it can write to
over: local disk, SFTP, its own REST server, Amazon S3, MinIO, generic S3-compatible endpoints,
Wasabi (named explicitly), Alibaba OSS, OpenStack Swift, Azure Blob, Google Cloud Storage, and —
indirectly — "many other different services" via `rclone:<remote>:<path>`
([restic docs, Preparing a new repository](https://raw.githubusercontent.com/restic/restic/master/doc/030_preparing_a_new_repo.rst)).
Backblaze B2 is a named exception: "Due to issues with error handling in the current B2 library
that restic uses, the recommended way to utilize Backblaze B2 is by using its S3-compatible API"
(same page) — i.e. restic's advice is to talk to B2 as if it were S3, not through its dedicated B2
backend.

**Postgres consistency.** No native database integration. The documented mechanism is
`--stdin-from-command`, which runs an external command and backs up its stdout as a single file,
detecting a non-zero exit and cancelling the backup rather than silently completing an empty one —
the documented failure mode of the plain `--stdin` flag it supersedes: "if `mysqldump` fails to
connect to the MySQL database, the restic backup will nevertheless succeed in creating an *empty*
backup"
([restic docs, Reading data from stdin](https://raw.githubusercontent.com/restic/restic/master/doc/040_backup.rst)).
Applied here: `restic backup --stdin-from-command -- pg_dump ...` (or `pg_dumpall`) for Immich's
database, subject to §1's dump-consistency scope. No built-in hook system exists for wrapping a
filesystem/ZFS snapshot instead; that would be external scripting (systemd unit, cron, or a
`zfs snapshot` + mount + `restic backup` sequence run by hand).

**Encryption.** Mandatory, not optional: "All data stored by restic in the repository is encrypted
with AES-256 in counter mode and authenticated using Poly1305-AES" — "everything except the
metadata included for informational purposes in the key files is encrypted and authenticated." The
repository key is derived from the user's password via scrypt
([restic docs, Design](https://raw.githubusercontent.com/restic/restic/master/doc/design.rst)).
There is no unencrypted-repository option.

**What it concedes.** No native pre/post-snapshot hook — `--stdin-from-command` covers the single
"run a command and back up its output" case, but there is no equivalent of Kopia's Actions for
orchestrating an external filesystem snapshot automatically. The B2 backend is explicitly
second-choice per restic's own docs. At the time of writing, restic's own release tag is
**0.19.1** (2026-07-05) — pre-1.0 by version number
([restic releases](https://github.com/restic/restic/releases)), though no data-loss bug specific to
a recent release was found in this research (contrast with Kopia, below).

### 2.2 Kopia

**What it needs from a destination.** Local disk or NAS, SFTP, "all cloud storage platforms that
support the S3 API", Backblaze B2 (native, described as full-S3-compatible), Azure Blob Storage,
Google Cloud Storage (direct, service-account JSON, or S3 interop), WebDAV, a self-hosted Kopia
Repository Server, and Google Drive or Rclone remotes — both of the latter two flagged by Kopia
itself as **experimental**: "Native support for Google Drive in Kopia is currently experimental";
Rclone "support is experimental. In theory, all Rclone-supported storage providers should work with
Kopia. However, in practice, only Dropbox, OneDrive, and Google Drive have been tested to work with
Kopia through Rclone" ([kopia.io/docs/repositories](https://kopia.io/docs/repositories/)).

**Postgres consistency.** Kopia ships a first-class mechanism for exactly this: **Actions** —
`before-snapshot-root-action` / `after-snapshot-root-action` (and folder-scoped variants), run via
`kopia policy set`, configurable as essential (must succeed or the snapshot fails), optional, or
async, with a default 5-minute timeout. Kopia's own documentation gives worked examples for a
`mysqldump`-style database export *and* for wrapping a ZFS or LVM snapshot: create the snapshot,
redirect the before-action's output to `KOPIA_SNAPSHOT_PATH=<new-directory>` so Kopia backs up the
frozen mount instead of the live one, then destroy the snapshot in the after-action
([kopia.io/docs/advanced/actions](https://kopia.io/docs/advanced/actions/)). This is the one engine
of the four with a documented, built-in path from "run `zfs snapshot`, mount it, back it up, clean
up" to a single policy — no external cron/systemd wrapper required.

**Encryption.** Mandatory: "Kopia does not allow creating unencrypted backups." Choice of AES-256 or
ChaCha20 ([kopia.io/docs/features](https://kopia.io/docs/features/)).

**What it concedes.** Actions are a genuine trust surface, and Kopia's own docs treat them as one:
"To reduce the security risk, actions are an opt-in feature and are not enabled by default"
(`--enable-actions` required), and a script can be **persisted inside the repository itself** (up to
32,000 characters) — meaning a shared or compromised repository can carry code that later executes
automatically during a snapshot
([kopia.io/docs/advanced/actions](https://kopia.io/docs/advanced/actions/)). Separately, and more
concretely: Kopia's own latest release, **v0.23.1** (2026-06-16), is described by the project as "a
bugfix release which fixes a rare race condition which might lead to **data loss** — an upgrade is
recommended" ([kopia/kopia releases](https://github.com/kopia/kopia/releases)). For a backup tool,
a recent, upstream-acknowledged data-loss bug is a directly relevant data point, not a general
maturity complaint. Kopia is also pre-1.0 by version number, same as restic.

### 2.3 Borg (BorgBackup)

**What it needs from a destination.** Local filesystem paths (absolute, relative, or `file://`), or
a remote reached over SSH — `ssh://user@host:port/path/to/repo` or the deprecated
`user@host:/path/to/repo` scp-style syntax. **Borg has no native object-storage backend.** Its own
docs, describing repository URLs, list only local and SSH forms; there is no S3, no rclone
integration, no REST server
([borgbackup docs, General](https://r.jina.ai/https://borgbackup.readthedocs.io/en/stable/usage/general.html)).
`BORG_RSH` lets the SSH transport be customized (e.g. a non-standard port or identity file), but the
transport is still SSH.

**Postgres consistency.** No built-in hook mechanism at all — not even restic's `--stdin-from-command`.
Consistency is entirely external: dump first, then `borg create` against the dump file, or snapshot
the source (LVM, ZFS) externally and point `borg create` at the frozen mount. (The common community
answer to this gap is `borgmatic`, a separate wrapper project with its own hook config — not part of
Borg itself, and not evaluated here as a primary source.)

**Encryption.** A required flag at `borg init`, not a default, with an explicit unencrypted choice
available: modes are `none`, `authenticated`, `authenticated-blake2`, `repokey`, `keyfile`,
`repokey-blake2`, `keyfile-blake2`. `repokey`/`keyfile` use "AES-CTR-256 for encryption and
HMAC-SHA256 for authentication" (the `-blake2` variants substitute BLAKE2b-256 for the MAC); the
`authenticated` modes provide integrity without encryption; `none` provides neither
([borgbackup docs, Initialize](https://r.jina.ai/https://borgbackup.readthedocs.io/en/stable/usage/init.html)).
Unlike restic and Kopia, Borg makes "no encryption" a reachable configuration, not a removed option
— a difference worth being deliberate about at `init` time, since it cannot be turned on
retroactively for the same repository.

**What it concedes.** The narrowest destination story of the three file-level tools: SSH or local
only. This rules out Backblaze B2 and Wasabi directly — reaching them from Borg would need an extra
translation layer (mounting the bucket over FUSE via rclone, an unsupported and undocumented
combination for Borg specifically). It fits cleanly, however, wherever the destination speaks SSH
natively — see §3.2, where both Hetzner Storage Box and rsync.net advertise Borg support by name.
Borg is also, by far, the most mature by version number: latest release **1.4.5** (2026-07-18),
years past its 1.0 line ([borgbackup releases](https://github.com/borgbackup/borg/releases)) —
where both restic and Kopia are still 0.x.

### 2.4 `zfs send` / `zfs receive`

**What it needs from a destination.** Another ZFS pool. The stream can be redirected to a file, or
piped to a remote host: "The output can be redirected to a file or to a different system (for
example, using `ssh(1)`)", with the documented form
`zfs send pool/fs@a | ssh host zfs receive poolB/received/fs@a`
([zfs-send(8)](https://openzfs.github.io/openzfs-docs/man/master/8/zfs-send.8.html)). This is a
**hard requirement**, not a preference: the receiving side must itself be running ZFS, and moreover
must support every pool feature the sending side used — "The receiving system must have the
`large_blocks` pool feature enabled as well" is stated as the general pattern (same page). A plain
object-storage bucket or an arbitrary SSH-only file host cannot be a `zfs receive` target at all.

**Postgres consistency.** `zfs send`/`receive` is not a backup engine with dump logic; it replicates
whatever a `zfs snapshot` already froze. Consistency is therefore exactly §1's filesystem-snapshot
contract: atomic per-dataset, crash-consistent (Postgres replays WAL on next start), whole-cluster
restore only, and — the one point worth restating for this platform specifically — it only reaches
what is actually a ZFS dataset. **This disqualifies `zfs send`/`receive` as the tool for the NAS-held
Immich originals outright**: the DS412+ is not running ZFS, so there is no source dataset to send
from for that half of the requirement in the ticket. It remains fully applicable to the *state
pool* (Postgres's own dataset, and Immich's derivatives), never to what lives on the NAS.

**Encryption.** A raw send (`-w`) transmits already-on-disk-encrypted blocks unmodified: "For
encrypted datasets, send data exactly as it exists on disk. This allows backups to be taken even if
encryption keys are not currently loaded." The trade is explicit and one-way: "if you do not use
this flag for sending encrypted datasets, data will be sent unencrypted and may be re-encrypted with
a different encryption key on the receiving system, which will disable the ability to do a raw send
to that system for incrementals"
([zfs-send(8)](https://openzfs.github.io/openzfs-docs/man/master/8/zfs-send.8.html)). Practically:
a raw send lets the sending host hand ciphertext to a destination that never needs the encryption
key at all — a real property for an untrusted or semi-trusted destination — but only if raw send is
used from the first (full) send onward, since mixing plain and raw sends to the same target breaks
future raw incrementals.

**What it concedes.** Destination must be ZFS, with compatible feature flags — no object storage, no
plain SSH-only host, ever, without a translation layer this note found no primary source for. Whole
dataset/snapshot granularity: no per-file selective restore without mounting the received snapshot
first. No cross-file deduplication the way restic/Kopia/Borg chunk and dedupe content — a `zfs send`
stream is exactly the blocks that changed since the reference snapshot, nothing more, nothing less.
And, as above, it structurally cannot reach the NAS-held originals, which are the majority of the
data this ticket is about by volume.

---

## 3. Off-site destinations

### 3.1 Zero recurring cost: a non-monetary destination

The only category that is genuinely free on an ongoing basis is reused hardware — a drive or a
small always-on device the operator already owns — kept at a trusted third party's home, not rented
from anyone. Two mechanical variants, both compatible with any of restic, Kopia or Borg (all three
speak local paths and SSH/SFTP natively, per §2):

**Networked**, over the platform's already-decided private mesh. Tailscale's Personal/Free plan is
free indefinitely and permits **unlimited devices**
([tailscale.com/pricing](https://tailscale.com/pricing); ADR-0011) — a device carried to a trusted
third party's home and joined to the same tailnet becomes reachable over SSH exactly as any other
tailnet member, with no port forwarded on either end and no new account or bill. Any of the three
file-level engines can then treat it as an ordinary SFTP or `ssh://` repository. The binding
constraint is issue #8's measured ~100 Mbit/s upstream ceiling: seeding the full ~1.5 TB corpus
after the device has left the LAN would take, at the physical limit of that link with no protocol
overhead and no contention from household use, **at least 1,500,000 MB / 12.5 MB/s ≈ 120,000 s ≈
33 hours** (derived from #8's figure; realistically longer once overhead and shared use are
counted). The practical sequencing is therefore to do the initial full backup while the device is
still on the LAN, and only ship incremental changes over the WAN afterward — a restriction on
*when* the first backup happens, not on whether the destination works.

**Rotated by hand.** The same device or a bare drive, synced locally over USB while it is home, then
physically moved to the third party's location and disconnected until the next rotation. No network
dependency at all for the bulk transfer, and — because the drive is offline between rotations — the
strongest available isolation from anything that could propagate from a compromised or malfunctioning
server (a ransomware-style write storm, a bad `zfs receive` from a corrupted stream) reaches nothing
while the drive is unplugged. The cost is staleness: the backup's effective age is bounded by the
rotation cadence, not by how often the engine runs, which is a direct input to whatever RPO figure
#23 settles on, not something this note fixes.

Neither variant has a technical citation beyond "the tools already discussed work over local paths
and SSH" (§2) and Tailscale's own device-cap statement — there is no vendor whitepaper for "put a
hard drive at a friend's house". What this note can state precisely is what any such destination
lacks by construction: no SLA, no redundancy behind that single drive or device (its own failure is
total, with the same shape of exposure #9 found and rejected for the seedbox — no RAID, no
data-recovery guarantee — accepted here only because there is no cheaper alternative and #23 can
choose to layer a second, independent copy on top), and a trust dependency on a real relationship
rather than a company's terms of service.

### 3.2 A small monthly cost: S3-compatible object storage and SSH-native storage

Published per-TB/month figures, current as of this research:

| Provider | Price | Egress | Minimums | Protocol fit |
| --- | --- | --- | --- | --- |
| **Backblaze B2** | $6.95/TB/mo ([backblaze.com/cloud-storage/pricing](https://www.backblaze.com/cloud-storage/pricing)) | Free up to 3x average monthly storage, then $0.01/GB ([same](https://www.backblaze.com/cloud-storage/pricing)) | **None** — "No minimum file size fees," "No minimum storage duration fees" ([backblaze.com/b2/cloud-storage-pricing.html](https://www.backblaze.com/b2/cloud-storage-pricing.html)); Backblaze's own blog contrasts this directly with Wasabi's minimum ([Backblaze blog](https://www.backblaze.com/blog/the-fine-print-how-minimum-data-retention-fees-affect-cloud-costs/)) | S3-compatible API — restic and Kopia both native; Borg cannot reach it (§2.3, §2.1's B2-via-S3 caveat) |
| **Wasabi** | $7.99/TB/mo ([wasabi.com/cloud-storage-pricing](https://wasabi.com/cloud-storage-pricing/)) | "No fees for egress or API requests" ([same](https://wasabi.com/cloud-storage-pricing/)) | **90-day minimum retention** on Pay-as-you-Go: deleting an object early bills "a Timed Deleted Storage charge equal to the storage charge for the remaining days" ([docs.wasabi.com](https://docs.wasabi.com/docs/how-does-wasabis-minimum-storage-duration-policy-work)); minimum billable object size 4 KB ([wasabi.com/pricing/faq](https://wasabi.com/pricing/faq)) | S3-compatible — same fit as B2, minus the B2-specific library caveat; the 90-day minimum interacts badly with a `prune`-heavy retention policy that deletes old snapshots sooner than that |
| **rsync.net**, standard | 1.5 c/GB/mo (0-9 TB tier), dropping to 1.25 c/GB (10-99 TB) and 0.75 c/GB (100+ TB) ([rsync.net/pricing.html](https://www.rsync.net/pricing.html)) | "No Egress Charges" (same) | None stated for standard tier | SSH/SFTP — fits Borg directly |
| **rsync.net**, Borg-specific | 1.5 c/GB/mo up to 999 GB, 0.8 c/GB at 1-99 TB ([rsync.net/products/attic.html](https://www.rsync.net/products/attic.html)) | Free (same) | $18/year minimum (100 GB) | Explicitly Borg-oriented pricing page |
| **rsync.net**, `zfs send`-capable | 1.25 c/GB/mo (10-99 TB) down to 0.75 c/GB (1+ PB) ([rsync.net/products/zfsintro.html](https://www.rsync.net/products/zfsintro.html)) | Free (same) | **10 TB minimum account size** (same page) | Native `zfs send \| ssh ... zfs receive` target — customer "control[s] your own zpool and manage[s] your own snapshots" |
| **Hetzner Storage Box** | Capacity tiers BX11/BX21/BX31/BX41 = 1/5/10/20 TB, each with its own snapshot count (10/20/30/40) ([hetzner.com/storage/storage-box](https://www.hetzner.com/storage/storage-box/)) | Not stated on the fetched page | Not stated on the fetched page | "FTP, FTPS, SFTP, SCP, Samba/CIFS, **BorgBackup**, **Restic**, Rclone, rsync via SSH, HTTPS, WebDAV" — named support for both Borg and restic, by Hetzner itself ([same](https://www.hetzner.com/storage/storage-box/)) |

**EUR price for Hetzner Storage Box is not established from primary sources here** — see §4; the
capacity tiers, snapshot counts and protocol list above are confirmed directly from Hetzner's own
page, but the page renders its EUR figures client-side and this research's automated fetch could not
retrieve them.

**Sizing against this platform's actual volume.** ADR-0010 puts the corpus at ~1.5 TB and the
Postgres dump at ~20 GB. At 1.5 TB:

- Backblaze B2: 1.5 x $6.95 ≈ **$10.43/month**.
- Wasabi: 1.5 x $7.99 ≈ **$11.99/month**, plus the 90-day early-deletion exposure above.
- rsync.net standard: 1.5 TB x 1.5 c/GB ≈ **$23.25/month** (and the `zfs send`-capable tier's 10 TB
  minimum prices out at **$125/month minimum** regardless of actual usage — clearly the wrong tier
  at this scale).

None of these lands near the "a few EUR" figure #27's precedent anchors to (27-49 EUR/year ≈
roughly €2-4/month) — every metered object-storage option for the *full* corpus runs to double
digits monthly, in the currency each provider publishes in. At the ~20 GB database alone, the same
math is nearly free: 20 GB x $6.95/TB ≈ **$0.14/month** on B2. The "few EUR" scenario fits the
database far more comfortably than it fits the photo corpus — a sizing fact this note surfaces
rather than smooths over, since #23 will need it either way.

---

## 4. Not established from primary sources

1. **Hetzner Storage Box's own published EUR price**, for any of the BX11/BX21/BX31/BX41 tiers.
   Hetzner's pricing table renders client-side; this research's automated fetch (including a
   render-through-proxy attempt) retrieved the page's structure and every other fact quoted above,
   but not the numeric price. Third-party hosting-plan directories report figures in the €3-41/month
   range across the four tiers, but per this ticket's own sourcing rule (no aggregator posts), those
   numbers are not cited as fact here — only recorded as unconfirmed.
2. **Whether Kopia's Rclone or Google Drive backends work with any of Backblaze B2, Wasabi, or the
   other providers in §3.2** beyond what each already supports natively — Kopia's own docs state
   only Dropbox, OneDrive and Google Drive have been tested through Rclone, not a wider list.
3. **A primary source for reaching Backblaze B2 or Wasabi with Borg**, e.g. via an rclone FUSE mount
   used as a local Borg repository path. No Borg or rclone documentation describing this combination
   as supported was found; it is not asserted to work.
4. **Whether restic, Kopia, or Borg document a repository-locking or multi-writer story** relevant to
   backing up from more than one source (server + a second node, say) into the same repository — out
   of scope for what this ticket asked, and not chased down, but worth flagging as unexamined rather
   than silently assumed safe.
5. **Any vendor-published SLA or redundancy guarantee for a home device kept at a trusted third
   party's location** — by definition there isn't one; recorded so the gap is explicit rather than
   implied.

---

## 5. What this note recommends

**Engine: restic**, for both jobs, into one repository.

Postgres: `restic backup --stdin-from-command -- pg_dump ...` (or `pg_dumpall`, subject to §1's
per-database caveat), which restic detects and fails loudly on a non-zero exit rather than silently
completing an empty backup. NAS-held originals: a plain `restic backup` of the existing NFS mount,
no special handling needed. One tool, one retention/prune policy, one encryption story (mandatory
AES-256, no configuration decision to get wrong the way Borg's `none` mode allows).

`zfs send`/`receive` is ruled out as the *primary* mechanism for one structural reason that has
nothing to do with feature comparison: **it cannot reach the NAS-held originals at all**, because the
DS412+ is not ZFS. It stays available as a same-technology, ZFS-native supplementary safety net for
the state pool specifically (Postgres's dataset, Immich's derivatives) if a second ZFS-capable host
ever exists to receive it — a "could also," not the backbone. Kopia was the closest competitor: its
Actions feature is a genuinely better primitive for orchestrating a ZFS-snapshot-before-backup
sequence than restic's external-scripting-only story, but that primitive is opt-in specifically
because Kopia's own docs treat it as a security-relevant trust surface, and the project's own most
recent release notes name a data-loss race condition fixed weeks before this research — a directly
relevant concession for a backup tool, not a generic maturity complaint. Borg was ruled out as the
single unifying engine because its destination story is SSH/local only, which works for §3.2's
SSH-native providers but forecloses the cheapest S3-compatible object storage outright — a
real strength for a Storage Box- or rsync.net-shaped destination, not a reason to prefer it as the
default when destination flexibility matters more at this stage.

**Destination: the zero-cost, non-monetary category, for the bulk of the data.** §3.2's sizing
finding is the deciding fact: at this corpus's actual size, every metered object-storage option
costs far more than the "a few EUR" figure #27's precedent anchors to — Backblaze B2, the cheapest
of them, comes to roughly $10/month for 1.5 TB, not a few euros. A reused drive or small device kept
at a trusted third party's home, reached over the platform's already-decided Tailscale mesh (or
rotated physically), costs nothing recurring and fits the actual data volume. What it gives up,
stated plainly: no vendor SLA, no redundancy behind that one drive, and a trust dependency on a
person rather than a company's terms of service — the same shape of gap #9 found and rejected for
the seedbox, accepted here only because it is the only destination that fits this corpus at zero
recurring cost, and because #23 can choose to layer a second copy on top of it rather than treating
it as the only copy.

**Where the "a few EUR" budget is actually well spent, if #23 wants to use it at all: the ~20 GB
Postgres dump, not the photo corpus.** At that size a paid off-site copy is not a compromise, it is
close to free (§3.2: ~$0.14/month on B2) — a second, provider-backed, geographically and
organizationally independent copy of the one dataset ADR-0010 already calls irreplaceable-tier,
layered on top of whatever the non-monetary destination is doing for the corpus. That spends the
accepted-but-small budget precisely where redundancy of destination matters most, rather than
diluting it across 1.5 TB that a zero-cost destination already covers. If the corpus itself
eventually needs a provider-backed copy too, Hetzner Storage Box is this research's strongest
candidate — it names both restic and Borg support directly, and prices by flat capacity tier rather
than metered per-GB — but its own EUR figure is the one number in this note that could not be
pinned down from Hetzner's own page (§4), and should be confirmed before it is relied on for a
budget line.
