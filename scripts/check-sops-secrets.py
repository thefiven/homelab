#!/usr/bin/env python3
# Local pre-commit hook (ADR-0009, #73): a file under secrets/ that pre-commit
# hands us here matched .pre-commit-config.yaml's `files:` regex, i.e. it's
# already scoped to the secrets path convention from .sops.yaml
# (`secrets/.*\.ya?ml$`). This script only checks the one thing that regex
# can't: does the file actually carry SOPS's `sops:` metadata block, proof
# it's encrypted and not plaintext committed under a path that must always
# be encrypted. That's the check's whole documented scope (ADR-0009,
# "Pre-commit scanning"): it enforces the structure, not the content of
# individual values. A value that ends up plaintext under a mistyped key
# outside `data`/`stringData` is exactly what layer 2 (gitleaks) exists to
# catch instead, the ADR names this split explicitly, so don't widen this
# check to parse YAML structure; extend gitleaks' ruleset if that gap
# matters.
import sys


def main(argv: list[str]) -> int:
    failed = 0
    for path in argv:
        try:
            with open(path, encoding="utf-8") as f:
                has_sops = any(line.startswith("sops:") for line in f)
        except (OSError, UnicodeDecodeError) as e:
            # A bad file here must not stop the rest of argv from being
            # checked - pre-commit hands this one hook every matched path
            # in a single invocation.
            print(f"check-sops-secrets: {path}: {e}", file=sys.stderr)
            failed = 1
            continue
        if not has_sops:
            print(
                f"check-sops-secrets: {path} is under secrets/ but has no "
                "top-level 'sops:' block (not encrypted).",
                file=sys.stderr,
            )
            print(
                f"  encrypt it first: sops --encrypt --in-place {path}",
                file=sys.stderr,
            )
            failed = 1
    return failed


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
