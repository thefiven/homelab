#!/usr/bin/env python3
# Stamp a stock Ubuntu Server ISO into zero-touch autoinstall media for one
# node (ADR-0013, gesture 3). Embeds a cloud-init NoCloud user-data/meta-data
# pair (storage.layout.match.serial disambiguates the target disk; the
# bootstrap account is named after --hostname, not a fixed name like
# `ubuntu`, so the OS hostname and the login account stay the same value;
# it is a locked-password, key-only, NOPASSWD-sudo user via user-data.users,
# never `identity`) and patches boot/grub/grub.cfg + loopback.cfg so install
# starts on insert + power-on, no console needed.
#
# ponytail: the grub.cfg patch matches the ` ---` cmdline-separator
# convention casper installer menus have used across releases, verified via
# community autoinstall-ISO tooling and Canonical's own zero-touch docs, but
# not against an actual Ubuntu Server 26.04 ISO (unavailable at authoring
# time). First real run should confirm the patched entry boots, before this
# node's stick is trusted; that hands-on check is the ready-for-human half
# of this ticket.
import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


class BuildMediaError(Exception):
    pass


def die(msg: str) -> None:
    raise BuildMediaError(msg)


def yaml_escape(value: str) -> str:
    """Escapes a value for embedding in a double-quoted YAML scalar."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def validate_hostname(value: str) -> None:
    # This value doubles as the bootstrap account name (user-data.users[].name
    # below), so the regex is a Linux username's constraints (lowercase start,
    # lowercase/digits/dash, <=32 chars), not a DNS label's looser ones (mixed
    # case, <=63 chars). A hostname that passed only the looser rule could
    # fail account creation with no fallback login (ssh key auth only).
    if not re.fullmatch(r"[a-z]([a-z0-9-]{0,30}[a-z0-9])?", value):
        die(
            f"invalid hostname: {value} (must also be a valid Linux username: "
            "lowercase, start with a letter, max 32 chars)"
        )


def validate_serial(value: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_.:-]+", value):
        die(f"invalid serial: {value}")


def validate_pubkey(value: str) -> None:
    # Reject embedded newlines first: the trailing-comment group below
    # matches a newline too, so a two-line value (e.g. --ssh-key
    # "$(cat file.pub)" against a file with a trailing blank line) would
    # otherwise pass and get YAML-folded into one corrupted authorized_keys
    # entry — fatal here since the bootstrap account is key-only, no fallback.
    if "\n" in value:
        die(f"SSH public key must be a single line: {value}")
    # authorized_keys line: "<type> <base64> [comment]", type is a known prefix.
    if not re.fullmatch(
        r"(ssh-ed25519|ssh-rsa|ecdsa-sha2-[a-z0-9-]+)\s+[A-Za-z0-9+/=]+(\s+.*)?",
        value,
    ):
        die(f"invalid SSH public key: {value}")


def resolve_pubkey(value: str) -> str:
    """A readable file wins; otherwise treat the argument as literal key content."""
    path = Path(value)
    if path.is_file():
        lines = path.read_text().splitlines()
        # An empty file has no first line - fall through to validate_pubkey()
        # for a clean error instead of an IndexError here.
        return lines[0] if lines else ""
    return value


def render_user_data(serial: str, pubkey: str, hostname: str) -> str:
    serial = yaml_escape(serial)
    pubkey = yaml_escape(pubkey)
    hostname = yaml_escape(hostname)
    return f"""#cloud-config
autoinstall:
  version: 1
  ssh:
    install-server: true
    allow-pw: false
  storage:
    layout:
      name: zfs
      match:
        serial: "{serial}"
  user-data:
    hostname: "{hostname}"
    users:
      - name: "{hostname}"
        lock_passwd: true
        sudo: "ALL=(ALL) NOPASSWD:ALL"
        ssh_authorized_keys:
          - "{pubkey}"
