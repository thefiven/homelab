#!/usr/bin/env python3
# Runs `flux bootstrap github` against this repo (ADR-0008, #71). One-time,
# per #62: needs a live k3s cluster reachable via kubectl and a GitHub PAT
# with repo scope. Installs Flux's four default controllers into
# clusters/homelab/flux-system/, patched per that directory's kustomization.yaml.
import os
import shutil
import sys


def main() -> int:
    if shutil.which("flux") is None:
        print(
            "flux-bootstrap: flux CLI not found "
            "(https://fluxcd.io/flux/installation/)",
            file=sys.stderr,
        )
        return 1
    if not os.environ.get("GITHUB_TOKEN"):
        print(
            "flux-bootstrap: set GITHUB_TOKEN to a GitHub PAT with repo scope",
            file=sys.stderr,
        )
        return 1

    try:
        os.execvp(
            "flux",
            [
                "flux",
                "bootstrap",
                "github",
                "--owner=thefiven",
                "--repository=homelab",
                "--branch=main",
                "--path=clusters/homelab",
                "--personal",
            ],
        )
    except OSError as e:
        # which() above is only advisory - flux can vanish between the check
        # and the exec (mid package-manager upgrade).
        print(f"flux-bootstrap: failed to exec flux: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
