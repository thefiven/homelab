# BIOS/UEFI reference: the server node

**Date: 2026-08-10**

The BIOS/UEFI settings this machine needs, each traced to an accepted ADR —
foundation (ADR-0003), storage (ADR-0010), power (ADR-0005). Not a full BIOS
walkthrough: only the items those three decisions actually bind. Everything
else stays at the board's shipped default. Menu paths, defaults and option
names below are read from the board's own manual ([B550 GAMING X V2 manual,
rev. 1101, Chapter 2 "BIOS
Setup"](https://download.gigabyte.com/FileList/Manual/mb_manual_b550-gaming-x-v2_e_1101.pdf),
pp. 20-36).

## Settings

| Setting | Menu path | Ship default | Set to | Why |
| --- | --- | --- | --- | --- |
| CSM Support | Boot | Enabled | **Disabled** | UEFI-only boot. Required for the GPT ESP the ZFS-root guided `autoinstall` layout creates (ADR-0010); the Secure Boot page is only reachable once this is off |
| Secure Boot | Boot → Secure Boot | (hidden while CSM on) | **Disabled** | ADR-0010 names ZFS "an out-of-tree module" — a DKMS-built `zfs.ko` isn't signed for this board's Secure Boot chain, and ADR-0013's seven-gesture, zero-touch autoinstall has no MOK-enrollment step to sign it |
| Boot Option Priorities | Boot | none set | System-pool NVMe's `UEFI:` entry, position 1 | The system pool holds the ESP and root (ADR-0010); the state-pool NVMe carries no ESP and must never be a boot candidate |
| Fast Boot | Boot | Disabled | **Disabled (confirm)** | Leaves both NVMe drives and the discrete GPU fully enumerated at every POST. ADR-0003 keeps the GPU's video output specifically "to diagnose a failed boot on a machine that must reboot unattended" — Fast Boot's abbreviated POST works against that |
| AC BACK | Settings → Platform Power | Always Off | **Always On** | The machine runs 24/7 (#27, ADR-0005) with no operator on hand to press the power button after an outage. "Memory" (last state) is state-dependent; "Always On" isn't |
| NVMe RAID mode | Settings → IO Ports → SATA Configuration | Disabled | **Disabled (confirm)** | ADR-0010 explicitly rejects a mirror — the two NVMe drives must stay two independent devices, never RAID members |
| SATA Mode | Settings → IO Ports → SATA Configuration | AHCI | AHCI (unused) | No SATA drives in this build — the NAS is reached over NFS, not SATA. Listed for completeness, not a change |
| Extreme Memory Profile (X.M.P.) | Tweaker | Disabled | **Disabled (confirm)** | No ADR asks for a memory overclock. ADR-0002's binding constraint is RAM capacity, not bandwidth, and stability outranks speed on the single node ADR-0005 already carries a named, accepted power-loss corruption risk for |
| Global C-state Control / AMD Cool'n'Quiet / Power Supply Idle Control | Tweaker → Advanced CPU Settings | Auto / Enabled / Auto | Leave at default | #27 engineers heat and noise at the cooling hardware, not by limiting uptime. Idle CPU power-scaling doesn't compete with that decision — it's free efficiency during the large fraction of each day the box is idle, not a mechanism this project relies on |
| Initial Display Output | Settings → IO Ports | PCIe 1 Slot | PCIe 1 Slot (confirm) | Already the discrete-GPU default. ADR-0003 keeps this output specifically for unattended-boot diagnosis, so it's confirmed rather than assumed |
| LEDs in System Power On State | Settings → Miscellaneous | On | **Off** | Board RGB has no diagnostic value and this box runs 24/7 in an office — light nobody wants overnight is pure downside |
| LEDs in Sleep, Hibernation, and Soft Off States | Settings → Miscellaneous | Off | Off (moot) | Only reachable when the item above is On; with that Off, this one is unreachable and stays at its already-Off default |

## Fan curve (CPU/case fans)

Not itself a consequence of ADR-0003/0010/0005, but the same 24/7-in-an-inhabited-
room posture (#27) applies, and the same headless-box constraint from ADR-0003
bites here too: there's no Windows System Information Viewer running on this box
to tune the "Normal" preset's curve, so BIOS-level Manual mode (Smart Fan 5
screen, manual p. 31) is the only way to get a persistent custom curve at all.

Scope: every case fan is daisy-chained through a hub back to the CPU_FAN header —
one physical group, one curve. The pump runs its own separate regime on its own
header and is out of scope here.

| Smart Fan 5 field | Set to | Why |
| --- | --- | --- |
| Monitor | CPU Fan | The hub's sense wire reports through this header; it's the one group controlling every case fan |
| Fan Speed Control | **Manual** | "Normal" is tuned via Windows-only SIV, which never runs on this headless box (ADR-0003); Manual is the only mode that gives a persistent curve without it |
| Fan Control Use Temperature Input | CPU Temperature | Single best proxy for whole-case heat without per-zone sensors; the live screen exposes other sources the manual doesn't itemize |
| Fan Control Mode | PWM | The manual's own recommendation for a 4-pin header, and deterministic where Auto-detect isn't |
| Fan Stop | **Disabled** | The whole case-airflow group would stop together below the threshold, not just one fan — too coarse a cut for a box carrying a GPU and two NVMe drives 24/7. A steady, quiet floor beats fans cycling on and off, which draws the ear more than constant low noise does |
| Temperature Warning Control | 80°C | Cheap early warning ahead of the 5600X's ~90-95°C thermal ceiling; doesn't gate anything, just an audible flag if the curve below ever falls short |

**Starting curve** (5 points; tune by ear once installed):

| CPU temp | Duty |
| --- | --- |
| ≤ 40°C | 30% |
| 50°C | 40% |
| 60°C | 55% |
| 70°C | 75% |
| ≥ 80°C | 100% |

A silence-first floor (30%, not 0%) instead of Fan Stop's on/off cycling —
continuous low airflow is less noticeable in an office than a fan spinning up and
down. The curve stays flat through the box's ordinary 24/7 baseline (background
containers, metrics scraping) and only climbs for real load (Immich ML, a
`restic` backup run, a `zpool trim`), reaching full speed with headroom before
the CPU's own thermal limit — deliberately, since nobody is in the room at 3 a.m.
to notice a throttle.

## Left to the installing ticket

- **Which physical M.2 socket carries which pool.** ADR-0010 splits system
  pool from state pool by role, not by socket, and leaves exact dataset
  boundaries to whoever installs. #6 already records the two sockets' link
  speeds (CPU-attached at its native Gen4; chipset-attached measured at
  Gen3, 8.0 GT/s) if that later informs the choice.
- **Any AMD CBS / AGESA sub-screen not itemized in the vendor manual.** The
  manual documents it exists but not its contents; visit only if a specific
  setting is later needed.
- **GPU or case-strip lighting, if any.** The BIOS toggle above only reaches
  onboard motherboard LEDs; a discrete GPU's own lighting or third-party ARGB
  strips need their own switch or vendor software, out of BIOS's reach.

## Source

[B550 GAMING X V2 manual, rev. 1101, Chapter 2 "BIOS
Setup"](https://download.gigabyte.com/FileList/Manual/mb_manual_b550-gaming-x-v2_e_1101.pdf),
pp. 20-36.
