---
status: accepted
date: 2026-08-15
tags: [repository, ci]
---

# CI quality gate: one required check, pre-commit and scripts/check, validator only

#122 named the gap directly: ADR-0009 documents two pre-commit layers that
are supposed to run ahead of GitHub's push protection, but neither actually
ran anywhere on this repository — `.git/hooks/` was empty, and `scripts/check`
(the one hardware-free check entry point written for #116) was invoked by
nothing. This ADR amends ADR-0009's "Pre-commit scanning" section from
aspirational to accurate, and records the mechanism that makes it so: a
single required CI check, run from the exact same configuration a
contributor runs locally.

## What blocks a merge

One job, `checks`, defined in `.github/workflows/ci.yml`, runs on every
`pull_request` and on every `push` to `main`. It runs two commands in
sequence and fails on the first non-zero exit:

1. `pre-commit run --all-files`
2. `scripts/check`

Both must pass. There is no warn-only step and no bypass actor — the ruleset
activated once this workflow first goes green on `main` (a separate,
non-diff repository-settings gesture, not part of this change) requires the
`checks` status check with zero exemptions, including for the repository
owner. A green `checks` run is the entire, non-negotiable claim "this PR
merges."

## Where each check runs

| Check | Local pre-commit hook | CI |
|---|---|---|
| `sops-metadata-policy` | yes | yes, via `pre-commit run --all-files` |
| `gitleaks` | yes | yes, via `pre-commit run --all-files` |
| `shellcheck` (`scripts/*`, not `scripts/lib/`) | yes | yes, via `pre-commit run --all-files` |
| `ansible-lint` (`ansible/`, not `clusters/`/`workloads/`) | yes | yes, via `pre-commit run --all-files` |
| `scripts/check` (hardware-free self-checks) | no | yes, its own step |
| `ansible --tags verify` (platform verify) | no | never |

`.pre-commit-config.yaml` is the single source of truth for the first four
rows: CI runs `pre-commit run --all-files` against that same file, so a hook
added, removed, or reconfigured there takes effect in both places from one
edit. There is deliberately no second, parallel declaration of any of these
tools in the workflow file — a duplicate definition is exactly the drift this
setup exists to prevent.

`gitleaks`'s upstream hook entry scans `git ... --staged`, meaningful for a
local commit hook but empty (and so vacuously green) on a plain CI
checkout, which has nothing staged. This config overrides that hook's
`entry` to `gitleaks detect --no-git`, scanning the working tree directly
instead, so a local run and a CI run see the same files. Scanning the whole
tree rather than a diff also surfaces a documented example key in
`docs/reference/research-secrets-on-a-public-repo.md` as a false positive
(an age public key, not a secret by definition — ADR-0009); it is listed in
`.gitleaksignore` by fingerprint rather than reworded, since the point was
to quote the upstream guide's own output verbatim.

`ansible-lint`'s own hook pins only `ansible-core` in its isolated venv
(upstream's `.pre-commit-hooks.yaml`), not the Galaxy collections
(`ansible.posix`, `community.general`) the roles actually call, which
its `syntax-check` rule needs to resolve every module. The workflow
installs them from `ansible/requirements.yml` to the default
`~/.ansible/collections` before `pre-commit run --all-files` — a path
ansible-lint's own collection search already includes regardless of which
venv is running it, so no override of the hook itself is needed here,
unlike gitleaks above.

`scripts/check` runs only in CI, as its own step, because it is not itself a
pre-commit hook (its self-checks are cheaper to run once per push than on
every commit) — see CONTEXT.md's "Hardware-free check" glossary entry.

Platform verify never runs in CI, for a structural reason, not an oversight:
it needs the real node, and CI has no path to it (next section).

## Why CI is a validator, never a deployer

Flux pulls from inside the network (ADR-0007's k3s orchestrator, ADR-0008's
choice of Flux specifically for its native reconciliation, ADR-0011's
Cloudflare Tunnel exposing services outward, never the reverse). No cluster
credential is issued to, or stored as, a CI secret — there is nothing for
this workflow to deploy with even if a step tried to. `checks` reads the
repository and runs tools against files already in the checkout; it has no
network path to node1 or the NAS, and `permissions: contents: read` on the
workflow keeps it that way. "CI is green" proves the tree passes its
hardware-free checks. It is never evidence that the platform verify passed
on a real node — CONTEXT.md's "Platform verify" entry states that
distinction as a standing rule, not a one-off caveat.

## Decision

One workflow, one job, two commands. `pre-commit run --all-files` reuses the
local hook's own config; `scripts/check` runs after it, in its own step,
because it isn't a hook. `permissions: contents: read`, a
`timeout-minutes`, and a `concurrency` group keyed on `github.ref` that
cancels superseded runs keep the job's privilege and runtime bounded to what
it needs. Third-party actions (`actions/checkout`, `actions/setup-python`,
`actions/cache`) are pinned to a commit SHA with the released version as a
trailing comment, so a retagged upstream action cannot silently change what
runs here; Dependabot (`.github/dependabot.yml`, `github-actions` ecosystem
only) is the mechanism that keeps those pins from going stale, with its
bump PRs merged by hand like any other change. `actions/cache`, keyed on
`.pre-commit-config.yaml`'s hash, caches the installed hook environments
(ansible-core, shellcheck, gitleaks' golang toolchain) across runs, so an
unrelated PR doesn't pay a full cold install of all four tools.

This amends ADR-0009's "Pre-commit scanning" section: the two-layer local
defense it described now actually executes, both locally (once
`pre-commit install` has been run — see `.pre-commit-config.yaml`'s header
for the venv-based install sequence this machine needs, since it has no
system `pip`) and, identically, in CI.

## Alternatives rejected

**A second, parallel job (or workflow) that re-declares shellcheck /
ansible-lint / gitleaks outside `.pre-commit-config.yaml`**, for per-tool
visibility in the Checks tab. Rejected: two definitions of the same tool
drift the moment one is edited and the other isn't, the exact failure mode
this ADR exists to close off. One job, one config, one required check name.

**`ansible --tags verify` (or any real-node check) in CI.** Rejected
structurally, not just as unnecessary: CI has no credential and no network
path to the platform, by design (previous section). A check CI cannot
actually run has no business being a required status.

**A standalone yamllint hook**, layered on top of ansible-lint's own bundled
YAML checks. Tried during this ticket's research: run against the full tree,
its only non-cosmetic findings were in Flux-generated
(`clusters/homelab/flux-system/gotk-components.yaml`) and upstream-vendored
YAML, already out of scope via `.ansible-lint`'s `exclude_paths`. A second,
differently-configured linter over the same files would find nothing
ansible-lint's own profile doesn't already cover here.

## Consequences

- Any future hook belongs in `.pre-commit-config.yaml`, never bolted onto
  the workflow directly — that is what keeps local and CI identical by
  construction rather than by discipline.
- Bumping a pinned action SHA is a Dependabot PR like any other change: read,
  checked, merged by hand.
- If a future check genuinely needs the real node (a platform verify, or
  anything that would need a cluster credential), it cannot become part of
  `checks` — CONTEXT.md's "Platform verify" entry and this ADR's "why CI is
  a validator" section both say why, and a change that wants to blur that
  line should amend this ADR explicitly rather than quietly add a CI secret.
