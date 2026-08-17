---
status: accepted
date: 2026-08-17
tags: [observability, alerting, hardware, thermal]
---

# A thermal alert on `k10temp` and NVMe `Composite`, and `node_exporter` on the host to publish it

#152 asked what alerts when this machine's cooling fails, and on which signal.
ADR-0004 accepted four alert categories (node unreachable, disk near full,
backup missed its RPO window, certificate expiring soon) and none of them is
thermal. This ADR amends that alert set to five, and settles the collector the
other four also silently needed.

Every hardware fact below was re-measured on the installed machine on
2026-08-17, not inherited from the GitLab archive that first recorded it.

## What the kernel actually exposes here, and what it does not

| `hwmon` chip | Sensors | Reading at idle (load 0.28) |
| --- | --- | --- |
| `k10temp` | `Tctl`, `Tccd1` | 36.0 degrees C / 32.25 degrees C |
| `nvme` (x2) | `Composite`, plus `temp1_crit` | 38.85 degrees C, crit **89.85 degrees C** |
| `gigabyte_wmi` | six unlabelled probes | 31 to 49 degrees C |
| `acpitz` | two probes | |

**No `fan*_input` and no `pwm*` exist anywhere.** The board's IT8688E
controller wants an out-of-tree driver, so Linux can neither read nor drive
the fans or the AIO pump. The BIOS curves recorded in
`docs/reference/bios-settings.md` are therefore the only cooling mechanism on
this machine, they live outside this repository, and nothing reconciles them.
A dead pump, a seized fan and failed thermal paste are all invisible to every
collector this platform runs.

Two absences shape everything below. **`k10temp` publishes no `temp*_crit` or
`temp*_max`**, so unlike the NVMe drives the CPU offers the kernel no trip
point and any threshold is a literal written by hand. And **the GPU is not in
`hwmon` at all**: `nvidia-smi` reports it (50 degrees C at idle) and nothing
else does.

## Alert, not signal

ADR-0004 leans on Prometheus's own guidance to "aim to have as few alerts as
possible" and "avoid having pages where there is nothing to do", and the
distinction that decides this case is action, not severity: an alert demands a
human, a signal lives in Grafana and never notifies.

The CPU does not need saving. A 5600X throttles at its Tjmax and does not
destroy itself, and each NVMe drive carries its own critical trip at
89.85 degrees C. What the alert protects is not the silicon but the absence of
any recovery loop around it. This machine is a named SPOF with a zero hardware
budget and no spare part, ADR-0012 makes it the only holder of a 1.5 TB photo
corpus with no off-site copy of anything, and ADR-0005 already accepted that it
takes unclean shutdowns without a UPS. Silent degradation on that machine is
not an inconvenience, it is the failure mode with the longest recovery. Node
unreachable, ADR-0004's root-cause alert, catches the same event only once it
has already happened.

Accepted as an alert, and as the **fifth and last** category.

## The two signals, and the one that is deliberately absent

The alert reads **`k10temp`'s `Tctl`** and **the `Composite` sensor of both
NVMe drives**.

`Tctl` rather than `Tccd1`: it is the quantity AMD's published Tjmax and the
BIOS fan curve both refer to, and the spread measured today (36.0 against
32.25) shows no gross offset on this part.

The NVMe drives are in scope because they are the only sensors on this machine
that arrive with a vendor threshold of their own, and because ADR-0010 puts
PostgreSQL and, since ADR-0012, its only backup on the state pool. Excluding
the most trustworthy signal available would have been a saving of nothing.

**The GPU is deliberately out of scope, and this leaves a real blind spot.**
`docs/reference/bios-settings.md` records that every case fan shares one hub
sense wire back to `CPU_FAN`, and that `Fan Control Use Temperature Input` is
set to CPU Temperature. A purely GPU-bound load, which is exactly what ADR-0002
budgets 8 GiB of Immich to produce, heats the case while the curve sees a cool
CPU and holds the whole airflow group at its 25% floor. `k10temp` would see
that second-hand and late. Covering it would require the textfile collector
ADR-0004 does not have, plus home-made scripts to test, for a component that is
not cooled by the circuit this alert watches. Recorded here and carried to #99
rather than solved.

## Absolute thresholds, sourced rather than chosen

