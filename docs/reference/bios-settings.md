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

## Left to the installing ticket

- **Which physical M.2 socket carries which pool.** ADR-0010 splits system
  pool from state pool by role, not by socket, and leaves exact dataset
  boundaries to whoever installs. #6 already records the two sockets' link
  speeds (CPU-attached at its native Gen4; chipset-attached measured at
  Gen3, 8.0 GT/s) if that later informs the choice.
- **Any AMD CBS / AGESA sub-screen not itemized in the vendor manual.** The
  manual documents it exists but not its contents; visit only if a specific
  setting is later needed.

## Source

[B550 GAMING X V2 manual, rev. 1101, Chapter 2 "BIOS
Setup"](https://download.gigabyte.com/FileList/Manual/mb_manual_b550-gaming-x-v2_e_1101.pdf),
pp. 20-36.
