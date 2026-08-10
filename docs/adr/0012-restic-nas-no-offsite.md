---
status: accepted
date: 2026-08-10
tags: [backup, storage]
---

# restic to the NAS; no off-site copy of platform data

#23 asked what is backed up, by what engine, to where, and how a restore is proven — a real
3-2-1, with the NAS explicitly disqualified as an off-site copy if it also holds the primary
originals. An inherited constraint sharpened the timing: part of the photo corpus exists today
only as a single copy on an external drive, a transfer medium into Immich, not infrastructure;
until that drive is wiped, it is de facto the corpus's second copy, and the chain has to be
proven before that stops being true, not after.

Grilled through five sub-decisions with `/grill-with-docs`, cross-checked against primary
sources (`docs/reference/research-backup-engines-and-offsite-destinations.md`).

## Scope: the state pool's databases and the NAS-held originals

Two data classes are irreplaceable and in scope: Immich's Postgres database (ADR-0010's state
pool; #19 corrects #11 — application databases holding user-generated state are irreplaceable-
tier, not regenerable) and the Immich photo originals themselves, held on the NAS over NFS, not
on the platform (ADR-0010).

Two things are explicitly out. The **system pool** is disposable by construction — a lost drive
is a reinstall via Ansible (ADR-0003), never a restore, so it needs no backup at all. Immich's
**generated derivatives** (thumbnails, previews, ML embeddings — also on the state pool) are
regenerable from the originals by re-running the pipeline that produced them; backing them up
would duplicate spend for no protection a restore actually needs. Configuration and secrets
already reconstruct from Git (ADR-0007, ADR-0008, ADR-0009) and are untouched by this decision.

## Engine: restic

restic backs up both jobs through one repository: `pg_dump` piped into `restic backup
--stdin-from-command` for the database (fails loudly on a broken pipe rather than silently
completing an empty backup), and a plain `restic backup` for the NFS-mounted originals.
Encryption is AES-256 and mandatory — there is no unencrypted mode to reach for by accident, the
way Borg's `none` repository mode allows.

`zfs send`/`receive` is ruled out as the primary mechanism on a structural ground, not a feature
comparison: it needs a ZFS receiver, and the NAS is not ZFS, so it can never reach the originals
— it stays available as a supplementary path for the state pool alone, unused for now. Kopia has
the best-designed Postgres/ZFS-snapshot consistency primitive of the candidates researched, but
its own documentation names it an opt-in trust surface (scripts persist inside the repository),
and its release notes name a data-loss race condition fixed only weeks before this research —
too fresh a scar to build on. Borg is SSH/local-only, which was a live concern while a metered
off-site destination was still on the table; it stops mattering once the decision below settles
on no off-site destination at all, but restic's mandatory encryption and its
`--stdin-from-command` primitive were already the deciding points independent of that.

## Destination: the NAS, locally — no off-site copy exists

Every off-site candidate closed. #9 and #29 had already ruled out the seedbox and paid hosting
for any *workload*; this decision closes the two candidates that remained even for backup, which
isn't a workload. A physical drive or device at a trusted third party's home was rejected
outright, not weighed. An existing family cloud subscription with spare capacity exists but was
rejected too — using it to guarantee the backup would keep the platform dependent on exactly the
kind of subscription Immich exists to replace, defeating the point of running Immich at all.
Metered object storage was checked against real, primary-sourced pricing: Backblaze B2, the
cheapest option found, prices 1.5 TB at ≈$10.43/month — and even the ≈$0.14/month it would cost
to send only the ~20 GB Postgres dump off-site was rejected on the same grounds as the rest: the
budget for a *recurring* payment is zero, not merely small.

What replaces it: the Postgres dump backs up to the **NAS**, over the network, at zero cost. The
ticket's own rule — a target holding the primary copy can't also be the backup — applies to the
*originals*, which the NAS already holds; it does not apply to the database, which lives on the
platform's NVMe state pool. Pushing the dump to the NAS is a second copy on different media,
using hardware already owned, protecting the database against a fault local to the platform
(a dead NVMe, an application bug, a ransomware infection scoped to k3s) without costing anything
or depending on anyone else.

**No copy of the photo originals exists anywhere but the NAS.** That is the real, load-bearing
consequence of a zero recurring-cost budget colliding with a corpus too large for any free tier
and a household unwilling to host infrastructure anywhere else. It is accepted here, not
mitigated, on the same footing as ADR-0005's accepted unclean-shutdown risk: named plainly rather
than hidden behind a comparison table with no real destination behind it.

## A convergence risk, not just an absent one

Putting the database backup on the NAS means the NAS now holds **both** the corpus's only copy
of the originals **and** the database's only backup. A catastrophic NAS failure — not a single
disk (see below), but the enclosure, a controller fault, fire, theft, or a network-borne attack
that reaches it — takes both at once. This is a sharper single point of failure than "no off-site
copy" alone would suggest, and it is deliberate: the alternative was no database backup at all.

Whatever redundancy the NAS's own RAID/SHR configuration provides protects against a single
failed disk, and nothing checked while charting this decision put a number on that or confirmed
which mode is configured. #7 already found that all four bays wear within 3% of each other at
~42-43k power-on hours — correlated aging, not independent — so a rebuild window after one disk
fails is not a safe assumption of extra time; a second failure close behind the first is exactly
the failure mode #7 flagged, not an edge case.

## Application-consistent snapshots and cadence

