# Nextcloud and a collaborative office server: memory footprint at two accounts

**Date:** 2026-08-05
**Status:** research note, no decision taken
**Sources:** primary only — official documentation, official system-requirements
pages, upstream source repositories, upstream package metadata and the official
app-store API. Vendor marketing pages are used only where labelled as such.
Every claim carries its URL inline.

---

## 1. Scope and the assumptions this note is written against

The target is a single machine: **32 GB RAM as a hard ceiling**, running 24/7,
one operator, no HA, zero hardware budget. The same box carries a photo library
with GPU-backed machine learning, an observability stack, two web stacks and
their databases. Nothing here may assume it can grow.

The demand side is fixed and is **not** re-opened by this note:

| Parameter | Value | Consequence for this note |
| --- | --- | --- |
| User accounts | 2 | Below every published sizing tier of every product surveyed |
| File corpus | 10 GB, +5 GB/year | Irrelevant to RAM; relevant only to disk |
| Peak interactive sessions | 2 | Sets the PHP-FPM worker count and the editor count |
| Background sync endpoints | 4–6 | Sets the *polling* load, which is the real driver of worker count |
| Bulk ingestion | none (photos go elsewhere) | No preview-generation storm, no import spike |

### 1.1 The rule this note enforces

**A memory figure without its concurrency assumption is worthless, and a figure
that does not move with concurrency is a floor, not a budget.** The single most
consequential finding below is that the office-server vendors publish sizing
tiers whose memory column is *flat* — the same number at 2 users as at 100. So
the question "what does it cost when nothing scales it" has a literal answer for
one of the two candidates: **exactly what it costs at a hundred times the
demand**.

Where a project publishes no figure at all, this note records it as **not
established**, as in the observability note. That happens less often here than
it did there — but where it happens, it happens on the number that matters most.

---

## 2. Nextcloud: the idle floor

### 2.1 What upstream *requires* versus what it *recommends*

The only memory statement on the system-requirements page, quoted verbatim —
<https://docs.nextcloud.com/server/stable/admin_manual/installation/system_requirements.html>:

> "Memory requirements for running a Nextcloud server are greatly variable,
> depending on the numbers of users, apps, files and volume of server activity.
>
> **Nextcloud needs a minimum of 128MB RAM per process, and we recommend a
> minimum of 512MB RAM per process.**
>
> In low memory environments, some features or apps may require adjustments to
> their default settings in order to function (or, in some cases, may need to be
> disabled outright)."
>
> Warning: "To use the built-in Updater, at least 256MB is required."

Three things to note, because they are routinely misread:

1. **This is a per-process figure, not a per-server figure.** It is the PHP
   `memory_limit`, i.e. the ceiling one request may allocate — not the resident
   size of a worker, and not the size of the instance.
2. **128 MB is the requirement; 512 MB is the recommendation.** The PHP
   configuration page states the recommendation as a hard floor —
   "`memory_limit`: Should be at least 512MB" —
   <https://docs.nextcloud.com/server/latest/admin_manual/installation/php_configuration.html>.
   Nextcloud's own reference container sets exactly that: `ENV PHP_MEMORY_LIMIT=512M`
   — <https://github.com/nextcloud/all-in-one/blob/main/Containers/nextcloud/Dockerfile>.
3. **There is no whole-instance minimum published anywhere.** Not on the
   system-requirements page, not in the All-in-One readme
   (<https://github.com/nextcloud/all-in-one/blob/main/readme.md>), which
   documents ports, apps, timeouts and the PHP memory limit but states no RAM
   figure for the assembled stack. **Nextcloud publishes no minimum RAM for a
   Nextcloud server.** That is a finding, not a gap.

Also required, from the same page: PHP 8.3 / 8.4 / 8.5 (8.5 recommended);
MariaDB 10.11+ / MySQL 8.4+ / PostgreSQL 14+ (18 recommended); "SQLite 3.24+
(only recommended for testing and minimal-instances)".

### 2.2 PHP-FPM: the one published formula

The server-tuning page is the only place upstream gives arithmetic —
<https://docs.nextcloud.com/server/stable/admin_manual/installation/server_tuning.html>:

> "PHP-FPM is required for Nginx setups and is widely used with Apache as well.
> Its default configuration is extremely conservative: the default pool has
> **`pm.max_children = 5`**, which limits Nextcloud to five simultaneous PHP
> requests…"
>
> `pm.max_children` — "Estimate it from available RAM:
> **`pm.max_children = floor(available_RAM_for_PHP / average_worker_RSS)`**"
>
> "**A typical Nextcloud worker uses 50–100 MB** (more if Imagick or LDAP is
> loaded). Leave headroom for the OS, web server, database, and cache. **Setting
> `pm.max_children` too high causes swapping, which is worse than queuing.**"
>
> The measurement recipe it gives:
> `ps --no-headers -o rss -C php-fpm | awk '{sum+=$1; count++} END {…}'`

Process-manager modes, same page, with upstream's own verdict on each:

- `dynamic` — "Good default for most Nextcloud installations: balances RAM
  efficiency with burst capacity. **Set `pm.min_spare_servers` high enough that
  sync-client poll bursts do not stall waiting for new processes to spawn.**"
- `static` — "Always keeps exactly `pm.max_children` processes running. Highest
  memory use, lowest latency."
- `ondemand` — "Lowest memory use but adds cold-start latency on every burst.
  **Not recommended for Nextcloud: desktop and mobile clients poll every 30
  seconds, repeatedly triggering cold starts.**"

The worked example on that page is `pm = dynamic`, `pm.max_children = 30`,
`start_servers = 8`, `min_spare = 4`, `max_spare = 16`, `max_requests = 500`,
sized for "a server with 2 GB of RAM dedicated to PHP".

