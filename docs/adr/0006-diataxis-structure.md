---
status: accepted
date: 2026-08-08
tags: [documentation]
---

# Diátaxis structure: what exists on day one, and where the ADR log sits

Graduated from the fog once ADR-0001 settled publication policy: every page is
written against placeholders, and the platform is illustrated with text
diagrams rather than screenshots. That changes how a how-to or an explanation
can be written before either the platform or a running instance to screenshot
exists.

## Which quadrants exist on day one

**Reference** exists already: `docs/reference/` holds the research notes
written so far, and continues to hold technical comparisons as they are
produced.

**Tutorial** and **how-to** are empty and stay empty until the platform is
built. Both are learning by doing or documenting a task against a system that
runs; neither can be written honestly against a design that exists only on
paper. "Building the platform is a separate effort" (this map's own
Destination) applies here without exception.

**Explanation** is the one quadrant that does not need a running system, only
a settled design, so it starts once this map closes, when every structural
decision carries an accepted ADR, not before and not deferred to the build
effort alongside tutorial and how-to. Writing it earlier would explain a
design still changing under it; writing it only once the platform exists
would waste the map's own output; the map's decisions and their reasoning are
already the raw material explanation turns into prose written to be read
start to finish, which is the "learned from and presented" objective this
project's standing constraints name.

## Where the ADR log sits

`docs/adr/` stays outside the four quadrants, an append-only journal, the
arrangement inherited from the prior iteration and confirmed here rather than
changed by default. None of the four modes fit it: it does not teach a task
(not a how-to), it does not describe a system as it currently stands (not a
reference), and it is not prose written to be read start to finish (not an
explanation, though explanation draws on it as raw material). An ADR is a
dated record of one decision, never rewritten once accepted; the four
quadrants describe living documentation that changes as the system it
documents does.

## How a how-to is written without a host to name

The placeholder convention (ADR-0001) means a how-to can never be a transcript
of a real session on a real machine: no real hostname, no real path, no real
IP address to paste. It has to be written as a procedure, generalized over
the placeholder conventions from the first draft, not captured from one and
sanitized after. That is more work than transcribing a session, and it is
also better technical writing, since a procedure written to be replayed
against a placeholder generalizes to any installation rather than
accidentally encoding one operator's specific setup.

## Where a failed approach is recorded

No quadrant carries a dated trace of what was tried and abandoned, and a
separate journal was explicitly declined when this project chose ADRs over
one. That leaves each ADR's own "Alternatives rejected" section as the only
home for that record. It follows that the section is a required part of
every ADR's argument, not a courtesy closing paragraph: an ADR whose
rejected alternatives are thin or absent has nowhere else in this repository
for that reasoning to live, and it is lost.

## Licensing upstream demo material

There is no single license to record here. Checked directly: neither Grafana
nor Immich, the two upstream projects already committed to this platform,
publishes a press kit or stated terms for reusing their screenshots.
Grafana's code license and its trademark policy are separate instruments; the
trademark policy restricts use of the Grafana marks to "open source
discussion, development and support," and a screenshot carrying the Grafana
UI carries its marks with it, so the software's own open-source license does
not settle what a reused screenshot is permitted to do. Immich's AGPLv3
covers its source, not its demo imagery. The policy this repository holds
to is therefore ADR-0001's own: checked once, per project, before reuse, not
a table of licenses fixed in advance for services not yet chosen.

## Decision

`docs/reference/` continues as the only populated quadrant today. Explanation
starts when this map closes; tutorial and how-to wait for the platform to
exist. `docs/adr/` stays outside the four quadrants as its own journal. A
how-to is written as a generalized procedure from its first draft, never a
sanitized transcript. Alternatives rejected is a required section of every
ADR, the sole record of abandoned approaches. Upstream demo material is
checked for its license and trademark terms per project, immediately before
reuse, not decided in advance here.

## Alternatives rejected

**Starting tutorial and how-to now with placeholder content**, to have all
four quadrants populated from day one. Rejected: a tutorial or how-to written
against a design that has not been built yet either teaches nothing real or
has to be rewritten once the platform exists, so the work would be done
twice for no reader who could use it in between.

**Folding the ADR log into explanation**, since both concern the reasoning
behind decisions. Rejected: explanation is prose meant to be read start to
finish and updated as understanding changes; an ADR is a dated, never-rewritten
record of one decision at the time it was made. Merging them would either
freeze explanation the way an ADR is frozen, or open ADRs to revision the way
explanation is, and this repository needs both properties, not a compromise
between them.

**Recording abandoned approaches in a separate journal.** Considered and
declined already in the prior iteration; nothing here found a reason to
reopen it. A second place to look for "what was tried and rejected" competes
with the ADR log rather than complementing it, and this repository already
has exactly one place that changes on every decision.

## Consequences

- `docs/explanation/` (or an equivalent root-level layout) is created once
  this map closes, drawing on the accepted ADRs as source material rather
  than restating this ADR's own findings, which are the map's own reasoning.
- Every future ADR is now expected to carry a substantive Alternatives
  rejected section; a thin one is a gap in this repository's only record of
  what did not work, not a stylistic choice.
- Every how-to written from here on is drafted as a procedure against
  placeholders from its first version, never lifted from a real session and
  redacted afterward.
- No upstream screenshot or demo image is reused without checking that
  specific project's license and trademark terms first; this ADR settles the
  process, not a pre-cleared list.