| Signal | Threshold | Held for | Why this number |
| --- | --- | --- | --- |
| `k10temp` `Tctl` | **85 degrees C** | **15 min** | The point at which the `CPU_FAN` curve reaches 100%. Above it the cooling has no lever left |
| `nvme` `Composite` | **70 degrees C** | **30 min** | Kingston's published Operating Temperature ceiling for the NV2, the only figure the vendor warrants |

Three CPU candidates were on the table and two lose on their own terms. **95
degrees C** is AMD's Tjmax, which is the throttling point, so an alert there
fires after the machine has already given up performance. **80 degrees C** is
the BIOS `Temperature Warning Control` value, but `bios-settings.md` records
that a Ryzen 5000 part spikes to 80 degrees C within a fraction of a second on
a brief load: that is a normal transient, not a symptom. 85 degrees C is the
only one of the three that marks a mechanical fact rather than a margin.

On the NVMe side the two primary figures sit 20 degrees C apart. The drive's
own `temp1_crit` at 89.85 degrees C is its emergency, far past anything
Kingston warrants; the datasheet's 0 to 70 degrees C operating range is the
bound the vendor stands behind, on drives the same datasheet says in writing
are "not intended for Server environments"
(`docs/reference/research-zfs-on-dramless-ssds.md`). 70 degrees C is the
earlier and twitchier of the two, and the duration is what keeps it quiet.

**Neither duration races damage**, because both components protect themselves.
The durations buy certainty instead, so they are generous. 15 minutes on the
CPU is three orders of magnitude above the documented transient. 30 minutes on
the NVMe leaves room for the legitimate multi-minute excursions this platform
schedules, a ZFS scrub and ADR-0012's monthly restore check, without crying;
the drives never see hours of saturating write, since ADR-0010 keeps the photo
originals on the NAS and leaves the state pool only PostgreSQL and Immich's
derivatives.

**One category, not two.** ADR-0004 counts in categories and pushes explicitly
toward fewer. CPU over-temperature and NVMe over-temperature have different
causes but call for the same gesture, which is to go and look at the machine,
and ADR-0004's criterion is action rather than cause. The two expressions ride
one category with the sensor carried on a label. The cost is that the
notification alone does not say which sensor spoke.

## Absolute only, with idle drift kept as a signal

An absolute threshold sees a cooling failure **only under load**, and this
machine's normal state is what was measured today: load 0.28, `Tctl` at
36 degrees C. A dead pump at idle would likely settle somewhere between 55 and
70 degrees C and never reach 85. The alert therefore catches the failure at the
moment it becomes damaging, not at the moment it occurs.

A second, load-conditioned rule on drift from an idle baseline would close that
gap and is rejected anyway. It is exactly the rule that misfires: an office
whose ambient temperature is neither measured nor stable between January and
August moves the baseline underneath it, and the resulting summer false
positives get silenced, which is the worst failure mode ADR-0004 names. Its
coverage gain is also smaller than it looks, since #16 replaced Immich's
library watcher with periodic scanning, so a real load arrives regularly rather
than never and does exercise the absolute rule.

Idle drift is kept as a **signal** in ADR-0004's sense: it lives in Grafana and
never notifies.

## `node_exporter` on the host, and which envelope pays

Nothing in the accepted ADR set publishes a single host metric. This is not
specific to the thermal alert: ADR-0004's "disk space near full" has no source
today either. VictoriaMetrics scrapes Prometheus-format targets itself
(`-promscrape.config`), which removes the scrape agent, not the exporter.

**`node_exporter` runs on the host**, as a systemd unit posed by Ansible where
ADR-0003 already puts the host, capped by `MemoryMax=` in keeping with
ADR-0004's rule that every limit is external, and **charged to ADR-0002's 1 GiB
host envelope rather than its 3 GiB observability envelope**.

`hwmon` is a host concern. Running the exporter in-cluster would hand a pod
access to `/sys` on the machine that carries the family photos in order to read
a health value, and would have to take 64 or 128 MiB back from VictoriaMetrics
or Grafana, since ADR-0004 splits its 3 GiB to exactly 3072 MiB with nothing
left over.

The accounting is a convenience and is named as one: ADR-0002 never itemised
what its host gigabyte contains, so charging the exporter there is a claim
about available room, not a measurement of it.

## Decision

