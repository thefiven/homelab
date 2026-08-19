# Flux GitOps UI dashboard: worth adding, and if so which one

**Date:** 2026-08-19
**Status:** research note, in progress: this pass covers #184 (163-01) only.
Sections 2 onward (candidate deep dives, budget/exposure comparison,
recommendation) land in follow-on tickets #185-#188.
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
| [Flux Operator Web UI](https://fluxoperator.dev/web-ui/) ([controlplaneio-fluxcd/flux-operator](https://github.com/controlplaneio-fluxcd/flux-operator)) | Standalone web dashboard, bundled with the Flux Operator | "Mission Control for GitOps — a lightweight, mobile-friendly web interface providing real-time visibility into your GitOps pipelines," with SSO (OIDC) and Kubernetes RBAC |
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

Weave GitOps carries a caveat worth flagging for #185/#186: its own GitHub
repository (<https://github.com/weaveworks/weave-gitops>) now headlines
"Weave GitOps is transitioning to a community driven project": not
archived, but a governance change away from its original vendor (Weaveworks).
Release cadence and maintainer count under the new governance need checking
before it is compared on equal footing with actively maintained options.

This section only establishes the field per fluxcd.io's own documentation
(user story 2 of #163). Footprint, storage, auth, and exposure evaluation
for each candidate is #163-02 through #163-04's job.
