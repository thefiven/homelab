# Install the admin workstation toolset

**Date: 2026-08-21**

ADR-0019 moved routine cluster access off SSH and onto a scoped kubeconfig,
minted by the `admin-access`/`admin-kubeconfig` Ansible roles (#247-#249)
and consumed by three tools run locally: `kubectl`, the `flux` CLI, `k9s`,
and `flux9s`. This guide walks a workstation with none of that installed
yet to a working `~/.kube/config` and a proven `kubectl get nodes`, no SSH
involved once it's done.

## Before you start

This guide assumes the workstation already has what running
`ansible-playbook` against node1 requires: the repository cloned, the
Ansible collections from `ansible/requirements.yml` installed, an SSH key
authorized on node1, and `ansible/host_vars/node1_secrets.yml` present and
decrypting. That setup predates this guide (ADR-0013's gesture 7,
ADR-0015's designator convention) and is not repeated here: routine access
moves off SSH after this guide, but provisioning still needs it, so nothing
here removes that prerequisite.

## 1. Install Tailscale and join the tailnet

Install the Tailscale client for the workstation's OS
(<https://tailscale.com/download>), then authenticate it into the same
tailnet node1 is already enrolled in (ADR-0011):

```
sudo tailscale up
```

This opens a browser to log into the tailnet account already used for
node1. Once connected, the workstation reaches node1's Tailscale address
the same way it already reaches it over LAN at home, and continues to work
away from home. Nothing else needs configuring: the kubeconfig this guide
ends with is templated against node1's Tailscale address directly, no
manual address to note down.

## 2. Install kubectl, flux, k9s, and flux9s

Four local tools, none of them cluster-side:

- **`kubectl`**: official install instructions per OS at
  <https://kubernetes.io/docs/tasks/tools/>.
- **`flux`** (the Flux CLI): official install instructions at
  <https://fluxcd.io/flux/installation/>.
- **`k9s`**: official install instructions at
  <https://k9scli.io/topics/install/>.
- **`flux9s`**: install via Homebrew, a downloaded release binary, or
  `cargo install`/`cargo binstall`, per the project's own README at
  <https://github.com/dgunzy/flux9s>.

None of these need configuring yet: they all read `~/.kube/config` by
default once step 4 writes it, the same as any other kubectl-compatible
tool.

## 3. Run, or confirm, the roles that produce the kubeconfig

The `admin-access` role mints the cluster-side RBAC (a ServiceAccount,
ClusterRole, and ClusterRoleBinding), and `admin-kubeconfig` assembles and
delivers the kubeconfig itself, to this workstation
(`docs/reference/platform-state.md`, invariants 11-12). Confirm they've
already run, without changing anything, from the repo root (the committed
`ansible.cfg` there is what makes `-l` resolve against
`ansible/inventory.yml` instead of silently targeting nothing, ADR-0013
gesture 7):

```
ansible-playbook ansible/site.yml --tags verify -l node1 -e @ansible/host_vars/node1_secrets.yml
```

This checks every platform invariant, not just these two (`docs/reference/platform-state.md`);
invariants 10-12 are the ones this guide depends on (the k3s server
certificate covering node1's Tailscale address, the RBAC objects, and the
delivered kubeconfig). If any of the three is missing, run the same command
without `--tags verify` to apply the full playbook, `-l node1` scoping it
to node1 alone.

## 4. Locate and verify `~/.kube/config`

`admin-kubeconfig` writes the file to `~/.kube/config` on whichever machine
`ansible-playbook` was run from in step 3, mode `0600`, `current-context:
admin-access`. That machine is this workstation. Confirm it works:

```
kubectl get nodes
```

A `Ready` node1 confirms both the kubeconfig's content and that it reaches
node1 over the tailnet from step 1. `flux get all`, `k9s`, and `flux9s`
all read the same file with no separate setup.

## What SSH still covers, and what it doesn't anymore

SSH to node1 stays necessary for `ansible-playbook` itself (provisioning
and `--tags verify`, SSH being Ansible's own transport) and for
exceptional low-level host debugging below the Kubernetes API: ZFS pool
state, disk and kernel issues. It stops being how routine status checks and
workload debugging happen: what used to mean SSH plus `k3s kubectl` on
node1 now means `flux9s`, `k9s`, or `flux` from this workstation, against
the kubeconfig this guide just delivered.
