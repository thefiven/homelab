---
status: accepted
date: 2026-08-07
tags: [substrate, os, gpu]
---

# Bare metal, mutable OS, no hypervisor

The foundation question was framed as three options: bare metal, Proxmox VE, or
an immutable OS. Each layer has to pay its rent, and the two facts that used to
force a hypervisor onto this host no longer apply: GPU passthrough to a
dedicated VM is off the table (the card is shared across containers), and
gaming is gone for good (#28). Neither of the traditional motives for Proxmox on
this box survives.

## No hypervisor

Nothing on this platform's service set needs an OS-level boundary. The
standing constraint names one physical machine and forbids claiming high
availability, so a hypervisor cannot buy resilience here, only rollback. That
rollback is already covered without the extra layer: a snapshot-capable root
filesystem gives the same system-level undo a Proxmox snapshot would, at zero
additional attack surface or patch cadence to carry (which filesystem is #19's
call, not this one; ZFS is a measured candidate per #15). The host also keeps
its only video output, needed to diagnose a failed boot on a machine that must
reboot unattended, something a hypervisor's own console would have to
reproduce rather than remove. No test-isolation need or non-container workload
was identified that would rent the layer.

## Mutable over immutable

Talos Linux was the immutable candidate, and the objection that disqualified it
in the previous iteration of this project, Wolf, the containerized game
server, needing `/dev/uinput`, udev rules and the Docker socket, none of which
exist under Talos, no longer holds now that gaming has left the service set.
Talos was re-examined on its own terms rather than dismissed by inheritance.

It supports the GPU: NVIDIA driver, Fabric Manager and container-toolkit
integration all ship as versioned system extensions, declaratively configured.
But the driver extension is **bound to a specific Talos release**:
`docs.siderolabs.com` states plainly that "the extensions versions also needs
to be updated when upgrading Talos", so every Talos upgrade on this GPU host
carries a driver-compatibility step in lockstep, not an independent one.
[siderolabs/extensions](https://github.com/siderolabs/extensions),
[NVIDIA GPU (Proprietary drivers)](https://docs.siderolabs.com/talos/v1.9/configure-your-talos-cluster/hardware-and-drivers/nvidia-gpu-proprietary).

Set against that cost is what immutability forecloses permanently: this
platform is explicitly agnostic to the services it runs, with "N unknown
services by construction" named in the map's own notes. Talos has no shell, no
package manager, and runs nothing that isn't a container under Kubernetes, so
any future workload that needs a host-level package, a non-containerized
service, or an ad-hoc diagnostic tool is unable to get one, ever, by
construction. Bare metal with Ansible keeps that door open at a cost already
paid once: the host is not declarative, and `ansible/` becomes the source of
truth for what Flux does not describe. The previous iteration of this project
accepted exactly this trade for the same reason, in its own ADR-0002 "Ubuntu
Server LTS headless, with k3s directly on bare metal" (archived, a different
document from this repository's own ADR-0002), and it held for its lifetime.

## Decision

**Ubuntu Server LTS, headless, bare metal.** No hypervisor. The GPU driver is
installed once on the host; `nvidia-container-toolkit` exposes it to
containers, making sharing the default rather than a configuration to obtain.
Ansible is the host's source of truth, versioned in this repository alongside
the GitOps-managed workload layer.

## Alternatives rejected

**Proxmox VE.** Would have bought VM snapshots and stronger isolation, at the
cost of a layer nothing here rents: GPU passthrough is already off the table,
this machine hosts no VM-shaped workload, and the SPOF is named rather than
mitigated regardless. Stays available for a future, heterogeneous second node
if virtualization ever becomes the right tool there.

**Talos Linux.** Reconsidered seriously now that its one disqualifying reason
(Wolf) is gone. Rejected on a different ground: its immutability is
unconditional, and this platform's defining property is that it does not yet
know what it will run. Trading that openness for a guarantee against
configuration drift, a guarantee Ansible's idempotent, re-playable roles
already approximate, was judged not worth the foreclosure. Revisit if the
service set ever stabilizes enough that "no more host-level surprises" stops
being a cost and becomes the point.

## Consequences

- The host is not declarative. `ansible/` in this repository is the record of
  what the host needs beyond what Flux describes: driver, kernel tuning, NFS
  client mounts, whatever the storage decision (#19) settles on. Without it the
  source of truth is incomplete and the machine is not reconstructible from Git
  alone.
- System-level rollback comes from a snapshot-capable root, not from a
  hypervisor snapshot. The specific filesystem is #19's decision, not this one.
- Node provisioning, what it costs in manual gestures to add a second machine,
  now has a foundation to be specified against: a configuration-managed
  distribution, not a declarative-API immutable one. That ticket was left in
  the map's fog pending exactly this decision and can now be sharpened.
- The GitOps engine question remains open and un-presupposed by this decision:
  bare metal with Ansible runs any orchestrator candidate still on the table
  (#21), unlike Talos, which would have implicitly committed the platform to a
  Kubernetes-shaped answer before #21 was settled.
