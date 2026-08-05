---
status: accepted
date: 2026-08-05
tags: [repository, documentation, security, privacy]
supersedes: >
  ADR-0008 "Dépôt privé, documentation publiée par pipeline" of the previous,
  single-machine iteration of this project. That repository was scheduled for
  deletion on 2026-08-05 and survives only as a local bare mirror; the ADR it
  contains is not reachable from this repository.
---

# What this public repository may contain

This repository is public, and the work it records is meant to be presented as
well as operated. The previous iteration of this project decided the opposite: a
private repository that published its documentation through CI. It did so while
explicitly acknowledging that a fully public repository is the most credible
showcase of a skill, and rejected it anyway, because publishing the detailed map
of an installation reachable from the internet is irreversible and a mistaken
commit cannot be recalled.

That call is reversed. The showcase is now the point. The cost the earlier
decision named has not gone away — it has simply moved from being avoided to
being managed, and this document is the management.

## Why "is it a secret?" does not sort anything

The obvious criterion fails in both directions, and it fails on real files.

The previous repository held an inventory of secrets that contained **no values
whatsoever** — only what must exist, where it is stored, and which service
consumes it. In a private repository that is good hygiene. Published, the same
file becomes a shopping list: it enumerates every service, the shape of each
authentication mechanism, and where key material lives. Not one line of it would
trip a credential scanner. It is nonetheless the single most useful document in
the repository for someone looking for a way in.

In the other direction, that repository's SOPS configuration carried an `age`
public key in plain text. It looks alarming and is entirely publishable: being
known is what a public key is for.

A criterion that misclassifies both of these is not a criterion.

## Threat model

Two adversaries, deliberately named, because the rule is derived from them:

**A human who is targeting this installation.** Someone who found the repository
— through the showcase, or because they want in. They read the prose, understand
the architecture, and look for the weak point. This is the only adversary against
whom documentation itself is a weapon.

**Ordinary exposure of the family's privacy.** First names, faces, the existence
of a family photo library, a deducible location. The asset is different and so is
the failure: the risk here is not intrusion but routine publication — a
screenshot, an example user, a name in a manifest.

Two adversaries are explicitly **not** in scope. Opportunistic automation — the
bots that trawl public repositories for tokens — is already handled by secret
scanning, push protection and a pre-commit credential scanner, and adds no
drafting rule because it does not read prose. And the professional reader is not
an adversary at all; that audience is the reason the repository is public, and it
argues for publishing more, not less.

## Decision

**The rule is to break the link, not to hide facts.**

Everything that explains **how the platform is built and why** is published
without reservation: architecture, component choices, versions, tunings,
measurements, the reasoning behind every decision, and the approaches that failed.
This is the substance of the showcase and withholding it would leave a repository
that demonstrates nothing.

Nothing that **designates this particular installation** is ever published:

- domain names and hostnames
- IP addresses, address plans, subnets, port mappings
- hardware identifiers — serial numbers, MAC addresses, disk identifiers
- given names, faces, personal e-mail addresses, user accounts of family members
- anything from which the physical location can be deduced

The test applies to a single commit and is binary: *does this line tell a reader
which installation is being described, or how to reach it?* If yes, it does not
ship. The result is a repository that describes a **reproducible platform**, not a
**reachable machine**.

Note what this does not claim. A domain name is not secret — Certificate
Transparency publishes every hostname for which a publicly trusted certificate is
issued, and public DNS is public. Keeping the domain out of the repository does
not conceal it. What it buys is that a reader of this repository does not
automatically know which of millions of installations it describes. The real
mitigation against hostname enumeration is a wildcard certificate, and that
belongs to the exposure decision, not here.

### How the rule is enforced

**By a placeholder convention, and by nothing else.** The repository writes only
reserved, canonical designators — `example.com` and friends from RFC 2606,
`192.0.2.0/24` from RFC 5737, generic node names. Real values exist only in
encrypted secrets and on the host itself. Because the real designators are never
written, there is nothing to detect.

A deny-list of the real values in a pre-commit scanner was considered and
rejected on a specific ground: scanner rules are regular expressions, and a
regular expression that matches a domain contains that domain. In a public
repository the rule file publishes exactly what it claims to protect. Keeping it
outside the repository works, but it is then unversioned, unshared, and drifts
silently the day the workstation changes.

### Images

**Third-party software is illustrated with upstream material** — the projects
publish their own public demos and press images. Their licensing is to be checked
once, before reuse. Standing up a local demo instance to produce screenshots was
rejected: it spends the scarcest resource on this platform to reproduce something
upstream already provides.

**The platform's own state is never screenshotted.** No dashboards, no cluster
views, no reconciliation status. Those are precisely the images that carry
designators — series labels hold hostnames and volume names, a terminal holds
paths, a browser tab holds a URL — and no tool inspects a PNG. The platform is
illustrated with diagrams written as text, in Mermaid or hand-authored SVG.

## Consequences

Nothing mechanical enforces this. A credential scanner catches a credential; it
does not catch a designator. The rule lives in this document and in the attention
of whoever commits. The two measures that would have reduced that exposure — an
out-of-repository deny-list, and a blanket ban on raster images — were both
weighed and declined, so this is an accepted residual risk rather than a gap to
be closed later.

The history of a public repository is irreversible in practice. Once a commit has
been cloned, forked or archived by a third party, it cannot be recalled; rewriting
history after the fact fixes the repository and not its copies. The rule is
therefore prospective: it holds at commit time or it does not hold.

The showcase loses its evidence that the platform actually runs. Text diagrams
describe a design; they do not demonstrate a working system. That is the price of
the decision on images, and it is real. It is partly offset by diagrams being
versioned, diffable and reviewable — on a repository where the architecture keeps
changing, a stale image misleads for longer than stale text.

Documentation gains a constraint it must carry from the first page: every
Diátaxis quadrant is written against placeholders. A how-to that cannot name the
host it operates on has to be written as a procedure rather than as a
transcript — which is better technical writing, and more work.

Two consequences land on decisions still open, and are recorded on their tickets
rather than here: the exposure decision inherits the wildcard-certificate
mitigation, and the secrets decision inherits the question of whether a secrets
inventory can exist in this repository at all, and in what form.

## Alternatives rejected

**Keeping the repository private and publishing documentation through CI**, as
the previous iteration decided. It is the safer arrangement and it was rejected
on its own terms: the showcase is now an objective of the project rather than a
side effect, and a private repository publishing selected pages does not
demonstrate the work — it demonstrates a website. The cost of the reversal is
accepted explicitly above rather than hidden.

**Withholding the architecture as well as the designators.** Safer against a
targeted reader, and it guts the deliverable: explaining *why* requires stating
*what*, so a repository that hides its structure cannot carry an explanation
quadrant at all. It would trade the entire purpose of publishing for a marginal
increase in an attacker's effort.

**Publishing everything except live credentials**, on the principle that
obscurity is not security and an architecture that only holds while unknown does
not hold. Intellectually clean, and rejected because it answers only one of the
two threats: family privacy is not a security property but a matter of consent,
and no amount of defence in depth makes publishing a child's face acceptable.

**Screenshots of the real instance with manual redaction.** Cheapest in
infrastructure and the most fragile in practice: it rests entirely on attention,
applied to the one artifact nothing reviews, and a missed redaction is permanent
because the history keeps the original image after the correction.

**Synthetic data on the real instance** to make screenshots safe. It manufactures
evidence that is not evidence, and it requires maintaining a fake dataset
alongside the real one — recurring work for an illustration.
