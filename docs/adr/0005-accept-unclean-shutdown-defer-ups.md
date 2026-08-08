---
status: accepted
date: 2026-08-08
tags: [power, storage]
---

# Accept unclean shutdown on power loss; defer the UPS

The 06:30-23:00 operating window was abandoned while charting (#27): the
machine runs continuously, so there is no nightly shutdown to design and no
RTC wake to configure. What remains is a single case, power loss, and a
second, unrelated one this ticket also has to settle: an administrator-
triggered shutdown or reboot.

## The two cases are not the same problem

A true power loss gives no warning. Without a UPS, nothing on this machine
can detect that power is about to disappear, so there is no window in which
to run an "ordered shutdown sequence": the machine is simply gone, mid-write,
whatever it was doing. Treating this as a sequencing problem would presuppose
a signal that does not exist.

An administrator-triggered shutdown or reboot is a different case entirely:
planned, signalled, with as much time as `systemd` is given to take it.
Conflating the two would import the wrong design constraints into each; this
ADR treats them separately.

## The UPS is deferred

An entry-level UPS (roughly 80 to 120 EUR, 15 to 25 minutes of runtime on a
600VA unit) would convert a power loss into a signalled event: paired with
NUT (Network UPS Tools), it gives the host a warning and a window to run an
actual ordered shutdown before the battery empties.

That capability is deferred, not rejected. The standing constraint is explicit
and already binding elsewhere on this project (ADR-0002, #20): zero hardware
budget now and for the coming months. The seedbox is the one named exception
to the platform's no-paid-hosting rule (#29), and it earned that exception
because the whole 3-2-1 backup strategy has no other candidate; a UPS has no
equivalent forcing argument today. It becomes the first purchase when budget
appears, or sooner if the risk below stops being acceptable in practice.

## The accepted risk

#15 already found, in writing from Kingston, that the NV2 drives are "not
intended for server environments." Power loss is the sharpest edge of that
finding: sudden power loss can corrupt NAND in several ways depending on what
the drive was doing at the instant it lost power, data still in a volatile
cache is lost outright, an interrupted program or erase operation leaves cells
that fail ECC on read, and in the worst case a damaged flash translation
table makes the whole drive unreadable, not just the file being written.
DRAM-less drives carry this risk more acutely, since they lean on system
memory (via Host Memory Buffer) rather than their own cache for mapping data.

This is accepted as a named risk, not mitigated by new tooling, consistent
with how #15 already accepted these drives for a workload their own vendor
does not recommend them for. If #19 chooses ZFS, its copy-on-write model adds
real protection at the filesystem layer: a transaction group is either fully
committed or not applied at all, so a crash mid-write does not corrupt
already-committed data, at the cost of losing only the most recent, uncommitted
transaction group. That protects the filesystem's consistency; it does not
reach the drive's own flash translation table, so the worst case above is not
eliminated by filesystem choice. This ADR does not presuppose #19; the
mitigation is named as a property ZFS would bring if chosen, not as a decision
made here.

## Orderly shutdown, for the case that can have one

An administrator-triggered shutdown or reboot relies on `systemd`'s native
unit ordering and its own timeout and `SIGKILL` escalation, not a custom
script. Nothing about this platform's requirements justifies reimplementing
what `systemd` already does for free. Graceful termination of containerized
workloads, drain order, in-flight request handling, follows whichever
orchestrator #21 settles on; it is that orchestrator's concern once chosen,
not a sequence to design here in its absence.

## Decision

No UPS for now. A true power loss is accepted as an unclean shutdown with no
warning and no orderly sequence, with the NV2 corruption risk named and
carried forward from #15. An administrator-triggered shutdown or reboot relies
on `systemd`'s native ordering; container-level graceful termination is
deferred to #21.

## Alternatives rejected

**Buying a UPS now.** Would convert power loss into a signalled, plannable
event. Rejected against the zero-hardware-budget constraint, absent a forcing
argument as strong as the one that carved out the seedbox exception. Revisit
when budget appears or the accepted risk stops being acceptable in practice.

**A custom shutdown script for the administrator-triggered case.** `systemd`
already provides ordered dependencies, timeouts and kill escalation. Writing
a bespoke sequence would duplicate that behaviour for no documented gain, and
would need redesigning again once #21 picks an orchestrator with its own
termination semantics.

## Consequences

- No RTC wake, no UPS-triggered shutdown script, no NUT configuration exists
  or is planned until the UPS decision reopens.
- The NV2 power-loss corruption risk is now named on two ADRs (#15's origin,
  this one's power-loss case) rather than assumed away; a drive that loses
  its flash translation table is a full-drive event, not a per-file one, and
  no mitigation available at zero budget closes that gap.
- Administrator-triggered shutdowns need no new tooling: `systemd` unit
  ordering is the mechanism, today and after #21.
- The risk register (still fogged, pending the foundation, storage and power
  decisions) inherits this as a named entry rather than a gap to discover
  later.
