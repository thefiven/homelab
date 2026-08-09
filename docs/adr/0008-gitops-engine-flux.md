---
status: accepted
date: 2026-08-09
tags: [gitops, orchestration, secrets]
---

# Flux, not Argo CD Core, as the GitOps engine

ADR-0007 settled the family: Kubernetes-shaped, because Flux was the only
pull-based reconciler that fit the no-cluster-credential-as-a-CI-secret
constraint, and left the specific engine as an open question, Flux or Argo
CD. ADR-0002's 1 GiB GitOps envelope was drafted before this ticket, already
priced against a published Flux footprint ("7 controllers at 64Mi
requested, 1Gi capped each"). That figure does not match Flux's actual
default install (see below), so this ADR checks the assumption against the
real alternative, and against Flux's own current numbers, rather than
letting either stand unverified.

## Argo CD Core is the fair comparison, not full Argo CD

Full Argo CD ships a UI, an API server and Dex for SSO. None of that has a
buyer here: the platform has one operator, no multi-tenant RBAC need, and
ADR-0001 forbids screenshotting the platform's own state, which removes the
one thing a UI would otherwise be worth having on a public repo. Argo CD's
own [Core install](https://argo-cd.readthedocs.io/en/stable/operator-manual/core/)
is the headless mode built for exactly this: no server, no Dex, GitOps
functionality intact through the `Application`/`ApplicationSet` CRDs.

## Neither ships with a footprint that fits, but only one is patchable in public

Flux's `flux install`/`flux bootstrap` deploys **four controllers by
default**: source, kustomize, helm, notification
([official docs](https://fluxcd.io/flux/installation/configuration/optional-components/)).
image-reflector-controller, image-automation-controller and source-watcher
are all optional extras requiring an explicit `--components-extra` flag;
they do not install unless asked for. This corrects the "7 controllers"
figure ADR-0002 priced the envelope against: that number describes every
controller Flux can run with every extra enabled, not what a plain install
deploys.

Each of the four default controllers ships the same profile in Flux's
official `install.yaml` (v2.9.4): `requests: 64Mi memory / 50-100m CPU`,
`limits: 1Gi memory / 1000m CPU`. Four controllers at a 1Gi cap each is
still above the 1 GiB envelope in the worst case, even though the combined
*request* (256Mi) sits well under it. Flux publishes an official
[vertical-scaling guide](https://fluxcd.io/flux/installation/configuration/vertical-scaling/)
for patching those limits down, which is the documented, supported path to
make the envelope true.

Argo CD Core's own `core-install.yaml` sets **no resource requests or
limits on any container**: `application-controller`, `repo-server`,
`redis` and `applicationset-controller` all ship unconstrained. There is no
default to patch down; sizing is entirely invented by the operator, with no
upstream figure to check it against. Under ADR-0002's rule that "a budget
whose figures cannot be traced to a source or a decision is the forecast
this document rejected," Flux's shrink-a-published-default path is the only
one of the two that stays traceable.

## Secrets: native versus bolted on

#14 already found SOPS is the only secret-management path that survives a
public repository. #26 (still open) picks the specifics, but whichever
engine is chosen inherits this requirement on day one. Flux's
kustomize-controller has
[native SOPS decryption](https://fluxcd.io/flux/guides/mozilla-sops/) (age,
GPG, or KMS, configured on the `Kustomization` resource). Argo CD has no
first-party equivalent; the documented path is
[KSOPS](https://github.com/viaduct-ai/kustomize-sops), a third-party
Kustomize plugin installed as an init container on `repo-server`, with alpha
plugin support enabled by hand. That is a second maintained component for a
single operator to own, for a capability Flux has out of the box.

## Governance: no discriminator

Both are CNCF Graduated, both Apache-2.0: Flux graduated 2022-11-30
([cncf.io](https://www.cncf.io/announcements/2022/11/30/flux-graduates-from-cncf-incubator/)),
Argo (the umbrella project covering Argo CD) graduated 2022-12-06
([cncf.io](https://www.cncf.io/announcements/2022/12/06/the-cloud-native-computing-foundation-announces-argo-has-graduated/)).
Neither carries the single-vendor or breaking-change risk that ruled out
other candidates in #13 and #14.

## Decision

**Flux**, on its default install: source, kustomize, helm, notification
controllers, nothing extra enabled. The image-reflector and
image-automation controllers stay off: tag bumps remain a human-reviewed
pull request (Renovate- or Dependabot-style), not an in-cluster process
writing back to Git. That keeps Git's write side to the operator alone, and
keeps the footprint at four controllers to shrink into the envelope rather
than six.

## Alternatives rejected

**Argo CD Core.** Headless mode removes the UI/Dex weight full Argo CD
carries, but the comparison still favours Flux: no published default
footprint to shrink (Flux has one), no native SOPS support (Flux has it),
and no UI value to recover under ADR-0001's screenshot ban even if full Argo
CD were considered instead of Core.

**Installing Flux's image-reflector/image-automation controllers.**
Available as a flag on the same install, so effectively free to add.
Rejected because an in-cluster controller that writes back to Git blurs
"Git is the source of truth" into "Git is also a write target," and a
single operator who already reads every merge loses nothing by keeping tag
bumps a reviewed PR instead.

## Consequences

- **The 1 GiB envelope is not met by Flux's default limits and needs active
  enforcement**, per ADR-0002's own rule that a cap alone doesn't bound a
  sum. Two mechanisms are available and neither is chosen here: patch each
  controller's `limits` down via the official vertical-scaling mechanism,
  and/or set a `ResourceQuota` on the `flux-system` namespace as a backstop.
  Left to whichever ticket actually installs Flux.
- **ADR-0002's "7 controllers" basis for the GitOps envelope is corrected
  here to 4**, the actual default install with no extras enabled. The
  envelope figure itself is not revisited by this ADR; a future reader
  sizing that envelope should use this ADR's numbers, not ADR-0002's.
- **SOPS key provider (age, GPG, or KMS) is #26's job, not this ADR's.**
  This decision only established that Flux can decrypt SOPS natively,
  whatever #26 picks.
- **Bootstrap method** (`flux bootstrap github`, the one-time GitHub PAT it
  needs, the deploy key it writes back) is an operational task, not an
  architectural trade-off, and is left for a future ticket when the
  platform is actually built.
