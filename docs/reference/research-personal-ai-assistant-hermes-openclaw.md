# Personal AI assistant: Hermes vs OpenClaw

**Date:** 2026-08-19
**Status:** in progress. Covers #196 (165-01, Hermes footprint/storage/provenance,
section 1 below) only. OpenClaw's equivalent check (#197/165-02),
provider/secrets inventory (#198/165-03), use-case analysis (#199/165-04), a
local-inference/VRAM check (#200/165-05), exposure posture (#201/165-06), and
the final comparison and recommendation (#202/165-07) are follow-on tickets
against this same file.
**Sources:** primary only, per this repo's `/research` convention: the
project's own repository (`README.md`, `Dockerfile`, `docker-compose.yml`,
`.env.example`, `hermes_state_search.py`, and the documentation site's source
under `website/docs/` (`developer-guide/session-storage.md`,
`user-guide/docker.md`, `user-guide/sessions.md`,
`reference/environment-variables.md`, `reference/faq.md`,
`getting-started/installation.md`, `getting-started/platform-support.md`),
the project's own GitHub issue tracker for real, open and closed reports of
measured memory and storage growth, the GitHub REST and Search APIs for the
repository's and the `NousResearch` organization's own metadata (creation
dates, contributor/commit counts, release cadence, security-advisories
endpoint), the public GitHub Advisory Database API
(`api.github.com/advisories`), the PyPI registry API and the npm registry API
for package metadata, and `docs/adr/0002-resource-budget-and-feasibility-verdict.md`
and `docs/adr/0014-hostpath-local-pv-no-csi.md` as the resource-budget and
storage-abstraction precedents this section checks Hermes against. Every
claim carries its URL inline. Figures pulled via API are timestamped to this
check (2026-08-19); they move as the project grows.

---

## 1. Hermes: footprint, storage, provenance

The candidate named by #165 is `NousResearch/hermes-agent`. That path is
confirmed live and current: the repository exists, is maintained by the
`NousResearch` GitHub organization, was created 2025-07-22, and was last
pushed to 2026-08-19T20:52Z, hours before this check
(`GET /repos/NousResearch/hermes-agent`,
<https://api.github.com/repos/NousResearch/hermes-agent>). No identity
correction is needed here, unlike the possibility #165's own wording left
open, and the name and path match exactly.

### 1.1 Resource footprint

#### No whole-application minimum is published outside the Docker guide

The README's own framing of resource use is a claim about where Hermes can
run, not a number: "Run it on a $5 VPS, a GPU cluster, or serverless
infrastructure that costs nearly nothing when idle"
(<https://raw.githubusercontent.com/NousResearch/hermes-agent/main/README.md>).
No system-requirements page or FAQ entry gives a RAM/CPU floor for the base
agent; a targeted search of the documentation site's own Markdown source for
"RAM" turns up only unrelated hits (skill references, a VRAM note about local
models) and no resource-requirements page
(`search/code?q=repo:NousResearch/hermes-agent+"RAM"+extension:md`). The one
place a real table exists is the Docker guide, and it is written for the
containerized deployment specifically, not the project as a whole.

#### What's documented: the Docker guide's own resource table

`website/docs/user-guide/docker.md`, section "Resource limits":

| Resource | Minimum | Recommended |
| --- | --- | --- |
| Memory | 1 GB | 2-4 GB |
| CPU | 1 core | 2 cores |
| Disk (data volume) | 500 MB | 2+ GB (grows with sessions/skills) |

"Browser automation (Playwright/Chromium) is the most memory-hungry feature.
If you don't need browser tools, 1 GB is sufficient. With browser tools
active, allocate at least 2 GB."
(<https://raw.githubusercontent.com/NousResearch/hermes-agent/main/website/docs/user-guide/docker.md>).
The same page's worked `docker run` example sets `--memory=4g --cpus=2`, and
a separate Compose snippet earlier in the guide sets
`deploy.resources.limits: memory: 4G, cpus: "2.0"`. Neither figure is
enforced by anything upstream ships by default: the repository's own
top-level `docker-compose.yml` sets no `deploy.resources` block on its
`gateway` or `dashboard` service at all, checked in full
(<https://raw.githubusercontent.com/NousResearch/hermes-agent/main/docker-compose.yml>).
The 1-4 GB range is the documentation's own recommendation, not a shipped
ceiling, the same absence Omniroute's own compose file showed
(`research-omniroute-ai-gateway.md` section 1.2).

One further soft ceiling exists, but for a different, non-application
component: `TERMINAL_CONTAINER_MEMORY` defaults to `5120` (MB) for the
sandboxed containers Hermes's own terminal tool spawns to execute code
(`docs/reference/environment-variables.md`, "Terminal, Container/Sandbox
Backends" section). That number bounds a spawned sandbox, not the Hermes
process itself, and is not part of the application's own footprint.

Read against ADR-0002's standard slot: the standard slot's Application
component is capped at 1 GiB
(`docs/adr/0002-resource-budget-and-feasibility-verdict.md`, "the standard
slot" section). Hermes's own documented *minimum* matches that line exactly
(1 GB), and its documented *recommended* range (2-4 GB) already exceeds the
slot's entire 2 GiB total (Application, Database, and margin combined)
before section 1.3's real-world measurements are counted at all. Unlike
Immich or a database-backed workload, Hermes carries no separate Database
container (section 1.2): all persistence is one embedded SQLite file, so the
standard slot's 768 MiB Database line has no equivalent to spend here, which
makes the 2-4 GB recommended range even more clearly an Application-only
figure competing against the slot's Application-only 1 GiB.

#### What was actually measured: an open, active cluster of memory-growth reports

Unlike Omniroute, whose issue tracker showed two closed reports with three
later ones still active (`research-omniroute-ai-gateway.md` section 1.3),
Hermes's own issue tracker shows a wide, currently **open** cluster on this
exact axis: a search for `RSS` or `OOM` against the repository returns 745
matching issues in total
(`search/issues?q=repo:NousResearch/hermes-agent+(RSS+OR+OOM)`), and the
concrete reports below are representative, not exhaustive:

- **#46082** (opened 2026-06-14, still open): the bundled dashboard process
  (`hermes dashboard --skip-build`) leaks progressively: RSS grows from
  ~340 MB at startup to 4.8-5.3 GB over 2-15 hours of uptime, at which point
  the kernel SIGKILLs it; six recorded runs all ended the same way, one as
  short as under 4 minutes
  (<https://github.com/NousResearch/hermes-agent/issues/46082>). The
  reporter's own workaround was setting a systemd `MemoryMax=4G` /
  `MemoryHigh=3.5G` so the unit dies on its own terms instead of taking the
  host down with it.
- **#62743** (opened 2026-07-11, still open): 8 concurrent TUI-gateway
  sessions on a 32 GB host measured a combined **7,889 MB RSS across 7
  active `tui_gateway.entry` processes**, growing "monotonically with
  uptime" at roughly 50-80 MB/hour per session, 99.97% anonymous private
  pages (not reclaimable page cache)
  (<https://github.com/NousResearch/hermes-agent/issues/62743>). The same
  report's `state.db` was 7.2 GB across 2,729 sessions and 533,439 messages
  and it is carried forward into section 1.2.
- **#48287** (opened 2026-06-18, closed 2026-07-14 as **`not_planned`**, not
  fixed): a Windows-scheduled-task gateway process grew to **~50 GB of
  virtual memory over ~20 hours**, severe enough to crash unrelated system
  processes (Volume Shadow Copy, the desktop compositor, an AnyDesk service)
  before a full reboot; root-caused to an unbounded `_agent_cache`
  `OrderedDict` (`maxlen=128`) in `gateway/run.py`, each entry holding a full
  LLM client with its own `httpx` connection pool
  (<https://github.com/NousResearch/hermes-agent/issues/48287>). The
  `not_planned` closure means this specific report was not carried to a fix,
  distinct from a `completed` closure, a materially weaker signal than
  Omniroute's two `completed`-closed memory reports.
- **#89034** (opened 2026-08-18, still open, most recent version checked:
  v0.20.3): the one moderate data point found, a container running under a
  4 GiB cgroup memory limit held RSS at "~270-365 MiB," explicitly *not* an
  OOM event (`memory.events` showed `oom=0`); the failure this issue reports
  is a restart-loop corrupting the SQLite state file instead, carried
  forward into section 1.2
  (<https://github.com/NousResearch/hermes-agent/issues/89034>).

These four are not isolated: a further dozen-plus open issues track the same
failure family as of this check: #69180 (desktop renderer OOM crash-loop),
#76759 and #76768 (dashboard OOM-killed repeatedly, cap proposed but not yet
merged), #69966 ("repair 5 non-MCP gateway leaks"), #62950 (unbounded
in-memory caches in long-running processes), #70684 (CLI process leaks
memory, no `gc.collect()` after tool results), #26770 (`hermes update`
restarts the gateway and OOMs low-memory servers), #87175 ("bound memory
retention and child-process resources"), #70573/#70575 (systemd/gateway
restart handling around child OOM), #82874 (shutdown hang under SIGTERM),
#53315 (memory-provider shutdown not called). None of these are cited
individually above beyond naming them; the pattern that matters is that the
whole cluster is **open**, not a closed-then-quiet history the way
Omniroute's #4041/#4425 were.

#### Verdict for this axis

Hermes documents a 1 GB minimum / 2-4 GB recommended container footprint,
matching or exceeding ADR-0002's entire 2 GiB standard slot on the
Application line alone, with no separate Database container to subtract
against. What was actually measured under real, if uncontrolled, usage goes
considerably further: a 5+ GB dashboard leak, a near-8 GB combined TUI-gateway
RSS figure, and a ~50 GB virtual-memory report closed without a fix, a wider
and, on the evidence found, more currently-active set of open reports than
Omniroute's comparable section produced. Any deployment sizing decision for
this platform would need to budget well above the documented "recommended"
range and treat memory growth over multi-hour/multi-day uptime as the norm to
plan against, not the exception, a question for whichever ticket eventually
sizes an actual deployment, not this one.

### 1.2 Storage model: SQLite FTS5

#### What it persists

Hermes's own developer documentation for this subsystem is direct and
current: "Hermes Agent uses a SQLite database (`~/.hermes/state.db`) to
persist session metadata, full message history, and model configuration
across CLI and gateway sessions"
(<https://raw.githubusercontent.com/NousResearch/hermes-agent/main/website/docs/developer-guide/session-storage.md>).
The schema, quoted from the same source:

```
~/.hermes/state.db (SQLite, WAL mode)
├── sessions              — Session metadata, token counts, billing
├── messages              — Full message history per session
├── session_model_usage   — Per-model/per-task usage attribution rows
├── messages_fts          — FTS5 virtual table (content + tool_name + tool_calls)
├── messages_fts_trigram  — FTS5 virtual table with trigram tokenizer (CJK / substring search)
├── messages_fts_cjk      — FTS5 virtual table with cjk_unicode61 tokenizer
├── state_meta            — Key/value metadata table
├── gateway_routing       — Gateway routing metadata
├── compression_locks     — Cross-process compression locking
├── async_delegations     — Async delegation bookkeeping
└── schema_version        — Single-row table tracking migration state
```

This directly answers the ticket title's question: the FTS5 tables index
**message content, tool names, and serialized tool-call JSON**, a full-text
search index over conversation history, not a vector/embedding store. There
is no separate embeddings table in this schema; semantic recall, where it
exists, is handled by opt-in third-party memory-provider plugins (Honcho,
Mem0, Hindsight, and others named in `reference/environment-variables.md`'s
"Memory Providers" block), out of scope for this ticket. The `messages`
table itself carries the complete conversation payload per session
(`role`, `content`, `tool_calls`, `reasoning`, token counts, an
`api_content` byte-fidelity sidecar for prompt-cache-stable replay), and
`sessions` carries per-session billing/cost estimates and gateway routing
metadata (`chat_id`, `chat_type`, `origin_json`): this is the durable
record of every conversation Hermes has had across every connected
messaging platform, not an ephemeral cache. Schema version 23 is current as
of this check, with FTS5 build-verified at container-build time in the
`Dockerfile` (a self-test inserts a row and queries it via `MATCH` before
the image is considered valid).

The Dockerfile also documents *why* FTS5 needs special handling here at all:
Debian 13 trixie's bundled SQLite (3.46.1) "contains the upstream WAL-reset
corruption bug," so the image builds and links a pinned SQLite 3.53.4 from
source with `-DSQLITE_ENABLE_FTS5` and related flags explicitly set, rather
than relying on the distro package
(<https://raw.githubusercontent.com/NousResearch/hermes-agent/main/Dockerfile>).

#### Location: a `DATA_DIR`-style path, one volume, one file family

Default path: `~/.hermes/state.db`, derived from
`hermes_constants.get_hermes_home()`, itself overridable by the `HERMES_HOME`
environment variable (`environment-variables.md` section on `HERMES_HOME`;
`session-storage.md`, "Database Location"). Inside the official Docker image
this resolves to a single fixed mount point: `ENV HERMES_HOME=/opt/data` and
`VOLUME [ "/opt/data" ]` in the `Dockerfile`, matching the shipped
`docker-compose.yml`'s `~/.hermes:/opt/data` bind mount. `/opt/data` holds
`state.db`, its WAL (`state.db-wal`) and shared-memory (`state.db-shm`)
sidecar files in the same directory, plus config, `.env`, per-profile
`sessions/`, `memories/`, `skills/`, `cron/`, `hooks/`, and `logs/`
directories (`user-guide/docker.md`, "Persistent volumes" file-layout
table). This is exactly the `DATA_DIR`-shaped single mount point the ticket
asked to confirm: one directory, one workload, no external database
service.

#### Retention: opt-in, off by default, and one open unbounded-growth bug

There is no automatic default retention or rotation policy. `hermes sessions
prune` is a manual, filter-driven CLI command
(`website/docs/user-guide/sessions.md`, "Prune Old Sessions"), and an
opt-in automatic sweep exists but ships disabled:

```yaml
sessions:
  auto_prune: true          # opt in — default is false
  retention_days: 90        # keep ended sessions active within this window
  vacuum_after_prune: true  # reclaim disk space after a pruning sweep
  min_vacuum_interval_days: 30 # don't rewrite the DB more often than this
  min_interval_hours: 24    # don't re-run the sweep more often than this
```

(same source, "Automatic Pruning"). The documentation's own words on why it
defaults off: "session history is valuable for `session_search` recall, and
silently deleting it could surprise users." Its own growth-rate claim: "The
database grows slowly (typical: 10-15 MB for hundreds of sessions)," against
its own named "observed failure mode: 384 MB state.db with ~1000 sessions
slowing down FTS5 inserts and `/resume` listing" (same source, closing tip).

Independent measurements from the issue tracker corroborate the pessimistic
end of that range, not the optimistic one: **#62743**'s 7.2 GB `state.db`
across 2,729 sessions / 533,439 messages (section 1.1), and **#87928**
(open), which measured a **572 MB `state.db` with only 35 session rows**
because `hermes sessions prune`/`delete` do not cascade-delete the
corresponding `messages` rows or their FTS5 shadow tables: 94% of that
instance's `messages` table (36,785 of 39,055 rows, 1,383 distinct dead
`session_id`s) was orphaned data left behind by prior pruning, "the real
unbounded growth" per the report itself
(<https://github.com/NousResearch/hermes-agent/issues/87928>). This is an
open bug, not a documented behavior: nothing in `sessions.md` or
`environment-variables.md` warns that pruning leaves orphaned FTS content
behind, so the "auto-prune caps growth" story the config block above implies
does not fully hold as shipped.

A second, unrelated failure mode touches the same file: **#89034** (open,
most recent version checked, 2026-08-18) documents a restart-loop where an
s6-supervised gateway container killed mid-FTS5-write corrupts the
`messages_fts_*` shadow tables ("database disk image is malformed"),
requiring a full manual `state.db` recreation
(<https://github.com/NousResearch/hermes-agent/issues/89034>). Not a memory
issue (RSS stayed stable in that report, cgroup `memory.events` showed no
OOM), but a real, currently open storage-integrity risk against the exact
file this section is about.

#### Whether this fits ADR-0014, or reopens it

It fits without reopening it. ADR-0014 settled the pattern for exactly this
shape of workload: "Plain `local` PersistentVolumes, one static,
GitOps-committed manifest per workload or standard slot, over the state
pool" (`docs/adr/0014-hostpath-local-pv-no-csi.md`, "Decision"). A single
`/opt/data` mount holding one SQLite database file family plus a handful of
config/log directories is architecturally identical to Immich's own
Postgres data directory, already served by a static `local` PV/PVC pair
(`postgres-pv.yaml`/`postgres-pvc.yaml` in `workloads/immich/`, the concrete
precedent both ADR-0014 and the Omniroute research doc point to). Nothing
found in section 1.1 or 1.2 asks for dynamic provisioning, `kubectl`-native
resize, or `kubectl`-native snapshot, the three capabilities ADR-0014
declined to pay RAM for. ZFS's own `zfs snapshot` mechanism, ADR-0014's
named substitute for volume snapshots, applies here exactly as it does to
every other static-PV workload on this platform.

RWX is not needed either. `docker.md`'s own warning is explicit: "Never run
two Hermes gateway containers against the same data directory
simultaneously"; "session files and memory stores are not designed for
concurrent write access" in its own words. That is a single-writer-container
assumption, matching
ADR-0014's own RWO-is-sufficient finding for every workload named on this
platform so far. The one form of real concurrency Hermes does have is
multiple *processes* (CLI sessions, the gateway, worktree agents) writing to
the same `state.db` from the same container/pod, and that is handled
entirely inside SQLite itself, not by the storage layer: `session-storage.md`'s
"Write Contention Handling" section documents a short 1-second lock timeout,
application-level retry with 20-150ms jittered backoff (up to 15 retries),
`BEGIN IMMEDIATE` transactions, and periodic WAL checkpoints every 50
writes. That is single-node, single-volume contention handling, entirely
inside the scope ADR-0014 already covers; it does not ask for anything a
static `local` PV cannot provide.

**Verdict: fits ADR-0014 as-is.** A `workloads/hermes/` Kustomization would
need one static PV/PVC pair for `/opt/data`, sized generously above the
documented "10-15 MB typical" growth figure given the real-world 384 MB-7.2
GB range measured above, and the orphaned-message growth bug (#87928) and
the FTS corruption-under-restart-loop bug (#89034) are both facts a future
deployment ticket should carry forward, not gaps this section needs to
resolve.

### 1.3 Provenance check

#### Maintainer identity: an established AI research org, not a name borrowed for this product

`NousResearch` is a GitHub Organization account created 2023-05-20, over
two years before this specific repository, with 8,131 followers, 92 public
repositories, and its own domain as its listed blog
(`nousresearch.com`) (`GET /users/NousResearch`,
<https://api.github.com/users/NousResearch>). This is the same organization
this repository's parent ticket (#165) itself already characterizes as "a
real, known AI research organization." The `hermes-agent` repository was
created 2025-07-22 and has been pushed to as recently as 2026-08-19T20:52Z,
hours before this check (<https://api.github.com/repos/NousResearch/hermes-agent>).
It is over a year old, not a repository spun up around a single announcement.
Its own homepage, `hermes-agent.nousresearch.com`, is a subdomain of the
org's own domain, not a third-party or throwaway host.

One detail worth naming directly: the "Hermes" name predates this specific
agent product by years inside this org: Nous Research's own `Nous-Hermes`
line of fine-tuned language models is the origin of the brand, and the
repository's top commit author by a wide margin (below) is the same
individual publicly associated with that model line. This argues against
reading `hermes-agent` as a copycat product borrowing a recognizable name;
it reads as the org's own agent product built on its own, pre-existing
brand.

#### Commit and contributor authorship: one dominant author, real daily activity beneath

`GET /repos/NousResearch/hermes-agent/contributors` lists **396** distinct
contributor logins across the full paginated result (3 full pages of 100
plus a 96-row final page)
(<https://api.github.com/repos/NousResearch/hermes-agent/contributors>).
Contribution counts are sharply concentrated at the top: `teknium1` shows
8,520 contributions, `OutThisLife` 3,125, `kshitijk4poor` 1,601,
`ethernet8023` 446, `benbarclay` 403, the same "one dominant author, real
breadth beneath" shape Omniroute's own provenance check found for
`diegosouzapw` (`research-omniroute-ai-gateway.md` section 4.2), not
distinguishing evidence on its own.

The 30 most recent commits as of this check span roughly 24 hours and
name at least eight distinct human authors interleaved: `OutThisLife`,
`kshitijk4poor`, `ethernet8023`, `pierrenode`, `yingliang-zhang`,
`SolshineCode`, `helix4u`, plus one bot,
`hermes-seaeye[bot]`, whose commits carry a GitHub-verified signature
(<https://api.github.com/repos/NousResearch/hermes-agent/commits>): active,
multi-author, day-to-day development, not a quiet history between periodic
solo pushes. 28 GitHub releases were published between 2026-03-12 and
2026-08-18 alone
(<https://api.github.com/repos/NousResearch/hermes-agent/releases>), close
to weekly cadence over the last five months, corroborating the commit
pattern from an independent angle.

#### Scale, re-measured: #165's cited figures against this check's numbers

#165 cited "231.8k stars / 46.1k forks / 32,586 open issues." Re-measured
today: **233,009 stargazers, 46,591 forks, 33,565 open issues**, 898
subscribers (<https://api.github.com/repos/NousResearch/hermes-agent>). All
three moved modestly upward since #165 was framed, consistent with
continued organic growth rather than a stat that was inflated once and has
since stalled or reversed. As with Omniroute's own re-measurement
(`research-omniroute-ai-gateway.md` section 4.3), whether this growth curve
is itself a plausible rate for an agent product from a research org is a
base-rate question this check cannot settle by re-counting stars; per this
repository's own prior finding on Hermes, OpenClaw, and Omniroute (the
operator has independently verified these three candidates through channels
of their own before #163-165 were opened), that question is not re-argued
here.

#### Independent coverage

No dedicated third-party technical review or security write-up was found
during this check beyond the advisory-database entries covered below; a
targeted search did not surface the kind of SEO/affiliate coverage Omniroute's
own check found either. This is recorded as an absence, not a clearance:
`Hermes` and `hermes-agent` are both common enough terms that search coverage
is noisy, and this check did not attempt an exhaustive sweep.

#### Package registries: an official PyPI release, and an unofficial npm wrapper

A `hermes-agent` package exists on PyPI, version 0.19.0, author "Nous
Research" (<https://pypi.org/pypi/hermes-agent/json>): the publisher
identity matches the GitHub organization by name, corroborating the same
identity across two independent registries the way Omniroute's npm/GitHub
match did. Notably, though, the project's own `platform-support.md`
explicitly lists PyPI installs as **unsupported**: "installs via `pypi`
(e.g. `uv tool install hermes-agent`, `pip install hermes-agent`, etc.)" is
named directly under "Unsupported," alongside Homebrew and AUR installs
(<https://raw.githubusercontent.com/NousResearch/hermes-agent/main/website/docs/getting-started/platform-support.md>).
The package is genuinely theirs; it is simply not the channel this project
stands behind operationally: the installer script and the Docker image are
the supported paths (section 1.1).

A `hermes-agent` package also exists on the npm registry, but it is **not**
NousResearch's: its own description reads "Unofficial npm bridge for Hermes
Agent 0.20.4," maintained by a single third-party account (`wyrtensi`),
pointing at a separate repository
(`github.com/wyrtensi/hermes-agent-npm`), first published 2026-05-25
(<https://registry.npmjs.org/hermes-agent>). This is not evidence against
the primary project: the package is transparently labeled unofficial and
does not claim to be the org's own release, but it is a real
namespace-adjacent fact worth naming: an operator or automation that
resolves "hermes-agent" against npm rather than PyPI or the project's own
installer would land on a third party's wrapper, not on `NousResearch`'s own
code.

#### Security advisories: nine landed fixes, one still open

The repository's own Security Advisories endpoint is empty: no advisory
was filed directly through GitHub's repository-scoped feature
(`GET /repos/NousResearch/hermes-agent/security-advisories` → `[]`). A
broader query against the public GitHub Advisory Database for the `pip`
package `hermes-agent`, however, returns **ten** reviewed advisories
(`GET https://api.github.com/advisories?affects=hermes-agent`), a
materially different picture from Omniroute's zero:

| GHSA / CVE | Summary | Severity | Fixed in | Source |
| --- | --- | --- | --- | --- |
| GHSA-4pqm-j46f-795x / CVE-2026-53869 | DNS rebinding bypasses Host/Origin validation on WebSocket endpoints (`/api/pty`, `/api/ws`, `/api/pub`, `/api/events`) | High (7.5) | 0.16.0 | VulnCheck |
| GHSA-99f9-j8r3-p853 | `response_store.db`/`webhook_subscriptions.json` created world-readable (0o644), exposing history + HMAC secrets | Medium (5.5) | 0.16.0 | VulnCheck |
| GHSA-33qv-c5qm-799v / CVE-2026-10223 | Injection in `_scan_memory_content` (`tools/memory_tool.py`) | Low (6.3) | 0.15.0 | VulDB |
| GHSA-pmqc-57g8-c22c / CVE-2026-10224 | Uncontrolled resource consumption, Feishu webhook (`_handle_webhook_request`) | Medium (5.3) | **unfixed** | VulDB |
| GHSA-mv8x-fg99-32mf / CVE-2026-10222 | Injection in `_sanitize_env_lines` (`hermes_cli/config.py`) | Low (5.6) | 0.18.0 | VulDB |
| GHSA-xq8w-9jvx-gm3v / CVE-2026-10221 | Injection in `_compress_context` (`run_agent.py`) | Medium (7.3) | *see below* | VulDB |
| GHSA-cv5c-mh6j-wvp9 / CVE-2026-9369 | Incorrect comparison in `_discover_dashboard_plugins` | Low (5.3) | 0.15.0 | VulDB |
| GHSA-wm96-9gfh-vvgq / CVE-2026-9368 | Sandbox issue, `execute_code` env-var handling | Medium (7.3) | 0.11.0 | VulDB |
| GHSA-pgp4-xr4j-h5cg / CVE-2026-9366 | Injection in `_scan_context_content` (`agent/prompt_builder.py`) | Medium (7.3) | 0.15.0 | VulDB |
| GHSA-238w-f66p-w349 / CVE-2026-9353 | Injection via `THREAT_PATTERNS` (`agent/skills_guard.py`) | Medium (7.3) | 0.15.0 | VulDB |

The two VulnCheck-sourced advisories (DNS rebinding, world-readable secret
files) are the cleanest: both landed a fix in the same release, 0.16.0,
referencing merged PRs (#30221/#31685 and #30917/#31469 respectively). The
seven VulDB-sourced entries all carry identical boilerplate framing not
present on the VulnCheck ones: "The vendor was contacted early about this
disclosure but did not respond in any way", a different engagement pattern
from Omniroute's same-day, per-finding maintainer reply to its own
Socket.dev finding (`research-omniroute-ai-gateway.md` section 4.5). Fix
status among those seven is mixed, and needed checking past the advisory
metadata itself:

- **Six show a real, merged fix**: GHSA-33qv-c5qm-799v, GHSA-mv8x-fg99-32mf,
  GHSA-cv5c-mh6j-wvp9, GHSA-wm96-9gfh-vvgq, GHSA-pgp4-xr4j-h5cg, and
  GHSA-238w-f66p-w349 all show a `first_patched_version` and reference a
  merged commit.
- **One (GHSA-xq8w-9jvx-gm3v / CVE-2026-10221) is fixed despite stale
  advisory metadata.** The GitHub Advisory Database record itself lists
  `first_patched_version: null`, which read alone would suggest this is
  still open. Checking the linked tracking issue (#26979) and PR (#69860)
  directly shows otherwise: PR #69860 merged 2026-07-23, and issue #26979
  is closed with `state_reason: completed`
  (<https://github.com/NousResearch/hermes-agent/pull/69860>,
  <https://github.com/NousResearch/hermes-agent/issues/26979>). The fix
  landed; the advisory record simply was never updated to reflect it.
- **One (GHSA-pmqc-57g8-c22c / CVE-2026-10224) is genuinely still open.**
  The repository's own tracking issue, #29154, links a private GitHub
  Security Advisory (`GHSA-jm8j-wwx3-97gc`) still in `triage` as of this
  check, and its named fix, PR #73406 ("fix(feishu): authenticate webhook
  traffic before quota"), is open and unmerged
  (<https://github.com/NousResearch/hermes-agent/issues/29154>,
  <https://github.com/NousResearch/hermes-agent/pull/73406>). This is a
  real, currently unpatched, medium-severity advisory against the exact
  version range (`<= 0.19.0`, the current PyPI release) this ticket would
  be evaluating for deployment, the single most concrete unresolved
  provenance finding in this section, and something #202 (165-07) should
  weigh directly.

#### Verdict

The identity behind the project is real and well-established: a
two-year-old research organization with a name predating this specific
product, a homepage on its own domain, active daily multi-author commit
activity, and near-weekly releases. That much reads the same as Omniroute's
own clean provenance verdict. Where this check diverges from Omniroute's is
the advisory record and the response pattern behind it: ten reviewed
GitHub Advisory Database entries rather than zero, most independently
confirmed fixed on closer inspection past the advisory metadata itself, but
one still genuinely open against the current release, and a "vendor did not
respond" framing attached to most of them rather than the same-day
engagement Omniroute's maintainer showed against its own Socket.dev
finding. Nothing found here is disqualifying on its own: real projects
accumulate real CVEs, and most of these were in fact fixed, but the
pattern is different enough from Omniroute's that it should carry forward
as its own line into whichever ticket writes the final recommendation,
not be treated as an equivalent "provenance clear" verdict.

---

This section covers #196 (165-01) only. OpenClaw's equivalent footprint,
storage, and provenance check (#197/165-02), the provider/secrets inventory
across both candidates (#198/165-03), use-case analysis (#199/165-04), the
local-inference/VRAM check (#200/165-05), exposure posture (#201/165-06),
and the final comparison and recommendation (#202/165-07) are all follow-on
tickets against this same file.
