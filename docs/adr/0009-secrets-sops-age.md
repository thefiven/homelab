---
status: accepted
date: 2026-08-09
tags: [secrets, gitops]
---

# SOPS + age for secret management, two recipients, layered pre-commit scanning

#14's research compared SOPS+age, Sealed Secrets, and External Secrets Operator
(ESO) backed by a self-hosted vault, on bootstrap cost, rotation cost, recovery
documentation, resident memory, and Kubernetes dependency
(`docs/reference/research-secrets-on-a-public-repo.md`). ADR-0007 has since
settled Kubernetes (k3s), which removes SOPS's "keeps the orchestrator open"
edge as a discriminator on its own. ADR-0008 then picked Flux specifically
citing its native SOPS decryption over Argo CD's third-party plugin
requirement, and explicitly deferred the SOPS recipient type (age, GPG, or
KMS) to this ticket. This ADR checks the mechanism against the alternatives
one more time under those settled facts, picks the recipient type, then
answers the questions the ticket named in order: bootstrap, rotation, and
recovery.

## Mechanism: SOPS + age, not Sealed Secrets or ESO

ESO's backing vault is disqualified by the budget, not by the GitOps
envelope specifically: ADR-0002 has no line item for a self-hosted vault, so
the number it competes against is the platform's flexible capacity, the
three free standard slots plus slack (6 GiB + 2.5 GiB = 8.5 GiB). HashiCorp
Vault's own reference architecture asks 8-16 GB RAM for a "small" cluster,
and Infisical asks 4 GB minimum including PostgreSQL and Redis. Vault either
does not fit at all or fits only by spending the platform's entire growth
capacity on one secrets backend; Infisical's connector in ESO is itself
rated Alpha by ESO's own provider-stability page, maintained by a single
individual, which is a statement about that connector's maintenance, not
about Infisical's own team.

Sealed Secrets fits the memory budget (roughly 60 MB, no official figure
published) but carries two standing risks: its governance is single-vendor
(three Broadcom-affiliated maintainers, not a CNCF project), and #14's
research flags its sealing-key backup, which silently goes stale every 30
days on automatic renewal, as the sharpest operational trap in the
comparison for a solo operator.

SOPS has zero resident memory cost, and since ADR-0008, decryption is native
to the already-chosen GitOps engine: Flux's kustomize-controller, no extra
pod and no third-party plugin. It is a CNCF Sandbox project, under new
stewardship since its 2023 donation from Mozilla, with a current release
(v3.13.3).

**Recipient type: age, not GPG, Vault, or cloud KMS.** SOPS supports four:
OpenPGP/GPG, age, HashiCorp Vault's transit engine, and cloud KMS (AWS,
GCP, Azure). Cloud KMS is out immediately: this platform runs on bare metal
with no cloud provider and a standing no-paid-hosting constraint. Vault as a
SOPS backend means running Vault, the same memory cost that just
disqualified it as ESO's backend above. That leaves age against GPG, and
Flux's own guide states the comparison directly: "age is a simple, modern
alternative to OpenPGP. It's recommended to use age over OpenPGP, if
possible." age's own README backs the same shape: "small explicit keys, no
config options."

## Bootstrap: one manual step, once

