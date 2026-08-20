---
status: accepted
date: 2026-08-20
tags: [access, gitops, networking, security]
---

# Admin workstation access without routine SSH: scoped kubeconfig, flux9s/k9s/flux, Tailscale enrollment

#244 asked what the admin workstation needs so that observing and operating the cluster stops
depending on SSH to node1 for anything but provisioning and low-level host debugging. The
workstation is the operator's single daily-use machine, bureautique and admin at once, not a
dedicated box: every choice below is weighed against what a compromised daily driver would expose,
the same constraint ADR-0009 already accepted for the SOPS "daily" age identity kept on it as a
plain local file. #163 had already settled the visualization tool itself
(`docs/reference/research-flux-ui-dashboard.md`): **flux9s**, run locally against the operator's
own kubeconfig, no in-cluster dashboard. This ADR is the access architecture #163 didn't cover:
what credential flux9s and its neighbours actually run against, how that credential is minted and
kept current, whether the workstation joins the tailnet ADR-0011 opened only on the node side, and
what SSH is deliberately kept for versus given up.

## Credential: a scoped kubeconfig, not node1's cluster-admin one

`/etc/rancher/k3s/k3s.yaml` on node1 carries cluster-admin. Copying it to a daily-use machine as-is
would mean a phished browser extension or a compromised office document is one file read away from
full cluster control, the same asymmetry ADR-0009 flagged and accepted only because the age identity
it protects is narrower than cluster-admin. A dedicated ServiceAccount with its own kubeconfig keeps
that asymmetry from getting worse as more tools move onto the workstation.

## RBAC shape: read everywhere, write only to Flux's own state

The ServiceAccount gets `get`/`list`/`watch` cluster-wide, the range flux9s, k9s, and Grafana-adjacent
debugging all need to be useful. Write is narrowed to `patch` on Flux's own CRDs
(`GitRepository`, `Kustomization`, `HelmRelease`, in `flux-system`), the exact verb `flux
reconcile`/`suspend`/`resume` operate through, since Flux implements those as annotation patches, not
a separate API. No `pods/exec`, no `pods/log`, no `delete` on workload-namespace resources: that
range of debugging (killing a stuck pod, shelling into a container) stays on the SSH path below,
deliberately, rather than duplicating it on a machine that also opens email. This is narrower than
Capacitor's or Radar's shipped presets, which either default to a `noauth`-wired ClusterRole granting
`*`/`*`/`*` or make full read/write a single flag away (`docs/reference/research-flux-ui-dashboard.md`,
§2.3, §3.3); neither of those tools is in play here, but the same permissiveness would be just as
wrong wired to a ServiceAccount instead.

## Minting: a new Ansible role, following `gitops`'s own pattern

