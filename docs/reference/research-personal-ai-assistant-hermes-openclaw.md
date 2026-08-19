# Personal AI assistant: Hermes vs OpenClaw

**Date:** 2026-08-19
**Status:** in progress. Covers #196 (165-01, Hermes footprint/storage/provenance,
section 1 below), #197 (165-02, OpenClaw's equivalent check, section 2 below),
and #198 (165-03, provider integration and secrets for both, section 3
below). Use-case analysis (#199/165-04), a local-inference/VRAM check
(#200/165-05), exposure posture (#201/165-06), and the final comparison and
recommendation (#202/165-07) are follow-on tickets against this same file.
**Sources:** primary only, per this repo's `/research` convention: the
project's own repository (`README.md`, `Dockerfile`, `docker-compose.yml`,
`.env.example`, `hermes_state_search.py`, and the documentation site's source
under `website/docs/` (`developer-guide/session-storage.md`,
`user-guide/docker.md`, `user-guide/sessions.md`,
`reference/environment-variables.md`, `reference/faq.md`,
`getting-started/installation.md`, `getting-started/platform-support.md`,
`integrations/providers.md`, `user-guide/messaging/index.md` and its
per-platform pages for Telegram, Discord, Slack, WhatsApp, Signal and email,
`user-guide/secrets/index.md`, `user-guide/features/provider-routing.md`,
`user-guide/features/credential-pools.md`), OpenClaw's own repository and
documentation site (`docs/providers/index.md`, `docs/providers/clawrouter.md`,
`docs/gateway/secrets.md`, `docs/reference/secretref-credential-surface.md`,
`docs/channels/index.md`, `docs/channels/telegram.md`, `docs/channels/discord.md`,
`docs/channels/slack.md`, `docs/channels/whatsapp.md`,
`docs/channels/signal.md`), the project's own GitHub issue tracker for real,
open and closed reports of measured memory and storage growth, the GitHub
REST and Search APIs for the repository's and the `NousResearch` and
`openclaw` organizations' own metadata (creation dates, contributor/commit
counts, release cadence, security-advisories endpoint), the public GitHub
Advisory Database API (`api.github.com/advisories`), the PyPI registry API
and the npm registry API for package metadata, and
`docs/adr/0002-resource-budget-and-feasibility-verdict.md`,
`docs/adr/0009-secrets-sops-age.md`, and
`docs/adr/0014-hostpath-local-pv-no-csi.md` as the resource-budget,
secrets-mechanism, and storage-abstraction precedents this file checks both
candidates against. Every claim carries its URL inline. Figures pulled via
API are timestamped to this check (2026-08-19); they move as the project
grows.

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

## 2. OpenClaw: footprint, storage, provenance

The candidate named by #165 is `openclaw/openclaw`. That path is confirmed
live and current: the repository exists, is maintained by the `openclaw`
GitHub organization, was created 2025-11-24, and was last pushed to
2026-08-19T21:08Z, within the hour of this check
(`GET /repos/openclaw/openclaw`,
<https://api.github.com/repos/openclaw/openclaw>). No identity correction is
needed; the name and path match exactly. One background fact worth stating up
front because it shapes several findings below: OpenClaw was launched under
the name Clawdbot, briefly renamed Moltbot, then settled on OpenClaw
(`docs.openclaw.ai/gateway/security`,
<https://docs.openclaw.ai/gateway/security>, and corroborated independently
by Northeastern University's own coverage, cited in section 2.3). That
rename history is also why the `openclaw` GitHub organization account itself
was created 2026-01-04
(`GET /users/openclaw`, <https://api.github.com/users/openclaw>), six weeks
*after* this specific repository, rather than the repository being younger
than the org, the shape section 1 found for Hermes/`NousResearch`.

### 2.1 Resource footprint

#### No single documented Docker minimum exists

Unlike Hermes's `user-guide/docker.md`, OpenClaw's own `docs/install/docker.md`
does not carry a resource-limits table for the running container at all: its
only RAM figure is a build-time warning, "Minimum: 2 GB for image build
operations... `pnpm install` may be terminated with exit code 137 (out-of-memory)
on hosts with only 1 GB"
(<https://raw.githubusercontent.com/openclaw/openclaw/main/docs/install/docker.md>).
`docs/install/hetzner.md` repeats the identical framing, "at least 2 GB RAM
for a source image build"
(<https://raw.githubusercontent.com/openclaw/openclaw/main/docs/install/hetzner.md>).
Both are about compiling the image, not running it; neither is a runtime
minimum. `docs/install/index.md` and `docs/vps.md`, the two pages that would
be the natural home for a whole-application requirement, state none
(<https://raw.githubusercontent.com/openclaw/openclaw/main/docs/install/index.md>,
<https://raw.githubusercontent.com/openclaw/openclaw/main/docs/vps.md>).

#### What is documented, scattered across device-specific guides

The one page carrying an explicit runtime table is written for a specific
device, not the Docker deployment: `docs/install/raspberry-pi.md`.

| Source | RAM | CPU | Disk |
| --- | --- | --- | --- |
| Raspberry Pi guide, minimum | 1 GB | 1 core | 500 MB free |
| Raspberry Pi guide, recommended | 2 GB (4 GB preferred) | Pi 4/5 | 16 GB+ microSD/SSD |
| Docker/Hetzner guides, build only | 2 GB | not specified | not specified |
| `fly.toml`, production deploy | 2,048 MB | `shared-cpu-2x` | not stated |

"Pi 4 with 4 GB" is rated "Good," "Pi 4 with 2 GB" is "OK" and needs swap,
"Pi 4 with 1 GB" is "Tight, possible only with swap," and the Pi Zero 2 W's
512 MB is "not recommended"
(<https://raw.githubusercontent.com/openclaw/openclaw/main/docs/install/raspberry-pi.md>).
That 1 GB minimum / 2-4 GB recommended shape is coincidentally close to
Hermes's own Docker-guide numbers (section 1.1), but it is sourced from a
device-sizing page, not a container resource-limits table; OpenClaw ships no
direct equivalent of Hermes's `docker.md` "Resource limits" section. The
project's own `fly.toml`, its actual production deployment manifest, commits
to a concrete number rather than a range: `2048mb` memory on a
`shared-cpu-2x` machine, with the Node.js heap explicitly capped below that
at 1,536 MB
(<https://raw.githubusercontent.com/openclaw/openclaw/main/fly.toml>). That
figure is a real operational choice, closer to Hermes's "recommended" band
than to either project's documented floor.

Nothing enforces any of these figures by default in the shipped Docker
artifacts: the repository's own `docker-compose.yml` sets no
`deploy.resources` block on either the `openclaw-gateway` or `openclaw-cli`
service, checked in full
(<https://raw.githubusercontent.com/openclaw/openclaw/main/docker-compose.yml>).
The same absence as Hermes's and Omniroute's own compose files.

#### What was actually measured: an active, currently-open leak cluster

A search of the issue tracker for `RSS` or `OOM` returns 2,332 matching
issues in total, 159 of them currently open
(`search/issues?q=repo:openclaw/openclaw+(RSS+OR+OOM)`,
`+is:open`). A narrower search for the literal phrase "memory leak" returns
888 issues: 30 open, 858 closed; of the closed ones, 743 carry
`state_reason: completed` and 112 carry `state_reason: not_planned`, a gap
of 3 against the 858 closed total that the search API's own `reason:` filter
does not explain (some closed issues may carry no `state_reason` at all)
(`search/issues?q=repo:openclaw/openclaw+"memory+leak"`, `+is:open`,
`+is:closed`, `+is:closed+reason:not_planned`,
`+is:closed+reason:completed`). The concrete reports below are
representative, not exhaustive:

- **#91588** (opened 2026-06-09, still open): "Critical: Gateway Memory Leak
  — RSS grows from 350MB to 15.5GB over days, causing repeated OOM crashes."
  Measured directly: gateway RSS at 15,513 MB before an OOM-triggered
  `launchd` restart, dropping to 350 MB immediately after, on an 8 GB Mac;
  "no heap limit configured... on an 8 GB machine, this means it can consume
  all available RAM before being killed"
  (<https://github.com/openclaw/openclaw/issues/91588>).
- **#103788** (opened 2026-07-10, still open): under memory pressure at
  "RSS ~1.8 GiB, 118-120% of 1.5 GiB threshold," the gateway does not crash
  but silently returns empty responses from every tool call (exec,
  session_status, cron, web_search, Read) while continuing to accept
  messages, a degraded-but-alive failure mode distinct from the crash #91588
  documents (<https://github.com/openclaw/openclaw/issues/103788>).
- **#121202/#121203/#121214** (three near-duplicate reports, opened and
  closed the same day, 2026-08-09, all closed `not_planned`): "Gateway
  memory leak on 2026.7.1-2: deferred session suspensions never released
  (~3 MB/session), OOM every 2-3 hours." Heap-snapshot analysis (memlab plus
  custom retainer tracing) traced it to `onDeferredSessionSuspension`
  closures never released from `sessionStore`; measured RSS growth of
  "~6-7 MB/min," hitting a systemd `MemoryHigh=1.2G` limit in 2-3 hours; the
  report itself notes "this looks like the same class as #120394," naming a
  fourth, separately-tracked report of the same failure family
  (<https://github.com/openclaw/openclaw/issues/121202>). The `not_planned`
  closure on all three, the same weaker signal Hermes's own #48287 showed
  (section 1.1), means this specific report was not carried to a fix under
  that number, though the linked #120394 remains open.

A further set of open reports names the same failure family without being
cited individually in depth here: #120394 (event-loop saturation and
subagent orphaning tied to the same leak class), #115424 (V8 heap OOM during
a main-session turn), #99659 (OOM after a companion app connected), #119565
(concurrent MCP calls causing "excessive memory amplification"), #86119
(orphaned worker processes accumulating after subagent/cron runs). As with
Hermes, the pattern that matters is that a real cluster of reports is
currently **open**, not a closed-then-quiet history.

#### Verdict for this axis

OpenClaw publishes no single Docker-specific resource-limits table the way
Hermes does; the closest documented figures are a device-sizing page's 1 GB
minimum / 2-4 GB recommended range (Raspberry Pi) and the project's own
production `fly.toml` commitment of 2,048 MB. Read against ADR-0002's
standard slot (Application capped at 1 GiB, no separate Database line
needed here since all persistence is SQLite embedded in the same process,
section 2.2), that 1 GB floor again matches the Application line exactly;
the fly.toml figure (2,048 MB, effectively 2 GiB) lands right at the slot's
entire budget rather than under it, and the Raspberry Pi guide's 4 GB upper
bound clears it outright, before any real-world measurement is counted.
What was actually measured
goes further in the same direction as Hermes's own finding: an open,
15.5 GB RSS crash report, an open degraded-state report at 1.8 GiB, and a
closed-`not_planned`, still-unresolved-elsewhere 2-3-hour-to-OOM leak class,
against a documented default of *no* Node.js heap limit at all in at least
one of those reports. Any deployment sizing decision for this platform would
need the same treatment section 1.1 gave Hermes: budget well above the
documented range and plan for multi-hour memory growth as the norm, a
question for whichever ticket eventually sizes an actual deployment.

### 2.2 Storage model: two-tier SQLite, FTS5 plus optional vector search

#### What it persists

OpenClaw's own architecture documentation describes a two-tier SQLite
design, current as of this check: a **global database**
(`~/.openclaw/state/openclaw.sqlite`, schema version 7) holding
control-plane state (agent discovery, gateway coordination, task/flow
ledgers, plugin state, scheduler runtime, backup metadata, migration
records), and a **per-agent database**
(`~/.openclaw/agents/<agentId>/agent/openclaw-agent.sqlite`, schema version
17) holding data-plane state owned by each agent: session metadata,
transcript event streams, workspace/cache data, and memory indexes
(<https://raw.githubusercontent.com/openclaw/openclaw/main/docs/refactor/database-first.md>).
Both run SQLite in WAL mode, using `node:sqlite` directly rather than a
wrapper, and the project states this split exists to give "one durable
global view without forcing large agent workspaces, transcripts, and binary
scratch data into the shared gateway write lane," isolating per-agent
growth from control-plane queries, the opposite structural choice from
Hermes's single `state.db` file (section 1.2). Session rows themselves carry
`sessionStartedAt`, `lastInteractionAt`, and `updatedAt` lifecycle timestamps,
with full conversation history archived as JSONL transcript files alongside
the SQLite session rows
(<https://raw.githubusercontent.com/openclaw/openclaw/main/docs/concepts/session.md>).
Configuration remains file-backed in `openclaw.json`; only "runtime auth
profiles move to SQLite," external provider or CLI credential files stay
owner-managed outside the database (`database-first.md`, same source).

#### Location: one state directory, no external database service

Default path: `~/.openclaw`, overridable via `OPENCLAW_STATE_DIR`
(`.env.example`,
<https://raw.githubusercontent.com/openclaw/openclaw/main/.env.example>).
Inside the official Docker image this resolves to three bind-mounted
directories under `/home/node`: `OPENCLAW_CONFIG_DIR` →
`/home/node/.openclaw` (holds `openclaw.json`, agent auth profiles, `.env`),
`OPENCLAW_WORKSPACE_DIR` → `/home/node/.openclaw/workspace`, and
`OPENCLAW_AUTH_PROFILE_SECRET_DIR` → `/home/node/.config/openclaw`
(encryption key material), matching the shipped `docker-compose.yml`'s
volume mounts
(<https://raw.githubusercontent.com/openclaw/openclaw/main/docs/install/docker.md>).
No external database service is required to run OpenClaw: both SQLite tiers
are embedded files under that same tree, the same `DATA_DIR`-shaped single
mount point the ticket asked to confirm.

#### Vector/embedding store: embedded by default, an external-file plugin optional

This is the one axis where OpenClaw's answer differs materially from
Hermes's. The builtin memory backend is a **hybrid retrieval engine**: FTS5
full-text search with BM25 scoring, plus vector search over embeddings from
a configurable provider (OpenAI by default if credentials are present,
Ollama, Bedrock, and others), merged into one "deterministic ranking by
relevance, recency, and write-time importance"
(<https://raw.githubusercontent.com/openclaw/openclaw/main/docs/concepts/memory-builtin.md>).
Both the FTS5 index and the vector embeddings for this default path live
inside the same per-agent `openclaw-agent.sqlite` file, no separate service,
no separate file. Indexed content is `MEMORY.md`, `USER.md`, and files under
`memory/*.md`, chunked at 400 tokens with 80-token overlap (same source). A
second, genuinely separate vector store exists as an **opt-in plugin, not a
default**: `@openclaw/memory-lancedb` runs LanceDB as "an embedded local
file store rather than an external service," installed explicitly and
writing to `~/.openclaw/memory/lancedb` by default (configurable, with an
optional S3-compatible backend)
(<https://raw.githubusercontent.com/openclaw/openclaw/main/docs/plugins/memory-lancedb.md>).
Neither path is an external database service; the plugin path is simply a
second local file store rather than a table inside the shared SQLite file.

#### Retention: auto-prune on by default, and two open unbounded-growth bugs

Unlike Hermes, whose `auto_prune` ships `false`, OpenClaw's session
maintenance defaults to active enforcement:

```json5
session: {
  maintenance: {
    mode: "enforce",           // "warn" only reports, does not prune
    pruneAfter: "30d",
    archiveDashboardAfter: "7d",
    maxEntries: 500,
    preserveRecent: "7d",
  },
}
```

(<https://raw.githubusercontent.com/openclaw/openclaw/main/docs/concepts/session.md>,
source of the schema default confirmed against
`src/config/sessions/store-maintenance.ts`). No equivalent to Hermes's own
"10-15 MB for hundreds of sessions" growth-rate claim was found in the pages
searched; this check records that absence rather than a number.

Two open bugs undercut that "enforce means bounded" story, on two different
tables:

- **#112638** (opened 2026-07-22, open): in `enforce` mode,
  `session.maintenance.maxEntries`/`maxDiskBytes` are "silently exceeded
  because thread/channel/topic session entries are treated as protected and
  skipped by all three reclaim paths." Reproduced directly: "Observed: 562
  entries and ~420MB with `maxEntries` effectively [unbounded]" against a
  configured 500-entry / 400 MB ceiling
  (<https://github.com/openclaw/openclaw/issues/112638>). This is the
  `enforce`-mode default failing on exactly the busy Slack/Telegram
  deployment shape the config is meant to bound.
- **#114612** (opened 2026-07-27, open): "SQLite unbounded growth:
  `memory_index_chunks` + `memory_embedding_cache` tables have no retention
  policy, will fill disk over time." Field evidence from a production
  instance: `memory_index_chunks` at 38,985 rows / 3.3 GB and growing, versus
  session tables held steady at ~200 MB by the same `session.maintenance`
  mechanism above; root cause traced to
  `measureSessionPhysicalDiskUsage` (`src/config/sessions/disk-budget.ts`)
  scanning only session/transcript tables, not the plugin-owned memory
  tables covered in the previous subsection
  (<https://github.com/openclaw/openclaw/issues/114612>). This is a direct,
  currently-open unbounded-growth bug against the vector/embedding path this
  section was asked to check specifically.

A separate cluster of open storage-*integrity* (not growth) bugs also exists
against the state database itself: **#125744** (opened 2026-08-18, open),
b-tree pointer-map corruption recurring twice in three days on
`state/openclaw.sqlite`, with the gateway holding a deleted `-shm` file
descriptor, a "WAL split-brain signature," and the project's own in-place
recovery mechanism (from a prior fix, #114278) failing to fire
(<https://github.com/openclaw/openclaw/issues/125744>); **#123327** and
**#120549**, both open, tracking WAL-mode SQLite corruption on non-local
filesystems (virtiofs, 9p, Docker Desktop/OrbStack bind mounts); and
**#94229**, open, a `plugin_state_entries` corruption report. None of these
are cited in further depth here beyond naming them; the pattern is that
storage-integrity risk against the same file family this section is about
is a currently-open, not historical, concern.

#### Whether this fits ADR-0014, or reopens it

It fits without reopening it, on the same reasoning section 1.2 used for
Hermes. ADR-0014's decision is "plain `local` PersistentVolumes, one static,
GitOps-committed manifest per workload or standard slot"
(`docs/adr/0014-hostpath-local-pv-no-csi.md`, "Decision"). A single
`~/.openclaw` mount holding two SQLite database files (global and per-agent),
JSONL transcript archives, and an optional LanceDB directory is
architecturally the same shape as Hermes's single `/opt/data` mount and
Immich's Postgres data directory, already served by a static `local` PV/PVC
pair. Nothing found in section 2.1 or 2.2 asks for dynamic provisioning,
`kubectl`-native resize, or `kubectl`-native snapshot, the three
capabilities ADR-0014 declined to pay RAM for; `zfs snapshot` applies here
exactly as it does to every other static-PV workload on this platform.

RWX is not needed either: nothing in the documentation describes multiple
containers writing to the same state directory concurrently, and the WAL
corruption reports above (#123327, #120549) are explicitly caused by running
a *single* SQLite writer over a *non-local* filesystem (network/virtualized
mounts), not by a legitimate multi-writer use case; if anything, those
reports argue for keeping this workload on a genuinely local `hostPath`-backed
volume rather than for RWX, reinforcing ADR-0014's own local-disk assumption
rather than testing it. The two-tier database split (global vs. per-agent)
is itself an application-level concurrency answer, not a storage-layer one,
consistent with ADR-0014's finding that this class of workload's contention
handling belongs inside the application, not the PV.

**Verdict: fits ADR-0014 as-is.** A `workloads/openclaw/` Kustomization would
need one static PV/PVC pair for `~/.openclaw`, sized above whatever the
memory-index growth shown in #114612 implies for a given deployment rather
than the small steady-state session-table figure alone, and the two open
storage-integrity bugs (#125744 and the filesystem-locality cluster) are
facts a future deployment ticket should carry forward, including the direct
warning inside those reports themselves that WAL-mode SQLite over a
non-local filesystem is the trigger, which is itself an argument for
exactly the local, non-networked `hostPath` model ADR-0014 already chose,
not against it.

### 2.3 Provenance check

#### Maintainer identity: a project mid-rebrand, not a name borrowed for this product

The `openclaw` GitHub organization was created 2026-01-04, with 23,263
followers, its own listed domain (`openclaw.ai`) as its blog, and a public
contact address (`peter@openclaw.ai`) (`GET /users/openclaw`,
<https://api.github.com/users/openclaw>). Read together with the rename
history noted in this section's opening (Clawdbot → Moltbot → OpenClaw), the
org account being younger than the repository is explained by the rebrand,
not by the org being freshly stood up around a single announcement: the
underlying project, under its earlier names, is older than either the org
account or this specific repository path. The email domain (`openclaw.ai`)
matches the org's own listed homepage exactly, and the individual behind it
identifiable from the commit history below (`steipete`) is independently
named as "OpenClaw developer Peter Steinberger" in Northeastern University's
own coverage ("Independent coverage," below), the same person, not a
pseudonymous or unverifiable maintainer.

#### Commit and contributor authorship: one very dominant author, real but thinner breadth beneath

`GET /repos/openclaw/openclaw/contributors` lists **372** distinct
contributor logins across the full paginated result (three full pages of
100 plus a 72-row final page)
(<https://api.github.com/repos/openclaw/openclaw/contributors>).
Concentration at the top is sharper than either Hermes or Omniroute showed:
`steipete` (Peter Steinberger) shows 41,561 contributions, more than three
times Hermes's top contributor's count against a comparable-sized
contributor list; `vincentkoc` 12,621, `shakkernerd` 4,176, `obviyus` 1,960,
and `github-actions[bot]` 1,051.

The 30 most recent commits as of this check span roughly three hours
(2026-08-19T18:05Z to 21:13Z) and name seven distinct logins: `steipete`
(the large majority of the 30), `clawsweeper` (twice), `vincentkoc` (twice),
`joshavant`, `shakkernerd`, `sjudson`, and `bdjben`
(<https://api.github.com/repos/openclaw/openclaw/commits>). All 30 carry a
GitHub-verified signature. `clawsweeper` is a registered `User` account, not
a GitHub App bot, per its own account record
(`GET /users/clawsweeper`, <https://api.github.com/users/clawsweeper>); this
check did not attempt to determine whether it is operated by a person or by
automation running under a personal token, and states only what the account
type field itself reports. Set against Hermes's 30-commit window (roughly 24
hours, at least eight distinct human authors interleaved plus one verified
bot), OpenClaw's most-recent-commits window is both shorter in wall-clock
time and more concentrated in a single author, even though its total
contributor list (372) is comparable in scale to Hermes's (396).

Release cadence is markedly faster than Hermes's: **234** GitHub releases
from `v0.1.1` (2025-11-25) to `v2026.8.1-beta.2` (2026-08-15)
(<https://api.github.com/repos/openclaw/openclaw/releases>), roughly 264
days apart, averaging close to one release per day rather than Hermes's
near-weekly cadence.

#### Scale, re-measured: #165's cited figures against this check's numbers

#165 cited "386.5k stars / 81.2k forks / 5,621 open issues." Re-measured
today: **386,803 stargazers, 81,264 forks, 5,804 open issues**, 1,757
subscribers (<https://api.github.com/repos/openclaw/openclaw>). All three
moved modestly upward since #165 was framed, the same direction Hermes's own
re-measurement showed (section 1.3). As with Hermes and Omniroute's own
re-measurements, whether this growth curve is itself a plausible rate is a
base-rate question this check does not re-argue, per this repository's own
prior finding that the operator has independently verified Hermes, OpenClaw,
and Omniroute through channels of their own before #163-165 were opened.

#### Independent coverage: extensive, and largely about security posture

Unlike Hermes, where this check found no dedicated third-party coverage,
OpenClaw has been covered directly and repeatedly by name, almost entirely
on its security posture. Two sources were read in full for this check:

- **Bitsight** (João Cruz, Principal Security Research Scientist),
  published 2026-02-09: Bitsight's own internet-wide scan "discovered over
  30,000 distinct OpenClaw instances online between January 27 and February
  8, 2026," spanning technology, healthcare, finance, government, and
  insurance sectors, and observed attackers attempting "authentication
  bypasses, protocol downgrades" against exposed instances, including
  evidence some "had read the source" code. The article quotes the
  project's own creator: "Most non-techies should not install this"
  (<https://www.bitsight.com/blog/openclaw-ai-security-risks-exposed-instances>).
- **Northeastern University** (Cesareo Contreras), published 2026-02-10:
  quotes cybersecurity researcher Aanjhan Ranganathan calling OpenClaw "a
  privacy nightmare" over the scope of data access it requests and limited
  visibility into where that data goes once granted, and separately
  confirms "OpenClaw developer Peter Steinberger announced security
  improvements, including requiring GitHub accounts (one week old minimum)
  for skill uploads to ClawHub"
  (<https://news.northeastern.edu/2026/02/10/open-claw-ai-assistant/>).

A further set of security-vendor and press pieces on the same topic was
located but not read in full for this check, recorded here as evidence of
coverage volume rather than as sourced claims: Sangfor, Atomicmail, Reco.ai,
Trend Micro, Cisco Blogs, and McAfee all published pieces specifically about
OpenClaw's security exposure during the same period (search results for
"OpenClaw AI assistant openclaw.ai review security", 2026-08-19). This is
the opposite finding from Hermes's "absence, not a clearance" verdict:
OpenClaw's coverage is real, substantial, and consistently about the same
theme, default-exposed instances and broad tool/data access under a
single-operator trust model the project's own security documentation
confirms by design (`docs.openclaw.ai/gateway/security`,
<https://docs.openclaw.ai/gateway/security>: "OpenClaw is not a hostile
multi-tenant security boundary for multiple adversarial users").

#### Package registries: a matching npm publisher, and an unrelated PyPI namesake

An `openclaw` package exists on the npm registry, maintained by `steipete`
(`steipete@gmail.com`) and `vincentkoc` (`vincentkoc@ieee.org`), the top two
contributors by commit count found above, pointing at
`git+https://github.com/openclaw/openclaw.git`
(<https://registry.npmjs.org/openclaw>). Publisher identity matches the
GitHub organization and its own top contributors directly, a cleaner match
than either Hermes's or Omniroute's own npm findings.

PyPI is a different picture, and a sharper one than Hermes's "unofficial
wrapper" finding. An `openclaw` package does exist on PyPI, but it is **not
related to this project at all**: its own description reads "Installer for
the cmdop CLI — one binary that runs an AI agent on your machine," with
project URLs pointing to `cmdop.com` and `github.com/commandoperator`, no
reference anywhere to `openclaw/openclaw` or `openclaw.ai`
(<https://pypi.org/pypi/openclaw/json>). It carries exactly two published
versions (2.0.1, 2.0.2), both uploaded on the same day, 2026-08-13, six days
before this check. This is a bare namespace collision, not a mislabeled
unofficial build: an operator or automation that resolved "openclaw" against
PyPI rather than npm or the project's own installer script would land on an
entirely unrelated product.

#### Security advisories: a large, actively-published record, fixed before disclosure

The repository's own Security Advisories endpoint is not empty, the
opposite finding from both Hermes and Omniroute: it lists **647** published
advisories as of this check, paginated in full
(`GET /repos/openclaw/openclaw/security-advisories`). Severity breakdown:
**14 critical, 219 high, 350 medium, 64 low**. Every one of the 647 carries
a `patched_versions` entry already set at publish time; none were found
unpublished-without-a-fix in this scoped set, the opposite pattern from
Hermes's one still-open advisory (section 1.3). Only 39 of the 647 carry an
assigned CVE identifier; the remainder are GHSA-only.

Publication is heavily bursty rather than steadily trickling: single-day
spikes of 67 advisories (2026-05-28), 59 (2026-03-31), 45 (2026-06-30), and
40 (2026-02-21 and again 2026-04-16) account for a large share of the total,
consistent with batches of findings from a security-review engagement being
published together rather than disclosed one at a time as found.

All 14 critical-severity advisories carry an external reporter credit, not
an internal one:

| GHSA | Summary | Fixed in | Credited reporter |
| --- | --- | --- | --- |
| GHSA-gv46-4xfq-jv58 | RCE via Node Invoke Approval Bypass in Gateway | `>= 2026.2.14` | `222n5` |
| GHSA-4rj2-gpmh-qq5x | Inbound allowlist bypass, voice-call extension | `>= 2026.2.2` | `simecek`, `stanislavfortaisle`, `MegaManSec` |
| GHSA-qrq5-wjgg-rvqw | Path traversal in plugin installation | `>= 2026.2.1` | `logicx24` |
| GHSA-4jpw-hj22-2xmc | Pairing-scoped device tokens could mint `operator.admin`, reach node RCE | `2026.3.11` | `tdjackey` |
| GHSA-rqpp-rjj8-7wv8 | WebSocket shared-auth connections could self-declare elevated scopes | `2026.3.12` | `LUOYEcode` |
| GHSA-hf68-49fm-59cq | `device.pair.approve` escalates `operator.pairing` to `operator.admin`, reaches node RCE | `>= 2026.3.22` | `zpbrent` |
| GHSA-fqw4-mph7-2vr8 | Gateway shared-auth reconnect widens scope to `operator.admin`, node RCE | `2026.3.25` | `zpbrent` |
| GHSA-hc5h-pmr3-3497 | `/pair approve` path omitted caller scope subsetting | `>= 2026.3.28` | `AntAISecurityLab` |
| GHSA-9hjh-fr4f-gxc4 | Backend reconnect lets non-admin scopes self-claim `operator.admin` | `2026.3.25` | `zpbrent` |
| GHSA-8rh7-6779-cjqq / GHSA-j7p2-qcwm-94v4 | CWD `.env` injection bypasses host-env policy / config takeover | `>= 2026.3.28` / `>= 2026.3.22` | `tdjackey` |
| GHSA-g5cg-8x5w-7jpm / GHSA-9p3r-hh9g-5cmg | Sandbox escape, heartbeat context inheritance / TOCTOU race | `>= 2026.3.31` (both) | `AntAISecurityLab` |
| GHSA-xh72-v6v9-mwhc | Feishu webhook/card-action validation now fails closed | `2026.4.15` | `dhyabi2` |

One advisory outside that top-14 list is worth naming directly because it is
the one independently cross-referenced against an NVD CVE and outside
coverage: **GHSA-g8p2-7wf7-98mq / CVE-2026-25253**, "OpenClaw/Clawdbot has
1-Click RCE via Authentication Token Exfiltration From `gatewayUrl`," high
severity, published 2026-02-02, filed against the `clawdbot` npm package
name (the project's pre-rename identity), fixed the same day, and credited
externally on both GitHub and a third-party write-up
(`depthfirst.com/post/1-click-rce-to-steal-your-moltbot-data-and-keys`)
(<https://api.github.com/advisories/GHSA-g8p2-7wf7-98mq>). This is the CVE
named in the security-vendor coverage found in the "Independent coverage"
subsection above.

The vendor response pattern this check found is consistently proactive: a
`patched_versions` field is set on every one of the 647 advisories at
publish time, all 14 critical-severity ones are credited to named external
individuals or a named external security lab (`AntAISecurityLab`), and the
one advisory independently cross-referenced against an outside write-up
shows a same-day fix. This is a materially different pattern from both
Hermes's "vendor did not respond" VulDB entries and Omniroute's single
same-day reply to one Socket.dev finding: it reads as routine, high-volume,
coordinated disclosure rather than an isolated response to an isolated
report.

#### Verdict

The identity behind the project is real, current, and traceable to a named
individual (Peter Steinberger, `steipete`) independently confirmed by
outside press coverage, not a pseudonymous or unverifiable maintainer. Scale
figures moved modestly upward since #165, the same direction Hermes showed.
Where this check diverges sharply from both Hermes and Omniroute is volume
and shape: a single, highly dominant commit author against a comparably
sized but thinner-active contributor pool; a near-daily release cadence; a
namesake PyPI package that is not this project at all, next to a cleanly
matching npm publisher; extensive, repeated, named third-party security
coverage rather than an absence; and a security-advisory record two orders
of magnitude larger than either other candidate, but one where, on the
evidence found, disclosure is consistently paired with an already-shipped
fix and external credit rather than an unresolved backlog. None of this is
disqualifying on its own: a personal-assistant product with broad tool and
data access, covered this heavily by security researchers, is exactly the
shape of project that generates a large, well-handled advisory record, but
the pattern is different enough from both other candidates that it should
carry forward as its own line into whichever ticket writes the final
recommendation, not be treated as an equivalent "provenance clear" verdict.

---

## 3. Provider integration and secrets for both

This section covers #165's stories 4 (every provider key and messaging
token, named), 5 (SOPS+age, no exception for "just a bot token"), and 9
(does Omniroute's routing role change the calculus). Story 6 (exposure
posture, the admin/control-surface question) is #201's (165-06) scope, not
this one's.

### 3.1 LLM provider integration: both already ship their own aggregator

Both candidates connect to remote LLM providers exclusively; neither's
provider catalog below asks for local GPU/VRAM, a question #200 (165-05)
checks in full. What both catalogs share structurally is the fact this
section was asked to surface: **each candidate already ships its own
first-party, multi-provider aggregation layer**, before Omniroute enters
the picture at all.

Hermes's `integrations/providers.md` lists 28 direct, static-API-key
providers in its "Inference Providers" table (`OPENROUTER_API_KEY`,
`FIREWORKS_API_KEY`, `DEEPSEEK_API_KEY`, `GOOGLE_API_KEY`/`GEMINI_API_KEY`,
`OPENAI_API_KEY`, and 23 more, each a distinct `{NAME}_API_KEY` read from
`~/.hermes/.env`) plus 13 OAuth/subscription-based paths in the same table
(Anthropic Claude Max, OpenAI Codex/ChatGPT, GitHub Copilot and its ACP
variant, xAI SuperGrok, Qwen, MiniMax, Google Vertex, Azure AI Foundry, AWS
Bedrock, Ollama Cloud, Nous Portal itself, and a custom-endpoint escape
hatch)
(<https://raw.githubusercontent.com/NousResearch/hermes-agent/main/website/docs/integrations/providers.md>).
Ahead of all of those, the same page names **Nous Portal** as "the
recommended way to run Hermes Agent": "one OAuth login covers 300+ frontier
agentic models (Claude, GPT, Gemini, DeepSeek, Qwen, Kimi, GLM, MiniMax,
Grok, ...) plus the Tool Gateway ... billed against your Nous subscription
instead of separate per-provider accounts" (same source, "Nous Portal"
section). That is Hermes's own answer to exactly the problem Omniroute
solves for a bare Claude-Code consumer (#164's own framing): one login, one
bill, many providers, run by the same organization that ships the agent.

OpenClaw's `docs/providers/index.md` links a comparable catalog under
`provider/model` naming; the underlying `docs/providers/` directory holds
68 individual provider pages, checked via the repository's own Git tree API
(<https://api.github.com/repos/openclaw/openclaw/git/trees/main?recursive=1>),
against the index page itself
(<https://raw.githubusercontent.com/openclaw/openclaw/main/docs/providers/index.md>).
Ahead of that catalog sits **ClawRouter**, "the bundled `clawrouter` plugin"
(`enabledByDefault: true`), giving "one policy-scoped key for multiple
upstream model providers": "you never install or authenticate each upstream
provider plugin on the OpenClaw host"
(<https://raw.githubusercontent.com/openclaw/openclaw/main/docs/providers/clawrouter.md>).
Its default origin, `https://clawrouter.openclaw.ai`, is a hosted service
run by the OpenClaw org itself, structurally the same "vendor's own
first-party router" shape as Hermes's Nous Portal, not a third-party
integration OpenClaw merely documents.

Neither project's docs found in this check name Omniroute, OmniRoute, or
reference it as a tested integration target. Both do support pointing a
direct provider connection at an arbitrary base URL: Hermes's `OpenAI API
(direct)` entry names an "optional `OPENAI_BASE_URL`" override (the
`integrations/providers.md` table cited above), and OpenClaw's own
provider config shape takes a `baseUrl` per provider (demonstrated by the
`clawrouter` provider's own `models.providers.clawrouter.baseUrl` field,
`docs/providers/clawrouter.md` "Managed non-interactive deployment"
section). Mechanically, routing either candidate through Omniroute would
mean reusing that generic base-URL override on one of the existing direct
provider slots (Hermes: `openai-api`; OpenClaw: any OpenAI-compatible
provider entry), the same mechanism #164's own research doc found Claude
Code itself uses against Omniroute via `ANTHROPIC_BASE_URL`
(`research-omniroute-ai-gateway.md` section 6.3). Neither candidate has a
documented, named Omniroute integration path the
way each has one for OpenRouter (both list `OPENROUTER_API_KEY` /
`openrouter` as a first-class, first-party-documented provider) — a real,
if generic, mechanical fit, not a tested one.

### 3.2 Messaging-platform token inventory (#165 story 4)

Every credential either candidate needs for the five platforms #165 names
by name (Telegram, Discord, Slack, WhatsApp, Signal), plus email as the
sixth "email-class" channel it also names:

| Platform | Hermes (env var, `reference/environment-variables.md`) | OpenClaw (config path, `secretref-credential-surface.md`) | Shape |
| --- | --- | --- | --- |
| Telegram | `TELEGRAM_BOT_TOKEN` (from @BotFather) | `channels.telegram.botToken` / `channels.telegram.webhookSecret` | Static bot token, BotFather-issued |
| Discord | `DISCORD_BOT_TOKEN` | `channels.discord.token` | Static bot token, Developer Portal-issued |
| Slack | `SLACK_BOT_TOKEN` (bot token) + `SLACK_APP_TOKEN` (app-level token, Socket Mode) | `channels.slack.botToken` / `.appToken` / `.userToken` / `.signingSecret` | Static tokens, Slack app manifest-issued |
| WhatsApp | none — Baileys bridge, QR-linked session saved under `~/.hermes/platforms/whatsapp/session` | none — `channels.whatsapp.creds.json` is explicitly **excluded** from the SecretRef surface | QR-linked device session, not a static secret |
| Signal | none — `SIGNAL_HTTP_URL`/`SIGNAL_ACCOUNT` point at an external `signal-cli` daemon the operator runs and links separately | none — Signal has **no entries at all** in the SecretRef credential surface | External `signal-cli` linked-device session, not a credential either project stores |
| Email | `EMAIL_ADDRESS` + `EMAIL_PASSWORD` (IMAP/SMTP app password) | **no email channel exists** — absent from the official channel catalog entirely | Static app-password credential (Hermes only) |

Sources: Hermes's messaging env-var block
(<https://raw.githubusercontent.com/NousResearch/hermes-agent/main/website/docs/reference/environment-variables.md>,
"Messaging" section) and its own WhatsApp/Signal setup guides
(<https://raw.githubusercontent.com/NousResearch/hermes-agent/main/website/docs/user-guide/messaging/whatsapp.md>,
<https://raw.githubusercontent.com/NousResearch/hermes-agent/main/website/docs/user-guide/messaging/signal.md>);
OpenClaw's canonical, CI-checked SecretRef list
(<https://raw.githubusercontent.com/openclaw/openclaw/main/docs/reference/secretref-credential-surface.md>),
its own official channel catalog
(<https://raw.githubusercontent.com/openclaw/openclaw/main/docs/channels/index.md>),
and its WhatsApp/Signal channel docs
(<https://raw.githubusercontent.com/openclaw/openclaw/main/docs/channels/whatsapp.md>,
<https://raw.githubusercontent.com/openclaw/openclaw/main/docs/channels/signal.md>).

The pattern that matters for #165's story 4 and story 5 together: three of
the five named platforms (Telegram, Discord, Slack) are ordinary static
secrets on both candidates, a SOPS+age Secret's natural shape. The other
two (WhatsApp, Signal) are **not** credentials either project stores as a
discrete secret value at all — they are linked-device session state,
persisted as files (a Baileys session directory, or an external
`signal-cli` account/daemon), something #165 itself did not distinguish
from "a token" when it grouped all five platforms together in story 4.
Both project's own docs confirm the QR/link model directly: Hermes's guide
says "Your session is saved automatically" after scanning
(`user-guide/messaging/whatsapp.md`, "Quick setup"), and OpenClaw's says
"Login is QR-only... The gateway owns the linked session(s)"
(`docs/channels/whatsapp.md`, "Quick setup" / summary). Neither is
something a `secrets configure` / SOPS workflow resolves the same way a
bot token does; both need the *session file itself* protected, which is a
storage-permissions question (the data PV, section 1.2/2.2 in this file),
not a Kubernetes-Secret question.

### 3.3 Each candidate's own secrets architecture

Both candidates ship a secret-injection system of their own, ahead of and
independent from whatever this platform layers on top with SOPS+age.

**Hermes** keeps every credential in a flat `~/.hermes/.env` file by
default, and can optionally pull values from an external manager at
startup instead: "Hermes can pull API keys from external secret managers
at process startup instead of storing them in `~/.hermes/.env`. The
bootstrap token for the secret manager lives in `.env`; every other
provider key ... can stay in the manager and rotate centrally." Three
backends ship in-tree: Bitwarden Secrets Manager, 1Password (`op://`
references), and a generic command helper wrapping any CLI vault
(`keepassxc-cli`, `secret-tool`, `pass`, custom scripts). A deterministic
precedence ladder governs when a source is allowed to overwrite an
existing `.env`/shell value
(<https://raw.githubusercontent.com/NousResearch/hermes-agent/main/website/docs/user-guide/secrets/index.md>).
Absent one of those three backends, every credential in the table above
(and every LLM-provider key from 3.1) sits as plaintext in `.env` on the
same `/opt/data` volume section 1.2 already flagged for the FTS5 database.

**OpenClaw** has a more structured but similarly shaped contract: a single
`SecretRef` object shape, `{ source: "env" | "file" | "exec" | "store", provider, id }`,
usable on every field listed in `secretref-credential-surface.md`'s
"Supported credentials" table (including `channels.telegram.botToken`,
`channels.slack.botToken`, `channels.discord.token`, and every
`models.providers.*.apiKey`)
(<https://raw.githubusercontent.com/openclaw/openclaw/main/docs/gateway/secrets.md>,
"SecretRef contract" section). The `store` source is OpenClaw's own
built-in vault, a Gateway-wide table in the same `state/openclaw.sqlite`
section 2.2 already covers — and its own docs carry an explicit warning
that mirrors Omniroute's own gap in `research-omniroute-ai-gateway.md`
section 3.3: "Store values are not encrypted at rest. They are stored
unencrypted in the shared state SQLite database ... protected by the same
`0600` file and `0700` directory permissions as other credentials in that
database" (same source, "Shared secret store" section). The `env` source
is the one that maps directly onto a Kubernetes Secret; the `exec` source
is the same "arbitrary CLI vault" shape as Hermes's command-helper backend
(that section's own worked example is a Vault-shaped resolver script).

### 3.4 SOPS+age boundary translation (ADR-0009)

ADR-0009 settles the mechanism (SOPS+age, `docs/adr/0009-secrets-sops-age.md`,
"Decision" section); `workloads/immich/secrets/immich-postgres.sops.yaml`,
consumed via `valueFrom.secretKeyRef` per variable, is this repo's own
concrete precedent, the same one both #164's Omniroute research
(section 3.6) and this file's sections 1.2/2.2 already point to for
storage. Translating that shape onto both candidates:

- **What fits cleanly, for both candidates**: every static credential in
  3.2's table (Telegram/Discord/Slack tokens), and every static
  provider-API-key from 3.1 (Hermes's 28 `{NAME}_API_KEY` variables read
  from `.env`; OpenClaw's `models.providers.*.apiKey` fields, each
  SecretRef-eligible against an `env` source) all resolve the same way
  Omniroute's four required app secrets did: one SOPS-encrypted `Secret`
  manifest per workload, `env`/`envFrom`-injected into the container, and
  (Hermes) referenced by the plain env var name in `.env`, or (OpenClaw)
  referenced by an explicit `{source: "env", provider: "default", id: "..."}`
  SecretRef in `openclaw.json`.
- **What doesn't fit as a Secret manifest at all, for both candidates**:
  the WhatsApp/Signal session state from 3.2. That state is a directory of
  files (Hermes) or a linked-device credential OpenClaw's own SecretRef
  surface explicitly excludes (`channels.whatsapp.creds.json`, "Unsupported
  credentials" in `secretref-credential-surface.md`) and Signal isn't
  listed in at all. This is not a SOPS+age gap; it is the same class of
  fact ADR-0014's static-PV model already covers (section 1.2/2.2 in this
  file), and needs the data volume itself treated as secret-adjacent
  storage, the same conclusion #164's own research reached for
  OmniRoute's `provider-credentials.json` path
  (`research-omniroute-ai-gateway.md` section 3.6).
- **What's a residual gap either way**: Hermes's plaintext `.env` absent a
  secret-source plugin, and OpenClaw's unencrypted `store` SQLite table
  absent routing through `env`/`file`/`exec` instead. Both are avoidable
  by construction — Hermes by choosing the `env` var itself as the sole
  path (skip its own secret-source plugins, since SOPS+age already
  centralizes rotation) and populating `.env` from the mounted Secret at
  container start; OpenClaw by using `env`-source SecretRefs exclusively
  and never writing a credential through `secrets store` (the CLI/Control
  UI path that lands in the unencrypted SQLite table). Neither candidate's
  docs suggest one path is "wrong," but this platform's own SOPS+age
  standard argues for the `env`-only path on both, the same choice
  Omniroute's own research doc reached for `STORAGE_ENCRYPTION_KEY`
  (section 3.6, treating it as required for this deployment even though
  upstream calls it optional).

### 3.5 Omniroute's routing role, weighed against each candidate's own aggregator

#165's story 9 asks whether using either candidate through Omniroute
changes the cost/footprint calculus, and #164's own research doc (164-07,
section 6.5) left this exact question open, pending #165: "a 'yes' for
OmniRoute at all requires a 'yes, and it doesn't need Claude-quality
output' from #165 first," since section 6.2 of that doc already found
Anthropic/Claude absent from Omniroute's free-tier pool entirely, so
whatever value Omniroute has left rests on Hermes/OpenClaw needing the
non-Claude models that make up nearly all of that pool
(`research-omniroute-ai-gateway.md` sections 6.2 and 6.5).

What 3.1 adds to that open question changes its shape further: Omniroute
would not be introducing aggregation where none existed, the way it does
for a bare Claude-Code consumer. Both candidates already have a
first-party answer to the same problem — Nous Portal for Hermes,
ClawRouter for OpenClaw — each run by the same organization that ships the
agent, each already covering multiple providers (including Claude, via
subscription-billed OAuth, not Omniroute's free pool) under one
credential. Layering Omniroute on top would be a *second* aggregation
layer, not the first, and neither project's own docs found in this check
name Omniroute as a tested or recommended integration target. Mechanically
possible (base-URL override on an existing direct-provider slot, 3.1), but
not a documented path either upstream project stands behind.

One mechanism 164-07's section 6.5 flagged but did not chase down is worth
naming here because it bears directly on Hermes/OpenClaw specifically:
Omniroute's own README describes a "Tier 1 Subscription (Claude Code,
Codex, Copilot)" routing tier and a "Quota-Share routing" feature that
could, in principle, let Omniroute serve Hermes or OpenClaw traffic off an
already-authenticated Claude Code subscription session at flat-fee rates
rather than metered ones — but 164-07's own section 2.3 already ruled out
the Docker profile (`cli`/`host`) that mechanism would need for this
platform ("nothing on this platform needs OmniRoute to run a coding-agent
CLI *inside* its own container"), leaving the `base` profile that section
actually recommends without that path. Whether that gap is disqualifying
or just unused depends on which specific provider access either candidate
ends up needing, a question #199 (165-04, use-case analysis) resolves, not
this section; this section's contribution is naming that "aggregator" is
not the axis Omniroute would be filling for either candidate the way it is
for a Claude-Code-only deployment, and that the one cost-saving mechanism
that could still matter here is already blocked by this platform's own
deployment-shape choice, not by Hermes or OpenClaw.

---

Sections 1 through 3 cover #196 (165-01, Hermes), #197 (165-02, OpenClaw),
and #198 (165-03, provider integration and secrets for both). Use-case
analysis (#199/165-04), the local-inference/VRAM check (#200/165-05),
exposure posture (#201/165-06), and the final comparison and
recommendation (#202/165-07) are all follow-on tickets against this same
file.