The documented sequence
([Flux SOPS guide](https://fluxcd.io/flux/guides/mozilla-sops/)):

```sh
age-keygen -o age.agekey
kubectl create secret generic sops-age \
  --namespace=flux-system \
  --from-file=age.agekey=/dev/stdin < age.agekey
```

Only the **daily** identity's private key goes into the cluster this way. The
recovery identity (below) is never loaded into the cluster in normal
operation; it exists solely offline, to be pulled out if the daily identity is
lost. Everything after this one step reconciles from Git. This step requires a
running k3s cluster, so its execution is out of scope for this map (Destination:
decisions, not the build) and belongs to whichever future ticket actually
installs Flux.

## Rotation: accepted cost, no calendar

Rotating the age key itself is a tree-wide operation: both `sops updatekeys`
(apply a changed recipient list) and `sops rotate` (issue a new data key) are
**per file**, so rotating means iterating every encrypted file and producing
one commit that touches all of them
([SOPS key management](https://getsops.io/docs/usage/key-management/)).
Rotating a single secret's value, by contrast, is a one-file diff.

No compliance driver applies to this platform, and #11 caps operational effort
at 4 hours/month steady-state. Given the tree-wide cost and no external forcing
function, the age key is rotated **on suspected compromise only, not on a
schedule.** A single secret's value still rotates whenever the service it
belongs to requires it, at the one-file cost.

## Recovery: two age identities, not one

Neither the age README nor the SOPS security page documents a recovery
procedure for a lost identity; this is a design position upstream takes, not
an omission. The documented mitigation is structural rather than procedural:
encrypt every secret to more than one recipient, so losing one identity alone
is survivable
([SOPS key groups](https://getsops.io/docs/usage/identities/key-groups/)).

**Two age identities.** A **daily** identity, kept as a local file on the
admin workstation and loaded into the cluster per the bootstrap step above.
A **recovery** identity, generated at the same time, whose private key is
stored as a note on a dedicated entry in Google Password Manager, kept
separate from the daily identity's storage. Every secret in the repository is
encrypted to both public keys via `.sops.yaml`'s `age` recipient list, so
losing either identity alone does not brick the repository.

Google Password Manager was checked against its own support documentation
([support.google.com](https://support.google.com/chrome/answer/95606)): it
supports a free-text note attached to a saved entry, which is sufficient for
an age private key (a single short string). Its recovery ultimately terminates
at the Google account's own recovery apparatus (2FA device, recovery
email/phone), which is accepted as a reasonable place for the chain to end,
being synced and not tied to any one local machine, rather than a further
requirement to source.

## Pre-commit scanning: two layers, plus GitHub's net

The ticket names pre-commit scanning as the real barrier, push protection only
a net. Two independent local checks, not one:

1. **A SOPS-metadata policy check.** Fails the commit if a file under the
   secrets path lacks the `sops:` block, i.e. "this path must always be
   encrypted." Custom because it enforces this repository's own path
   convention, which no off-the-shelf scanner knows about.
2. **gitleaks.** Pattern-matches likely secret material anywhere in the diff,
   catching a value pasted somewhere the path convention never anticipated.
   Chosen over detect-secrets or trufflehog on availability alone, both are
   comparable pattern scanners and none was compared on primary sources here;
   revisit if the installing ticket finds a reason to.

They catch different mistakes: (1) enforces the intended structure, (2) is the
backstop for everything that structure doesn't cover. GitHub's own secret
scanning and push protection sit behind both, as the ticket's framing intends,
not as the primary control.

**Amendment, 2026-08-15 (ADR-0016, #124):** the paragraph above described a
design that had never actually executed — no local hook was installed, and
nothing ran these two layers anywhere. ADR-0016 wires both hooks into an
installed `pre-commit` config and adds a required CI job that runs the exact
same config on every PR and push to `main`, closing that gap. The two-layer
design itself is unchanged; only its execution status moves from
aspirational to enforced.

## Encryption scope: partial, not whole-file

Flux's suggested `--encrypted-regex '^(data|stringData)$'` encrypts only a
Secret's values. SOPS's own security docs describe the general case this
relies on: "in YAML, JSON, ENV, and INI modes, keys are stored in cleartext,
and values are encrypted," and that "diffs are meaningful: if a single value
of a file is modified, only that value will show up in the diff"
([SOPS security](https://getsops.io/docs/security/)). Under Flux's narrower
regex, key names, namespaces, labels and structure all stay readable; only
the `data`/`stringData` values are ciphertext. What a hostile reader of the
public history learns under this scope is an inventory of secret *names*,
never secret *values*. Whole-file encryption was considered and rejected: it
maximises opacity at the cost of reviewable diffs, and this platform already
treats documentation and reviewable history as a deliverable, not a by-product
(map Notes; ADR-0006).

## Decision

**SOPS + age.** Two recipients per secret: a daily identity on the admin
workstation, a recovery identity whose private key lives in Google Password
Manager. Bootstrap is the one documented `kubectl create secret` for the daily
identity, executed once a cluster exists. The age key rotates on suspected
compromise only; individual secret values rotate as needed. Pre-commit is
enforced by a SOPS-metadata policy check plus gitleaks, both ahead of GitHub's
push protection. Encryption scope is partial
(`^(data|stringData)$`), keeping structure and names readable.

## Alternatives rejected

**Sealed Secrets.** No bootstrap secret to inject, and the best-documented
recovery story of the three, but single-vendor governance (Broadcom, not
CNCF) and a sealing-key backup that silently expires every 30 days, the
sharpest operational trap found in #14's research for a solo operator.

**ESO + a self-hosted vault.** The only option where no secret material ever
enters the repository, and single-secret rotation costs nothing. Rejected on
memory alone: every viable backing vault (Vault, Infisical) exceeds the
platform's entire flexible capacity (8.5 GiB), before weighing the monthly
forced-upgrade treadmill, the free-Bitwarden path that does not exist
(Vaultwarden's maintainer closed the request), or the `SecretStore` publishing
the vault's address into the public repository.

**GPG and cloud KMS as the SOPS recipient type.** Cloud KMS needs a cloud
account this platform doesn't have. Vault-backed SOPS needs Vault, already
rejected above on memory. GPG works, but Flux's own guide recommends age over
it directly, and age's smaller, option-free design matches a single
operator's key management better.

**A single age identity.** Simplest, but the backup becomes a single point of
failure with no documented recovery path if it fails. Two independent
recipients cost nothing at encryption time and are the mitigation SOPS's own
documentation points to.

**`key_groups` + Shamir threshold**, and **whole-file encryption**: both
covered in full above (Recovery, Encryption scope), rejected for the same
reason in each case, added machinery without added independence or
readability for a solo operator.

## Consequences

- **`.sops.yaml` needs both age public keys in its creation rules** before the
  first secret is ever encrypted; adding a second recipient after the fact
  requires a tree-wide `updatekeys` pass, the exact operation this ADR is
  trying to avoid doing under pressure.
- **The recovery identity's private key must never be loaded into the
  cluster** in normal operation. Doing so routinely would collapse the
  two-recipient design back into a single active identity in practice, even
  though two are still configured. Unlike pre-commit scanning, this ADR
  proposes no automated check for it; the installing ticket should consider
  one, since a rule enforced only by discipline is weakest exactly when a
  recovery event is stressful enough to need it.
- **This ADR does not choose the pre-commit tooling's exact configuration**
  (which paths the SOPS-metadata check covers, gitleaks' ruleset) or write any
  hook, per the map's standing rule against configuration before the ADR it
  derives from is accepted. Left to whichever ticket wires up the repository's
  CI.
- **Bootstrap execution is a future, out-of-scope task.** It needs a running
  k3s cluster, which does not exist yet; this ADR settles the mechanism, not
  the act.