A fifth alert category, thermal, amending ADR-0004's set of four. It reads
`k10temp`'s `Tctl` above 85 degrees C for 15 minutes and either NVMe
`Composite` above 70 degrees C for 30 minutes, as absolute thresholds with no
baseline term, in one category with the sensor on a label. Idle drift is a
Grafana signal, never a notification. `node_exporter` runs on the host under
systemd and a `MemoryMax=` cap, inside ADR-0002's host envelope, publishing
`hwmon` for this alert and the filesystem metrics ADR-0004's disk alert also
needs. The GPU and case airflow stay out of scope.

Exact PromQL expressions are implementation, as ADR-0004 already established
for its own four; the thresholds and durations above are not.

## Alternatives rejected

**No thermal alert at all.** The smallest answer, and consistent with
ADR-0004's push toward fewer alerts. Rejected because there is no recovery loop
around this machine to absorb the failure: no redundancy, no hardware budget,
no off-site copy, and per ADR-0012 the NAS convergence already makes a long
outage expensive. What it would have given up is exactly what is written above,
so the refusal was priced before being declined.

**Thermal as a signal only, in Grafana.** Cheaper still and honest about the
fact that the CPU cannot destroy itself. Rejected because a signal is read when
someone thinks to look, and the failures this watches for (a dead pump, a
seized fan, failed paste) are precisely the ones nobody thinks to look for.

**80 degrees C on the CPU**, matching the BIOS `Temperature Warning Control`.
Rejected because `bios-settings.md` documents an 80 degrees C spike as a normal
sub-second transient on this part, and because at 80 the curve still has its
last two steps in hand, so the machine has a response available and the alert
would fire while it is still working.

**95 degrees C on the CPU**, AMD's Tjmax. Rejected as too late by
construction: it is the throttling point, so the alert would report a loss
already taken.

**89.85 degrees C on the NVMe**, the drive's own kernel-published critical
trip. The tempting choice, since it is the one CPU-side figure this ADR wishes
it had. Rejected because it is the drive's emergency rather than its
specification, and Kingston warrants 70.

**Two alert categories, CPU and NVMe.** Rejected on ADR-0004's own criterion:
the two share one remedy, and Alertmanager groups them regardless.

**A second rule on drift from an idle baseline.** The one option that would
catch a dead pump at the moment it dies. Rejected on false positives in an
unmeasured, seasonally drifting ambient, which end in a silence and then in a
habit of ignoring notifications.

**`node_exporter` as an in-cluster DaemonSet.** The GitOps-native placement,
described by Flux like everything else. Rejected for granting a pod raw `/sys`
access on this machine, and for the 3 GiB envelope having nothing to give.

**No exporter, a systemd timer pushing three sysfs values to
VictoriaMetrics's import endpoint.** The shortest path in RAM. Rejected because
it is home-made code to maintain and test, the exact cost the archived
iteration's own alerting ADR named for its textfile collector, and it would
leave ADR-0004's disk alert still without a source.

**An `absent()` rule to detect the collector's own death.** Rejected because it
watches the monitoring from inside the monitoring, which is the flaw a dead-man
switch exists to fix, and it would cost a sixth alert on a list just raised to
five. Sent to the receiver ticket instead, see below.

## Consequences

- **ADR-0004's alert set becomes five categories.** Adding a sixth stays a
  deliberate decision against its "as few alerts as possible" guidance, not a
  default.
- **`node_exporter` enters ADR-0013's still-unwritten Ansible host role**, with
  a `MemoryMax=` unit override. This does not reopen ADR-0013: the roles were
  already deferred to build time, and this adds one, not a change to the
  manual-gesture count.
- **ADR-0002's host gigabyte now has a named occupant** and no measured one.
  The first real measurement of `node_exporter` on this machine either confirms
  the accounting or forces the exporter back onto the observability envelope,
  where something must be taken from VictoriaMetrics or Grafana.
- **The alert has no witness, and no destination.** Alertmanager still routes
  to nothing named, for all five categories, and if `node_exporter` dies the
  thermal alert stops working in silence while the node stays perfectly
  reachable. Both land on
  [Decide the alert receiver and the dead-man witness](https://github.com/thefiven/homelab/issues/154),
  which is a dependency of this ADR being operational, not a nice-to-have.
- **A dead pump at idle is discovered at the next real load**, not when it
  dies. Between those two moments nobody is woken.
- **The GPU and the case airflow are unwatched**, on a board whose entire case
  fan group is driven by CPU temperature alone. Carried to #99.
- **The BIOS curves remain outside the repository and unreconciled.** This
  alert observes their failure, it does not close the gap that they are
  configured by hand at a console and that nothing here can read them back.
