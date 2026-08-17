# Platform state: invariants

What "the base platform is up" means. Each invariant below is owned by one
role's `--tags verify` tasks — this page is an index into them, not a
second copy of what they check. Run all eight at once:

```
ansible-playbook ansible/site.yml --tags verify -l <host>
```

No measured values here — a value belongs in the check's own output when
it runs, not committed to a doc that immediately goes stale.

1. **ZFS pools ONLINE.** Both the system pool (Subiquity's ZFS-guided
   autoinstall, ADR-0013) and the state pool (ADR-0010) report `ONLINE`
   health. `zfs` role, `--tags verify`.
2. **k3s node Ready.** The single k3s server (ADR-0007) reports `Ready`.
   `k3s` role, `--tags verify`.
3. **Flux controllers healthy.** Every Deployment in `flux-system`
   (source, kustomize, helm, notification controllers, ADR-0008) has all
   replicas ready. `gitops` role, `--tags verify`.
4. **GPU visible to a pod.** A pod requesting `nvidia.com/gpu` schedules
   and can run `nvidia-smi` (#68; NVIDIA k8s-device-plugin, #105). `nvidia`
   role, `--tags verify`.
5. **NAS mounts present, non-root write proven.** Both exports
   (`upload/`, `library/`, ADR-0010) are mounted, and a non-root UID can
   write and read back a file on each — not just root (#69). `nfs-client`
   role, `--tags verify`.
6. **`sops-age` secret present.** The daily age identity is loaded into
   `flux-system` as `sops-age` (ADR-0009), so kustomize-controller's
   `decryption` block on `clusters/homelab/workloads.yaml` can actually
   decrypt. `gitops` role, `--tags verify` (creation/rotation is the same
   role's unmarked task).
7. **No pending reboot.** `/var/run/reboot-required` is absent — the last
   applied change (kernel, GPU driver, ZFS module) is the one actually
   running. `base` role, `--tags verify`.
8. **`node_exporter` reachable and scraped.** VictoriaMetrics reports a
   fresh `up{job="node-exporter"} == 1` series, the same series
   ADR-0018's Watchdog rule and `NodeUnreachable` alert key off
   (`workloads/observability/vmalert-configmap.yaml`), so this invariant
   is proven against what the platform actually depends on, not a direct
   `:9100/metrics` curl that a stuck scrape target would still pass.
   `node-exporter` role, `--tags verify`.

## Known gap: three components outside GitOps

Traefik, svclb (k3s's ServiceLB), and metrics-server ship as part of k3s's
own bundled add-ons, not through Flux. They run today and are not currently
declared as Flux `HelmRelease`/`Kustomization` resources anywhere in this
repository. Bringing them under GitOps management is not one of this page's
invariants and not in scope for #101 — noted here so their absence from
`clusters/homelab/` isn't mistaken for an oversight when reading the
manifests next to this doc.