The `gitops` role already does the shape this credential needs: gated on `k3s_role == 'server'`, runs
`k3s kubectl` over the existing SSH session (no local `kubectl` needed on node1), and uses
`delegate_to: localhost` to read and write files that belong to the control node, never to node1
(`ansible/roles/gitops/tasks/main.yml`). A new role reuses that idiom: create or update the
ServiceAccount, ClusterRole, and ClusterRoleBinding idempotently, mint a token, and write a kubeconfig
file to the workstation, `become: false` under `delegate_to: localhost` the same way the daily age
identity is read. A `--tags verify` check proves the ServiceAccount and binding exist, the same
category of invariant `gitops`'s own verify tags already prove for `sops-age` and Flux's controllers.
A manual one-off `kubectl create serviceaccount` was rejected: it is not reproducible on a node
reinstall (ADR-0013's provisioning story already assumes Ansible replays cleanly), and it is exactly
the kind of hand-typed state ADR-0013 moved everything else away from.

## Tailscale: the workstation joins the tailnet

ADR-0011 picked Tailscale for private access and enrolled node1, but never the workstation: today it
reaches node1 over plain LAN, which only works at home. Installing the Tailscale client on the
workstation closes that gap with no new decision, it is the same mechanism ADR-0011 already argued
for, applied to the other end of the same connection. This also means the new kubeconfig's server URL
points at node1's tailnet address, not its LAN IP, so kubectl/flux9s/k9s keep working away from home
the same way SSH already does today over LAN only.

## Tooling: flux9s, k9s, and the `flux` CLI

flux9s (#163) reads Flux's reconciliation state; it says nothing about the workload it manages. Three
components run today with their own bundled add-ons, outside Flux entirely
(`docs/reference/platform-state.md`, "Known gap: three components outside GitOps"), and any pod-level
symptom is invisible to a tool that only watches Flux CRDs. **k9s** is added for exactly that gap: a
generic Kubernetes TUI over the same read-heavy RBAC scope above, covering pods, logs, and general
cluster state that flux9s never claimed to. The **`flux` CLI** is added alongside flux9s so a stuck
reconciliation can be forced (`flux reconcile`) or paused (`flux suspend`/`resume`) without waiting on
Git polling, both patch operations the RBAC scope above already grants; flux9s exposes the same
actions from its TUI once write mode is turned on
(`docs/reference/research-flux-ui-dashboard.md`, §3.4), so the CLI is redundant with flux9s for that
one purpose and kept anyway for scripting and for the cases flux9s's TUI doesn't cover.

## What SSH keeps, and what it gives up

SSH stays for **`ansible-playbook`** (provisioning and `--tags verify`, SSH being Ansible's own
transport, ADR-0013) and for **exceptional low-level host debugging**: ZFS pool state, disk and kernel
issues, anything below the Kubernetes API that the RBAC scope above was deliberately not extended to
cover. It gives up **routine status checking and workload debugging**: what used to mean SSH plus
`k3s kubectl` on the node now means flux9s, k9s, or `flux` from the workstation, against the scoped
kubeconfig, over the tailnet. Application deployment never needed SSH in the first place; Flux has
been pulling from Git since ADR-0008.

## Grafana and VictoriaLogs in the meantime: `kubectl port-forward`

#162 (Traefik ACME wildcard cert, Cloudflare Tunnel) hasn't shipped, so Grafana and VictoriaLogs
(ADR-0004) have no external exposure yet. The scoped kubeconfig this ADR mints already grants the
`get` on Services and Pods that `kubectl port-forward` needs, so an operator can reach either
dashboard from the workstation today without waiting on #162 and without opening a second SSH tunnel
by hand. This is a stated use of the credential this ADR already creates, not a new mechanism, and it
stops mattering once #162 lands.

## No additional credential isolation

Beyond the file permissions already in place (0600, the same as the existing age identity and SSH
key), nothing further is added: no passphrase, no `ssh-agent` timeout, no separate OS user or VM for
admin tooling. The existing SSH key and age identity on this same workstation carry none of that
protection today; adding it only to the new kubeconfig would be an inconsistency with no real gain,
not a meaningful hardening of the machine as a whole. Revisit as a single pass across every credential
on the workstation if that hardening is ever wanted, not piecemeal per new file.

## Decision

A new Ansible role mints a scoped kubeconfig (cluster-wide read, `patch` on Flux CRDs only) via a
dedicated ServiceAccount/ClusterRole/ClusterRoleBinding, following the `gitops` role's
`delegate_to: localhost` idempotent pattern, with a `--tags verify` check. The workstation joins the
tailnet (ADR-0011's other half) and the kubeconfig points at node1's tailnet address. flux9s, k9s, and
the `flux` CLI are installed on the workstation manually, the same precedent as the daily age identity
(ADR-0009), no Ansible scope extension to the workstation itself. SSH keeps `ansible-playbook`
provisioning/verify and exceptional low-level host debugging; everything else routine (Flux status,
workload debugging, dashboard access via `kubectl port-forward` until #162 ships) moves to the scoped
kubeconfig. No additional credential isolation is added beyond the existing 0600 convention. The
install steps are documented as a `docs/how-to/` guide; the Ansible role and its RBAC manifests are
separate implementation tickets against this ADR.

## Alternatives rejected

**Copy node1's cluster-admin `k3s.yaml` to the workstation as-is.** The simplest path and rejected
first: cluster-admin on a machine that also opens email and browses the web is a bigger blast radius
than this ADR is willing to accept, the same reasoning ADR-0009 already applied to the age identity.

**A manual one-off `kubectl create serviceaccount` instead of an Ansible role.** Faster to type once,
but not reproducible on a node reinstall and exactly the hand-typed state ADR-0013 already moved every
other piece of provisioning away from.

**Grant `pods/exec`, `pods/log`, and `delete` on workload namespaces (k9s's full debug capability)
from the workstation.** Rejected because it would duplicate the SSH path this ADR just decided to keep
for exactly that class of action, on the machine this ADR is trying to keep a narrower footprint on.

**Deploy an in-cluster Flux dashboard instead of (or alongside) flux9s.** Already closed by #163: every
in-cluster candidate either needs a gated license, is dormant, ships unauthenticated by default, or
reopens ADR-0008 to get first-class support (`docs/reference/research-flux-ui-dashboard.md`, §5). Not
re-litigated here.

**Manage the workstation itself via Ansible** (installing kubectl/flux/k9s/flux9s/Tailscale through a
localhost play). Rejected as a scope extension nothing here demands: the inventory manages node1 only,
and the age identity precedent already establishes that workstation-side setup is a manual, documented
gesture, not an Ansible-managed one.

**Add passphrase/agent-timeout protection to the new kubeconfig specifically.** Rejected for
inconsistency: the SSH key and age identity already on this workstation carry neither, so protecting
only the newest file gives a false sense of hardening without changing the machine's actual exposure.

## Consequences

- **The new Ansible role and its RBAC manifests are not written here.** Per the established pattern
  (ADR-0009, ADR-0011), this ADR settles the mechanism and scope; the role itself is a
  `type/implementation` ticket against this decision.
- **The `docs/how-to/` guide for workstation tool installation is not written here either**, same
  deferral, tracked as its own ticket.
- **The scoped kubeconfig's write access is narrower than what flux9s and k9s are technically capable
  of.** flux9s's own write mode and k9s's exec/delete actions will surface as unauthorized against this
  RBAC scope; that is deliberate, not a bug to fix by widening the role.
- **Reaching node1 outside the tailnet (e.g., before Tailscale is installed, or if it's ever removed)
  falls back to nothing**: the kubeconfig's server URL is the tailnet address, so cluster access from
  the workstation depends on Tailscale staying up, the same dependency ADR-0011 already accepted for
  Immich.
- **#162 shipping makes the `kubectl port-forward` interim for Grafana/VictoriaLogs unnecessary**, not
  wrong; nothing here needs revisiting when it lands.
- **Low-level host debugging (ZFS, disk, kernel) keeps its SSH dependency permanently.** This ADR does
  not attempt to close that gap; it was never in scope for a Kubernetes-scoped credential to cover.
