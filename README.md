# homelab

A self-hosted execution platform, agnostic to the services it runs. The
platform is the product; applications are interchangeable consumers.

Architecture decisions land as ADRs under `docs/adr/` before any
configuration is written; `CONTEXT.md` fixes the vocabulary they share.

The base platform (#62: bare metal to a reconciling GitOps substrate) is
under construction: `ansible/` provisions node 1 (base hardening, ZFS
system/state pools, Tailscale, k3s), `clusters/homelab/` holds the Flux
bootstrap, and `secrets/` holds SOPS+age-encrypted manifests. No workload
runs on top of it yet: each one (Immich, observability, ingress, backup)
is its own later ticket. Every ticket touching the physical node or NAS is
human-in-the-loop; acceptance is checked against the real hardware, never
simulated.
