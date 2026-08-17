# BIOS/UEFI reference: the server node

**Date: 2026-08-17**

The BIOS/UEFI settings this machine needs, each traced to an accepted ADR —
foundation (ADR-0003), storage (ADR-0010), power (ADR-0005). Not a full BIOS
walkthrough: only the items those three decisions actually bind. Everything
else stays at the board's shipped default. Menu paths, defaults and option
names below are read from the board's own manual ([B550 GAMING X V2 manual,
rev. 1101, Chapter 2 "BIOS
Setup"](https://download.gigabyte.com/FileList/Manual/mb_manual_b550-gaming-x-v2_e_1101.pdf),
pp. 20-36), the only revision that exists as a PDF. The BIOS visit of
2026-08-02 found the machine itself running firmware whose own manual
reference is rev. 1301; no PDF of that revision has been located, and the
menu paths below have not been checked line-by-line against it. Where the two
might diverge, trust the machine over this table.

## Provenance

Every row that is actually a claim about the machine's state carries when and
how that claim was last checked, in one of three classes:

- **Verified from the running OS**: read back from the installed machine
  with a userspace tool (`mokutil`, `efibootmgr`, `dmidecode`, `lsblk`), so a
  BIOS visit isn't needed to re-confirm it.
- **Attested by the operator**: set at the BIOS console on 2026-08-02 and
  confirmed by eye, but not readable from the OS afterwards (for example the
  Platform Power items, the fan and pump curves, and the decision to leave
  the firmware unflashed).
- **Never verified**: proposed by ADR/manual reasoning alone, on neither the
  2026-08-02 visit nor any earlier one. These are the only rows a future BIOS
  visit still needs to settle, and none of them is urgent.

A few rows carry no such claim and sit outside this scheme entirely: one
setting is unused on this build, one is left at its shipped default on
purpose, and one is unreachable while another row gates it. Their "Verified"
cell says so directly rather than forcing a fit into the three classes above.

## Settings

