---
status: accepted
date: 2026-08-09
tags: [gitops, orchestration, secrets]
---

# Flux, not Argo CD Core, as the GitOps engine

ADR-0007 settled the family — Kubernetes-shaped, because Flux was the only
pull-based reconciler that fit the no-cluster-credential-as-a-CI-secret
constraint — and left the specific engine as an open question: Flux or Argo
CD. ADR-0002's 1 GiB GitOps envelope was drafted before this ticket, already
priced against Flux's own published footprint ("7 controllers at 64Mi
requested, 1Gi capped each"). This ADR checks that assumption against the
real alternative rather than letting it stand by default.

## Argo CD Core is the fair comparison, not full Argo CD

Full Argo CD ships a UI, an API server and Dex for SSO. None of that has a
buyer here: the platform has one operator, no multi-tenant RBAC need, and
ADR-0001 forbids screenshotting the platform's own state — the one thing a
UI would otherwise be worth having on a public repo, and the same argument
that already sank Collabora and ONLYOFFICE as "showcase" material in #36. Argo
CD's own [Core install](https://argo-cd.readthedocs.io/en/stable/operator-manual/core/)
is the headless mode built for exactly this: no server, no Dex, GitOps
functionality intact through the `Application`/`ApplicationSet` CRDs.

## Neither ships with a footprint that fits, but only one is patchable in public

Flux's official `install.yaml` (v2.9.4) sets every controller's container to
`requests: 64-100Mi/50-100m CPU`, `limits: 1Gi/1000m CPU`. Six controllers
ship by default (source, kustomize, helm, notification, image-reflector,
image-automation), so the worst case is well above the 1 GiB envelope — but
Flux publishes an official
[vertical-scaling guide](https://fluxcd.io/flux/installation/configuration/vertical-scaling/)
for patching those defaults down, which is the documented, supported path to
make the envelope true.

Argo CD Core's own `core-install.yaml` sets **no resource requests or
limits on any container** — `application-controller`, `repo-server`,
`redis`, `applicationset-controller` all ship unconstrained. There is no
default to patch down; sizing is 100% invented by the operator, with no
upstream figure to check it against. Under ADR-0002's rule that "a budget
whose figures cannot be traced to a source or a decision is the forecast
this document rejected," Flux's shrink-a-published-default path is the only
one of the two that stays traceable.

## Secrets: native versus bolted on

#14 already found SOPS is the only secret-management path that survives a
public repository; #26 (still open) picks the specifics, but whichever
engine is chosen inherits this requirement on day one. Flux's
kustomize-controller has
[native SOPS decryption](https://fluxcd.io/flux/guides/mozilla-sops/) — age,
GPG, or KMS, configured on the `Kustomization` resource. Argo CD has no
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

**Flux**, installing only the four core controllers — source, kustomize,
helm, notification. The image-reflector and image-automation controllers are
left uninstalled: tag bumps stay a human-reviewed pull request (Renovate- or
Dependabot-style), not an in-cluster process writing back to Git. That keeps
Git's write side to the operator alone and drops two more 1Gi-capped
controllers from the footprint that would otherwise need shrinking.

## Alternatives rejected

**Argo CD Core.** Headless mode removes the UI/Dex weight full Argo CD
carries, but the comparison still favours Flux: no published default
footprint to shrink (Flux has one), no native SOPS support (Flux has it),
and no UI value to recover under ADR-0001's screenshot ban even if full Argo
CD were considered instead of Core.

**Installing Flux's image-reflector/image-automation controllers.** Native
to Flux and would have been "free" to add to the same install. Rejected
because an in-cluster controller that writes back to Git blurs "Git is the
source of truth" into "Git is also a write target," and a single operator
who already reads every merge loses nothing by keeping tag bumps a reviewed
PR instead.

## Consequences

- **The 1 GiB envelope is not met by Flux's shipped defaults and needs
  active enforcement**, per ADR-0002's own rule that a cap alone doesn't
  bound a sum. Two mechanisms are available and neither is chosen here: patch
  each controller's `limits` down via the official vertical-scaling
  mechanism, and/or set a `ResourceQuota` on the `flux-system` namespace as
  the belt-and-suspenders backstop. Left to whichever ticket actually
  installs Flux.
- **SOPS key provider (age, GPG, or KMS) is #26's job, not this ADR's.**
  This decision only established that Flux can decrypt SOPS natively,
  whatever #26 picks.
- **Bootstrap method** (`flux bootstrap github`, the one-time GitHub PAT it
  needs, the deploy key it writes back) is an operational task, not an
  architectural trade-off, and is left for a future ticket when the platform
  is actually built.
