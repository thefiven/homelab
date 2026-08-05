# What ZFS Costs on Two DRAM-less Consumer NVMe SSDs

**Date: 2026-08-05**

Research note. Establishes, from primary sources only, what running ZFS on this
machine's storage actually costs in RAM and in write amplification. It does not
choose a layout; it ends with the trade-offs and what each option gives up.

## Scope: the hardware this is about

| Item | Value |
| --- | --- |
| Motherboard | Gigabyte B550 GAMING X V2, two M.2 sockets |
| SSDs | 2 x Kingston NV2 1 TB (`SNV2S/1000G`), M.2 2280, PCIe 4.0 x4, DRAM-less |
| RAM | 32 GiB DDR4, hard ceiling — no budget to add more |
| Duty cycle | 24/7 — Immich, Nextcloud, databases, metrics, logs |
| Operator | one person, one machine |

## Source policy

Every claim below cites OpenZFS official documentation or man pages, OpenZFS
upstream source and issues, the Linux kernel source, the NVM Express Base
Specification, Kingston's own datasheet, or the Gigabyte board manual. Where a
question could not be answered from such a source, it is recorded under
[Not established from primary sources](#not-established-from-primary-sources)
rather than filled in from elsewhere. Arithmetic performed on sourced numbers is
labelled **derived**.

---

## 1. ARC memory behaviour on Linux

### 1.1 The default `zfs_arc_max` changed, and the change matters here

`zfs_arc_max` defaults to `0`, which means "derive from installed memory". What
that derivation *is* changed across releases.

- **OpenZFS <= 2.2.x on Linux**: "Max size of ARC in bytes. If **0**, then the max
  size of ARC is determined by the amount of system memory installed. Under
  Linux, half of system memory will be used as the limit. Under FreeBSD, the
  larger of **all_system_memory - 1 GiB** and **5/8 x all_system_memory** will be
  used as the limit."
  ([zfs(4), v2.2](https://openzfs.github.io/openzfs-docs/man/v2.2/4/zfs.4.html))
- **OpenZFS >= 2.3.0, all platforms**: "The larger of **all_system_memory - 1 GiB**
  and **5/8 x all_system_memory** will be used as the limit."
  ([zfs(4), v2.3](https://openzfs.github.io/openzfs-docs/man/v2.3/4/zfs.4.html),
  [zfs(4), master](https://openzfs.github.io/openzfs-docs/man/master/4/zfs.4.html))

OpenZFS's own module-parameter database pins the version explicitly: "Since
v2.3.0 every platform uses the larger of `all_system_memory - 1 GiB` and
`5/8 x all_system_memory`. Before that the platforms differed: **Linux**: half of
system memory; **FreeBSD**: the larger of `all_system_memory - 1 GiB` and
`5/8 x all_system_memory`."
([openzfs-docs `module_parameters.yaml`](https://github.com/openzfs/openzfs-docs/blob/master/docs/module_parameters.yaml))

The upstream source confirms the current formula:

```c
uint64_t
arc_default_max(uint64_t min, uint64_t allmem)
{
	uint64_t size;

	if (allmem >= 1 << 30)
		size = allmem - (1 << 30);
	else
		size = min;
	return (MAX(allmem * 5 / 8, size));
}
```

([`module/os/linux/zfs/arc_os.c`](https://github.com/openzfs/zfs/blob/master/module/os/linux/zfs/arc_os.c))

The change is commit
[`6a629f3`](https://github.com/openzfs/zfs/commit/6a629f32344468ae81b264055916641480cb438d),
"arc_default_max on Linux should match FreeBSD", merged 2023-10-26 via
[PR #15437](https://github.com/openzfs/zfs/pull/15437). Its rationale: the
previous half-of-RAM cap "has become too strict for modern systems with large
amounts of RAM". It was validated on a 256 GB server — not on a 32 GB one.

**Derived, for this machine (32 GiB installed):**

| OpenZFS version | Default ARC ceiling on 32 GiB |
| --- | --- |
| <= 2.2.x | `32 / 2` = **16 GiB** |
| >= 2.3.0 | `max(32 - 1, 32 x 5/8)` = `max(31, 20)` = **31 GiB** |

On a 32 GiB box with a hard ceiling, upgrading from OpenZFS 2.2 to 2.3 nearly
doubles the default ARC ceiling, from half the machine to almost all of it.
**This is the single most consequential default on the list.** The ARC does yield
under memory pressure, but the ceiling is what it will grow to absent pressure.

Note that the OpenZFS Workload Tuning page still says the maximum ARC size "is
half of system memory on Linux"
([Workload Tuning, Synchronous I/O](https://github.com/openzfs/openzfs-docs/blob/master/docs/Performance%20and%20Tuning/Workload%20Tuning.rst)).
That sentence is stale with respect to 2.3.0+; the man page and the source are
authoritative.

### 1.2 The other memory consumers, which are not ARC

- **`zfs_arc_min`** — "If set to **0**, `arc_c_min` will default to consuming the
  larger of **32 MiB** and `all_system_memory / 32`."
  ([zfs(4)](https://openzfs.github.io/openzfs-docs/man/master/4/zfs.4.html))
  **Derived on 32 GiB: 1 GiB floor.** ARC will not be squeezed below this.
- **`zfs_dirty_data_max`** — "Determines the dirty space limit in bytes. Once this
  limit is exceeded, new writes are halted until space frees up. [...] Defaults to
  `physical_ram/10`, capped at `zfs_dirty_data_max_max`", which itself defaults to
  `min(physical_ram/4, 4GiB)`
  ([zfs(4)](https://openzfs.github.io/openzfs-docs/man/master/4/zfs.4.html)).
  **Derived on 32 GiB: 3.2 GiB of in-flight dirty data, on top of ARC.**
- **Host Memory Buffer** — up to 128 MiB of host RAM *per NVMe controller* by
  default, so up to 256 MiB for two drives. See [section 4](#4-dram-less-ssds-and-host-memory-buffer).
- **L2ARC would make this worse, not better** — "**L2ARC costs RAM.** Every cached
  block needs a header in the ARC, so an oversized L2ARC shrinks the cache that
  actually matters. On a RAM-constrained system an L2ARC can make things slower."
  ([Caching and Auxiliary Devices](https://github.com/openzfs/openzfs-docs/blob/master/docs/Basic%20Concepts/Pool%20Structure/Caching.rst))

### 1.3 How to cap it

Persistently, via modprobe — OpenZFS documents the format:

```
# /etc/modprobe.d/zfs.conf
# change PARAMETER for workload XZY to solve problem PROBLEM_DESCRIPTION
# changed by YOUR_NAME on DATE
options zfs PARAMETER=VALUE
```

([Module Parameters intro](https://github.com/openzfs/openzfs-docs/blob/master/docs/Performance%20and%20Tuning/_module_parameters_intro.rst);
the OpenZFS FAQ uses exactly this form for ARC, e.g.
`options zfs zfs_arc_max=6442450944` —
[FAQ](https://github.com/openzfs/openzfs-docs/blob/master/docs/Project%20and%20Community/FAQ.rst))

At runtime, via `/sys/module/zfs/parameters/zfs_arc_max`, with documented caveats:

> This value can be changed dynamically, with some caveats. It cannot be set back
> to **0** while running, and reducing it below the current ARC size will not cause
> the ARC to shrink without memory pressure to induce shrinking.

([zfs(4)](https://openzfs.github.io/openzfs-docs/man/master/4/zfs.4.html))

The floor is hard: "This value must be at least **67108864** B (64 MiB)"
([zfs(4)](https://openzfs.github.io/openzfs-docs/man/master/4/zfs.4.html)).

Verification is documented as the `c` column of `zarcstat` (`arcstat` before
2.4.0) or the `c_max` entry in `/proc/spl/kstat/zfs/arcstats`
([`module_parameters.yaml`](https://github.com/openzfs/openzfs-docs/blob/master/docs/module_parameters.yaml)).

### 1.4 What officially happens when it is capped hard

There is **no quantified upstream statement** of the performance cost of a given
ARC cap. What upstream does say:

- "RAM is by far the most effective ZFS 'tuning knob'. Before adding any cache
  device, check whether the ARC is simply too small."
  ([Caching](https://github.com/openzfs/openzfs-docs/blob/master/docs/Basic%20Concepts/Pool%20Structure/Caching.rst))
- The documented decision rule for `zfs_arc_max` is qualitative: "Reduce if ARC
  competes too much with other applications, increase if ZFS is the primary
  application and can use more RAM."
  ([`module_parameters.yaml`](https://github.com/openzfs/openzfs-docs/blob/master/docs/module_parameters.yaml))
- Per-dataset relief exists without a global cap: `primarycache=metadata` on
  datasets whose data is not worth caching
  ([zfsprops(7)](https://openzfs.github.io/openzfs-docs/man/master/7/zfsprops.7.html),
  [Caching](https://github.com/openzfs/openzfs-docs/blob/master/docs/Basic%20Concepts/Pool%20Structure/Caching.rst)).

### 1.5 A live caveat on the 2.3.x series

[Issue #17052](https://github.com/openzfs/zfs/issues/17052), "ZFS 2.3.0 ignores
`zfs_arc_max`, exhausts system memory" — ARC observed at roughly 4.6 GB on a
16 GB system with `zfs_arc_max` set to 2 GB; 2.2.6 did not do this. Closed by
[PR #17542](https://github.com/openzfs/zfs/pull/17542) ("enforce
arc_dnode_limit", merged 2025-07-21), which fixes
[#17487](https://github.com/openzfs/zfs/issues/17487) — the dnode cache growing
past quota and not shrinking under memory pressure.

**Verified against the upstream tags:** the fix commit
[`a7a144e`](https://github.com/openzfs/zfs/commit/a7a144e655850b4160943e4ba315eb9a5dc2b2fe)
is an ancestor of `zfs-2.4.0` but **not** of `zfs-2.3.4`. On the 2.3.x series, a
hard `zfs_arc_max` is therefore not a guarantee of total ZFS memory use. On a
machine whose RAM ceiling is the binding constraint, that matters.

---

## 2. Write amplification

### 2.1 `ashift` — immutable, and the cost of getting it wrong is documented but not quantified

> Top-level vdevs contain an internal property called ashift, which stands for
> alignment shift. **It is set at vdev creation and it is immutable.** [...] This
> makes 2^ashift the smallest possible IO on a vdev. **Configuring ashift correctly
> is important because partial sector writes incur a penalty where the sector must
> be read into a buffer before it can be written.** ZFS makes the implicit
> assumption that the sector size reported by drives is correct and calculates
> ashift based on that.

([Workload Tuning, Alignment Shift](https://github.com/openzfs/openzfs-docs/blob/master/docs/Performance%20and%20Tuning/Workload%20Tuning.rst))

Drives misreport. Upstream is blunt about NAND flash:

> NAND flash SSDs **should** report these pages as being sectors, but so far, all
> of them incorrectly report 512-byte sectors for Windows XP compatibility.

([Hardware, Flash pages](https://github.com/openzfs/openzfs-docs/blob/master/docs/Performance%20and%20Tuning/Hardware.rst))

The current recommendation, same page:

> As of 2017, NAND-flash SSDs are tuned for 4096-byte IOs. Matching the flash page
> size is unnecessary and **ashift=12 is usually the correct choice**. Public
> documentation on flash page size is also nearly non-existent.

For NVMe specifically, upstream recommends fixing the problem below ZFS, by
low-level formatting:

> Many NVMe SSDs support both 512-byte sectors and 4096-byte sectors. They often
> ship with 512-byte sectors, which are less performant than 4096-byte sectors.
> [...] NVMe drives should be formatted to use 4096-byte sectors without metadata
> prior to being given to ZFS for best performance [...] Lower numbers in the
> Rel_Perf of Supported LBA Sizes from `smartctl -a /dev/$device_namespace` [...]
> indicate higher performance low level formats, with 0 being the best. [...] You
> may format a drive using `nvme format /dev/nvme1n1 -l $ID`.

([Hardware, NVMe low level formatting](https://github.com/openzfs/openzfs-docs/blob/master/docs/Performance%20and%20Tuning/Hardware.rst))

`zpoolprops(7)` adds the operational constraints: "Values from 9 to 16, inclusive,
are valid; also, the value 0 (the default) means to auto-detect using the kernel's
block layer and a ZFS internal exception list. [...] **Changing this value will not
modify any existing vdev, not even on disk replacement**"
([zpoolprops(7)](https://openzfs.github.io/openzfs-docs/man/master/7/zpoolprops.7.html)).
The exception list is
[`cmd/zpool/os/linux/zpool_vdev_os.c`](https://github.com/openzfs/zfs/blob/master/cmd/zpool/os/linux/zpool_vdev_os.c);
upstream notes it "is unable to fully compensate for misreported sector sizes
whenever drive identifiers are used ambiguously (e.g. virtual machines, iSCSI
LUNs, some rare SSDs)"
([Workload Tuning](https://github.com/openzfs/openzfs-docs/blob/master/docs/Performance%20and%20Tuning/Workload%20Tuning.rst)).

**No primary source quantifies the write amplification from a wrong `ashift`.**
The documented cost is a read-modify-write per partial sector, described but not
measured. What *is* certain from the sources: it cannot be corrected after vdev
creation, and it must be decided before the pool exists.

### 2.2 `recordsize` and small random writes — the one number upstream gives

The only quantified amplification figure in OpenZFS documentation:

> Bit torrent performs 16KB random reads/writes. **The 16KB writes cause
> read-modify-write overhead. The read-modify-write overhead can reduce performance
> by a factor of 16 with 128KB record sizes when the amount of data written exceeds
> system memory.** This can be avoided by using a dedicated dataset for bit torrent
> downloads with recordsize=16KB.

([Workload Tuning, Bit Torrent](https://github.com/openzfs/openzfs-docs/blob/master/docs/Performance%20and%20Tuning/Workload%20Tuning.rst))

That "factor of 16" is a **performance** factor, not a bytes-written factor. The
bytes-written factor is a separate, smaller number: **derived**, a 16 KiB
modification inside a 128 KiB record causes the whole 128 KiB record to be
rewritten, i.e. **8x the logical write volume** (128/16). Both matter; they are
not the same number and the sources only state the first.

Upstream's per-workload record sizes, all from
[Workload Tuning, Database workloads](https://github.com/openzfs/openzfs-docs/blob/master/docs/Performance%20and%20Tuning/Workload%20Tuning.rst):

| Workload | Documented setting |
| --- | --- |
| MySQL / InnoDB data files | `recordsize=16K`, `primarycache=metadata`, `logbias=throughput`; leave logs at 128K |
| PostgreSQL | `recordsize=32K` ("64K also work well, as does the 128K default"), `compression=lz4` |
| SQLite | `recordsize=64K` and SQLite page size 65536 |
| 16 KiB random-write workloads | dedicated dataset at `recordsize=16K` |

And the warning that cuts the other way — `recordsize` is not a free knob:

> Use of this property for general purpose file systems is strongly discouraged,
> and may adversely affect performance. [...] Changing the file system's
> `recordsize` **affects only files created afterward; existing files are
> unaffected.**

([zfsprops(7)](https://openzfs.github.io/openzfs-docs/man/master/7/zfsprops.7.html))

For this box that maps cleanly: Postgres/MariaDB backing Immich and Nextcloud
belong on their own datasets with a matched `recordsize`; the photo and file
blobs do not, and should stay at the 128 KiB default.

### 2.3 `atime` / `relatime` — a write per file read, per day

Defaults: `atime=on`, and `relatime=on`
([zfsprops(7)](https://openzfs.github.io/openzfs-docs/man/master/7/zfsprops.7.html)).

> **atime** — Controls whether the access time for files is updated when they are
> read. **Turning this property off avoids producing write traffic when reading
> files and can result in significant performance gains**, though it might confuse
> mailers and other similar utilities. [...] The default value is **on**.

> **relatime** — [...] Access time is only updated if the previous access time was
> earlier than the current modify or change time **or if the existing access time
> hasn't been updated within the past 24 hours**. The default value is **on**.

([zfsprops(7)](https://openzfs.github.io/openzfs-docs/man/master/7/zfsprops.7.html))

Upstream's tuning advice:

> Set either `relatime=on` or `atime=off` to minimize IOs used to update access
> time stamps. For backward compatibility with a subset of software that supports
> it, relatime is preferred when available and should be set on your entire pool.
> `atime=off` should be used more selectively.

([Workload Tuning, atime updates](https://github.com/openzfs/openzfs-docs/blob/master/docs/Performance%20and%20Tuning/Workload%20Tuning.rst))

**Derived:** the default is *not* "no atime writes". It is "at most one metadata
write per file per 24 hours". A photo library that a client walks daily turns
that into one metadata write per photo per day. `atime=off` is the only setting
that removes it entirely.

### 2.4 Metadata redundancy — every metadata block is written twice, before the mirror

> ZFS stores an extra copy of metadata, so that if a single block is corrupted, the
> amount of user data lost is limited. **This extra copy is in addition to any
> redundancy provided at the pool level (e.g. by mirroring or RAID-Z)** [...] When
> set to **all**, ZFS stores an extra copy of all metadata. [...] **The default value
> is all.**

> When set to **most**, ZFS stores an extra copy of most types of metadata. **This
> can improve performance of random writes, because less metadata must be written.**
> In practice, at worst about 1000 blocks (of `recordsize` bytes each) of user data
> can be lost if a single on-disk block is corrupt.

([zfsprops(7), `redundant_metadata`](https://openzfs.github.io/openzfs-docs/man/master/7/zfsprops.7.html))

Upstream's own example is explicit that the multipliers stack: "if the pool is
mirrored, `copies=2`, and `redundant_metadata=most`, then ZFS stores **6 copies**
of most metadata, and 4 copies of data and some metadata."

**Derived, for a 2-way mirror at defaults (`copies=1`, `redundant_metadata=all`):
each logical data block hits flash twice (once per mirror member); each metadata
block hits flash four times (2 ditto copies x 2 mirror members).**

Upstream quantifies the relief only vaguely: `redundant_metadata=most` "can
increase IOPS by at least a few percentage points"
([Workload Tuning, Database workloads](https://github.com/openzfs/openzfs-docs/blob/master/docs/Performance%20and%20Tuning/Workload%20Tuning.rst)).

### 2.5 ZIL — synchronous writes are written twice

The ZIL exists on every pool whether or not a `log` vdev is configured:

> The ZFS Intent Log satisfies POSIX durability requirements: `fsync()` and
> `O_SYNC` writes must be on stable storage before the call returns. **The ZIL
> exists on every pool — by default it is allocated from blocks in the main pool.**
> [...] **A SLOG is not a write cache.** Asynchronous writes never touch the ZIL;
> they are aggregated in memory and written out at the next transaction group.

([Caching](https://github.com/openzfs/openzfs-docs/blob/master/docs/Basic%20Concepts/Pool%20Structure/Caching.rst))

The size threshold is a documented tunable:

> `zfs_immediate_write_sz=32768B (32 KiB)` — Largest write size to store the data
> **directly into the ZIL** if `logbias=latency`. Larger writes may be written
> indirectly similar to `logbias=throughput`.

([zfs(4)](https://openzfs.github.io/openzfs-docs/man/master/4/zfs.4.html))

**Derived:** with the default `logbias=latency`, a synchronous write of <= 32 KiB
is written into the ZIL *and* again into the pool at the next transaction group —
**2x on flash for that data**, then doubled again by the mirror. Upstream's own
remedy, for database data files: "Set `logbias=throughput` on the data **to stop
ZIL from writing twice**"
([Workload Tuning](https://github.com/openzfs/openzfs-docs/blob/master/docs/Performance%20and%20Tuning/Workload%20Tuning.rst)).

`sync=disabled` "skips the ZIL entirely, trading recent-write durability for
speed"
([Caching](https://github.com/openzfs/openzfs-docs/blob/master/docs/Basic%20Concepts/Pool%20Structure/Caching.rst)) —
which is a data-loss decision, not a tuning decision.

### 2.6 What works in the other direction

- **Transaction group coalescing.** `zfs_txg_timeout=5s` — "Flush dirty data to
  disk at least every this many seconds (maximum TXG duration)"
  ([zfs(4)](https://openzfs.github.io/openzfs-docs/man/master/4/zfs.4.html)).
  Repeated writes to the same block within a 5-second window collapse into one
  flash write. This is a real and large reduction for log and metrics workloads.
- **Compression is on by default and reduces bytes written.** "Since OpenZFS 2.2.0
  `compression` defaults to `on`, which selects LZ4"; LZ4 "averages a 2.1:1
  compression ratio"
  ([Workload Tuning, Compression](https://github.com/openzfs/openzfs-docs/blob/master/docs/Performance%20and%20Tuning/Workload%20Tuning.rst)).
  That ratio is a general average, not a claim about already-compressed JPEGs and
  video, which will not compress.
- **I/O aggregation.** `zfs_vdev_aggregation_limit_non_rotating=131072B (128 KiB)`
  ([zfs(4)](https://openzfs.github.io/openzfs-docs/man/master/4/zfs.4.html)).

### 2.7 TRIM — and the one line upstream writes about cheap drives

> `autotrim` [...] **The default value for this property is off.** [...] **Be aware
> that automatic trimming of recently freed data blocks can put significant stress
> on the underlying storage devices.** This will vary depending of how well the
> specific device handles these commands. **For lower-end devices it is often
> possible to achieve most of the benefits of automatic trimming by running an
> on-demand (manual) TRIM periodically.**

([zpoolprops(7)](https://openzfs.github.io/openzfs-docs/man/master/7/zpoolprops.7.html))

This is the closest thing in OpenZFS documentation to guidance aimed at consumer
drives, and it points at scheduled `zpool trim` rather than `autotrim=on`.

---

## 3. The PCIe 4.0 / 3.0 asymmetry between the two M.2 sockets

### 3.1 What the board manual states

> **Storage Interface** — 1 x M.2 connector (**M2A_CPU**), integrated in the CPU,
> supporting Socket 3, M key, type 2242/2260/2280/22110 SSDs:
> - 3rd Generation AMD Ryzen processors support SATA and **PCIe 4.0 x4/x2** SSDs
> - 3rd Generation AMD Ryzen with Radeon Graphics processors support SATA and
>   PCIe 3.0 x4/x2 SSDs
>
> 1 x M.2 connector (**M2B_SB**), integrated in the **Chipset**, supporting Socket 3,
> M key, type 2242/2260/2280/22110 SSDs:
> - Supporting SATA and **PCIe 3.0 x4/x2** SSDs
>
> 4 x SATA 6Gb/s connectors, integrated in the Chipset

([B550 GAMING X V2 manual, rev. 1101, p. 6](https://download.gigabyte.com/FileList/Manual/mb_manual_b550-gaming-x-v2_e_1101.pdf))

Two consequences that are easy to get wrong:

1. **The first socket's speed depends on the CPU.** PCIe 4.0 x4 on M2A_CPU
   requires a non-APU Ryzen. With a Ryzen with Radeon Graphics (an APU), M2A_CPU
   is PCIe 3.0 x4 — and the asymmetry disappears entirely, because both sockets
   are then Gen 3.
2. **M2B_SB is behind the chipset**, as are all four SATA ports and most USB.

### 3.2 SATA lane sharing: a negative finding

**The manual states no SATA-port disabling or lane-sharing footnote for either
M.2 socket.** The specification page lists 2 x M.2 and 4 x SATA 6Gb/s
unconditionally, and the connector section for `M2A_CPU/M2B_SB` says only:

> The M.2 connectors support M.2 SATA SSDs or M.2 PCIe SSDs and support RAID
> configuration. Please note that an M.2 PCIe SSD cannot be used to create a RAID
> set either with an M.2 SATA SSD or a SATA hard drive.

([B550 GAMING X V2 manual, rev. 1101, p. 20](https://download.gigabyte.com/FileList/Manual/mb_manual_b550-gaming-x-v2_e_1101.pdf))

A full-text search of the manual for lane-sharing language ("unavailable",
"disabled when", "shared") returns nothing relating M.2 population to SATA
availability. **Populating both M.2 sockets with NVMe drives does not, per the
manual, cost any SATA port on this board.** Verify against the manual revision
matching your board revision (this is rev. 1101; the board ships as rev.
1.0/1.1/1.2, 1.3 and 1.4).

Separately: M2B_SB and all four SATA ports are chipset-attached, so they share
the chipset's uplink to the CPU. The Gigabyte manual does not state the uplink's
width or generation, and this note does not assert one.

### 3.3 What a mirror's write throughput is actually bounded by

From the OpenZFS source, the mirror write path:

```c
} else {
	ASSERT(zio->io_type == ZIO_TYPE_WRITE);

	/*
	 * Writes go to all children.
	 */
	c = 0;
	children = mm->mm_children;
}
```

([`module/zfs/vdev_mirror.c`](https://github.com/openzfs/zfs/blob/master/module/zfs/vdev_mirror.c))

Every child write is issued as a child zio and the parent does not complete until
all children have; on completion, "Always require at least one good copy" governs
error handling, not sequencing (same file). **A mirror write is therefore bounded
by its slowest member.** There is no write-side load balancing to bypass a slow
member.

Reads are different: mirror reads pick one child by *queue length*, not by link
speed —

```c
/* Standard load based on pending queue length. */
load = vdev_queue_length(vd);
```

with `zfs_vdev_mirror_non_rotating_inc = 0` and
`zfs_vdev_mirror_non_rotating_seek_inc = 1` for non-rotating media
([`vdev_mirror.c`](https://github.com/openzfs/zfs/blob/master/module/zfs/vdev_mirror.c),
[zfs(4)](https://openzfs.github.io/openzfs-docs/man/master/4/zfs.4.html)).
**ZFS has no notion of PCIe link speed when selecting a mirror child.** Both
members will receive roughly equal read load even if one has half the link
bandwidth.

### 3.4 Whether any of this binds — the arithmetic

Linux's PCI subsystem encodes the per-lane rates:

```c
#define PCIE_SPEED2MBS_ENC(speed) \
	((speed) == PCIE_SPEED_64_0GT ? 64000*1/1 : \
	 (speed) == PCIE_SPEED_32_0GT ? 32000*128/130 : \
	 (speed) == PCIE_SPEED_16_0GT ? 16000*128/130 : \
	 (speed) == PCIE_SPEED_8_0GT  ?  8000*128/130 : \
	 (speed) == PCIE_SPEED_5_0GT  ?  5000*8/10 : \
	 (speed) == PCIE_SPEED_2_5GT  ?  2500*8/10 : \
	 0)
```

([`drivers/pci/pci.h`](https://github.com/torvalds/linux/blob/master/drivers/pci/pci.h))

**Derived:**

| Link | Encoded per lane | x4 |
| --- | --- | --- |
| PCIe 3.0 (8 GT/s) | 7,877 Mb/s | ~3,938 MB/s |
| PCIe 4.0 (16 GT/s) | 15,754 Mb/s | ~7,877 MB/s |

Kingston's datasheet for this drive:

> Sequential Read/Write — 250GB – 3,000/1,300MB/s; 500GB – 3,500/2,100MB/s;
> **1TB – 3,500/2,100MB/s**; 2TB - 4TB – 3,500/2,800MB/s

([Kingston NV2 datasheet, `SNV2S_us.pdf`](https://www.kingston.com/datasheets/SNV2S_us.pdf))

**The 1 TB NV2's own peak sequential write is 2,100 MB/s — roughly 53% of a
PCIe 3.0 x4 link.** The Gen 3 socket is therefore **not** the binding constraint
on this mirror's write throughput; the drive is. The Gen 4 socket buys nothing
for writes on a 1 TB NV2, and about 3,500 MB/s of read ceiling that Gen 3 also
covers.

The asymmetry that *does* remain is latency and queueing behind the chipset for
M2B_SB, which the primary sources do not quantify.

---

## 4. DRAM-less SSDs and Host Memory Buffer

### 4.1 What Kingston's own documentation states — and does not

The complete specification list from the datasheet:

> Form Factor: M.2 2280. Interface: PCIe 4.0 x4 NVMe. Capacities: 250GB, 500GB,
> 1TB, 2TB, 4TB. Sequential Read/Write: 1TB – 3,500/2,100MB/s. Nand: **3D**.
> Endurance (Total Bytes Written): **1TB – 320TB**. Storage Temperature:
> -40C~85C. Operating Temperature: **0C~70C**. MTBF: 2,000,000 hours.
> Warranty/Support: Limited 3-year warranty with free technical support.

And the footnotes:

> **This SSD is designed for use in desktop and notebook computer workloads and is
> not intended for Server environments.**
>
> 1. Based on "out-of-box performance" using a PCIe 4.0 motherboard. Speed may
>    vary due to host hardware, software, and usage.
> 3. Total Bytes Written (TBW) is derived from the **JEDEC Client Workload
>    (JESD219A)**.
> 4. Limited warranty based on **3 years or "Percentage Used"** [...] For NVMe SSDs,
>    a new unused product will show a Percentage Used value of 0, whereas a product
>    that reaches its warranty limit will show a Percentage Used value of greater
>    than or equal to one hundred (100).

([Kingston NV2 datasheet, `SNV2S_us.pdf`, MKD-453.3 US](https://www.kingston.com/datasheets/SNV2S_us.pdf))

Three things follow directly:

1. **Kingston states the drive is not intended for server environments.** A 24/7
   homelab hosting databases, metrics and logs is closer to that than to "desktop
   and notebook computer workloads". This is a first-party statement about fitness
   for purpose, not an opinion.
2. **The 2,100 MB/s figure is explicitly "out-of-box performance"** — Kingston
   scopes it to a fresh drive, and disclaims variation by usage.
3. **The warranty is 3 years *or* `Percentage Used` >= 100, whichever comes first.**
   Kingston ties the warranty directly to the NVMe SMART field.

**The datasheet says nothing about DRAM, nothing about Host Memory Buffer, nothing
about an SLC cache, and nothing about sustained or steady-state write speed after
cache exhaustion.** No controller model is named. The NAND is described only as
"3D". Kingston's product support page could not be retrieved (HTTP 403 to
automated clients), so a wider first-party search was not possible.

**The collapse of sustained write performance after SLC cache exhaustion on this
drive is not established from primary sources.** It is a real phenomenon for
DRAM-less consumer SSDs generally, but Kingston publishes no figure for it, and
none of the permitted sources supply one. Treat any specific number you have seen
for the NV2 as unsourced.

### 4.2 What Host Memory Buffer actually does — from the spec and the kernel

From the NVM Express Base Specification:

> The Host Memory Buffer feature provides a mechanism for the host to allocate a
> portion of host memory **for the exclusive use of the controller**. After a
> successful completion of a Set Features command enabling the host memory buffer,
> the host shall not write to [...] the associated host memory region [...] until the
> host memory buffer has been disabled.

> The Host Memory Buffer (HMB) feature allows the controller to utilize an assigned
> portion of host memory exclusively. **The use of the host memory resources is
> vendor specific.** The host may not be able to provide any or a limited amount of
> the host memory resources requested by the controller. **The controller shall
> function properly without host memory resources.**

> The host memory resources are **not persistent** in the controller across a
> Controller Level Reset.

> The controller shall ensure that there is **no data loss or data corruption in the
> event of a surprise removal** while the Host Memory Buffer feature is being
> utilized.

([NVM Express Base Specification, Revision 2.3, sections 5.2.26.2.4 and 8.2.3](https://nvmexpress.org/wp-content/uploads/NVM-Express-Base-Specification-Revision-2.3-2025.08.01-Ratified.pdf))

Read those together and the answer to "does HMB compensate for the missing DRAM"
is: **the specification does not say what HMB is used for.** It is vendor
specific. It is explicitly optional and the drive must work without it. It is
explicitly not a place where data may be lost on surprise removal — which is a
strong hint that it is not a write buffer — but the spec never states what it
*is* a buffer for. Any claim that the NV2's HMB caches the FTL mapping table is
not sourceable from the spec or from Kingston.

Under Linux, the size is capped by the kernel, not by the drive:

```c
static unsigned int max_host_mem_size_mb = 128;
module_param(max_host_mem_size_mb, uint, 0444);
MODULE_PARM_DESC(max_host_mem_size_mb,
	"Maximum Host Memory Buffer (HMB) size per controller (in MiB)");
```

and HMB is skipped entirely for a controller that does not request it:

```c
if (!dev->ctrl.hmpre)
	return 0;
```

([`drivers/nvme/host/pci.c`](https://github.com/torvalds/linux/blob/master/drivers/nvme/host/pci.c))

**Derived, for this machine: up to 128 MiB of RAM per drive, so up to 256 MiB for
two, taken from the 32 GiB budget before ZFS sees it.** The kernel logs the actual
figure at probe: `allocated %lld MiB host memory buffer (%u segment%s)`
([same file](https://github.com/torvalds/linux/blob/master/drivers/nvme/host/pci.c)),
so the real cost is measurable with `dmesg | grep -i "host memory buffer"`. The
parameter is `0444` — read-only at runtime; changing it requires a module
parameter at load time.

---

## 5. Endurance arithmetic

### 5.1 The two fields, defined

> **Percentage Used (PUSED)**: Contains a **vendor specific estimate** of the
> percentage of NVM subsystem life used based on the actual usage and the
> manufacturer's prediction of NVM life. A value of 100 indicates that the
> estimated endurance of the NVM in the NVM subsystem has been consumed, but may
> not indicate an NVM subsystem failure. **The value is allowed to exceed 100.**
> Percentages greater than 254 shall be represented as 255. **This value shall be
> updated once per power-on hour** (when the controller is not in a sleep state).
> Refer to the JEDEC JESD218B-02 standard for SSD device life and endurance
> measurement techniques.

> **Data Units Written (DUW)**: Contains the number of **512 byte data units** the
> host has written to the controller as part of processing a User Data Out Command;
> this value does not include metadata. **This value is reported in thousands**
> (i.e., a value of 1 corresponds to 1,000 units of 512 bytes written) and is
> rounded up.

([NVM Express Base Specification, Revision 2.3, Figure 210: SMART / Health Information Log Page](https://nvmexpress.org/wp-content/uploads/NVM-Express-Base-Specification-Revision-2.3-2025.08.01-Ratified.pdf))

`nvme-cli` reads exactly this log page — "Retrieves the NVMe SMART log page from an
NVMe device"
([`nvme-smart-log.txt`](https://github.com/linux-nvme/nvme-cli/blob/master/Documentation/nvme-smart-log.txt)) —
and converts with the same constant, `1000 * 512`:

```c
uint128_t_to_si_string(le128_to_cpu(smart->data_units_written), 1000 * 512);
```

([`nvme-print-stdout.c`](https://github.com/linux-nvme/nvme-cli/blob/master/nvme-print-stdout.c))

**So: 1 Data Unit Written = 512,000 bytes.**

```
bytes_written = data_units_written x 512000
TB_written    = data_units_written / 1953125
```

### 5.2 The field that exposes the drive's own write amplification

The SMART log's DUW counts *host* writes. The drive's internal amplification —
SLC folding, garbage collection — is invisible there. The Endurance Group
Information log page exposes both sides:

> **Data Units Written (DUW)**: Contains the total number of data bytes that have
> been written to the Endurance Group. **This value does not include controller
> writes due to internal operations such as garbage collection.**

> **Media Units Written (MUW)**: Contains the total number of data bytes that have
> been written to the Endurance Group **including both host and controller writes
> (e.g., garbage collection).**

([NVM Express Base Specification, Revision 2.3, Figure 222: Endurance Group Information Log Page](https://nvmexpress.org/wp-content/uploads/NVM-Express-Base-Specification-Revision-2.3-2025.08.01-Ratified.pdf))

**MUW / DUW is the drive's measured write amplification factor**, if the drive
reports it — "A value of 0h indicates that controller does not report the number
of Media Units Written" (same page). Whether this NV2 reports it is an empirical
question answerable on the machine with `nvme endurance-log`, and is worth
checking early: it is the only way to see the flash-side cost of a DRAM-less
controller without vendor documentation.

The same page defines the drive's own honest lifetime figure:

> **Endurance Estimate (EE)**: This field is an estimate of the total number of data
> bytes that may be written to the Endurance Group over the lifetime of the
> Endurance Group **assuming a write amplification of 1**.

### 5.3 What 320 TBW tolerates

Kingston: 1 TB NV2 = **320 TB** TBW, per JEDEC Client Workload JESD219A, and
warranty ends at 3 years or `Percentage Used` >= 100
([datasheet](https://www.kingston.com/datasheets/SNV2S_us.pdf)).

**Derived** (320 TB decimal = 320,000 GB; years of 365.25 days):

| Sustained daily writes **per drive** | Lifetime to 320 TBW |
| --- | --- |
| 30 GB/day | 29.2 years |
| 50 GB/day | 17.5 years |
| 87.6 GB/day | **10.0 years** |
| 100 GB/day | 8.8 years |
| 150 GB/day | 5.8 years |
| **175.2 GB/day** | **5.0 years** |
| 292 GB/day | 3.0 years (= the warranty term) |
| 500 GB/day | 1.8 years |

Read the other way:

- **5-year target: 175 GB/day per drive.**
- **10-year target: 88 GB/day per drive.**

**The mirror does not halve this.** Writes go to all children
([`vdev_mirror.c`](https://github.com/openzfs/zfs/blob/master/module/zfs/vdev_mirror.c)),
so **each** drive in a 2-way mirror absorbs the full pool write stream. The
budget above is the pool's write budget, not half of it. Two independent
single-disk pools split the stream instead, so each drive sees only its own
share.

And the budget is consumed by *amplified* writes, not application writes. The
amplifiers from [section 2](#2-write-amplification), all multiplicative on the
paths where they apply: partial-record rewrites (up to 8x on 16 KiB writes at the
128 KiB default), metadata written twice by `redundant_metadata=all`, sync data
written twice via the ZIL, one metadata write per file per day from `relatime`,
plus the drive's own internal amplification which DUW does not show.

### 5.4 Measuring it on the machine

```
nvme smart-log /dev/nvme0    # data_units_written, percentage_used, power_on_hours
nvme endurance-log /dev/nvme0 # data_units_written vs media_units_written, endurance_estimate
```

([`nvme-smart-log(1)`](https://github.com/linux-nvme/nvme-cli/blob/master/Documentation/nvme-smart-log.txt))

Two cautions from the spec itself: `Percentage Used` is a **vendor specific
estimate**, updated **once per power-on hour**, and is an integer — one percentage
point is 3.2 TB on this drive (**derived**), so it is far too coarse to trend in
the first months. `data_units_written` is the field to baseline now and delta
later.

---

## 6. Mirror vs. two independent single-disk pools

### 6.1 What a mirror gives

> **mirror** — A mirror of two or more devices. Data is replicated in an identical
> fashion across all components of a mirror. **A mirror with N disks of size X can
> hold X bytes and can withstand N-1 devices failing, without losing data.**

> All metadata and data is checksummed, and **ZFS automatically repairs bad data
> from a good copy, when corruption is detected.**

([zpoolconcepts(7)](https://openzfs.github.io/openzfs-docs/man/master/7/zpoolconcepts.7.html))

That second sentence is the part that a pair of independent pools cannot
reproduce. On a single-disk pool, ZFS still *detects* corruption via checksums —
but with no second copy, detection is all it can do (except for metadata, which
`redundant_metadata=all` still duplicates within the one disk).

### 6.2 What a mirror does not give

> Redundancy in ZFS lives **inside** a top-level vdev, not across them. [...] The
> corollary matters more than the rule: **if a top-level vdev is lost, the pool is
> lost.** Because data is striped across all top-level vdevs, there is no copy of
> its contents anywhere else. A single non-redundant disk added to an otherwise
> mirrored pool therefore puts the entire pool at the mercy of that one disk.

([VDEVs](https://github.com/openzfs/openzfs-docs/blob/master/docs/Basic%20Concepts/Pool%20Structure/VDEVs.rst))

Two consequences for the two-drive case:

- A mirror is one fault domain of two identical drives, bought together, aged
  together, and — because writes go to all children — **worn at the same rate by
  the same write stream**. Correlated wear-out is not something the mirror
  protects against.
- Two independent single-disk pools are two fault domains. Losing one loses that
  pool's data and only that pool's data. But adding both disks to *one* pool as
  two separate top-level vdevs is the worst of both: no redundancy, and either
  disk's death kills everything.

**No primary source was found comparing a mirror against two independent
single-disk pools as a recommendation.** OpenZFS documents the mechanics of each;
it does not publish guidance for the two-drive single-operator case.

### 6.3 Structural asymmetry: what can be undone later

- `zpool attach` widens a mirror; `zpool add` adds a top-level vdev
  ([VDEVs](https://github.com/openzfs/openzfs-docs/blob/master/docs/Basic%20Concepts/Pool%20Structure/VDEVs.rst)).
  So a single-disk pool can later become a mirror by attaching the second drive —
  the reverse is also possible via `zpool detach`.
- `ashift` cannot be changed later, at all: "It is set at vdev creation and it is
  immutable" and "Changing this value will not modify any existing vdev, not even
  on disk replacement"
  ([Workload Tuning](https://github.com/openzfs/openzfs-docs/blob/master/docs/Performance%20and%20Tuning/Workload%20Tuning.rst),
  [zpoolprops(7)](https://openzfs.github.io/openzfs-docs/man/master/7/zpoolprops.7.html)).
- `recordsize` changes "affect only files created afterward; existing files are
  unaffected"
  ([zfsprops(7)](https://openzfs.github.io/openzfs-docs/man/master/7/zfsprops.7.html)).

**The pool topology is the reversible decision. `ashift` and per-dataset
`recordsize` are the ones that are not.**

---

## 7. Official guidance on consumer DRAM-less SSDs

**There is none, and that is a finding.**

- The OpenZFS Hardware page has extensive sections on NAND flash SSDs, flash
  pages, TRIM, low-level formatting, Optane, and power-failure protection. **The
  string "DRAM" appears nowhere in it** in the sense of an SSD cache, and there is
  no consumer/enterprise SSD recommendation beyond power-loss protection
  ([Hardware](https://github.com/openzfs/openzfs-docs/blob/master/docs/Performance%20and%20Tuning/Hardware.rst)).
- A search of the openzfs/zfs issue tracker for "DRAM-less" returns no issue about
  DRAM-less SSD suitability.

What upstream *does* say about consumer drives, in full:

> As of 2020, use of hardware power loss protection is now a feature solely of
> enterprise SSDs that attempt to protect unflushed data in addition to drive
> metadata and flushed data. **This additional protection beyond protecting flushed
> data and the drive metadata provides no additional benefit to ZFS**, but it does
> not hurt it.

> SSD manufacturers now claim that firmware power loss protection is robust enough
> to provide equivalent protection to hardware power loss protection.
> [Kingston is one example](https://www.kingston.com/us/solutions/servers-data-centers/ssd-power-loss-protection).
> **Firmware power loss protection is used to guarantee the protection of flushed
> data and the drives' own metadata, which is all that filesystems such as ZFS
> need.**

([Hardware, Power Failure Protection](https://github.com/openzfs/openzfs-docs/blob/master/docs/Performance%20and%20Tuning/Hardware.rst))

That is a notably *permissive* position, and it is worth quoting exactly because
it contradicts a common assumption: for ZFS's own integrity, upstream says
hardware power-loss protection buys nothing beyond firmware PLP. Note the NV2 is
**not** on upstream's list of NVMe drives with power failure protection; the
Kingston DC1000B is.

The one place upstream is stricter is the SLOG:

> It should be a low-latency device with power-loss protection. **Consumer SSDs
> without it will happily report data as stable that a power cut then loses.**

([Caching](https://github.com/openzfs/openzfs-docs/blob/master/docs/Basic%20Concepts/Pool%20Structure/Caching.rst))

**Derived implication: do not configure a `log` vdev on these drives.** Since the
ZIL exists in the main pool anyway, this costs nothing — it simply means not
adding a SLOG.

---

## Not established from primary sources

Recorded explicitly, because absence of evidence is part of the answer:

1. **The NV2's sustained write speed after SLC cache exhaustion.** Kingston
   publishes only "out-of-box performance" (2,100 MB/s write on the 1 TB). No SLC
   cache size, no steady-state figure, no controller model, no NAND vendor.
2. **Whether the NV2 uses HMB at all, and for what.** The NVMe spec says HMB use
   is "vendor specific"; Kingston does not mention HMB. The actual HMB request
   (`hmpre`) is readable on the machine via `nvme id-ctrl` and `dmesg`, not from
   documentation.
3. **The write-amplification cost of a wrong `ashift`, quantified.** Upstream
   describes the read-modify-write penalty; it never measures it.
4. **The performance cost of a specific `zfs_arc_max` cap.** No upstream figure,
   curve or rule of thumb. The guidance is entirely qualitative.
5. **The B550 chipset uplink width/generation**, and therefore how much M2B_SB
   contends with SATA and USB. The Gigabyte manual does not state it; AMD's
   chipset page could not be retrieved.
6. **PCI-SIG specification text for PCIe raw data rates.** pcisig.com blocks
   automated retrieval; the per-lane figures in section 3.4 come from the Linux
   kernel's own encoding table instead, which is a primary source for how Linux
   computes link bandwidth.
7. **Any OpenZFS recommendation for or against consumer DRAM-less SSDs.**
8. **Any OpenZFS comparison of a two-disk mirror against two independent
   single-disk pools.**

---

## What the evidence supports

The decision is not made here. What the sources establish is the shape of the
trade, and what each option costs.

**The facts that constrain every option:**

- Each drive tolerates **175 GB/day for 5 years, or 88 GB/day for 10 years**, of
  *amplified* writes ([5.3](#53-what-320-tbw-tolerates)).
- **A mirror does not split that budget** — both drives absorb the full stream
  ([`vdev_mirror.c`](https://github.com/openzfs/zfs/blob/master/module/zfs/vdev_mirror.c)).
- Kingston states the drive **is not intended for server environments**
  ([datasheet](https://www.kingston.com/datasheets/SNV2S_us.pdf)).
- On 32 GiB with OpenZFS >= 2.3.0, ARC's default ceiling is **31 GiB**, plus
  ~3.2 GiB of dirty data, plus up to 256 MiB of HMB
  ([1.1](#11-the-default-zfs_arc_max-changed-and-the-change-matters-here),
  [1.2](#12-the-other-memory-consumers-which-are-not-arc)).
- `ashift` and per-file `recordsize` are decided once, at creation, forever
  ([6.3](#63-structural-asymmetry-what-can-be-undone-later)).

### Option A — one mirrored pool across both drives

**Buys:** the only configuration in which ZFS can *repair* what its checksums
detect ("ZFS automatically repairs bad data from a good copy, when corruption is
detected",
[zpoolconcepts(7)](https://openzfs.github.io/openzfs-docs/man/master/7/zpoolconcepts.7.html)).
Survives one drive failing outright. Single namespace, simplest operations.

**Gives up:**
- **Half the capacity** — "A mirror with N disks of size X can hold X bytes".
- **Endurance headroom.** Both drives receive every write, so the pool's write
  budget is 175 GB/day (5 y), not 350. The write budget does not scale with the
  drive count.
- **Independence of failure timing.** Two identical drives, same batch, same
  write stream, same wear rate. The mirror protects against one drive failing
  early; it does not protect against both reaching 320 TBW at the same time.
- **Write throughput to the slower member's ceiling** — though on the numbers in
  [3.4](#34-whether-any-of-this-binds--the-arithmetic), the Gen 3 socket is not
  the constraint for a 1 TB NV2; the drive's own 2,100 MB/s is.

### Option B — two independent single-disk pools

**Buys:** the full 2 TB. Two fault domains — losing one pool does not touch the
other. Each drive absorbs only its own workload's writes, so the aggregate write
budget genuinely doubles, and the two drives wear at different rates.

**Gives up:**
- **Repair.** ZFS still detects corruption via checksums, but with no second copy
  it can only report it. `copies=2` on a critical dataset would restore repair at
  the cost of writing that data twice to the same drive — trading endurance for
  integrity, on a drive whose endurance is the scarce resource.
- **Availability.** A drive failure is an outage for that pool, restored from
  backup, not a degraded pool that keeps serving.
- **Operational simplicity.** Two pools to scrub, snapshot, monitor and keep from
  filling.

Note this is reversible: `zpool attach` can convert a single-disk pool into a
mirror later ([VDEVs](https://github.com/openzfs/openzfs-docs/blob/master/docs/Basic%20Concepts/Pool%20Structure/VDEVs.rst)).

### Option C — one drive for the system, one for data (two single-disk pools, split by role)

A specialisation of B, and the only one that exploits the PCIe asymmetry
deliberately.

**Buys:** everything B buys, plus the ability to put the write-heavy role on the
Gen 4 CPU-attached socket and the quieter role behind the chipset; and — the
larger effect — to tune the two pools independently. The data pool keeps
`recordsize=128K` for photo and file blobs; the system pool carries the database
datasets at `recordsize=16K`/`32K` with `logbias=throughput` and
`primarycache=metadata`, per
[Workload Tuning](https://github.com/openzfs/openzfs-docs/blob/master/docs/Performance%20and%20Tuning/Workload%20Tuning.rst).
Separating the wear profiles means the two drives do not reach 320 TBW together.

**Gives up:** the same repair and availability that B gives up, and it front-loads
an irreversible guess about which role writes more. If the split is wrong, one
drive burns through its TBW years ahead of the other, and rebalancing means
rebuilding a pool — `ashift` and existing files' `recordsize` do not move.

### The measures that apply under every option

From the primary sources, and independent of topology:

- `ashift=12` at creation, after low-level formatting both drives to 4096-byte
  sectors — the only irreversible knob
  ([Hardware](https://github.com/openzfs/openzfs-docs/blob/master/docs/Performance%20and%20Tuning/Hardware.rst)).
- `atime=off` where nothing depends on access times; `relatime=on` elsewhere
  ([Workload Tuning](https://github.com/openzfs/openzfs-docs/blob/master/docs/Performance%20and%20Tuning/Workload%20Tuning.rst)).
- Matched `recordsize` on database datasets, default 128 KiB on blob datasets
  ([Workload Tuning](https://github.com/openzfs/openzfs-docs/blob/master/docs/Performance%20and%20Tuning/Workload%20Tuning.rst)).
- An explicit `zfs_arc_max` — with the 2.3.x caveat from
  [1.5](#15-a-live-caveat-on-the-23x-series) that it is not yet a hard bound on
  total ZFS memory.
- **No `log` vdev and no `cache` vdev.** A SLOG on a consumer SSD without
  power-loss protection is documented as unsafe; an L2ARC on a RAM-constrained
  system is documented as counterproductive
  ([Caching](https://github.com/openzfs/openzfs-docs/blob/master/docs/Basic%20Concepts/Pool%20Structure/Caching.rst)).
- Scheduled `zpool trim` rather than `autotrim=on`, which upstream recommends
  specifically for "lower-end devices"
  ([zpoolprops(7)](https://openzfs.github.io/openzfs-docs/man/master/7/zpoolprops.7.html)).
- Baseline `data_units_written` on both drives on day one, and check whether
  `nvme endurance-log` reports `media_units_written` — it is the only available
  measurement of the drives' internal write amplification
  ([NVMe Base Spec 2.3](https://nvmexpress.org/wp-content/uploads/NVM-Express-Base-Specification-Revision-2.3-2025.08.01-Ratified.pdf)).

The number that decides between the options is not in any of these documents: it
is this machine's actual amplified write rate in GB/day. Until that is measured
against the 175 GB/day (5-year) and 88 GB/day (10-year) lines, the choice between
redundancy and endurance is being made without the one figure that governs it.
