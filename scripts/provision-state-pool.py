#!/usr/bin/env python3
# Import or create ADR-0010's state pool on the disk a serial number
# designates (#116), extracted from role `zfs` so the sequencing bugs
# already found running this against real hardware (unconditional relist,
# hostid-mismatch recognition, the pkname backing-device walk-back) can be
# caught by --self-check instead of by risking the platform's one
# irreplaceable dataset again.
#
# Behaviour is carried over verbatim from the role: `ID_SERIAL` is the one
# discriminant that survives a disk moving slot or enumeration order;
# `/dev/disk/by-id` (never `/dev/nvmeXn1`) is what `zpool` gets, for the
# same reason. Import-before-create is what makes a rerun safe — a pool can
# exist on the disk without being imported (lost cache, moved disk,
# reinstalled system disk), and a bare `zpool create` would happily
# overwrite it. The backing-device check at the end runs unconditionally,
# on every invocation, including when the pool was already imported before
# this script ever ran (e.g. by zfs-import-cache.service at boot) — that is
# the one gap the original role's own comments flagged as still open.
import argparse
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path


class ProvisionError(Exception):
    pass


def die(msg: str) -> None:
    raise ProvisionError(msg)


def provision(serial: str, pool: str, props: list[str]) -> None:
    """Resolves the state pool on the serial-matched disk: imports it if
    already on disk, creates it if the disk is bare, and either way
    verifies the pool's actual backing device is that same disk. Prints the
    resolved by-id path, then a final status line ending in "No change
    detected" iff the pool was already imported before this call — the
    exact idiom k3s/tasks/main.yml's changed_when already keys off, reused
    rather than invented twice.
    """
    by_id_dir = Path(
        os.environ.get("PROVISION_STATE_POOL_BY_ID_DIR", "/dev/disk/by-id")
    )

    # `eui.*` links name the same disk again under its native NVMe
    # identifier; `-part*` links name a partition, not the whole disk `zpool
    # create` needs to own the partitioning of. Skipping both is what keeps
    # one physical disk from being double-counted or handed to zpool wrong.
    links = []
    for link in sorted(by_id_dir.glob("nvme-*")):
        if "eui." in link.name or "-part" in link.name:
            continue
        info = subprocess.run(
            ["udevadm", "info", "--query=property", f"--name={link}"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        link_serial = next(
            (
                line.removeprefix("ID_SERIAL=")
                for line in info.splitlines()
                if line.startswith("ID_SERIAL=")
            ),
            None,
        )
        if link_serial == serial:
            links.append(link)
    if not links:
        die(f"no disk on this host has ID_SERIAL={serial}")

    # Multiple *links* for one disk is normal (one per udev naming
    # convention); what must be unique is the *disk* they resolve to. One
    # readlink invocation for every link, not one per link (mirrors the
    # bash original's `readlink -f "${links[@]}" | sort -u`).
    devices = sorted(
        set(
            subprocess.run(
                ["readlink", "-f", *(str(link) for link in links)],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.splitlines()
        )
    )
    if len(devices) != 1:
        die(
            f"{serial} designates {len(devices)} distinct disks "
            f"({' '.join(devices)}); refusing, that serial is not the "
            "stable discriminant it's assumed to be"
        )

    disk, device = links[0], devices[0]

    imported_proc = subprocess.run(
        ["zpool", "list", "-H", "-o", "name"], capture_output=True, text=True
    )
    if imported_proc.returncode != 0:
        die(f"zpool list failed: {imported_proc.stdout}{imported_proc.stderr}")
    imported = [line for line in imported_proc.stdout.splitlines() if line]

    changed = False
    # Pool names are compared literally, never as a regex — a serial or
    # pool name containing a metacharacter must not coincidentally match.
    if pool not in imported:
        env = dict(os.environ, LC_ALL="C")
        import_proc = subprocess.run(
            ["zpool", "import", "-d", str(by_id_dir), pool],
            capture_output=True,
            text=True,
            env=env,
        )
        import_out = import_proc.stdout + import_proc.stderr
        if import_proc.returncode == 0:
            changed = True
        elif "no such pool available" in import_out:
            # `-f`: a bare disk can carry a stale non-ZFS signature (an old
            # filesystem, an old partition table) that create would
            # otherwise refuse to write over. Safe here because the branch
            # above already confirmed no importable pool exists — the only
            # thing `-f` can be bypassing is that stale signature, never a
            # live pool.
            create_cmd = [
                "zpool",
                "create",
                "-f",
                "-o",
                "ashift=12",
                "-o",
                "cachefile=/etc/zfs/zpool.cache",
            ]
            for prop in props:
                create_cmd += ["-O", prop]
            create_cmd += [pool, str(disk)]
            if subprocess.run(create_cmd).returncode != 0:
                die(f"zpool create failed for {pool} on {disk}")
            changed = True
        elif "pool was previously in use from another system" in import_out:
            # A reinstalled system disk always leaves a fresh /etc/hostid
            # without touching the state disk's labels, producing exactly
            # this message. `-f` overrides that stale-ownership refusal
            # only; the backing-device check below still catches a
            # same-named pool that turns out to live on the wrong disk,
            # same as every other path.
            force_proc = subprocess.run(
                ["zpool", "import", "-f", "-d", str(by_id_dir), pool],
                capture_output=True,
                text=True,
                env=env,
            )
            if force_proc.returncode != 0:
                die(
                    f"force-import failed for {pool} after hostid mismatch: "
                    f"{force_proc.stdout}{force_proc.stderr}"
                )
            changed = True
        else:
            die(
                f"zpool import did not report {pool} as absent, but also "
                f"failed to import it: {import_out}. Nothing created or "
                f"force-imported. Diagnose by hand with zpool import -d {by_id_dir}"
            )

    # Unconditional: a pool already imported before this script ever ran
    # (e.g. zfs-import-cache.service at boot) skips every branch above, with
    # no check yet on which disk it actually came from.
    # `zpool create` on a whole-disk link auto-partitions it (labels live in
    # partition 1), so `zpool status` reports the pool backed by
    # `.../nvme1n1p1`, never the whole-disk path `device` holds — comparing
    # those directly fails every real create. `lsblk -no pkname` walks a
    # partition back to its parent disk; a device with no parent (already a
    # whole disk) falls through to itself unchanged.
    status_out = subprocess.run(
        ["zpool", "status", "-P", pool], capture_output=True, text=True, check=True
    ).stdout
    raw_paths = [
        parts[0]
        for line in status_out.splitlines()
        if (parts := line.split()) and parts[0].startswith("/")
    ]
    # One readlink invocation for every matched path, not one per path
    # (mirrors the bash original's `xargs -r readlink -f`); -r's "skip if
    # empty" becomes just not calling readlink at all when there's nothing
    # to resolve.
    resolved = (
        subprocess.run(
            ["readlink", "-f", *raw_paths], capture_output=True, text=True, check=True
        ).stdout.splitlines()
        if raw_paths
        else []
    )
    backing = set()
    for dev in resolved:
        pkname = subprocess.run(
            ["lsblk", "-no", "pkname", dev], capture_output=True, text=True
        ).stdout.strip()
        backing.add(f"/dev/{pkname}" if pkname else dev)

    if not (len(backing) == 1 and next(iter(backing)) == device):
        shown = ", ".join(sorted(backing)) if backing else "<none>"
        die(
            f"pool {pool} is backed by {shown}, not the disk resolved from "
            f"serial {serial} ({device}); refusing to touch ARC, datasets "
            "or trim for a pool that isn't confirmed to live on the "
            "serial-matched disk"
        )

    print(disk)
    if changed:
        print(f"provisioned state pool {pool} on {disk}")
    else:
        print(f"No change detected: state pool {pool} already imported on {disk}")


_UDEVADM_FAKE = """#!/usr/bin/env bash
# Fakes `udevadm info --query=property --name=<by-id link>`: the by-id
# filename itself encodes the serial (nvme-<SERIAL>), so no lookup table.
path=""
for arg in "$@"; do
  case "$arg" in --name=*) path="${arg#--name=}" ;; esac
done
echo "ID_SERIAL=$(basename "$path" | sed 's/^nvme-//')"
"""

_READLINK_FAKE = """#!/usr/bin/env bash
# Fakes `readlink -f`: a by-id link (nvme-<SERIAL>) canonicalizes to a
# fixed fake device path; anything else (already a /dev path) passes
# through unchanged, matching real readlink -f on a non-symlink node.
shift
for p in "$@"; do
  base=$(basename "$p")
  case "$base" in
    nvme-*) echo "/dev/fake-${base#nvme-}" ;;
    *) echo "$p" ;;
  esac
done
"""

_LSBLK_FAKE = """#!/usr/bin/env bash
# Fakes `lsblk -no pkname <partition>`: strips a trailing pN, the same
# shape as the real command walking a partition back to its parent disk.
dev="${*: -1}"
basename "$dev" | sed -E 's/p[0-9]+$//'
"""


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _seed_by_id(by_id_dir: Path, serial: str) -> None:
    by_id_dir.mkdir(parents=True, exist_ok=True)
    (by_id_dir / f"nvme-{serial}").touch()
    (by_id_dir / f"nvme-{serial}-part1").touch()
    (by_id_dir / f"nvme-{serial}_eui.0000000000000001").touch()


# Fakes zpool/udevadm/lsblk/readlink and replays them through `provision`
# (invoked as a subprocess of this same script, PATH pointed at the fakes)
# so the four scenarios that matter can run with no NVMe attached: a blank
# disk, an already-importable pool, a hostid-mismatch pool, and a
# same-named pool backed by the wrong disk. A fifth checks the idempotent-
# rerun contract the role's changed_when depends on.
def self_check() -> None:
    with tempfile.TemporaryDirectory() as scratch_str:
        scratch = Path(scratch_str)
        shared = scratch / "shared"
        shared.mkdir()
        _write_executable(shared / "udevadm", _UDEVADM_FAKE)
        _write_executable(shared / "readlink", _READLINK_FAKE)
        _write_executable(shared / "lsblk", _LSBLK_FAKE)

        script_path = Path(__file__).resolve()

        def run_provision(zpool_dir: Path, by_id_dir: Path, serial: str, pool: str):
            env = dict(os.environ)
            env["PATH"] = f"{zpool_dir}:{shared}:{env.get('PATH', '')}"
            env["PROVISION_STATE_POOL_BY_ID_DIR"] = str(by_id_dir)
            proc = subprocess.run(
                [
                    str(script_path),
                    "--serial",
                    serial,
                    "--pool",
                    pool,
                    "-O",
                    "atime=on",
                ],
                capture_output=True,
                text=True,
                env=env,
            )
            return proc.returncode, proc.stdout + proc.stderr

        pool = "state"

        # 1. Blank disk: no pool anywhere -> create.
        s1 = scratch / "s1"
        zpool_dir, by_id_dir = s1 / "zpool", s1 / "byid"
        zpool_dir.mkdir(parents=True)
        _seed_by_id(by_id_dir, "BLANK1")
        _write_executable(
            zpool_dir / "zpool",
            """#!/usr/bin/env bash
case "$1" in
  list) : ;;
  import) echo "cannot import 'state': no such pool available" >&2; exit 1 ;;
  create) exit 0 ;;
  status) echo "  /dev/fake-BLANK1p1 ONLINE" ;;
  *) echo "unhandled: $*" >&2; exit 9 ;;
esac
""",
        )
        rc, out = run_provision(zpool_dir, by_id_dir, "BLANK1", pool)
        if rc != 0:
            die(f"self-check: blank-disk scenario should succeed, got rc={rc}: {out}")
        if "nvme-BLANK1" not in out:
            die(
                "self-check: blank-disk scenario didn't resolve the disk "
                "it should create on"
            )
        if "No change detected" in out:
            die("self-check: blank-disk scenario should report a change")

        # 2. Already-importable pool -> plain import, no force, no create.
        s2 = scratch / "s2"
        zpool_dir, by_id_dir = s2 / "zpool", s2 / "byid"
        zpool_dir.mkdir(parents=True)
        _seed_by_id(by_id_dir, "IMPORTABLE2")
        _write_executable(
            zpool_dir / "zpool",
            """#!/usr/bin/env bash
case "$1" in
  list) : ;;
  import)
    for a in "$@"; do
      [[ "$a" == "-f" ]] && { echo "unexpected forced import" >&2; exit 9; }
    done
    exit 0 ;;
  create) echo "unexpected create" >&2; exit 9 ;;
  status) echo "  /dev/fake-IMPORTABLE2p1 ONLINE" ;;
  *) echo "unhandled: $*" >&2; exit 9 ;;
esac
""",
        )
        rc, out = run_provision(zpool_dir, by_id_dir, "IMPORTABLE2", pool)
        if rc != 0:
            die(
                "self-check: importable-pool scenario should succeed, "
                f"got rc={rc}: {out}"
            )
        if "No change detected" in out:
            die("self-check: importable-pool scenario should report a change")

        # 3. Hostid mismatch -> force-import, no create.
        s3 = scratch / "s3"
        zpool_dir, by_id_dir = s3 / "zpool", s3 / "byid"
        zpool_dir.mkdir(parents=True)
        _seed_by_id(by_id_dir, "HOSTID3")
        _write_executable(
            zpool_dir / "zpool",
            """#!/usr/bin/env bash
case "$1" in
  list) : ;;
  import)
    force=0
    for a in "$@"; do [[ "$a" == "-f" ]] && force=1; done
    if [[ $force -eq 1 ]]; then
      exit 0
    else
      echo "cannot import 'state': pool was previously in use from another system" >&2
      exit 1
    fi ;;
  create) echo "unexpected create" >&2; exit 9 ;;
  status) echo "  /dev/fake-HOSTID3p1 ONLINE" ;;
  *) echo "unhandled: $*" >&2; exit 9 ;;
esac
""",
        )
        rc, out = run_provision(zpool_dir, by_id_dir, "HOSTID3", pool)
        if rc != 0:
            die(
                "self-check: hostid-mismatch scenario should succeed, "
                f"got rc={rc}: {out}"
            )
        if "No change detected" in out:
            die("self-check: hostid-mismatch scenario should report a change")

        # 4. Same-named pool backed by a different disk than the serial
        #    matched -> must refuse. Both create and force-import die if hit,
        #    so a zero exit here would mean a mutation was attempted, not
        #    just missed.
        s4 = scratch / "s4"
        zpool_dir, by_id_dir = s4 / "zpool", s4 / "byid"
        zpool_dir.mkdir(parents=True)
        _seed_by_id(by_id_dir, "RIGHT4")
        _write_executable(
            zpool_dir / "zpool",
            """#!/usr/bin/env bash
case "$1" in
  list) : ;;
  import)
    for a in "$@"; do
      [[ "$a" == "-f" ]] && { echo "unexpected forced import" >&2; exit 9; }
    done
    exit 0 ;;
  create) echo "unexpected create" >&2; exit 9 ;;
  status) echo "  /dev/fake-WRONG4p1 ONLINE" ;;
  *) echo "unhandled: $*" >&2; exit 9 ;;
esac
""",
        )
        rc, out = run_provision(zpool_dir, by_id_dir, "RIGHT4", pool)
        if rc == 0:
            die(
                "self-check: wrong-backing-disk scenario should refuse, "
                f"but exited 0: {out}"
            )

        # 5. Idempotent rerun: pool already imported before the script
        #    starts -> no import/force/create call at all, changed_when
        #    contract holds.
        s5 = scratch / "s5"
        zpool_dir, by_id_dir = s5 / "zpool", s5 / "byid"
        zpool_dir.mkdir(parents=True)
        _seed_by_id(by_id_dir, "ALREADY5")
        _write_executable(
            zpool_dir / "zpool",
            """#!/usr/bin/env bash
case "$1" in
  list) echo state ;;
  import) echo "unexpected import" >&2; exit 9 ;;
  create) echo "unexpected create" >&2; exit 9 ;;
  status) echo "  /dev/fake-ALREADY5p1 ONLINE" ;;
  *) echo "unhandled: $*" >&2; exit 9 ;;
esac
""",
        )
        rc, out = run_provision(zpool_dir, by_id_dir, "ALREADY5", pool)
        if rc != 0:
            die(
                "self-check: idempotent-rerun scenario should succeed, "
                f"got rc={rc}: {out}"
            )
        if "No change detected" not in out:
            die(
                "self-check: idempotent rerun must report no change "
                "(changed_when contract)"
            )

    print("self-check: passed")


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="provision-state-pool",
        description=(
            "Import or create ADR-0010's state pool on the disk a serial "
            "number designates."
        ),
        epilog=(
            "Env (only meaningful under --self-check; real runs always use "
            "the real /dev/disk/by-id): PROVISION_STATE_POOL_BY_ID_DIR "
            "overrides the by-id directory searched"
        ),
    )
    parser.add_argument("--serial", help="udev ID_SERIAL of the state disk")
    parser.add_argument("--pool", help="name of the ZFS pool to import or create")
    parser.add_argument(
        "-O",
        dest="props",
        action="append",
        default=[],
        metavar="key=value",
        help="root-of-pool property, passed verbatim to `zpool create -O` (repeatable)",
    )
    parser.add_argument(
        "--self-check",
        action="store_true",
        help=(
            "replay import/create logic against fake zpool/udevadm/lsblk/"
            "readlink executables, no NVMe or ZFS module needed"
        ),
    )
    args = parser.parse_args()

    try:
        if args.self_check:
            self_check()
            return 0

        if not (args.serial and args.pool):
            parser.print_usage(sys.stderr)
            die("--serial and --pool are both required")

        provision(args.serial, args.pool, args.props)
        return 0
    except ProvisionError as e:
        print(f"provision-state-pool: {e}", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as e:
        print(
            f"provision-state-pool: {e.cmd[0]} failed: {e.stderr or e.stdout}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