The database backup runs on a schedule that satisfies #11's RPO for irreplaceable data, corrected
by #19 to cover application databases: **daily**, at minimum, closing to within 24 hours of loss
in the worst case. `pg_dump`'s own consistency (a single transactionally-consistent snapshot of
the running database, per PostgreSQL's documented behaviour) is what `--stdin-from-command` backs
up — no filesystem or ZFS snapshot coordination is needed for this data class.

#5's measurement that random 4K synchronous writes to the NAS cost ~52 ms/op governed a
different write pattern than this one: restic writes content-defined, multi-megabyte pack files,
not small synchronous transactions, and a ~20 GB daily dump is a bulk transfer with no real-time
deadline. It is expected to complete comfortably; this is not re-measured here and should be
checked once the job actually runs.

## Restore rehearsal

Within #11's 4-hours/month operational appetite: a **monthly automated `restic check`**
(near-zero human time, verifies repository integrity) plus a **quarterly manual restore drill**
(~30-60 minutes, restoring the Postgres dump into a scratch environment and confirming Immich can
actually read it). "A backup that has never been restored does not exist" is honoured for the one
thing that has a backup. There is nothing to rehearse for the photo originals — no copy exists to
restore from.

## Reconstruction path for total loss of the main machine

Losing the server, not the NAS: reinstall the OS via Ansible (ADR-0003); Flux reconciles k3s and
every workload from Git, decrypting SOPS+age secrets in-cluster (ADR-0007, ADR-0008, ADR-0009);
restic restores the Postgres dump from the NAS. The photo originals need no recovery step at all
— they were never on the lost machine. This sequence is checked against #11's targets for
irreplaceable data (24-hour RPO, 72-hour RTO, as corrected by #19 for the database): a same-day
Ansible reinstall plus a Flux reconciliation plus a dump restore is expected to close well inside
72 hours, though the actual timing is not measured here and should be confirmed the first time
the quarterly drill exercises the full sequence rather than just the database restore.

Losing the **NAS** instead is the scenario the rest of this ADR names as an accepted risk, not a
reconstruction path: nothing here restores photo originals that had only one copy.

## Decision

**restic**, one repository, backs up the Postgres database via `pg_dump --stdin-from-command`,
daily, to the **NAS** — at zero cost, using already-owned hardware, not off-site. The same engine
is held in reserve for the NFS-mounted originals, unused until a destination for them is ever
funded. **No off-site copy exists for the photo originals or the database**: every candidate
(metered cloud storage, a third-party physical location, an existing family subscription) was
checked and rejected, on cost or on principle. The NAS is accepted, explicitly, as the single
point of failure for the entire photo corpus and now also for the database's only backup.
Restore rehearsal: monthly automated integrity check, quarterly manual restore drill, within
#11's 4-hour/month budget.

## Alternatives rejected

**Backblaze B2 (or Wasabi, Hetzner Storage Box) for the full corpus.** The cheapest option found,
B2, prices 1.5 TB at ≈$10.43/month — checked against a primary source for B2; Hetzner's own
pricing page renders client-side and could not be confirmed the same way, though a
secondary-sourced figure for the tier that would actually fit (5 TB, since 1.5 TB doesn't fit the
1 TB tier) landed in the same range. Rejected: the budget for a recurring payment is zero.

**Backblaze B2 for the Postgres dump alone.** At ≈$0.14/month for ~20 GB, this was not a
capacity problem — it's the same zero-recurring-cost principle applied consistently rather than
carved out for looking cheap.

**A drive or small device at a trusted third party's home.** Rejected outright, not weighed on
cost or mechanics — the household is not willing to host infrastructure anywhere but its own
premises.

**Reusing an existing family cloud subscription with spare capacity.** Technically available at
zero marginal cost, and rejected anyway: leaning on it to guarantee the backup would keep the
platform dependent on the exact kind of subscription Immich was adopted to retire.

**A rotated external drive as a local (non-off-site) second copy of the originals.** Raised and
left open rather than decided: the household already owns the drive named in this ticket's
inherited constraint, and rotating it costs nothing, but committing to a cadence is deferred to a
later, unspecified decision — possibly folded into adding a second NAS or node, not ruled out
here.

**Kopia**, for its Postgres/ZFS-snapshot integration. The strongest consistency story of the four
candidates researched, but self-flagged as a trust surface and carrying a data-loss race
condition fixed only weeks before this research — too fresh to build the one database backup
this decision has on top of.

**Borg**, SSH/local-only with no native path to metered object storage. Moot once no metered
destination was chosen, but restic's mandatory encryption already carried the comparison before
that.

## Consequences

- **A real 3-2-1 is not achieved.** The database gets two copies on two media, zero off-site. The
  photo originals get one copy, full stop. This is a decision to accept, not a target this ADR
  claims to have hit.
- **The ticket's own sequencing constraint is only partly satisfied.** The chain is provably
  restorable for the database once the daily job and the quarterly drill exist. It is not, and
  cannot be, proven for the photo originals — there is nothing to restore from should the
  external drive named in the ticket's inherited comment be wiped before a second copy exists by
  some other means.
- **The NAS's RAID/SHR configuration is unverified by this decision.** Whatever single-disk
  tolerance it provides is the only redundancy the photo corpus has; #7's correlated-wear finding
  means it should not be assumed to cover a second failure during a rebuild.
- **No configuration is written here.** The restic schedule, its NAS-side credentials, and the
  monthly/quarterly rehearsal automation are SOPS+age secrets and CronJobs for the installing
  ticket, per the map's standing rule against configuration ahead of the ADR it derives from.
- **This reopens** if the zero-recurring-cost constraint changes, if a second NAS or node is
  added (raised in this session, not yet specified enough to ticket), or if the external drive is
  wiped without a replacement local copy in place.
