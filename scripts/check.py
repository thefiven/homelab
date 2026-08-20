#!/usr/bin/env python3
# Runs every hardware-free self-check in the repo (#116), stopping at the
# first failure — the one entry point a contributor or CI job runs instead
# of invoking each script's --self-check separately.
import subprocess
import sys
from pathlib import Path

DIR = Path(__file__).resolve().parent

STEPS = [
    [str(DIR / "provision-state-pool.py"), "--self-check"],
    [str(DIR / "build-media.py"), "--self-check"],
    [str(DIR / "check-sops-secrets-test.py")],
    # Kustomization under workloads/immich parses and builds cleanly (#130),
    # same check kustomize-controller runs against it every reconcile,
    # without needing a live cluster. SOPS ciphertext still parses as valid
    # YAML, so this doesn't need a decryption key.
    ["kubectl", "kustomize", str(DIR / ".." / "workloads" / "immich")],
    # Same for workloads/observability (#160/#170). Its two SOPS secrets
    # (ntfy topic, Healthchecks ping URLs) aren't committed yet -
    # scripts/observability-secrets-setup is a human-only wizard (#169) -
    # and this build has to keep passing without them: the Deployment only
    # references their Secret names in a volume, which kustomize never
    # resolves.
    ["kubectl", "kustomize", str(DIR / ".." / "workloads" / "observability")],
    # Same for workloads/backup (#161-05): the restic postgres-dump and
    # restic-check CronJobs, and their three SOPS secrets (repository
    # password, duplicated Postgres credentials, duplicated Healthchecks
    # pings - 161-02 through 161-04).
    ["kubectl", "kustomize", str(DIR / ".." / "workloads" / "backup")],
    # Same for workloads/ingress (162-05/#182): the cloudflared Deployment
    # (#180) only references the cloudflare-tunnel-token Secret by name
    # (secretKeyRef), so this builds without it - neither that secret nor
    # the Cloudflare API token exists yet (both are
    # scripts/ingress-secrets-setup's job, #179).
    ["kubectl", "kustomize", str(DIR / ".." / "workloads" / "ingress")],
    # Same for workloads/smoke (162-05/#182): the whoami backend and
    # catch-all Ingress added by #181 sit alongside #101's SOPS-decryption
    # test-secret, now under their own kustomization.yaml so this entry
    # point can build them.
    ["kubectl", "kustomize", str(DIR / ".." / "workloads" / "smoke")],
]


def main() -> int:
    for cmd in STEPS:
        try:
            result = subprocess.run(
                cmd, stdout=subprocess.DEVNULL if cmd[0] == "kubectl" else None
            )
        except FileNotFoundError as e:
            print(f"check: {cmd[0]}: {e.strerror}", file=sys.stderr)
            return 127
        if result.returncode != 0:
            return result.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
