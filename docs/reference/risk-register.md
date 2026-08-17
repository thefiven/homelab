# Risk register

**Date: 2026-08-17**

Every risk this platform's accepted ADRs knowingly carry rather than
mitigate, one entry per risk. Each entry is traced to the ADR whose Decision
or Consequences section accepted it, and states what would have to change
before it is worth revisiting. This document records what has already been
decided; it does not decide anything itself (ADR-0006). A risk that cannot be
traced to an accepted ADR does not belong here: that would be a missing
decision, not a register entry, and none was found while compiling this.

## 1. One machine, no UPS

This machine is the platform's entire hardware: one Ryzen 5 5600X box, no
second node, no clustering to fail over to. A true power loss gives no
warning and no orderly shutdown sequence, the machine is simply gone,
mid-write. The state-pool NVMe drives compound this: Kingston's own
documentation states they are "not intended for Server environments," and
sudden power loss can corrupt NAND, in the worst case damaging the flash
translation table and losing the whole drive rather than one file.

**Accepted by:** ADR-0005.
**Revisits when:** hardware budget appears (none is allocated now or for the
coming months, per #4's standing constraint), or the risk stops being
acceptable in practice. A UPS paired with NUT is the named mitigation, not
purchased.

## 2. No off-site copy of anything

Every off-site backup candidate was checked and rejected, on cost or on
principle: metered object storage, a physical drive at a trusted third
party's home, an existing family cloud subscription. The Postgres database's
only backup and the photo corpus's only copy both live in the same building
as the platform they protect. A real 3-2-1 backup strategy is not achieved.

**Accepted by:** ADR-0012.
**Revisits when:** the zero-recurring-cost constraint changes, or a second
NAS or node is added.

## 3. The photo corpus has one copy, on correlated hardware

No copy of the Immich photo originals exists anywhere but the DS412+ NAS.
Its four disks are the same batch and wear together: power-on hours within
3% of each other, at roughly 42,000-43,000 hours (#7). A rebuild window
after one disk fails is not safe extra time against a second failure close
behind it, which is exactly the correlated failure mode no RAID level
protects against.

ADR-0012's own consequences left a door ajar: a second, local, non-off-site
copy, "possibly folded into adding a second NAS or node." That door is now
closed for the hardware on hand. #97 and #98 closed as not planned, and the
LaCie 5big Network 2 considered as a candidate medium was rejected: more
obsolete than the DS412+ it would have supplemented, and it does not speak
NFS, which ADR-0010 and the `nfs-client` role are built on.

**Accepted by:** ADR-0012 (the sole-copy risk itself, and the NAS as its
accepted SPOF), sharpened by #7's correlated-wear finding. The door's
closure, that no second local copy is planned from owned hardware, is
recorded from #97, #98 and #99's own follow-up comment, not from ADR-0012's
text; it does not reopen ADR-0012's decision, since the second-local-copy
option was never adopted there, only raised and left unspecified.
**Revisits when:** budget exists for a second medium worth trusting, one
that is NFS-capable and not itself more obsolete than the DS412+. No ticket
is open toward this; it is the standing state of the corpus, not a deferred
one.

## 4. NVMe not rated for server duty, run without a mirror

Both state-pool NVMe drives are Kingston NV2s the vendor documents as "not
intended for Server environments" (#15). ADR-0010 chose not to mirror them:
a mirror doubles metadata writes and ages two identical, same-batch drives
together, spending the platform's entire endurance headroom against an
unmeasured amplification factor for protection against only one of the
failure modes an unmirrored pool leaves open. Each drive runs as a single
point of failure for whatever it holds.

**Accepted by:** ADR-0010, informed by #15. ADR-0005 separately accepts the
sharper edge of the same drives: sudden power loss corrupting NAND with no
UPS to prevent it (entry 1).
**Revisits when:** a baseline of `nvme endurance-log`'s write-amplification
figures, an ADR-0010 measurement task not yet run, shows the real factor is
better than the x5.5 worst case assumed. `zpool attach` can then widen
either pool into a mirror without a rebuild.

## 5. No component publishes an enforceable internal cap

Neither the observability stack (#17: none of Prometheus, Loki,
VictoriaMetrics or VictoriaLogs document an internal memory cap) nor a
collaborative office server (#35) publishes one. Every memory limit on this
platform is external: a cgroup, a systemd slice, an admission gate. Within
the reserved floor of mandatory platform overhead (host, filesystem cache,
control plane, GitOps, observability), the largest single line, the 5 GiB
ZFS ARC, sits in the enforcement class that is weakest, kernel memory,
invisible to any cgroup. Even its external cap is a target rather than a
guarantee: an upstream OpenZFS 2.3.x bug let the ARC exceed `zfs_arc_max`,
fixed only in July 2025.

**Accepted by:** ADR-0002.
**Revisits when:** a consumer this platform runs publishes its own
enforceable internal cap. The ARC's cap remaining a target rather than a
guarantee is a standing property of the running OpenZFS version, and no
ticket here schedules a check of which side of the July 2025 fix this
platform's version sits on.

## 6. A ~100 Mbit/s powerline segment on the path to the internet

A powerline (CPL) segment sits on the router-to-switch leg, confirmed by
physical `iperf3` bisection: roughly 940 Mbit/s on the LAN side, roughly
100 Mbit/s once the CPL is crossed (#8). Every public-facing decision, what
can be exposed through the Cloudflare Tunnel and how the household's own use
competes with it, is designed around this ceiling as a given, not a target
to raise.

**Accepted by:** ADR-0011, which builds its exposure design on #8's measured
ceiling without proposing to raise it.
**Revisits when:** the household's ISP plan or physical wiring changes.
Neither is scheduled by any ADR.

## 7. No VLAN on the unmanaged switch

The office switch is unmanaged: no VLAN, no LACP, no port mirroring. The
NAS's own isolation trick, no gateway and no DNS configured on the device,
buys isolation from the internet and nothing else. Any device already on the
LAN can still reach it, narrowed only by the NFS export rule naming one
address, a configuration a future change could widen with nothing to flag
it.

**Accepted by:** ADR-0011.
**Revisits when:** the switch hardware changes. Nothing here schedules or
requires that.

## 8. Nothing mechanical enforces the publication policy

The placeholder convention, no real hostname, IP address, hardware
identifier, or family member's name ever committed, is enforced by the
attention of whoever commits, and by nothing else. A deny-list scanner was
considered and rejected: a regular expression that matches a real domain
contains that domain, which a public repository cannot carry. A credential
scanner catches a credential; it does not catch a designator.

**Accepted by:** ADR-0001.
**Revisits when:** nothing scheduled. Named as an accepted residual risk,
not a gap deferred to a future ticket.

## 9. The GPU and case airflow are thermally unwatched

The board's entire case-fan group takes its one sense wire from `CPU_FAN`,
driven by CPU temperature alone. A purely GPU-bound load, exactly what
Immich's machine-learning component (2 of its 8 GiB envelope, ADR-0002)
produces, heats the case while the curve sees a cool CPU and holds the whole
airflow group at its 25% floor. `k10temp`, the signal the thermal alert
reads, sees that only second-hand and late; the GPU itself is not in
`hwmon` at all, so nothing on this platform alerts on it directly.

**Accepted by:** ADR-0017.
**Revisits when:** covering it would need the textfile collector ADR-0004
does not have, plus new scripts to test, for a component the alert's watched
circuit does not cool. Not scheduled.
