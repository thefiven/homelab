# Flux GitOps UI dashboard: worth adding, and if so which one

**Date:** 2026-08-19
**Status:** complete. Covers #184 (163-01), #185 (163-02, Capacitor deep
dive), #186 (163-03, other candidates deep dive), #187 (163-04,
budget/exposure comparison) and #188 (163-05, recommendation, section 5).
**Sources:** primary only: official documentation and upstream repositories.
Every claim carries its URL inline.

---

## 1. Flux's documented UI integrations

Flux's own site publishes an ecosystem page listing every third-party
integration it recognizes, grouped by category. The **"Flux UIs / GUIs"**
section is the authoritative starting point for this investigation: it is
what fluxcd.io itself documents, independent of what was already on the
table (Capacitor):

<https://fluxcd.io/ecosystem/> (rendered from
<https://github.com/fluxcd/website/blob/main/content/en/ecosystem/index.md>)

| Project | Shape | What the ecosystem page says |
| --- | --- | --- |
| [Flux Operator Web UI](https://fluxoperator.dev/web-ui/) ([controlplaneio-fluxcd/flux-operator](https://github.com/controlplaneio-fluxcd/flux-operator)) | Standalone web dashboard, bundled with the Flux Operator | "Mission Control for GitOps - A lightweight, mobile-friendly web interface providing real-time visibility into your GitOps pipelines," with SSO (OIDC) and Kubernetes RBAC |
| [Capacitor](https://github.com/gimlet-io/capacitor) (gimlet-io) | Standalone web dashboard | "A general purpose Flux UI to debug Flux and application issues" |
| [Weave GitOps](https://github.com/weaveworks/weave-gitops) (weaveworks) | Standalone web dashboard, installed via a Flux `HelmRelease` | "Weaveworks offered a free and open source GUI for Flux under the weave-gitops project" |
| [Radar](https://github.com/skyhook-io/radar) (skyhook-io) | Standalone Kubernetes UI with a Flux workspace | "An open-source Kubernetes UI with a Flux workspace for Kustomizations and HelmReleases, source and dependency topology, managed-resource views, condition-based failure diagnosis" |
| [flux9s](https://github.com/dgunzy/flux9s) (dgunzy) | Terminal UI (k9s-style), not a web dashboard | "A K9s-inspired terminal UI for monitoring and managing Flux GitOps resources," real-time via the Kubernetes Watch API, suspend/resume/reconcile, dependency graphs |
| [Headlamp Flux plugin](https://github.com/headlamp-k8s/plugins/tree/main/flux) (headlamp-k8s) | Plugin for an existing general Kubernetes UI (Headlamp), not standalone | "Allows visualizing Flux and performing common operations like quick syncing, suspending/resuming, and others" |
| [Backstage Flux plugin](https://www.npmjs.com/package/@backstage-community/plugin-flux) (backstage-community) | Plugin for an existing developer portal (Backstage), not standalone | "Provides views of Flux CD resources available in Kubernetes clusters and allows performing actions such as source syncing and reconciliation suspending/resuming" |
| [Freelens FluxCD extension](https://github.com/freelensapp/freelens-fluxcd-extension) (freelensapp) | Extension for an existing Kubernetes IDE (Freelens), not standalone | "Visualizes Flux resources and allows performing operations on them" |
| [VS Code GitOps Tools](https://github.com/weaveworks/vscode-gitops-tools) (weaveworks) | IDE extension, not a deployed cluster service | "Provides an intuitive way to manage, troubleshoot and operate your Kubernetes environment following the GitOps operating model" |
| [Kubeapps](https://github.com/vmware-tanzu/kubeapps) (vmware-tanzu) | Standalone web app, general application catalog: Flux is one integration among several, not the subject | "An in-cluster web-based application that enables users with a one-time installation to deploy, manage, and upgrade applications on a Kubernetes cluster" |

### 1.1 Reading this list against #163's scope

#163 wants a read/observe surface for "what did the last reconcile do,
what's out of sync, which Kustomization failed": that narrows the ten
entries above to the ones that are (a) a standalone deployable service and
(b) actually about Flux rather than a general catalog or an IDE add-on:

- **In scope as standalone Flux dashboards:** Flux Operator Web UI,
  Capacitor, Weave GitOps, Radar.
- **In scope but a different shape** (terminal, not a deployed web service,
  so a different resource/exposure question): flux9s.
- **Plugins for a host tool this repo doesn't already run** (Headlamp,
  Backstage, Freelens, VS Code): only relevant if this repo were already
  running the host, which it isn't. Carried forward as a note, not a
  frontline candidate, unless #186 finds a reason to reconsider.
- **Off-topic for this ticket:** Kubeapps, a package/application catalog
  that happens to integrate with Flux as a source, not a Flux status
  dashboard.

Weave GitOps carries a caveat worth flagging for #186: its own GitHub
repository (<https://github.com/weaveworks/weave-gitops>) now headlines
"Weave GitOps is transitioning to a community driven project": not
archived, but a governance change away from its original vendor (Weaveworks).
Release cadence and maintainer count under the new governance need checking
before it is compared on equal footing with actively maintained options.

This section only establishes the field per fluxcd.io's own documentation
(user story 2 of #163). Footprint, storage, and auth evaluation for each
candidate is done in sections 2 and 3 below (#163-02, #163-03); the
budget/exposure comparison against ADR-0002 and ADR-0011 is #163-04's job.

## 2. Capacitor (gimlet-io) deep dive

The product has been rebranded **"Capacitor Next"** since the ecosystem page
was written; the GitHub repository is unchanged
(<https://github.com/gimlet-io/capacitor>), and its own README now describes
it primarily as "a local-first Kubernetes client that uses your kubeconfig to
access your clusters... a single binary distribution - like docker or
terraform... like k9s, but in the browser"
(<https://raw.githubusercontent.com/gimlet-io/capacitor/main/README.md>).
That is a shift in primary framing from a deployed team dashboard to a
locally-run tool with an *optional* in-cluster mode, which the repo still
ships and documents in full (`self-host/` directory), and the findings below
cover that in-cluster mode, since that is the shape #163 is evaluating.

### 2.1 Memory footprint

Both shipped deployment paths (Helm chart and plain manifest) declare the
same figures for the `capacitor-next` server container:

| | Requests | Limits |
| --- | --- | --- |
| CPU | 100m | 500m |
| Memory | 128Mi | 512Mi |

Sources: Helm chart default values
(<https://github.com/gimlet-io/capacitor/blob/main/self-host/charts/capacitor-next/values.yaml>)
and the plain-manifest Deployment
(<https://github.com/gimlet-io/capacitor/blob/main/self-host/yaml/capacitor-next/deployment.yaml>).
This is a real, published figure (not an estimate), and it fits well inside
ADR-0002's 2 GiB standard slot on its own.

### 2.2 Storage/state requirements

No PersistentVolumeClaim anywhere in the chart or the plain manifests. The
Deployment mounts exactly one volume: a `registry.yaml` file (the list of
clusters Capacitor talks to) sourced from a Kubernetes `Secret`, not a
database
(<https://github.com/gimlet-io/capacitor/blob/main/self-host/yaml/capacitor-next/deployment.yaml>).
Capacitor Next is stateless against the Kubernetes API: nothing here reopens
ADR-0014's static-`local`-PV posture.

### 2.3 Auth / write-access model

The chart's `values.yaml` documents three modes via the `AUTH` environment
variable, with example configuration for each
(<https://github.com/gimlet-io/capacitor/blob/main/self-host/charts/capacitor-next/values.yaml>):

- **`noauth`**: "ClusterAdmin access without authentication. For your home
  lab, local development or testing." The shipped example wires this
  directly to a `capacitor-next-preset-clusteradmin` ServiceAccount with a
  ClusterRole granting `apiGroups: ["*"], resources: ["*"], verbs: ["*"]`
  (<https://github.com/gimlet-io/capacitor/blob/main/self-host/yaml/capacitor-next/rbac-preset-clusteradmin.yaml>)
  unauthenticated full cluster write access, by the project's own naming.
- **`oidc`**: per-user RBAC via an OIDC provider, with `AUTHORIZED_EMAILS`
  domain-scoping and configurable group-claim mapping.
- **`static`**: bcrypt-hashed local users mapped to impersonated
  ServiceAccounts via `IMPERSONATE_SA_RULES`.

Independent of the `AUTH` mode, four RBAC **presets** ship as ready-made
ClusterRoles: `readonly` (only `get`/`list`/`watch` verbs, across core,
Flux, and a long list of common CRD groups), `editor`, `clusteradmin`, and an
`impersonator` role for the impersonation mechanism itself
(<https://github.com/gimlet-io/capacitor/tree/main/self-host/yaml/capacitor-next>,
e.g.
<https://github.com/gimlet-io/capacitor/blob/main/self-host/yaml/capacitor-next/rbac-preset-readonly.yaml>).
A genuinely read-only deployment is achievable by binding a user/OIDC group
to the `readonly` preset instead of `clusteradmin`; nothing in the shipped
examples defaults to that: the documented quick-start explicitly
wires `noauth` to `clusteradmin`.

**Every self-hosted install path requires a `LICENSE_KEY`.** The Helm chart
values, the Helm chart README, and the plain-manifest README all set
`LICENSE_KEY: "message laszlo at gimlet.io"` / `"contact laszlo at
gimlet.io"` as a placeholder in every example, for every auth mode
(<https://github.com/gimlet-io/capacitor/blob/main/self-host/charts/capacitor-next/README.md>,
<https://github.com/gimlet-io/capacitor/blob/main/self-host/yaml/capacitor-next/README.md>).
The main README frames self-hosting explicitly as a gated beta: "Self-host
for your team - beta testers wanted... Reach out to laszlo at gimlet.io. We
are looking for beta testers"
(<https://raw.githubusercontent.com/gimlet-io/capacitor/main/README.md>). No
pricing or licensing terms for this key are published anywhere in the repo
or on the linked docs site (`gimlet.io/capacitor-next/`); a `gimlet.io/pricing`
page exists for the maintainer's other product (Gimlet) but returns 404 for
any Capacitor-specific terms, so **not published** is the honest answer for
cost and terms of the required license key, not an estimate.

### 2.4 Deployment shape

Three documented paths, all in the `self-host/` directory of the same repo:

- Plain Kubernetes manifests, installable directly or via a Flux
  `OCIRepository` + `Kustomization`
  (<https://github.com/gimlet-io/capacitor/blob/main/self-host/yaml/capacitor-next/README.md>).
- A Helm chart, pulled from an OCI registry
  (`oci://ghcr.io/gimlet-io/charts/capacitor-next`), installable via `helm`
  directly or via a Flux `OCIRepository` + `HelmRelease`
  (<https://github.com/gimlet-io/capacitor/blob/main/self-host/charts/capacitor-next/README.md>).

Plain manifests are available, so this repo's no-`HelmRepository`-yet
precedent (#160/#161/#162) is not a blocker either way.

### 2.5 Maintenance status

- **Not archived.** 1,177 stars, 36 open issues, Apache-2.0 license on the
  source (<https://api.github.com/repos/gimlet-io/capacitor>,
  <https://github.com/gimlet-io/capacitor/blob/main/LICENSE.md>).
- **Release cadence:** roughly biweekly to monthly from 2025-09 through
  2026-01 (nine tagged releases in that window), but the latest tag,
  `0.14.0`, published 2026-01-05, is the most recent release found as of
  this research (2026-08-19): a **more than seven-month gap**
  (<https://api.github.com/repos/gimlet-io/capacitor/releases/latest>). The
  repository's last code push was 2026-02-10, a month after that release,
  so development did not stop outright, but no new release has shipped
  since (<https://api.github.com/repos/gimlet-io/capacitor>).
- **Contributors:** 10 distinct GitHub contributors on record, with one
  (`laszlocph`, the founder) accounting for 441 of roughly 464 total
  contributions: a pronounced single-maintainer concentration
  (<https://api.github.com/repos/gimlet-io/capacitor/contributors>).

## 3. Other candidates deep dive

Same five axes as section 2, one subsection per candidate. flux9s does not
fit the same table (it is a locally-run terminal client, not an in-cluster
web service), so it gets a shorter, differently-shaped treatment per
section 1's note.

### 3.1 Flux Operator Web UI (controlplaneio-fluxcd/flux-operator)

**Memory footprint.** The Helm chart's shared `resources` block, which
applies to both the combined operator+web Deployment (the default) and the
standalone web-only Deployment (`web.serverOnly: true`), is:

| | Requests | Limits |
| --- | --- | --- |
| CPU | 100m | 2000m |
| Memory | 64Mi | 1Gi |

Source: chart default values
(<https://github.com/controlplaneio-fluxcd/charts/blob/main/charts/flux-operator/values.yaml>).
This is one figure covering the operator's reconciliation workload and the
web UI together; the chart does not publish a separate, smaller figure for
`serverOnly` mode alone, so treat 1 GiB as the ceiling to budget against
rather than an under-estimate.

**Storage/state requirements.** No PersistentVolumeClaim in the chart.
Dashboard data is built by scanning Flux custom resources live and caching
the result in memory on a periodic background refresh; pod CPU/memory usage
is likewise held in an in-memory ring buffer with a roughly 30-minute
retention window, not a database
(<https://github.com/controlplaneio-fluxcd/flux-operator/blob/main/docs/web/web-least-privilege-rbac.md>,
section "Cluster-Wide Report Building" and "Pod Metrics and Workload
Usage"). Stateless against the Kubernetes API and the in-cluster Metrics
API only.

**Auth / write-access model.** The most thoroughly documented of every
candidate researched here. Every Kubernetes API call the backend makes on a
user's behalf is impersonated as that user by default (`Impersonated`
access mode), so Kubernetes RBAC is the actual authorization boundary; a
`FineGrained` mode exists for narrower per-action verbs when running
standalone. SSO (OIDC) is documented for Dex, Keycloak, OpenShift, and
Microsoft Entra
(<https://github.com/controlplaneio-fluxcd/flux-operator/tree/main/docs/web>).
The project publishes a full transparency page naming every backend
operation that runs with elevated (non-impersonated) privilege and exactly
what data it does and does not expose to the user
(<https://github.com/controlplaneio-fluxcd/flux-operator/blob/main/docs/web/web-least-privilege-rbac.md>).
Pod log viewing is explicitly disabled when no authentication is
configured. Write actions (reconcile, suspend, resume, restart, delete pod,
run job) are each gated behind their own RBAC verb, so a read-only role is a
supported, first-class configuration, not an afterthought.

**Deployment shape.** Helm chart only, via an OCI-hosted chart
(`oci://ghcr.io/controlplaneio-fluxcd/charts/flux-operator`); the standalone
web-only install is itself expressed as a Flux `ResourceSet` that renders an
`OCIRepository` + `HelmRelease`
(<https://github.com/controlplaneio-fluxcd/flux-operator/blob/main/docs/web/web-standalone.md>).
No plain-manifest path is documented. This repo has no `HelmRepository` (or
equivalent OCI) source yet, so adopting this candidate would be the first
departure from #160/#161/#162's plain-manifest precedent.

There is a coupling cost beyond the chart format: the standalone Web UI's
own docs state "we officially support installing the Web UI only on
clusters managed by Flux Operator," and installing it on a cluster whose
Flux was bootstrapped the plain-CLI way (as ADR-0008 already did) requires
setting `installCRDs: true` to bring in Flux Operator's own CRDs as an
explicitly unsupported configuration
(<https://github.com/controlplaneio-fluxcd/flux-operator/blob/main/docs/web/web-standalone.md>).
Getting first-class support means adopting Flux Operator as the mechanism
that installs and manages Flux itself, which reopens ADR-0008, not just
"add a UI workload."

**Maintenance status.** Not archived, AGPL-3.0 licensed
(<https://github.com/controlplaneio-fluxcd/flux-operator/blob/main/LICENSE>),
741 stars, 66 open issues, last push 2026-08-17, two days before this
research (<https://api.github.com/repos/controlplaneio-fluxcd/flux-operator>).
Release cadence is roughly weekly: eight tagged releases from 2026-06-10 to
2026-08-07 (`v0.52.0` through `v0.58.0`)
(<https://api.github.com/repos/controlplaneio-fluxcd/flux-operator/releases>).
31 distinct contributors; the top two (`stefanprodan`, a long-standing Flux
core maintainer, and `matheuscscp`) account for the large majority of
commits, with a longer real contributor tail than Capacitor's
(<https://api.github.com/repos/controlplaneio-fluxcd/flux-operator/contributors>).
This is the most actively maintained of the standalone-dashboard candidates
researched.

### 3.2 Weave GitOps (weaveworks/weave-gitops)

**Governance/maintenance status checked fresh, per section 1's flag.** The
repository's own GitHub description still reads "Weave GitOps is
transitioning to a community driven project!"
(<https://api.github.com/repos/weaveworks/weave-gitops>). Checked against
the actual commit and release history rather than taken at face value:

- The last **stable** (non-release-candidate) tag is `v0.38.0`, published
  2023-12-06. The single tag published since is `v0.39.1-rc.1`
  (2026-01-25), a release candidate.
- **No commits at all** appear in the repository's commit history after
  2026-01-25 (verified by querying the GitHub API for commits since
  2026-01-26, the day after that tag, through this research's date of
  2026-08-19: zero results across the full window)
  (<https://api.github.com/repos/weaveworks/weave-gitops/commits?since=2026-01-26T00:00:00Z>).
- 162 open issues, not archived
  (<https://api.github.com/repos/weaveworks/weave-gitops>).
- 85 distinct historical contributors on record
  (<https://api.github.com/repos/weaveworks/weave-gitops/contributors>), but
  none with a commit in the last seven months per the point above.

Read plainly: the governance transition has not produced a maintained
"community driven" cadence as of this research. The project reads as
dormant, not actively transitioning.

**Memory footprint.** The chart's `values.yaml` ships **no default
resources at all** (`resources: {}`), with the standard Helm-chart
boilerplate comment recommending against setting one so the chart runs on
resource-constrained environments; a commented-out example (100m CPU /
128Mi memory limits and requests) is offered only as a suggestion, not a
shipped default
(<https://github.com/weaveworks/weave-gitops/blob/main/charts/gitops-server/values.yaml>).
**Not published** is the accurate answer for an actual figure.

**Storage/state requirements.** No persistence, volume, or database key
anywhere in the chart's `values.yaml`. Stateless against the Kubernetes API.

**Auth / write-access model.** Both authentication mechanisms the chart
supports are **off by default**: `adminUser.create: false` (no local admin
user is created) and `oidcSecret.create: false` (no OIDC secret is
provisioned) unless explicitly configured
(<https://github.com/weaveworks/weave-gitops/blob/main/charts/gitops-server/values.yaml>).
RBAC is impersonation-based, same shape as the other candidates, with
`impersonationResourceNames` and `viewSecretsResourceNames` available to
scope it. Nothing in the chart wires a safe unauthenticated read-only
default the way Capacitor's `noauth` mode or Flux Operator's RBAC presets
do; getting a working, secured install means configuring one of the two
auth mechanisms, or fronting the service with an external auth layer, as a
manual step.

**Deployment shape.** Helm chart, matching section 1's summary ("installed
via a Flux `HelmRelease`"); the chart lives in-repo at `charts/gitops-server`
(<https://github.com/weaveworks/weave-gitops/tree/main/charts/gitops-server>).
No plain-manifest path is documented, same `HelmRepository` gap as the Flux
Operator Web UI.

### 3.3 Radar (skyhook-io/radar)

**Memory footprint.**

| | Requests | Limits |
| --- | --- | --- |
| CPU | 100m | 500m |
| Memory | 128Mi | 512Mi |

Source: Helm chart default values
(<https://github.com/skyhook-io/radar/blob/main/deploy/helm/radar/values.yaml>).
Same order of magnitude as Capacitor, comfortably inside the 2 GiB standard
slot.

**Storage/state requirements.** Configurable, and the chart documents the
tradeoff directly in its own comments. Default is `timeline.storage:
memory` (events live in-process, lost on pod restart, no PVC). An optional
`sqlite` mode persists an events timeline to `/data/timeline.db` on a PVC
(`persistence.enabled: false` by default; `accessMode: ReadWriteOnce`, `size:
1Gi` when turned on), with a configurable retention window and a max-size
prune threshold (default 800Mi)
(<https://github.com/skyhook-io/radar/blob/main/deploy/helm/radar/values.yaml>).
Radar is stateless against the Kubernetes API by default, and only reopens
ADR-0014's static-PV question if the operator opts into the SQLite timeline.

**Auth / write-access model.** `auth.mode: none` is the documented default
(no authentication); `proxy` (header-based, for fronting with something like
oauth2-proxy) and `oidc` modes are available
(<https://github.com/skyhook-io/radar/blob/main/deploy/helm/radar/values.yaml>).
Separately from authentication, **write capability is RBAC-gated and
off by default**: the chart's `rbac.helm` flag (default `false`) controls
whether the ClusterRole grants the `patch` verb needed to trigger Flux
Reconcile/Suspend/Resume and Argo CD Sync/Suspend/Rollback, alongside a
broader Helm-write grant; with it left `false`, Radar can only `get`/`list`/
`watch` Flux and Argo custom resources, i.e. read-only for GitOps actions by
default, confirmed directly in Radar's own GitOps documentation ("Triggering
Sync / Reconcile / Suspend / Rollback needs `patch` on the parent CRDs. The
chart enables the right verbs when `rbac.helm: true` is set")
(<https://github.com/skyhook-io/radar/blob/main/docs/gitops.md>). Combining
the two defaults: an out-of-the-box install is unauthenticated but
read-only for GitOps write actions; reaching Capacitor/Flux-Operator-style
unauthenticated write access would require deliberately setting both
`auth.mode: none` and `rbac.helm: true`, which is not the shipped default
pairing.

**Deployment shape.** Helm chart only
(<https://github.com/skyhook-io/radar/tree/main/deploy/helm/radar>); the
project also ships a local CLI/desktop binary (`kubectl radar`, Homebrew,
Krew) as an alternative to the in-cluster deployment, not a substitute for
it. No plain-manifest path found in the repository. Same `HelmRepository`
gap as the two candidates above.

**Maintenance status.** Not archived, Apache-2.0, 2,997 stars, 63 open
issues (<https://api.github.com/repos/skyhook-io/radar>). This is by far the
**youngest** candidate in this research: the repository was created
2026-01-20, seven months before this research. Release cadence is the
fastest of anything researched here: `v1.10.0` published 2026-08-12, one
week before this research, with releases roughly every few days to two
weeks going back through `v1.8.6` (2026-07-24)
(<https://api.github.com/repos/skyhook-io/radar/releases>). 37 distinct
contributors, with one (`nadaverell`) dominant at 910 of roughly 1,100 total
contributions, a similar concentration to Capacitor's, but with a real
double-digit-contribution second and third contributor
(<https://api.github.com/repos/skyhook-io/radar/contributors>). Young
project, high velocity: the flip side of the fast cadence is the shortest
track record of any candidate here.

### 3.4 flux9s (dgunzy/flux9s): a different shape

flux9s is a terminal UI, run from an operator's own machine against their
kubeconfig, the same way `k9s` or the `flux` CLI itself is run. It is never
deployed into the cluster, so most of the standalone-dashboard axes above
do not apply to it the way section 1 already flagged:

- **Memory footprint / deployment shape**: not applicable in the same
  sense: there is no in-cluster Deployment, no chart, no manifest, and
  therefore nothing to weigh against ADR-0002's 2 GiB standard slot. The
  tool's own resource use is on the operator's laptop, not the cluster.
  Install is via Homebrew, a downloaded binary, or `cargo install`/`cargo
  binstall`
  (<https://raw.githubusercontent.com/dgunzy/flux9s/main/README.md>). No
  CPU/memory figures are published for the binary itself.
- **Storage/state requirements**: none against the cluster; state is
  whatever `kubectl`/kubeconfig context is already configured locally.
- **Auth / write-access model**: flux9s "launches in readonly mode by
  default" and is described as RBAC-aware, showing a restricted note on a
  403 from the Kubernetes API rather than exposing a write action the
  user's own credentials don't already have. Write actions (suspend,
  resume, reconcile, delete) are available but must be explicitly turned on
  by the operator with `flux9s config set readOnly false`
  (<https://raw.githubusercontent.com/dgunzy/flux9s/main/README.md>). Since
  it runs with the operator's own kubeconfig, its effective permissions are
  whatever that kubeconfig already grants: it adds no new exposure surface
  of its own, unlike an in-cluster service with its own ServiceAccount.
- **Exposure**: not applicable. Nothing is reachable over the network;
  there is no ADR-0011 question to answer for it.

**Maintenance status.** Not archived, Apache-2.0, 243 stars, only 2 open
issues (<https://api.github.com/repos/dgunzy/flux9s>). Young project
(created 2025-11-10, roughly nine months before this research) with a fast,
current release cadence: `v1.0.3` published 2026-08-18, one day before this
research, with four releases (`v1.0.0` through `v1.0.3`) in the preceding
month (<https://api.github.com/repos/dgunzy/flux9s/releases>). Effectively a
single maintainer: `dgunzy` accounts for 121 of the human commits against
one outside contributor with a single commit
(<https://api.github.com/repos/dgunzy/flux9s/contributors>).

### 3.5 Candidates ruled out in section 1: no reason found to reconsider

Headlamp's Flux plugin, the Backstage Flux plugin, the Freelens FluxCD
extension, and the VS Code GitOps Tools extension were all carried forward
in section 1 as "only relevant if this repo were already running the host"
rather than frontline candidates. Nothing found in this pass changes that:
none of the deep-dive research above turned up a reason this repo would
adopt Headlamp, Backstage, Freelens, or VS Code as a *new* host tool purely
to gain its Flux plugin, when every standalone candidate researched in
sections 2 and 3 already covers the same ground without that dependency.
Kubeapps remains off-topic for the same reason section 1 gave: it is an
application catalog that happens to integrate with Flux as a source, not a
Flux status dashboard, and nothing here reopens that framing. Scope stays as
section 1 set it.

## 4. Budget and exposure comparison

This section checks two questions against the four in-cluster candidates
from sections 2 and 3 (Capacitor Next, Flux Operator Web UI, Weave GitOps,
Radar): does a free slot cover the figure (ADR-0002), and where does the
resulting service sit under ADR-0011's exposure default. flux9s is carried
in the tables for completeness, but section 3.4 already settled that neither
question applies to it: it never runs in the cluster, so there is nothing to
charge against a slot and no ADR-0011 exposure question to ask. No candidate
is picked here; that is #188's job (163-05).

### 4.1 Memory footprint against the 2 GiB standard slot

ADR-0002 sizes its **standard slot** at 2 GiB (1 GiB application, 768 MiB
database, 256 MiB margin) and reserves **three free standard slots (6 GiB)**
as the platform's stated growth capacity: the unit "does a free slot cover
this" is checked against.

| Candidate | Requests / limits | Fits a standard slot? |
| --- | --- | --- |
| Capacitor Next | 128Mi / 512Mi (§2.1) | Yes, at its limit a quarter of the slot |
| Radar | 128Mi / 512Mi (§3.3) | Yes, same margin as Capacitor |
| Flux Operator Web UI | 64Mi / 1Gi (§3.1) | Yes, but at its limit it alone consumes half the slot, and the figure covers the combined operator+web pod, not a web-only number: "fits" is as far as this goes |
| Weave GitOps | not published; chart ships `resources: {}` (§3.2) | Cannot be checked: there is no figure to compare against the slot |
| flux9s | not applicable, runs on the operator's machine, never deployed to the cluster (§3.4) | Nothing to charge against the slot |

Every candidate that publishes a figure fits comfortably inside one free
standard slot on its own, with Flux Operator Web UI the tightest fit of the
three and the only one where the number covers more than the dashboard
itself. Weave GitOps is the one candidate this question cannot be answered
for: absence of a published limit is not the same finding as "it fits."

### 4.2 Storage/state against ADR-0014's static-PV posture

| Candidate | State | Reopens ADR-0014? |
| --- | --- | --- |
| Capacitor Next | stateless: one Secret-sourced config file (§2.2) | No |
| Flux Operator Web UI | stateless: in-memory cache + ring buffer (§3.1) | No |
| Weave GitOps | stateless: no persistence key anywhere in the chart (§3.2) | No |
| Radar | stateless by default; an opt-in `sqlite` mode adds a 1Gi PVC (§3.3) | Only if the operator turns on `timeline.storage: sqlite`, the shipped default does not |
| flux9s | no cluster-side state at all (§3.4) | Not applicable |

None of the four in-cluster candidates reopen ADR-0014 at their default
settings.

### 4.3 Exposure under ADR-0011

ADR-0011's default is explicit: "Any future, not-yet-known service defaults
to **private** until a ticket argues it out." The two exceptions it names
(the showcase web stacks) go public through the Cloudflare tunnel because
they are outward-facing by design; Immich stays private-only on CVE-surface,
proxy-limit, and ToS grounds specific to media serving. None of the four
in-cluster Flux dashboard candidates matches either shape: each is an
operator-facing status/administration surface over the cluster API, the same
category Immich's Tailscale-only precedent already covers for a different
reason, and #163's own problem statement ("what did the last reconcile do")
is an operator question, not a family-facing one. No ticket has argued a
public case for any of them, so ADR-0011's default, private, applies
regardless of which candidate #188 picks. flux9s stays out of this
subsection entirely: section 3.4 already established it has no network
exposure surface to place behind Tailscale or a tunnel in the first place.

That default gets a second, independent reason for the candidates whose
authentication is off or absent out of the box:

- **Capacitor Next**'s documented quick-start wires `noauth` straight to a
  ClusterRole granting `apiGroups: ["*"], resources: ["*"], verbs: ["*"]`
  (§2.3): exposing that beyond Tailscale would publish unauthenticated
  cluster-admin.
- **Weave GitOps** ships with both its auth mechanisms (`adminUser`,
  `oidcSecret`) off by default (§3.2).
- **Radar**'s default (`auth.mode: none`) is unauthenticated, though
  read-only for GitOps actions unless `rbac.helm: true` is also set (§3.3):
  a smaller write risk than Capacitor's, but still not a stated exception to
  the private default.
- **Flux Operator Web UI** is the one candidate with a documented SSO story
  and per-action RBAC gating by default (§3.1), the strongest auth posture
  of the four. ADR-0011's default is not conditional on auth quality ("stays
  private until a ticket argues it out"), so this does not change the
  recommendation, only how costly a mistake would be if the default were
  skipped.

**Recommendation: whichever in-cluster candidate #188 selects should be
deployed private-only over Tailscale, matching Immich's posture, never
through the Cloudflare tunnel.** This follows from ADR-0011's default
alone, holds for all four in-cluster candidates identically, and does not
need to be re-argued per candidate in #188. If #188 instead selects flux9s,
this recommendation does not apply: there is nothing to expose.

## 5. Recommendation

**Adopt flux9s (§3.4) as a local tool. Deploy no in-cluster dashboard.**

#163's problem statement is "no visual surface... short of reading CLI
output" for an operator already running `flux`/`kubectl` from their own
machine against the cluster's kubeconfig. flux9s answers exactly that: a
real-time, k9s-style view over Flux's `Kustomization`/`HelmRelease`
reconcile state, dependency graphs, and suspend/resume/reconcile actions,
launched read-only by default (§3.4). It clears every axis #163 asked about
by not needing to answer them: no Deployment means no figure to weigh
against ADR-0002's standard slot (§4.1), no cluster-side state means no
ADR-0014 question (§4.2), and nothing listens on the network means no
ADR-0011 exposure decision (§4.3): no ticket, no Tailscale entry, no
tunnel. It runs on the operator's own credentials, so it adds no new
ServiceAccount or RBAC surface beyond what `kubectl` already has today. It
is not currently installed on the machine that manages this cluster; that
install is the one action item this ticket produces, and it is a `cargo
install`/`brew`/binary step, not a change to `workloads/`.

None of the four in-cluster web dashboards clears the bar of "worth
deploying now":

- **Capacitor Next** is ruled out by a fact this research surfaced that
  wasn't visible when #163 named it as the starting candidate: self-hosting
  now requires a `LICENSE_KEY` gated behind contacting the founder directly,
  framed as a beta with beta testers wanted, and no pricing or terms
  published anywhere (§2.3). Its published memory figure and stateless
  design are otherwise the best in class, but running production
  infrastructure on an undocumented, vendor-gated license for a single-file
  home-lab convenience is a cost this ticket's own scope (lowest priority of
  this round, per #163's Further Notes) does not justify taking on.
- **Weave GitOps** is ruled out on currency alone: no commits since
  2026-01-25, seven months of silence at the time of this research despite
  the repository's own "transitioning to a community driven project"
  banner (§3.2), no published memory figure, and no safe unauthenticated
  default. Adopting a dormant project for a convenience feature is the wrong
  trade in either direction.
- **Radar** is the youngest in-cluster candidate (repository created seven
  months before this research, §3.3) and ships unauthenticated by default;
  it is read-only for GitOps write actions in that default (§3.3, §4.3),
  which is a real mitigation, but "unauthenticated-by-default, seven months
  old, single-maintainer-dominated" is not a combination worth taking on for
  a convenience this ticket already calls lowest priority.
- **Flux Operator Web UI** is the strongest in-cluster candidate by every
  axis measured here: the best-documented auth model of any candidate
  (per-action RBAC gating, SSO, a published transparency page naming every
  privileged operation, §3.1), the most active maintenance (weekly
  releases, 31 contributors, §3.1), and a figure that fits the standard
  slot even as an upper bound. It is not recommended *now* because taking it
  means adopting Flux Operator as the mechanism that installs and manages
  Flux itself: first-class support requires it, and the workaround is
  explicitly unsupported (§3.1), which reopens ADR-0008's plain-CLI
  bootstrap decision. That is a materially bigger change than "add a UI
  workload," and this ticket's mandate ("no decision is made here about
  deploying it," per #163's Implementation Decisions) does not extend to
  reopening a settled ADR. **This is the candidate to revisit first** if a
  later ticket decides a persistent, multi-operator, browser-accessible
  dashboard is worth the ADR-0008 reopening: its auth model and
  maintenance cadence are not in question, only the coupling cost.

**What flux9s-and-nothing-else gives up:** a persistent, browser-accessible,
multi-operator view (no value today, with a single operator already holding
SSH/kubeconfig access); push-style always-on visibility versus an on-demand
terminal session; and a mobile-friendly surface, which only Flux Operator
Web UI documents at all (§1). None of these are gaps #163's problem
statement named. **What it keeps:** the entire budget, storage, and
exposure questions sections 4.1-4.3 spent real research effort answering
stay moot, because there is nothing deployed to answer them about.

**Revisit if:** a second regular operator needs cluster visibility without
their own kubeconfig, or the need shifts from "what failed" to "show this on
a shared/mobile screen." At that point Flux Operator Web UI is the
candidate to re-open, priced against reopening ADR-0008.
