#!/usr/bin/env python3
# Self-check for the sops-metadata-policy pre-commit hook (ADR-0009, #73).
#
# Tests the two things that actually enforce the policy, directly and
# without a pre-commit install: scripts/check-sops-secrets.py itself (does
# it accept/reject correctly), and .pre-commit-config.yaml's `files:` regex
# (does it scope to secrets/, unanchored, same as .sops.yaml's own
# path_regex). No git-init/pre-commit dependency: this is what pre-commit
# would run and what would route a commit to it, tested at that level
# instead of through the framework's plumbing.
import re
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> int:
    try:
        repo_root = Path(
            subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        )
    except subprocess.CalledProcessError as e:
        print(
            f"check-sops-secrets-test: not a git checkout: {e.stderr}", file=sys.stderr
        )
        return 1

    fail = 0

    def ok(msg: str) -> None:
        print(f"ok   - {msg}")

    def bad(msg: str) -> None:
        nonlocal fail
        print(f"FAIL - {msg}")
        fail = 1

    config_text = (repo_root / ".pre-commit-config.yaml").read_text()
    try:
        files_line = next(
            line
            for line in config_text.splitlines()
            if line.strip().startswith("files:")
        )
    except StopIteration:
        print(
            "check-sops-secrets-test: no 'files:' line in .pre-commit-config.yaml",
            file=sys.stderr,
        )
        return 1
    files_regex = files_line.strip().removeprefix("files:").strip()
    pattern = re.compile(files_regex)

    # 1. files: regex scopes to secrets/, unanchored (nested paths included),
    #    and excludes paths outside secrets/.
    if pattern.search("secrets/plain.yaml"):
        ok("files regex matches secrets/plain.yaml")
    else:
        bad("files regex should match secrets/plain.yaml")

    if pattern.search("apps/foo/secrets/bar.yaml"):
        ok("files regex matches nested apps/foo/secrets/bar.yaml")
    else:
        bad("files regex should match nested secrets/ paths")

    if pattern.search("outside/plain.yaml"):
        bad("files regex should not match outside/plain.yaml")
    else:
        ok("files regex excludes outside/plain.yaml")

    # 2. the hook script itself: reject plaintext, accept a real encrypted file.
    hook = repo_root / "scripts" / "check-sops-secrets.py"
    with tempfile.TemporaryDirectory() as scratch:
        plain = Path(scratch) / "plain.yaml"
        plain.write_text("apiVersion: v1\nkind: Secret\nstringData:\n  ping: pong\n")
        result = subprocess.run([str(hook), str(plain)], capture_output=True)
        if result.returncode != 0:
            ok("hook rejects an unencrypted secret")
        else:
            bad("hook should reject an unencrypted secret")

    real_secret = (
        repo_root / "workloads" / "smoke" / "secrets" / "test-secret.sops.yaml"
    )
    result = subprocess.run([str(hook), str(real_secret)], capture_output=True)
    if result.returncode == 0:
        ok("hook accepts the repo's real encrypted secret")
    else:
        bad("hook should accept workloads/smoke/secrets/test-secret.sops.yaml")

    return fail


if __name__ == "__main__":
    sys.exit(main())
