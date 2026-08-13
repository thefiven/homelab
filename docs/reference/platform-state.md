# Platform state: invariants

What "the base platform is up" means, checked in order by
`scripts/check-platform` (#101). This page lists the same invariants in
prose; keep the two in sync rather than letting this page drift into a
second source of truth. No measured values here — a value belongs in the
check's own output when it runs, not committed to a doc that immediately
goes stale.

1. **ZFS pools ONLINE.** Both the system pool (Subiquity's ZFS-guided
   autoinstall, ADR-0013) and the state pool (`zfs` role, ADR-0010) report
   `ONLINE` health.
2. **k3s node Ready.** The single k3s server (ADR-0007) reports `Ready`.
3. **Flux controllers healthy.** Every Deployment in `flux-system`
   (source, kustomize, helm, notification controllers, ADR-0008) has all
   replicas ready.
4. **GPU visible to a pod.** A pod requesting `nvidia.com/gpu` schedules
   and can run `nvidia-smi` (`nvidia` role, #68).
5. **NAS mounts present, non-root write proven.** Both exports
   (`upload/`, `library/`, ADR-0010) are mounted, and a non-root UID can
   write and read back a file on each — not just root (`nfs-client` role,
   #69, #101).
6. **`sops-age` secret present.** The daily age identity is loaded into
   `flux-system` as `sops-age` (ADR-0009, `scripts/sops-age-bootstrap`),
   so kustomize-controller's `decryption` block on `clusters/homelab/workloads.yaml`
   can actually decrypt.
7. **No pending reboot.** `/var/run/reboot-required` is absent — the last
   applied change (kernel, GPU driver, ZFS module) is the one actually
   running.

## Known gap: three components outside GitOps

Traefik, svclb (k3s's ServiceLB), and metrics-server ship as part of k3s's
own bundled add-ons, not through Flux. They run today and are not currently
declared as Flux `HelmRelease`/`Kustomization` resources anywhere in this
repository. Bringing them under GitOps management is not one of this page's
invariants and not in scope for #101 — noted here so their absence from
`clusters/homelab/` isn't mistaken for an oversight when reading the
manifests next to this doc.
