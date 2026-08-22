# homelab

A self-hosted execution platform, agnostic to the services it runs. The
platform is the product; applications are interchangeable consumers.

Architecture decisions land as ADRs under `docs/adr/` before any
configuration is written; `CONTEXT.md` fixes the vocabulary they share.

The base platform (#62: bare metal to a reconciling GitOps substrate) is
under construction: `ansible/` provisions node 1 (base hardening, ZFS
system/state pools, Tailscale, k3s), `clusters/homelab/` holds the Flux
bootstrap, and each workload's SOPS+age-encrypted manifests live under its
own `workloads/*/secrets/`. Four workloads already run on top of it: Immich
(server, Postgres, Redis, machine-learning), observability
(VictoriaMetrics, VictoriaLogs, Grafana, vmalert, Alertmanager), ingress
(cloudflared, currently failing on a missing secret pending a domain
purchase, #162) and backup (two CronJobs, with completed runs on the
cluster). Every ticket touching the physical node or NAS is
human-in-the-loop; acceptance is checked against the real hardware, never
simulated.

Issues are open for discussion; external pull requests are not currently
treated as a request surface.

