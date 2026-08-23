#!/usr/bin/env python3
"""Write NVMe SMART/health-log data as a node_exporter textfile (#270).

Discovers every /dev/nvmeNn1 device, reads smartctl's own JSON output and
emits four series per device: overall health, power-on hours, the
percentage-used wear indicator, and data-units-written converted to bytes
(the figure risk register 4's x5.5 amplification threshold needs, per #6).

Run as root (smartctl's NVMe health-log query needs it); one device's
failure does not block the others, and the file is only replaced if at
least one device answered, so a bad run leaves the previous reading in
place rather than an empty file.
"""

import glob
import json
import os
import subprocess
import sys
import tempfile

DEFAULT_OUTPUT_PATH = "/var/lib/node_exporter/textfile_collector/smart.prom"

# NVMe's own unit for data_units_written (NVMe Base Spec 1.4, section
# 5.14.1.2, Data Units Written): "one unit = 512,000 bytes", not the plain
# 512-byte sector its name suggests.
DATA_UNIT_BYTES = 512_000


def read_device(device: str) -> dict:
    proc = subprocess.run(
        ["smartctl", "-j", "-a", device],
        capture_output=True,
        text=True,
        check=False,
    )
    # smartctl's exit code is a bitmask (drive-warning bits can be set on an
    # otherwise-successful read), so a nonzero code alone is not a failure;
    # a JSON parse failure is the actual signal that nothing usable came
    # back.
    return json.loads(proc.stdout)


def format_metrics(readings: dict) -> str:
    lines = [
        "# HELP smartctl_device_smart_passed Overall SMART health self-assessment"
        " (1 = passed).",
        "# TYPE smartctl_device_smart_passed gauge",
        "# HELP smartctl_device_power_on_hours Power-on hours from the NVMe"
        " SMART/health-information log.",
        "# TYPE smartctl_device_power_on_hours gauge",
        "# HELP smartctl_device_percentage_used NVMe vendor-normalized wear"
        " indicator (100 = rated endurance reached).",
        "# TYPE smartctl_device_percentage_used gauge",
        "# HELP smartctl_device_data_units_written_bytes Bytes written to the"
        " device, converted from the NVMe spec's 512000-byte data unit.",
        "# TYPE smartctl_device_data_units_written_bytes counter",
    ]
    for device, info in sorted(readings.items()):
        log = info.get("nvme_smart_health_information_log", {})
        labels = f'device="{device}"'
        passed = info.get("smart_status", {}).get("passed")
        if passed is not None:
            lines.append(f"smartctl_device_smart_passed{{{labels}}} {int(passed)}")
        if "power_on_hours" in log:
            lines.append(
                f"smartctl_device_power_on_hours{{{labels}}} {log['power_on_hours']}"
            )
        if "percentage_used" in log:
            lines.append(
                f"smartctl_device_percentage_used{{{labels}}} {log['percentage_used']}"
            )
        if "data_units_written" in log:
            written_bytes = log["data_units_written"] * DATA_UNIT_BYTES
            lines.append(
                f"smartctl_device_data_units_written_bytes{{{labels}}} {written_bytes}"
            )
    return "\n".join(lines) + "\n"


def main(output_path: str) -> int:
    readings = {}
    for device in sorted(glob.glob("/dev/nvme[0-9]n1")):
        try:
            readings[device] = read_device(device)
        except (json.JSONDecodeError, OSError) as e:
            print(f"smart-textfile: {device}: {e}", file=sys.stderr)
    if not readings:
        print(
            "smart-textfile: no NVMe device answered, leaving previous file in place",
            file=sys.stderr,
        )
        return 1

    out_dir = os.path.dirname(output_path)
    # Atomic replace: node_exporter's textfile collector scrapes this
    # directory on every /metrics request, and a half-written file would
    # either fail to parse or expose a torn reading.
    fd, tmp_path = tempfile.mkstemp(dir=out_dir, prefix=".smart.prom.")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(format_metrics(readings))
        os.chmod(tmp_path, 0o644)
        os.replace(tmp_path, output_path)
    except BaseException:
        os.unlink(tmp_path)
        raise
    return 0


def _self_check() -> None:
    sample = {
        "/dev/nvme0n1": {
            "smart_status": {"passed": True},
            "nvme_smart_health_information_log": {
                "power_on_hours": 1234,
                "percentage_used": 3,
                "data_units_written": 100,
            },
        }
    }
    out = format_metrics(sample)
    assert 'smartctl_device_smart_passed{device="/dev/nvme0n1"} 1' in out
    assert 'smartctl_device_power_on_hours{device="/dev/nvme0n1"} 1234' in out
    assert 'smartctl_device_percentage_used{device="/dev/nvme0n1"} 3' in out
    expected = 100 * DATA_UNIT_BYTES
    assert (
        f'smartctl_device_data_units_written_bytes{{device="/dev/nvme0n1"}} {expected}'
        in out
    )
    print("self-check ok")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--self-check":
        _self_check()
        sys.exit(0)
    # Output path is an optional argv, not the DEFAULT_OUTPUT_PATH constant
    # directly: the systemd service template passes
    # node_exporter_textfile_dir explicitly, so this script can never drift
    # from that Ansible var the way a second hardcoded copy of the path
    # would.
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUTPUT_PATH
    sys.exit(main(path))