| Setting | Menu path | Ship default | Set to | Why | Verified |
| --- | --- | --- | --- | --- | --- |
| CSM Support | Boot | Enabled | **Disabled** | UEFI-only boot. Required for the GPT ESP the ZFS-root guided `autoinstall` layout creates (ADR-0010); the Secure Boot page is only reachable once this is off | OS, 2026-08-02 (UEFI boot confirmed) |
| Secure Boot | Boot → Secure Boot | (hidden while CSM on) | **Disabled** | ADR-0010 names ZFS "an out-of-tree module" — a DKMS-built `zfs.ko` isn't signed for this board's Secure Boot chain, and ADR-0013's seven-gesture, zero-touch autoinstall has no MOK-enrollment step to sign it | OS, 2026-08-02 (`mokutil --sb-state`) |
| Boot Option Priorities | Boot | none set | System-pool NVMe's `UEFI:` entry, position 1 | The system pool holds the ESP and root (ADR-0010); the state-pool NVMe carries no ESP and must never be a boot candidate | OS, 2026-08-02 (boot entries read back) |
| Fast Boot | Boot | Disabled | Disabled (confirm) | Leaves both NVMe drives and the discrete GPU fully enumerated at every POST. ADR-0003 keeps the GPU's video output specifically "to diagnose a failed boot on a machine that must reboot unattended" — Fast Boot's abbreviated POST works against that | Never verified |
| AC BACK | Settings → Platform Power | Always Off | **Always On** | The machine runs 24/7 (#27, ADR-0005) with no operator on hand to press the power button after an outage. "Memory" (last state) is state-dependent; "Always On" isn't | Operator, 2026-08-02 |
| `ErP` | Settings → Platform Power | Disabled | Disabled (confirm) | Sits directly beside `AC BACK` in the same menu. Enabled, it cuts power in S5 and disables every wake path: one row away from breaking the wake behaviour `AC BACK` exists for | Operator, 2026-08-02 |
| NVMe RAID mode | Settings → IO Ports → SATA Configuration | Disabled | Disabled (confirm) | ADR-0010 explicitly rejects a mirror — the two NVMe drives must stay two independent devices, never RAID members | OS, 2026-08-02 (two independent block devices) |
| SATA Mode | Settings → IO Ports → SATA Configuration | AHCI | AHCI (unused) | No SATA drives in this build — the NAS is reached over NFS, not SATA. Listed for completeness, not a change | N/A, unused |
| Extreme Memory Profile (X.M.P.) | Tweaker | Disabled | **Profile1 (DDR4 3600 CL17)** | Decided on 2026-08-02 and validated on 2026-08-03 by memtest86+ 8.00: 6 passes, 0 errors, 6h30, with this exact profile active. `dmidecode` on the live machine confirms 3600 MT/s configured on all four modules. ADR-0002's binding constraint is RAM capacity, not bandwidth, and stability here is now measured, not merely argued for | OS, 2026-08-02 (`dmidecode`) |
| Motherboard firmware | main BIOS screen (current version) | FB (14/11/2022) | **Do not flash** | A flash resets every setting for no identified benefit. Reopens only if memory proves unstable at 3600 | Operator, 2026-08-02 |
| Global C-state Control / AMD Cool'n'Quiet / Power Supply Idle Control | Tweaker → Advanced CPU Settings | Auto / Enabled / Auto | Leave at default | #27 engineers heat and noise at the cooling hardware, not by limiting uptime. Idle CPU power-scaling doesn't compete with that decision — it's free efficiency during the large fraction of each day the box is idle, not a mechanism this project relies on | Default, unchanged |
| Initial Display Output | Settings → IO Ports | PCIe 1 Slot | PCIe 1 Slot (confirm) | Already the discrete-GPU default. ADR-0003 keeps this output specifically for unattended-boot diagnosis, so it is worth confirming rather than assuming the shipped default holds | Never verified |
| LEDs in System Power On State | Settings → Miscellaneous | On | **Off** | Board RGB has no diagnostic value and this box runs 24/7 in an office — light nobody wants overnight is pure downside | Never verified |
| LEDs in Sleep, Hibernation, and Soft Off States | Settings → Miscellaneous | Off | Off (moot) | Only reachable when the item above is On; with that Off, this one is unreachable and stays at its already-Off default | Moot (gated by the row above) |

## Fan and pump curves

Posed at the BIOS console on 2026-08-02 and already tuned by ear on that
visit, not starting values for later tuning. Attested by the operator, not
readable from the OS afterwards: this board's fan controller exposes no
`fan*_input` or `pwm*` under Linux, so none of it is ever visible to the
running host.

The AIO pump and the radiator fans sit on separate headers with separate
regimes:

| Header | Component | Set to | Why |
| --- | --- | --- | --- |
| `CPU_OPT` (the manual's "Water Cooling CPU Fan Header") | AIO pump | Flat 60% | 85% was audible from the desk. A pump runs at constant flow rather than a curve: varying it buys a degree or two at the cost of a noise that changes on its own |
| `CPU_FAN` | Radiator/case fans, daisy-chained through a hub | 25% @ 40°C, 40% @ 60°C, 60% @ 70°C, 80% @ 80°C, 100% @ 85°C | 280 mm of radiator for a 65 W CPU affords a lazy curve; the ceiling still keeps margin under AMD's ~90-95°C Tjmax |

Every case fan shares the hub's single sense wire back to `CPU_FAN`: one
physical group, one curve. The Smart Fan 5 fields below (Smart Fan 5 screen,
manual p. 31) apply to that group: Manual mode is the only way to get a
persistent custom curve at all, since the "Normal" preset's curve is tuned via
a Windows-only System Information Viewer that never runs on this headless box
(ADR-0003).

| Smart Fan 5 field | Set to | Why |
| --- | --- | --- |
| Monitor | CPU Fan | The hub's sense wire reports through this header; it's the one group controlling every case fan |
| Fan Speed Control | **Manual** | "Normal" is tuned via Windows-only SIV, which never runs on this headless box (ADR-0003); Manual is the only mode that gives a persistent curve without it |
| Fan Control Use Temperature Input | CPU Temperature | Single best proxy for whole-case heat without per-zone sensors; the live screen exposes other sources the manual doesn't itemize |
| Fan Control Mode | PWM | The manual's own recommendation for a 4-pin header, and deterministic where Auto-detect isn't |
| Fan Stop | **Disabled** | The whole case-airflow group would stop together below the threshold, not just one fan — too coarse a cut for a box carrying a GPU and two NVMe drives 24/7. A steady, quiet floor beats fans cycling on and off, which draws the ear more than constant low noise does |
| Temperature Interval | 3-5°C | Hysteresis. A Ryzen 5000 part can spike to 80°C within a fraction of a second under a brief load; without an interval the fans audibly "breathe" in response |
| Temperature Warning Control | 80°C | Cheap early warning ahead of the 5600X's ~90-95°C thermal ceiling; doesn't gate anything, just an audible flag if the curve above ever falls short |

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
pp. 20-36. The machine itself, read at the console on 2026-08-02, reports
firmware manual rev. 1301; no PDF of that revision has been found, so rev.
1101 remains the documentary source for menu paths and shipped defaults
above.