**Upstream contradicts itself here, and the contradiction is load-bearing.**
Nextcloud's own reference deployment does the thing its manual says not to do —
from the All-in-One container build
(<https://github.com/nextcloud/all-in-one/blob/main/Containers/nextcloud/Dockerfile>):

```
sed -i 's/^pm = dynamic/pm = ondemand/' www.conf
sed -i 's/^pm.max_children =.*/pm.max_children = 5000/' www.conf
sed -i 's/^;*pm.process_idle_timeout\s*=.*/pm.process_idle_timeout = 300s/' www.conf
```

with the reasoning in the file's own comments: `pm.max_children = 5000` because
"We don't actually expect so many children but don't want to limit it
artificially because people will report issues otherwise", and
`process_idle_timeout = 300s` because "The upstream default is 10 s, which is
aggressive: after a brief quiet period (e.g. desktop-sync clients polling every
few seconds), all workers are reaped and the next request burst must wait for
fresh forks."

So the manual's objection to `ondemand` is a cold-start objection, and Nextcloud
resolves it by raising the idle timeout from 10 s to 300 s rather than by
switching mode. **`ondemand` with a 300 s idle timeout is upstream's own
answer for a machine that cares about resident memory** — which is exactly this
machine. The cost of that answer is `pm.max_children = 5000` with no memory
bound of any kind: see §6.

### 2.3 The part of the floor that is *not* per-worker

Two shared-memory segments are allocated once per PHP-FPM pool and mapped into
every worker. They are the fixed part of the floor and they do not shrink with
two users.

Upstream PHP defaults —
<https://www.php.net/manual/en/opcache.configuration.php> and
<https://www.php.net/manual/en/apcu.configuration.php>:

| Setting | PHP default | What it is |
| --- | --- | --- |
| `opcache.memory_consumption` | **128** (MB) | "The size of the shared memory storage used by OPcache, in megabytes." |
| `opcache.interned_strings_buffer` | **8** (MB) | "The amount of memory used to store interned strings, in megabytes." |
| `opcache.jit_buffer_size` | **0** | "The amount of shared memory to reserve for compiled JIT code. A zero value disables the JIT." |
| `apc.shm_size` | **"32M"** | "The size of each shared memory segment" |

Nextcloud's guidance moves all four upward. The caching page —
<https://docs.nextcloud.com/server/latest/admin_manual/configuration_server/caching_configuration.html>:

> "Depending on your installation size and the number of users and interactions
> with the system you may want to adapt the `apc.shm_size` setting in your
> `php.ini`. **The default value is 32M which is usually too low for Nextcloud.
> A good starting point is 128M.** … Keep in mind that **this memory needs to be
> available in your system's memory and kept in mind when sizing the amount of
> workers on your server.**"

And the tuning page recommends `opcache.jit = 1255` with
`opcache.jit_buffer_size = 8M`, noting "Most Nextcloud instances use less than
2 MiB of the configured JIT buffer size, so 8 MiB is generally sufficient. **The
overall OPcache usage, however, increases by a larger margin.**"

Nextcloud's reference container commits to concrete values
(<https://github.com/nextcloud/all-in-one/blob/main/Containers/nextcloud/Dockerfile>):

```
opcache.max_accelerated_files=20000
opcache.memory_consumption=256
opcache.interned_strings_buffer=64
opcache.save_comments=1
opcache.revalidate_freq=60
opcache.jit=1255
opcache.jit_buffer_size=128M
apc.shm_size=128M
```

**Derived, with the assumption stated:** taking upstream's own reference values,
the fixed shared allocation is `256 + 64 + 128 + 128` ≈ **576 MB**, present at
zero users and zero requests. Taking bare PHP defaults with Nextcloud's APCu
advice it is `128 + 8 + 0 + 128` ≈ **264 MB**. Neither figure moves with two
accounts. **This, not the workers, is the Nextcloud idle floor.**

**A trap in upstream's own measurement recipe.** `ps -o rss` counts shared
mappings in full against every process that maps them. Summing worker RSS
therefore counts the 264–576 MB OPcache/APCu segments once per worker.
Nextcloud publishes the 50–100 MB per-worker range without stating whether it is
RSS or private, and its recipe measures RSS —
<https://docs.nextcloud.com/server/stable/admin_manual/installation/server_tuning.html>.
**The private, non-shared cost of one additional PHP-FPM worker is not
established from primary sources.** The formula errs on the safe side (it
under-provisions workers rather than over-provisioning them), but it cannot be
used to predict total instance RSS.

### 2.4 The caching layer, and what Client Push costs

Nextcloud's recommendation is explicitly tiered by deployment size —
<https://docs.nextcloud.com/server/latest/admin_manual/configuration_server/caching_configuration.html>:

> **Small/Private home server** — "Only use APCu: `'memcache.local' => '\OC\Memcache\APCu'`"
>
> **Organizations with single-server** — "Use Redis for everything except local
> memcache" (`memcache.distributed` and `memcache.locking` on Redis)
>
> "APCu is faster for local caching than Redis. **If you have enough memory, use
> APCu for Memory Caching and Redis for File Locking. If you are low on memory,
> use Redis for both.**"

Also on that page: "A memcache is not required. You may safely ignore the
warning if you prefer."

So the documented answer for two accounts is **APCu only, and no Redis process
at all**. That matters, because a Redis or Valkey instance is a second daemon
with no default memory bound: "Set `maxmemory` to zero to specify that you don't
want to limit the memory for the dataset. **This is the default behavior for
64-bit systems**" —
<https://redis.io/docs/latest/develop/reference/eviction/>.

**But the demand side pushes back.** With 4–6 background sync endpoints polling,
the thing that consumes workers is not user activity, it is polling. Nextcloud's
own answer is the Client Push app —
<https://github.com/nextcloud/notify_push/blob/main/README.md>:

> "This app attempts to solve the issue where Nextcloud clients have to
> periodically check the server if any files have been changed. … **With many
> clients all checking for updates a large portion of the server load can consist
> of just these update checks.** By providing a way for the server to send update
> notifications to the clients, the need for the clients to make these checks can
> be greatly reduced."
>
> Requirements: "**This app requires a redis server to be setup** and for
> nextcloud to be configured to use the redis server."

**The trade is explicit and unavoidable:** the documented small-instance
configuration (APCu only) and the documented fix for sync-client polling (Client
Push) are mutually exclusive. Choosing Client Push adds a Redis/Valkey daemon
plus a Rust push binary to the floor in order to remove PHP-FPM workers from the
peak. **No memory figure is published for the `notify_push` binary.**

### 2.5 The database

Nextcloud recommends PostgreSQL 18 and ships PostgreSQL in its own reference
deployment
(<https://docs.nextcloud.com/server/stable/admin_manual/installation/system_requirements.html>,
<https://github.com/nextcloud/all-in-one/blob/main/readme.md>). Nextcloud
publishes no database sizing guidance of its own; the tuning page delegates:
"Databases are not plug-and-play… For more details and help tuning your
database: MariaDB – Optimization and Tuning; PostgreSQL – Resource Consumption."

The relevant PostgreSQL defaults —
<https://www.postgresql.org/docs/current/runtime-config-resource.html>:

- `shared_buffers` — "Sets the amount of memory the database server uses for
  shared memory buffers. **The default is typically 128 megabytes (128MB)**…
  If you have a dedicated database server with 1GB or more of RAM, a reasonable
  starting value for `shared_buffers` is 25% of the memory in your system."
- `work_mem` — "**The default value is four megabytes (4MB).** … several running
  sessions could be doing such operations concurrently. Therefore, **the total
  memory used could be many times the value of `work_mem`**".
- `hash_mem_multiplier` — "The default value is 2.0, which makes hash-based
  operations use twice the usual `work_mem` base amount."
- `maintenance_work_mem` — "It defaults to **64 megabytes (64MB)**."

**This is not a dedicated database server.** The 25% rule would allocate 8 GB on
a 32 GB box for a 10 GB file corpus's metadata, which is absurd here; the
default 128 MB is the correct starting point and the note records the rule only
to mark it inapplicable.

### 2.6 What actually moves the floor, given that 2 accounts and 10 GB do not

Upstream names the variables: "the numbers of users, apps, files and volume of
server activity"
(<https://docs.nextcloud.com/server/stable/admin_manual/installation/system_requirements.html>).
Of those four, only **apps** and **server activity** are live here.

- **Apps move the OPcache.** `opcache.max_accelerated_files` is raised to 20000
  in Nextcloud's reference container specifically because a Nextcloud install is
  tens of thousands of PHP files, and every enabled app adds to that. The tuning
  page notes "If any OPcache size limit exceeds 90% of its allocated size, the
  admin panel will show a related warning".
- **Preview generation is the one documented burst.** From the configuration
  reference
  (<https://docs.nextcloud.com/server/latest/admin_manual/configuration_server/config_sample_php_parameters.html>):
  `preview_max_memory` — "**Defaults to 256 megabytes.** Max memory for
  generating image previews with imagegd… If creating the image would allocate
  more memory, preview generation will be disabled and the default mimetype icon
  is shown." And `preview_concurrency_new` — "Number of new previews that are
  being concurrently generated. Depending on the max preview size… **the
  generation process can consume considerable CPU and memory resources.** It's
  recommended to limit this to be no greater than the number of CPU cores. **If
  unspecified, defaults to the number of CPU cores, or 4** if that cannot be
  determined." `preview_concurrency_all` defaults to twice that.

  **This is the largest single documented memory excursion in a Nextcloud
  instance, and it is not sized by user count.** On a 6-core host the default is
  6 concurrent preview generators; the documented per-preview guard is 256 MB.
  With no bulk photo ingestion the trigger is rare — but the default
  concurrency is set from the CPU, not from the demand, and it should be pinned
  down rather than left to the core count.
- **Background jobs are a separate PHP process.** `cron.php` on a 5-minute
  system timer is the recommended mode —
  <https://docs.nextcloud.com/server/latest/admin_manual/configuration_server/background_jobs_configuration.html>.
  One CLI PHP process, bounded by the same `memory_limit`.

### 2.7 Derived: a defensible Nextcloud idle floor

**The arithmetic below is derived by this note. Only the inputs are published.**

| Component | Figure used | Source of the figure |
| --- | --- | --- |
| OPcache + JIT + interned strings + APCu (shared, allocated once) | 264–576 MB | PHP defaults + Nextcloud AIO reference values |
| PHP-FPM workers, 6–10 alive under sync polling | 50–100 MB RSS each, shared segments included in that RSS | Nextcloud tuning page |
| PostgreSQL, defaults, handful of connections | ~128 MB `shared_buffers` + per-connection work | PostgreSQL docs |
| Web server | not established | — |
| `cron.php`, one process every 5 min | ≤ `memory_limit` | Nextcloud docs |

Because worker RSS double-counts the shared segments (§2.3), the honest form of
the estimate is a **bracket, not a sum**: the fixed floor is 264–576 MB of
shared PHP memory plus ~128 MB of PostgreSQL, and the marginal cost of the
workers is an unpublished private-page figure smaller than the 50–100 MB RSS
each. **A cap of 2 GB for the whole Nextcloud service (PHP-FPM + web server +
database + cron) is generous at this demand; 1.5 GB is defensible.** It must be
measured against, not trusted.

Two accounts and 10 GB genuinely move nothing. Sync-client polling and app count
move everything.

---

## 3. The finding that changes the shape of the question

**Nextcloud 35 replaces Collabora Online as the default office solution.**

Nextcloud 34, the current release —
<https://docs.nextcloud.com/server/stable/admin_manual/office/index.html>:

> "**Nextcloud Office is based on the Collabora Online Development Edition
> (CODE)** and is available free and under heavy development… Enterprise users
> have access to the more stable, scalable Collabora Online Enterprise based
> version through a Nextcloud support subscription."

Nextcloud 35, the upcoming release — <https://docs.nextcloud.com/server/latest/admin_manual/office/index.html>:

> "Nextcloud supports two office solutions for collaborative document editing:
>
> **Nextcloud Office (powered by Euro-Office)** — The default office solution
> built into Nextcloud… **Requires a Euro-Office Document Server.**
>
> **Collabora Online** — A fully supported alternative based on the Collabora
> Online Development Edition (CODE)."

**What Euro-Office is, from its own repository.** The `ATTRIBUTION` file at
<https://github.com/Euro-Office/DocumentServer/blob/main/ATTRIBUTION>:

> "Euro-Office is based on ONLYOFFICE DocumentServer, originally developed by
> Ascensio System SIA (https://www.onlyoffice.com/). The original source code is
> available at: https://github.com/ONLYOFFICE. ONLYOFFICE DocumentServer is
> licensed under the GNU Affero General Public License v3.0 (AGPL-3.0)."

Corroborated by the app-store metadata for the `eurooffice` connector app
(<https://apps.nextcloud.com/api/v1/apps.json>), which lists its authors as
**"Nextcloud Office contributors"** and **"Ascensio System SIA"**, its licence as
`AGPL-3.0-only`, its issue tracker as
`https://github.com/Euro-Office/eurooffice-nextcloud/issues`, and its supported
platform range as `>=33.0.0 <36.0.0` — and by the Euro-Office GitHub
organisation, whose repository set (`core`, `sdkjs`, `web-apps`, `server`,
`DocumentServer`, `document-server-package`, `desktop-sdk`) is the ONLYOFFICE
repository set.

**Consequences that land directly on a 32 GB box:**

1. The Nextcloud 35 manual states the Document Server's minimum plainly —
   <https://docs.nextcloud.com/server/latest/admin_manual/office/euro-office/installation.html>:
   "Minimum system requirements: **4 GB RAM (8 GB recommended for multi-user
   deployments)**; 10 GB disk space".
2. The `Euro-Office/DocumentServer` repository was created **2026-03-24**. The
   connector app has exactly **two releases**. This is a months-old fork being
   presented as the default.
3. **The change is not in the release notes.** The Nextcloud 35 upgrade page
   (<https://docs.nextcloud.com/server/latest/admin_manual/release_notes/upgrade_to_35.html>)
   covers PHP, OS and database version changes and says nothing about the office
   server. The only place the default change is documented is the Office section
   of the manual itself.

This does not force a decision, but it reframes it: choosing Collabora is now
choosing the *non-default* path on Nextcloud 35, and choosing the default path
means choosing an ONLYOFFICE derivative that costs 4 GB before anyone opens a
document.

---

## 4. Collabora Online / CODE

Collabora Online is MPL-2.0 —
<https://github.com/CollaboraOnline/online.mirror/blob/main/COPYING>.

**A note on sources.** Collabora's SDK documentation site
(`sdk.collaboraonline.com`) is behind an Anubis proof-of-work bot challenge and
could not be retrieved programmatically; every attempt returns the challenge
page. The authoritative substitute used throughout this section is the upstream
annotated configuration file `coolwsd.xml.in` and the server source, which is
where the documentation's own defaults come from. Note also that **active
development has moved off GitHub to a Gerrit instance**: "Active development of
Collabora Online has moved to our Gerrit instance at
https://gerrit.collaboraoffice.com… Source code changes go to Gerrit, not
GitHub" — <https://github.com/CollaboraOnline/online/blob/main/README.md>. The
read-only mirror at `CollaboraOnline/online.mirror` is cited below.

### 4.1 The process model, which is the whole memory story

`coolwsd` forks a LibreOffice "kit" process per open document, and keeps a pool
of them warm. From
<https://github.com/CollaboraOnline/online.mirror/blob/main/coolwsd.xml.in>:

- `<num_prespawn_children desc="Number of child processes to keep started in
  advance and waiting for new clients.">` — the build-time default is
  **`NUM_PRESPAWN_CHILDREN=4`** ("a reasonable default"; set to 1 only in debug
  builds) —
  <https://github.com/CollaboraOnline/online.mirror/blob/main/configure.ac>.
- `<per_document>` exists as a configuration section at all — with
  `max_concurrency` (4 threads), `limit_virt_mem_mb`, `limit_stack_mem_kb`
  (8000), `limit_num_open_files`, `idle_timeout_secs` (3600) — because every
  document *is* a process.
- `<max_idle_subforkits desc="The maximum number of recently-used idle sub
  forkits to keep alive. Defaults to 5.">`

**So the at-rest cost is not zero even with zero documents open: four
pre-spawned kit processes plus the forkit plus `coolwsd` itself.** That is by
design — it is what makes the first document open fast.

### 4.2 The one published memory figure

Collabora publishes a per-user memory figure for exactly one deployment shape:
the built-in CODE server that runs as an AppImage inside the Nextcloud
container. From
<https://github.com/CollaboraOnline/richdocumentscode/blob/master/README.md>:

> "## System requirements
> - Linux x86-64 or ARM64 (aarch64) platform
> - 2 CPU cores
> - **1 GB RAM + 100 MB RAM / user**
> - 100 kbit/s network bandwidth / user
> - 300 MB space on disk (800 MB in `/tmp` if not using FUSE)"

**Derived for this demand:** 2 users → `1 GB + 200 MB` = **1.2 GB**.

The same app's own store summary sets expectations honestly
(<https://apps.nextcloud.com/api/v1/apps.json>, app `richdocumentscode`):
"Built-in Collabora Online Development Edition (CODE) server **for local testing
and non-production use**", and its description: "Easy to install, for personal
use or for small teams. **A bit slower than a standalone server and without the
advanced scalability features.**" Nextcloud's own installation page repeats it:
"This is the default option which works out of the box in most scenarios,
however for improved performance it is highly recommended to switch to a
dedicated Collabora Online installation" —
<https://docs.nextcloud.com/server/latest/admin_manual/office/installation.html>.

**For the standalone `coolwsd` server, no memory figure is published.** The
official Helm chart ships `resources: {}` — no memory request, no limit — at
every one of its four occurrences, including the single-replica case —
<https://github.com/CollaboraOnline/online/blob/main/kubernetes/helm/collabora-online/values.yaml>.
The CODE product page states no hardware requirement at all
(<https://www.collaboraonline.com/code/>, vendor marketing page). This is the
same shape as the Loki finding in the observability note: the chart is the
sizing documentation, and the chart declines to say.

The 1 GB + 100 MB/user figure is for the AppImage build of the same binaries, so
it is the best available anchor for the standalone server too — but it is
**published for a different deployment shape** and should be labelled as such.

### 4.3 `memproportion`: the only cgroup-aware internal cap found — and it does not work

This is the sharpest finding in the note, and it is the one that answers the
question #17 asked of the observability stacks.

The setting, from
<https://github.com/CollaboraOnline/online.mirror/blob/main/coolwsd.xml.in>:

> `<memproportion desc="The maximum percentage of available memory consumed by
> all of the [coolwsd] processes, after which we start cleaning up idle
> documents. **If cgroup memory limits are set, this is the maximum percentage of
> that limit to consume.**" type="double" default="80.0">`

That description promises exactly what no observability project offered: an
internal cap that *reads the cgroup limit* and enforces a proportion of it.

The implementation does read the cgroup limit. From
<https://github.com/CollaboraOnline/online.mirror/blob/main/wsd/Admin.cpp>,
constructor:

```cpp
_totalSysMemKb(Util::getTotalSystemMemoryKb())
_totalAvailMemKb(_totalSysMemKb)
// If there is a cgroup limit that is smaller still, apply it.
const std::size_t cgroupMemLimitKb = Util::getCGroupMemLimit() / 1024;
if (cgroupMemLimitKb > 0 && cgroupMemLimitKb < _totalAvailMemKb)
    _totalAvailMemKb = cgroupMemLimitKb;
// If there is a cgroup soft-limit that is smaller still, apply that.
```

But the routine that actually decides when to free memory uses the **unclamped,
host-wide** value:

```cpp
void Admin::triggerMemoryCleanup(const size_t totalMem)
{
    static const double memLimit = ConfigUtil::getConfigValue<double>("memproportion", 80.0);
    if (memLimit == 0.0 || _totalSysMemKb == 0) { … return; }
    const double memToFreePercentage =
        (totalMem / static_cast<double>(_totalSysMemKb)) - memLimit / 100.;
```

`_totalSysMemKb` comes from `/proc/meminfo` `MemTotal` and is not cgroup-aware —
<https://github.com/CollaboraOnline/online.mirror/blob/main/common/Util-server.cpp>.
The cgroup-clamped `_totalAvailMemKb` is used only in a startup log line, in the
admin-console `total_avail_mem` message, and in the `global_memory_available_bytes`
metric. **It is reported, not enforced.**

**Practical consequence, derived:** on this 32 GB host, a `coolwsd` container
capped at 2 GB by cgroup with the default `memproportion` of 80 would trigger
its internal cleanup only when `coolwsd` reached ~25.6 GB — which it never will,
because the cgroup OOM-killer fires at 2 GB first. **The internal cap silently
does nothing under a container memory limit unless it is deliberately
recalculated against host RAM.** For a 2 GB budget on a 32 GB host the correct
setting is `memproportion ≈ 5.0`, not 80.

What the cleanup does when it *does* fire, same file:

> "OOM: Killing saved document with DocKey […]" — documents are sorted by idle
> time; **saved** documents are closed outright, **unsaved** ones are force-saved
> first. A floor of `MinMemToFreeKB = 1024` prevents it "killing documents to
> save a MB or two".

**So the answer to "is there an enforceable internal cap" is: yes, uniquely
among everything surveyed here and in #17 — and it is mis-wired for containers.
An external cgroup limit is still mandatory, and the internal cap must be
re-derived from host RAM to be useful at all.**

### 4.4 The per-document guards that do work

From the `<per_document>` and `<cleanup>` blocks of `coolwsd.xml.in`:

| Setting | Default | Description (verbatim) |
| --- | --- | --- |
| `limit_virt_mem_mb` | `0` | "The maximum virtual memory allowed to each document process. **0 for unlimited.**" |
| `limit_stack_mem_kb` | `8000` | "The maximum stack size allowed to each document process." |
| `idle_timeout_secs` | `3600` | "The maximum number of seconds before unloading an idle document. Defaults to 1 hour." |
| `autosave_duration_secs` | `300` | "The number of seconds after which document, if modified, should be saved." |
| `cleanup` (`enable="true"`) | on | "Checks for resource consuming (bad) documents and kills associated kit process." |
| `cleanup/limit_dirty_mem_mb` | **`3072`** | "Minimum memory usage for a document to be candidate for bad state" |
| `cleanup/idle_time_secs` | `300` | "Minimum idle time for a document to be candidate for bad state" |
| `cleanup/bad_behavior_period_secs` | `60` | how long it must stay bad before the kit is killed |
| `cleanup/limit_cpu_per` | `85` | CPU-percentage equivalent of the same rule |

**Read `limit_dirty_mem_mb = 3072` carefully.** It is not a per-document cap —
it is the threshold above which upstream considers a *single document* to be
pathological, and only then if the document has also been idle for 300 s and
stays that way for 60 s. Out of the box, **a single open document may consume
3 GB before Collabora considers it a problem at all**, and no default bounds it
while someone is actively editing. `limit_virt_mem_mb` is the per-document
hard cap and it defaults to unlimited.

### 4.5 The free tier, and whether two users can hit it

There is no licence key, no activation and no functional gate in CODE. There is
one build-time limit pair and one runtime switch that turns it on.

From <https://github.com/CollaboraOnline/online.mirror/blob/main/configure.ac>,
the generated `home_mode` config fragment — this is upstream's own description,
verbatim:

> "Home users can enable this setting, which in turn **disables welcome screen
> and user feedback popups**, but also **limits concurrent open connections to 20
> and concurrent open documents to 10**. The default means that number of
> concurrent open connections and concurrent open documents are **unlimited**,
> but welcome screen and user feedback **cannot be switched off**."

The enforcement, from
<https://github.com/CollaboraOnline/online.mirror/blob/main/wsd/COOLWSD.cpp>:

```cpp
#if ENABLE_WELCOME_MESSAGE
    if (ConfigUtil::getConfigValue<bool>(conf, "home_mode.enable", false))
    {
        COOLWSD::MaxConnections = 20;
        COOLWSD::MaxDocuments = 10;
    }
    else
    {
        conf.setString("welcome.enable", "true");
        COOLWSD::MaxConnections = MAX_CONNECTIONS;
        COOLWSD::MaxDocuments = MAX_DOCUMENTS;
    }
#endif
```

with `MAX_CONNECTIONS = 9999` and `MAX_DOCUMENTS = 9999` as the source defaults
(`configure.ac`; the `--with-max-connections` / `--with-max-documents` help
strings still advertise the historical "Def: 20" / "Def: 10", which the code no
longer uses). A signed support key raises the numbers to 1000 connections / 200
documents, but that path requires a build configured `--with-support-public-key`.

**At 2 accounts and 2 peak sessions, `home_mode` is free money.** It costs 20
connections and 10 documents that will never be reached, and it buys the removal
of the welcome screen and the feedback popup — which are otherwise
**not switchable off**. This is precisely the case the issue described: "a cap
that binds at 20 documents is irrelevant here".

**There is no licensing gate.** CODE is MPL-2.0, self-hostable, with no
registration, no telemetry key and no expiry. What is given up is stated by
Collabora on its own product page (<https://www.collaboraonline.com/code/>,
vendor marketing): "CODE is the development version of Collabora Online. It is
perfect for testing, home use or small teams, **but not recommended for
production environments**. … CODE builds are released on average once a month."
The supported build requires a subscription.

### 4.6 It can be measured, which matters for the observability budget

`coolwsd` exposes a Prometheus-format endpoint at `/cool/getMetrics`
(`security.enable_metrics_unauthenticated`, default `false`, in
`coolwsd.xml.in`). The memory series, from
<https://github.com/CollaboraOnline/online.mirror/blob/main/wsd/Admin.cpp> and
<https://github.com/CollaboraOnline/online.mirror/blob/main/wsd/AdminModel.cpp>:

`global_host_system_memory_bytes`, `global_memory_available_bytes`,
`global_memory_used_bytes`, `global_memory_free_bytes`,
`coolwsd_memory_used_bytes`, `forkit_memory_used_bytes`,
`kit_memory_used_bytes` (active aggregate), `doc_memory_used_bytes{…}` per
document, and `document_resource_consuming_count` /
`document_resource_consuming_aborted_count` for the cleanup path.

**The per-document memory figure upstream declines to publish can be measured
per document on this machine, for free, through the metrics path #17 and #18 are
already building.** That is the cheapest way to close the gap.

---

## 5. ONLYOFFICE Docs, and therefore Euro-Office

ONLYOFFICE Docs is AGPL-3.0
(<https://github.com/ONLYOFFICE/DocumentServer/blob/master/Readme.md>), and
Euro-Office inherits that licence and that architecture (§3). Everything in this
section applies to both unless stated.

### 5.1 The sizing table is flat

ONLYOFFICE publishes a hardware table indexed by concurrent active users —
<https://helpcenter.onlyoffice.com/docs/installation/docs-community-sys-reqs-linux.aspx>
and
<https://helpcenter.onlyoffice.com/docs/installation/docs-community-sys-reqs-docker.aspx>:

> "**What counts as a concurrent active user?** A concurrent active user is any
> user who currently has a document open in the ONLYOFFICE Docs editor, whether
> actively editing or just viewing. Users who are logged in to the integrated
> platform but do not have a document open are not counted toward this limit."

| Number of concurrent active users | Minimal hardware server configuration |
| --- | --- |
| less than 100 | Single core processor at 2.8 GHz, **4 GB RAM**, 40 GB disk |
| 100–200 | Dual core at 2.8 GHz, **4 GB RAM**, 80 GB disk |
| 200–400 | Quad core at 2.8 GHz, **4 GB RAM**, 160 GB disk |
| 400+ | "Cluster deployment recommended." |

**The memory column does not move.** CPU cores scale, disk scales, RAM does not.
**Two users cost the same 4 GB as ninety-nine.** This is the literal answer to
"what does it cost when nothing scales it", and it is the reason the option is
hard to justify here.

The bare hardware requirements on those same two pages **contradict each other
and the table**:

- Linux page: "**RAM: at least 2 GB**, but depends on the host OS. More is
  better"; "SWAP: at least 4 GB"; "HDD: at least 40 GB of free space".
- Docker page: "**RAM: 4 GB or more**"; "SWAP: at least 4 GB"; "HDD: at least
  40 GB".
- The Docker repository readme states a third set: "**RAM**: 4 GB or more;
  **CPU**: dual-core 2 GHz or higher; **Swap**: at least 2 GB; **HDD**: at least
  2 GB of free space" —
  <https://github.com/ONLYOFFICE/Docker-DocumentServer/blob/master/README.md>.

Nextcloud's own figure for the Euro-Office build agrees with the higher number:
"**4 GB RAM (8 GB recommended for multi-user deployments)**; 10 GB disk space" —
<https://docs.nextcloud.com/server/latest/admin_manual/office/euro-office/installation.html>.
Euro-Office's own documentation says the same: "4 GB RAM minimum" for both the
Docker and the Ubuntu package paths —
<https://github.com/Euro-Office/documentation/blob/main/docs/installation/docker.md>,
<https://github.com/Euro-Office/documentation/blob/main/docs/installation/ubuntu.md>.

**Take 4 GB as the published figure and the 2 GB on the Linux page as an
inconsistency, not a small-instance tier.** No small-instance tier exists.

### 5.2 It is not one process, it is a stack

From Euro-Office's own architecture page —
<https://github.com/Euro-Office/documentation/blob/main/docs/introduction/architecture.md>:

> Backend services (**"All four are Node.js processes"**): **DocService**
> ("Real-time collaboration, Socket.io transport, document session
> orchestration"), **FileConverter** ("Wraps native C++ converters for format
> translation"), **AdminPanel**, **Metrics** ("StatsD-based metrics emission").
>
> External dependencies: "**Redis** — Session state and real-time coordination.
> **RabbitMQ** — Inter-service messaging. **SQL database** — One of MySQL,
> PostgreSQL, MSSQL, or Oracle. **Object storage** *(optional)*".

And the install guide is explicit:

> "Euro-Office requires **PostgreSQL, Redis, RabbitMQ, Nginx, and Supervisor**.
> Install them before the package" —
> <https://github.com/Euro-Office/documentation/blob/main/docs/installation/ubuntu.md>

ONLYOFFICE's own Docker readme confirms the same dependency set, and notes that
in the Community Edition image these are *not* bundled — the volumes
`/var/lib/postgresql`, `/var/lib/rabbitmq`, `/var/lib/redis` are listed only for
the Enterprise/Developer images —
<https://github.com/ONLYOFFICE/Docker-DocumentServer/blob/master/README.md>.

**So the 4 GB is the document server. A second PostgreSQL, a RabbitMQ broker and
a Redis are on top**, on a machine that has one PostgreSQL and (per §2.4) was
trying to avoid needing a Redis at all.

Architecturally the trade against Collabora is clean and worth stating plainly:
**Collabora renders server-side** (one LibreOffice process per open document),
**ONLYOFFICE renders client-side** ("Editors are vanilla JavaScript with
RequireJS modules… built per document type and **served as static assets**" —
Euro-Office architecture page; "Document editor — the user interface for viewing
and editing documents" on the client side —
<https://api.onlyoffice.com/docs/docs-api/get-started/how-it-works/>). In
principle that should make ONLYOFFICE the *cheaper* server. In published
figures it is 3.3× more expensive at rest, because the fixed cost of the
Node.js services, the converter, the broker, the cache and the database dominates
everything two users could ask of it.

### 5.3 The "20 connection limit" is not what it is usually said to be

The README's edition table lists, for Community Edition: "Number of users: **up
to 20 recommended**"; "Clusterization: −"; "Licence: **GNU AGPL v.3**";
"Admin Panel: −"; "Mobile web editors: −"; "Document Builder Service: −";
"Automation API: −" —
<https://github.com/ONLYOFFICE/DocumentServer/blob/master/Readme.md>.

"Recommended" is doing real work in that sentence. In the open-source build the
licence reader returns an effectively unlimited connection count —
<https://github.com/ONLYOFFICE/server/blob/master/Common/sources/license.js>:

```js
packageType: constants.PACKAGE_TYPE_OS,
connections: constants.LICENSE_CONNECTIONS_OS,
connectionsView: constants.LICENSE_CONNECTIONS_OS,
hasLicense: false,
```

and <https://github.com/ONLYOFFICE/server/blob/master/Common/sources/constants.js>:

```js
exports.LICENSE_CONNECTIONS = 20;
exports.LICENSE_CONNECTIONS_OS = 0x7fffffff; // max signed 32-bit value
```

The `20` constant is applied in exactly one place — the grace period after a
*paid* licence expires —
<https://github.com/ONLYOFFICE/server/blob/master/Common/sources/tenantManager.js>:

```js
// Grace period after end license = limited mode with limited connections
res.connections = Math.min(res.connections, constants.LICENSE_CONNECTIONS);
```

**So: no enforced concurrent-connection cap in the AGPL build. Two users cannot
hit it, and neither could two hundred.** The binding constraints in Community
Edition are feature removals (no Admin Panel, no clustering, no mobile web
editors) and the flat 4 GB, not a connection counter.

**On the licence itself:** AGPL-3.0 with the note "No trademark rights are
granted under this License", and "The interactive user interfaces in modified
versions of the Program are required to display Appropriate Legal Notices in
accordance with Section 5 of the GNU AGPL version 3"
(<https://github.com/ONLYOFFICE/server/blob/master/Common/sources/license.js>
header). For an unmodified self-hosted deployment serving two household
accounts this imposes nothing. It would bind if the platform were ever exposed
as a service to third parties with modified sources — which is not on this map.

### 5.4 Internal memory cap: none found

No `memproportion` equivalent exists. The published configuration
(<https://github.com/ONLYOFFICE/server/blob/master/Common/config/default.json>)
bounds *inputs* rather than residency: `FileConverter.converter.maxprocesscount`
= 1, `maxDownloadBytes` = 104857600, `streamWriterBufferSize` = 8388608, and
per-format `inputLimits` on uncompressed archive size ("50MB" for docx, "300MB"
for xlsx). Those cap what one conversion may chew through; they do not cap the
service.

**The cap must therefore be a cgroup limit** — the same conclusion #17 reached
for every observability project, reached again here.

One further requirement that a container limit does not solve: **"SWAP: at least
4 GB"** appears on both ONLYOFFICE system-requirements pages. A platform that
runs without swap by design has to decide whether it is ignoring a stated
requirement.

---

## 6. Enforceable internal caps: the cross-cutting answer

| Component | Internal memory cap? | Verdict |
| --- | --- | --- |
| PHP-FPM / Nextcloud | `memory_limit` per **request** (512 MB recommended), `pm.max_children` per **pool** | Bounds one request and the worker count, not the pool's residency. Nextcloud's own reference config sets `pm.max_children = 5000` explicitly to avoid limiting it. **No effective cap.** |
| OPcache / APCu | Yes — fixed shared segments, sized at startup | The one genuinely bounded allocation in the whole stack. It is a floor, not a limit. |
| PostgreSQL | `shared_buffers` fixed; `work_mem` × `hash_mem_multiplier` **per operation, per session** | Docs state plainly the total "could be many times the value of `work_mem`". **No cap.** |
| Redis / Valkey | `maxmemory`, **default 0 = unlimited on 64-bit** | A real cap on the dataset if set; does not bound fragmentation or client buffers. Off by default. |
| Collabora `coolwsd` | `memproportion` (default 80%), documented as cgroup-aware | Reads the cgroup limit; **does not use it in the cleanup decision** (§4.3). Useful only if re-derived against host RAM. |
| Collabora per document | `limit_virt_mem_mb` **default 0 = unlimited**; `cleanup/limit_dirty_mem_mb` = 3072 | The default tolerates 3 GB in one document before calling it pathological, and only when idle. |
| ONLYOFFICE / Euro-Office | none found | Input-size limits only. |

**Conclusion, identical in shape to #17: the only enforceable cap is external.**
A `systemd` `MemoryMax=` or a container memory limit per service is mandatory,
and on this box it is the mechanism that decides *which* service dies when
something goes wrong. Collabora is the single exception that offers an internal
mechanism at all, and even it needs the external limit underneath.

---

## 7. Free tiers and licensing gates: can two accounts hit them?

| Product | Free tier | The limit | Binds at 2 users? |
| --- | --- | --- | --- |
| Collabora Online (CODE) | MPL-2.0, unlimited, no key | Default: unlimited connections/documents, **welcome screen and feedback popups cannot be disabled**. With `home_mode.enable`: 20 connections / 10 documents, popups gone. | **No.** `home_mode` is strictly better here. |
| Collabora Online (supported) | — | Requires a Collabora or Nextcloud subscription | Not applicable — zero budget |
| Built-in CODE server (`richdocumentscode`) | Apache-2.0 app wrapping the CODE AppImage | Upstream labels it "for local testing and **non-production use**" and "a bit slower" | **No numeric limit.** The limit is upstream's own recommendation against it. |
| ONLYOFFICE Docs Community | AGPL-3.0 | "up to 20 recommended"; source enforces `0x7fffffff` connections | **No.** No enforced cap exists. |
| ONLYOFFICE Enterprise/Developer | Proprietary | Priced per plan | Not applicable |
| Euro-Office Document Server | AGPL-3.0, inherited | Licensing page is a stub: "Coming soon: **Commercial licensing options**… the contributor license agreement (CLA) and signed-commit requirements" | **Not yet knowable** — the commercial model is announced but unpublished |

**No licensing gate binds at two users on any option.** The Euro-Office entry is
the only one carrying forward risk, and it is risk of a *future* gate on a
project four months old whose own licensing page is a placeholder —
<https://github.com/Euro-Office/documentation/blob/main/docs/introduction/licensing.md>.

---

## 8. Hard blockers and things that change the shape of an option

Nothing found here is fatal in the way Promtail's EOL was in #17. Four findings
change the shape of an option:

1. **Nextcloud 35 demotes Collabora from default to alternative** (§3). Choosing
   Collabora means choosing the non-default integration path going forward. It
   remains documented as "a fully supported alternative", and the built-in CODE
   server app already publishes a Nextcloud 35-compatible release
   (`richdocumentscode` 26.4.104, platform spec `>=25.0.0 <36.0.0` —
   <https://apps.nextcloud.com/api/v1/apps.json>). The Collabora **connector**
   app `richdocuments` has no Nextcloud 35 release yet (newest 11.1.0, spec
   `>=34.0.0 <35.0.0`) — which is normal for an unreleased server version and is
   recorded as a thing to re-check, not as a blocker.
2. **The default office server is a four-month-old fork.**
   `Euro-Office/DocumentServer` was created 2026-03-24; the connector app has two
   releases; the licensing page is a stub; upstream still says "We currently
   provide a docker image **for testing and integration purposes**. We are going
   to publish deb/rpm packages shortly" —
   <https://github.com/Euro-Office/DocumentServer/blob/main/README.md> — while
   Nextcloud's manual already documents the deb/rpm path.
3. **`memproportion` is mis-wired under a container limit** (§4.3). Not a
   blocker; a configuration obligation that is invisible unless the source is
   read.
4. **ONLYOFFICE/Euro-Office requires a swap device** ("SWAP: at least 4 GB") and
   a Redis, a RabbitMQ and a SQL database beyond its own 4 GB. On a machine that
   is already rationing RAM, this is the finding that decides the option.

One non-blocking observation, recorded because it affects reproducibility:
**Collabora's SDK documentation site is unreachable to automated tooling**
(Anubis proof-of-work challenge), and **Collabora's source has moved from GitHub
to Gerrit**. Any procedure in this repository that cites `sdk.collaboraonline.com`
will need a human in front of a browser.

---

## 9. Not established from primary sources

These gaps are findings, not omissions:

1. **A whole-instance minimum RAM for Nextcloud.** The system-requirements page
   publishes a per-process figure only; All-in-One publishes none.
2. **The private (non-shared) resident cost of one PHP-FPM worker.** The
   published 50–100 MB is RSS, and upstream's own measurement recipe sums RSS
   across workers, double-counting the OPcache and APCu segments.
3. **Any memory figure for the standalone `coolwsd` server.** The only published
   figure (1 GB + 100 MB/user) belongs to the AppImage-in-container build; the
   official Helm chart ships `resources: {}`.
4. **Per-open-document memory for Collabora.** The `cleanup/limit_dirty_mem_mb`
   default of 3072 MB is a pathology threshold, not a typical value. Measurable
   locally via `doc_memory_used_bytes`; not published.
5. **Per-connected-editor memory for ONLYOFFICE / Euro-Office.** The published
   tier table's RAM column is constant from 1 to 400 concurrent users, so it
   contains no per-user information at all.
6. **Memory for the `notify_push` (Client Push) binary.**
7. **A coherent bare-minimum RAM figure for ONLYOFFICE Docs.** Three official
   sources give 2 GB, 4 GB and 4 GB, with swap requirements of 4 GB, 4 GB and
   2 GB respectively.
8. **Whether Euro-Office will remain wholly AGPL.** Its own licensing page
   announces "Commercial licensing options" as forthcoming.
9. **MariaDB's `innodb_buffer_pool_size` default.** MariaDB's documentation site
   could not be retrieved in machine-readable form; PostgreSQL is used as the
   database anchor throughout, which is also what Nextcloud recommends and ships.

---

## 10. What the evidence supports

Not a decision — the reasoning a decision can be built on.

### 10.1 The load-bearing asymmetry

**The office server costs more than Nextcloud does.** At this demand:

| Service | Published or derived cost | Basis |
| --- | --- | --- |
| Nextcloud (PHP-FPM + web server + PostgreSQL + cron) | **1.5–2 GB cap**, derived; fixed floor ~400–700 MB | §2.7 |
| Collabora / CODE, 2 users | **1.2 GB**, published (1 GB + 100 MB/user) | §4.2 |
| Euro-Office / ONLYOFFICE Docs | **4 GB**, published, flat — plus Redis, RabbitMQ and a second database | §5.1, §5.2 |

Nextcloud at two accounts is genuinely cheap; the collaborative office server is
the expensive half of the pair. **Any budget written for this pair that assumes
the file store is the big item is wrong.**

### 10.2 A defensible allocation

The evidence supports **a hard external cap of 3.5 GB for the pair**, allocated:

| Component | Cap | Basis |
| --- | --- | --- |
| Nextcloud (PHP-FPM + web server) | 1–1.5 GB | Derived from documented shared-segment sizes plus an unpublished per-worker private cost; must be measured |
| PostgreSQL | 256–512 MB | `shared_buffers` 128 MB default plus per-session `work_mem`; the 25% rule is for dedicated servers and does not apply |
| Collabora `coolwsd` + kits | 1.5 GB | Published 1 GB + 100 MB/user at 2 users = 1.2 GB, plus headroom for the 4 pre-spawned kits |
| Redis/Valkey, only if Client Push is adopted | 256 MB with `maxmemory` set | Default `maxmemory` is 0; setting it is the whole point |

With reasoning:

1. **Every cap must be external.** `memory_limit` bounds a request, not a pool.
   `pm.max_children` is set to 5000 by Nextcloud's own reference build precisely
   so that it does *not* bind. PostgreSQL states its own total "could be many
   times `work_mem`". Redis defaults to unlimited. Only Collabora offers an
   internal mechanism, and it is mis-wired under containers. **`MemoryMax=` or a
   container limit per service, or there is no budget.**
2. **If Collabora is deployed under a memory limit, `memproportion` must be
   restated as a percentage of host RAM.** For a 1.5 GB cap on a 32 GB host that
   is roughly `4.5`, not the default `80`. Left at 80 it never fires and the
   cgroup killer does the work instead — which loses the open document rather
   than closing an idle one.
3. **Set `home_mode.enable = true` on day one.** It costs limits that two
   accounts cannot approach and removes the only two pieces of UI that upstream
   otherwise refuses to let an administrator disable.
4. **Pin `preview_concurrency_new` explicitly.** Its default is derived from CPU
   core count, not from demand, and `preview_max_memory` is 256 MB per generator.
   On a 6-core host the default sizes the worst burst in the system against
   hardware rather than against two users.
5. **Decide Client Push deliberately, as a memory trade and not a feature.**
   APCu-only is the documented small-instance answer and costs no daemon. Client
   Push removes the polling that drives worker count at the price of a Redis
   daemon plus a push binary with no published footprint. With 4–6 sync
   endpoints, it is a real question; it is not free.
6. **Prefer `pm = ondemand` with `pm.process_idle_timeout = 300s`** over the
   manual's `dynamic` advice, on upstream's own reasoning in its own reference
   container. The manual's objection to `ondemand` is cold-start latency at a
   10 s timeout; raising the timeout to 300 s is the documented fix and it keeps
   resident memory tied to actual use.
7. **Measure rather than trust.** `coolwsd` exposes `doc_memory_used_bytes`,
   `kit_memory_used_bytes` and `coolwsd_memory_used_bytes` in Prometheus format;
   the number upstream declines to publish can be observed per document through
   the collector chosen in #17. Euro-Office emits StatsD, not Prometheus, which
   is a second small cost of that option.

### 10.3 What each option gives up

**Collabora Online / CODE, standalone container — the recommendation.**
- Gives up: **the default path**. On Nextcloud 35 this is now "a fully supported
  alternative", not the default. Integration-side breakage is more likely to be
  noticed late, and the connector's release cadence must be watched.
- Gives up: **a supported build**. Collabora states on its own product page that
  CODE is "not recommended for production environments" and ships roughly
  monthly. There is no supported build without a subscription, and the zero
  budget removes that option.
- Gives up: **published sizing for the shape actually deployed**. The one memory
  figure belongs to the AppImage variant; the Helm chart declines to state
  requests or limits.
- Gives up: **CPU headroom under editing**. Every open document is a LibreOffice
  process with `max_concurrency = 4` threads, on a box that also runs GPU-backed
  machine learning. Server-side rendering is a CPU decision as much as a memory
  one.
- Gives up: **a working internal cap out of the box**. `memproportion` must be
  re-derived; left alone it is decorative under a container limit.
- Keeps: the lowest published memory cost of any office option (1.2 GB at two
  users); **no database, no message broker, no second cache**; a permissive
  MPL-2.0 licence with no gate; a Prometheus metrics endpoint that closes the
  measurement gap; and a per-document cleanup path that degrades by closing idle
  documents instead of dying.

**Built-in CODE server (`richdocumentscode`) — the cheapest thing that works.**
- Gives up: **upstream's own endorsement**. Labelled "for local testing and
  non-production use"; Nextcloud "highly recommend[s]" a dedicated server.
- Gives up: **process isolation and an independent memory cap**. It runs as an
  AppImage inside the Nextcloud container, so it shares that container's cgroup
  and cannot be capped separately — which is exactly the control §6 says is the
  only real control.
- Gives up: **speed** ("a bit slower than a standalone server").
- Keeps: the same published figure (1 GB + 100 MB/user), one fewer service to
  operate, 300 MB of disk, and no reverse-proxy work.
- **Worth keeping in view as the fallback** if the standalone server's measured
  footprint proves worse than its published one.

**Euro-Office / ONLYOFFICE Docs — the default, and the one this note argues
against.**
- Gives up: **3.3× the memory before anyone opens a document**, on the only
  resource that is genuinely scarce, for a demand side that cannot use it. The
  published RAM column is identical at 2 users and at 99.
- Gives up: **the single-service property**. PostgreSQL, Redis, RabbitMQ, Nginx
  and Supervisor are stated prerequisites; four Node.js services plus a native
  converter run inside. That is a second platform beside the one being built.
- Gives up: **a swap-free host**, if the stated "SWAP: at least 4 GB" is honoured.
- Gives up: **maturity**. Four months old, two connector releases, a licensing
  page that promises commercial options later, and packages that upstream says
  are still coming.
- Keeps: the position of *default*, which is not nothing — it is the path
  Nextcloud will test, document and fix first from version 35 onward. It also
  keeps client-side rendering, which is the architecturally cheaper design and
  would win decisively at a scale this platform will never reach.
- **Revisit if** the demand side ever changes shape (many concurrent editors on
  large spreadsheets), or if Collabora's integration path visibly decays.

**No office server at all.**
- Gives up: collaborative editing, and with it a visible part of what makes the
  file store worth running for a household rather than a sync folder.
- Keeps: 1.2–4 GB, and the entire operational surface of a second stack.
- **This is the honest baseline the other three must beat**, and it should be
  priced as an option rather than assumed away — because at two accounts the
  office server is the more expensive half of the pair, not the accessory.

---

## Source index

Nextcloud
- <https://docs.nextcloud.com/server/stable/admin_manual/installation/system_requirements.html>
- <https://docs.nextcloud.com/server/stable/admin_manual/installation/server_tuning.html>
- <https://docs.nextcloud.com/server/latest/admin_manual/installation/system_requirements.html>
- <https://docs.nextcloud.com/server/latest/admin_manual/installation/server_tuning.html>
- <https://docs.nextcloud.com/server/latest/admin_manual/installation/php_configuration.html>
- <https://docs.nextcloud.com/server/latest/admin_manual/configuration_server/caching_configuration.html>
- <https://docs.nextcloud.com/server/latest/admin_manual/configuration_server/config_sample_php_parameters.html>
- <https://docs.nextcloud.com/server/latest/admin_manual/configuration_server/background_jobs_configuration.html>
- <https://docs.nextcloud.com/server/latest/admin_manual/release_notes/upgrade_to_35.html>
- <https://docs.nextcloud.com/server/stable/admin_manual/office/index.html> (Nextcloud 34)
- <https://docs.nextcloud.com/server/latest/admin_manual/office/index.html> (Nextcloud 35)
- <https://docs.nextcloud.com/server/latest/admin_manual/office/installation.html> (Collabora)
- <https://docs.nextcloud.com/server/latest/admin_manual/office/euro-office/index.html>
- <https://docs.nextcloud.com/server/latest/admin_manual/office/euro-office/installation.html>
- <https://docs.nextcloud.com/server/latest/admin_manual/office/euro-office/configuration.html>
- <https://github.com/nextcloud/all-in-one/blob/main/readme.md>
- <https://github.com/nextcloud/all-in-one/blob/main/Containers/nextcloud/Dockerfile>
- <https://github.com/nextcloud/notify_push/blob/main/README.md>
- <https://apps.nextcloud.com/api/v1/apps.json> (official app-store API)

Collabora Online / CODE
- <https://github.com/CollaboraOnline/online/blob/main/README.md>
- <https://github.com/CollaboraOnline/online/blob/main/kubernetes/helm/collabora-online/values.yaml>
- <https://github.com/CollaboraOnline/online.mirror/blob/main/coolwsd.xml.in>
- <https://github.com/CollaboraOnline/online.mirror/blob/main/configure.ac>
- <https://github.com/CollaboraOnline/online.mirror/blob/main/wsd/COOLWSD.cpp>
- <https://github.com/CollaboraOnline/online.mirror/blob/main/wsd/Admin.cpp>
- <https://github.com/CollaboraOnline/online.mirror/blob/main/wsd/AdminModel.cpp>
- <https://github.com/CollaboraOnline/online.mirror/blob/main/common/Util-server.cpp>
- <https://github.com/CollaboraOnline/online.mirror/blob/main/COPYING>
- <https://github.com/CollaboraOnline/richdocumentscode/blob/master/README.md>
- <https://www.collaboraonline.com/code/> (vendor product page — labelled as such)
- `https://sdk.collaboraonline.com/docs/installation/Configuration.html` — **unreachable**, proof-of-work bot challenge

ONLYOFFICE Docs
- <https://github.com/ONLYOFFICE/DocumentServer/blob/master/Readme.md>
- <https://github.com/ONLYOFFICE/Docker-DocumentServer/blob/master/README.md>
- <https://github.com/ONLYOFFICE/server/blob/master/Common/sources/license.js>
- <https://github.com/ONLYOFFICE/server/blob/master/Common/sources/constants.js>
- <https://github.com/ONLYOFFICE/server/blob/master/Common/sources/tenantManager.js>
- <https://github.com/ONLYOFFICE/server/blob/master/Common/config/default.json>
- <https://helpcenter.onlyoffice.com/docs/installation/docs-community-sys-reqs-linux.aspx>
- <https://helpcenter.onlyoffice.com/docs/installation/docs-community-sys-reqs-docker.aspx>
- <https://helpcenter.onlyoffice.com/docs/installation/docs-community-install-ubuntu.aspx>
- <https://api.onlyoffice.com/docs/docs-api/get-started/how-it-works/>

Euro-Office
- <https://github.com/Euro-Office/DocumentServer/blob/main/README.md>
- <https://github.com/Euro-Office/DocumentServer/blob/main/ATTRIBUTION>
- <https://github.com/Euro-Office/documentation/blob/main/docs/introduction/architecture.md>
- <https://github.com/Euro-Office/documentation/blob/main/docs/introduction/licensing.md>
- <https://github.com/Euro-Office/documentation/blob/main/docs/installation/docker.md>
- <https://github.com/Euro-Office/documentation/blob/main/docs/installation/ubuntu.md>

Runtime and storage components
- <https://www.php.net/manual/en/opcache.configuration.php>
- <https://www.php.net/manual/en/apcu.configuration.php>
- <https://www.php.net/manual/en/install.fpm.configuration.php>
- <https://www.postgresql.org/docs/current/runtime-config-resource.html>
- <https://redis.io/docs/latest/develop/reference/eviction/>