"""


def render_meta_data(hostname: str) -> str:
    hostname = yaml_escape(hostname)
    return f'instance-id: "{hostname}"\nlocal-hostname: "{hostname}"\n'


def patch_grub_cfg(text: str) -> str:
    """Patches a grub.cfg/loopback.cfg boot entry so it boots straight into
    unattended autoinstall: the bare `autoinstall` word skips the "Continue
    with autoinstall?" console prompt, `ds=nocloud;s=/cdrom/nocloud/` points
    cloud-init at the embedded pair. The trailing backslash before `;` is a
    GRUB escape, not a shell one.
    """
    return re.sub(r" ---", r" autoinstall ds=nocloud\\;s=/cdrom/nocloud/ ---", text)


def self_check() -> None:
    serial, hostname = "SAMPLE_SERIAL_123", "node2"
    pubkey = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIsample test@example"

    out = render_user_data(serial, pubkey, hostname)
    if "name: zfs" not in out:
        die(
            "self-check: storage.layout.name must be zfs (ADR-0010: ZFS "
            "root, not a plain partition table)"
        )
    if 'serial: "SAMPLE_SERIAL_123"' not in out:
        die("self-check: serial not substituted into storage.layout.match.serial")
    if 'hostname: "node2"' not in out:
        die("self-check: hostname not substituted")
    if pubkey not in out:
        die("self-check: pubkey not substituted")
    if "lock_passwd: true" not in out or "NOPASSWD:ALL" not in out:
        die("self-check: bootstrap account shape missing")
    if '- name: "node2"' not in out:
        die(
            "self-check: bootstrap account name must equal --hostname, not a fixed name"
        )
    if "identity:" in out:
        die("self-check: identity: section must not be emitted (ADR-0013)")

    out = render_meta_data(hostname)
    if 'instance-id: "node2"' not in out or 'local-hostname: "node2"' not in out:
        die("self-check: meta-data hostname not substituted")

    out = patch_grub_cfg("linux\t/casper/vmlinuz quiet ---\ninitrd\t/casper/initrd\n")
    if " autoinstall ds=nocloud\\;s=/cdrom/nocloud/ ---" not in out:
        die("self-check: kernel cmdline not patched")

    # A quote in operator-supplied input must not break the generated YAML.
    out = render_user_data('evil"serial', pubkey, hostname)
    if 'serial: "evil\\"serial"' not in out:
        die("self-check: quote in serial not escaped")

    print("self-check: passed")


def build(serial: str, pubkey: str, hostname: str, iso: Path, output: Path) -> None:
    if shutil.which("xorriso") is None:
        die("xorriso is required (apt install xorriso)")
    if not iso.is_file():
        die(f"no such ISO: {iso}")
    # xorriso's own collision handling for a pre-existing -outdev is untested
    # here; refuse up front rather than risk a hang or opaque error.
    if output.exists():
        die(f"output already exists: {output} (remove it first)")

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)

        (tmp / "user-data").write_text(render_user_data(serial, pubkey, hostname))
        (tmp / "meta-data").write_text(render_meta_data(hostname))

        subprocess.run(
            [
                "xorriso",
                "-indev",
                str(iso),
                "-osirrox",
                "on",
                "-extract",
                "/boot/grub/grub.cfg",
                str(tmp / "grub.cfg"),
            ],
            check=True,
        )
        (tmp / "grub.cfg.patched").write_text(
            patch_grub_cfg((tmp / "grub.cfg").read_text())
        )

        # `-mkdir` takes a variable-length list of paths and only stops
        # consuming args at an explicit `--`, not at the next `-`-prefixed
        # word — without it, the `-update` commands below are swallowed as
        # more mkdir targets instead of running, and the ISO is written with
        # empty directories where /nocloud/user-data and /nocloud/meta-data
        # should be.
        xorriso_args = [
            "-indev",
            str(iso),
            "-outdev",
            str(output),
            "-boot_image",
            "any",
            "replay",
            "-update",
            str(tmp / "grub.cfg.patched"),
            "/boot/grub/grub.cfg",
            "-mkdir",
            "/nocloud",
            "--",
            "-update",
            str(tmp / "user-data"),
            "/nocloud/user-data",
            "-update",
            str(tmp / "meta-data"),
            "/nocloud/meta-data",
        ]
        # loopback.cfg (BIOS boot menu) is optional across releases; patch it
        # too when present so a non-UEFI boot is also unattended. Any
        # extraction failure (absent file, or a real error — xorriso's
        # stderr still prints) is treated the same: skip it, but say so,
        # since a silent skip here means a BIOS boot falls back to the
        # console prompt this script exists to avoid.
        extract = subprocess.run(
            [
                "xorriso",
                "-indev",
                str(iso),
                "-osirrox",
                "on",
                "-extract",
                "/boot/grub/loopback.cfg",
                str(tmp / "loopback.cfg"),
            ],
        )
        if extract.returncode == 0:
            (tmp / "loopback.cfg.patched").write_text(
                patch_grub_cfg((tmp / "loopback.cfg").read_text())
            )
            xorriso_args += [
                "-update",
                str(tmp / "loopback.cfg.patched"),
                "/boot/grub/loopback.cfg",
            ]
        else:
            print(
                "build-media: warning: could not extract "
                "boot/grub/loopback.cfg, leaving it unpatched (BIOS boot "
                "may show the confirmation prompt)",
                file=sys.stderr,
            )

        subprocess.run(["xorriso", *xorriso_args], check=True)
        print(f"wrote {output}")


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="build-media",
        description=(
            "Stamp a stock Ubuntu Server ISO into zero-touch autoinstall "
            "media for one node."
        ),
    )
    parser.add_argument(
        "--serial",
        help="udev ID_SERIAL of the target disk (storage.layout.match.serial)",
    )
    parser.add_argument(
        "--ssh-key",
        dest="ssh_key",
        help="SSH public key, literal or a path to a .pub file",
    )
    parser.add_argument("--hostname", help="node hostname (single label)")
    # Not type=Path: an empty string "--iso ''" would parse as Path(""), which
    # is truthy (Path has no __bool__), silently defeating the all([...])
    # required-argument check below. Convert to Path only after that check.
    parser.add_argument("--iso", help="path to a stock Ubuntu Server ISO")
    parser.add_argument("--output", help="path to write the stamped ISO")
    parser.add_argument(
        "--self-check",
        action="store_true",
        help="verify config generation against sample input, no ISO/xorriso needed",
    )
    args = parser.parse_args()

    try:
        if args.self_check:
            self_check()
            return 0

        if not all([args.serial, args.ssh_key, args.hostname, args.iso, args.output]):
            parser.print_usage(sys.stderr)
            die("--serial, --ssh-key, --hostname, --iso and --output are all required")

        pubkey = resolve_pubkey(args.ssh_key)
        validate_serial(args.serial)
        validate_pubkey(pubkey)
        validate_hostname(args.hostname)

        build(args.serial, pubkey, args.hostname, Path(args.iso), Path(args.output))
        return 0
    except BuildMediaError as e:
        print(f"build-media: {e}", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as e:
        print(f"build-media: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
