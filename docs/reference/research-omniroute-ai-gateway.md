# OmniRoute AI gateway: resource footprint and whether it's worth running here

**Date:** 2026-08-19
**Status:** in progress. Covers #189 (164-01, resource footprint, section 1
below), #190 (164-02, deployment shape, section 2 below), #191 (164-03,
secrets inventory, section 3 below), #192 (164-04, provenance check, section
4 below), #193 (164-05, exposure posture, section 5 below), and #194 (164-06,
cost/routing impact, section 6 below). The recommendation (#195, 164-07) is
a follow-on ticket.
**Sources:** primary only, per this repo's `/research` convention: the
project's own repository (`docker-compose.yml`, `Dockerfile`,
`docs/reference/ENVIRONMENT.md`, `docs/reference/FREE_TIERS.md`,
`docs/architecture/cluster-decisions.md`, `docs/guides/DOCKER_GUIDE.md`,
`docs/guides/SETUP_GUIDE.md`, `docs/security/SOCKET_DEV_FINDINGS.md`,
`docs/security/ROUTE_GUARD_TIERS.md`, `docs/architecture/AUTHZ_GUIDE.md`,
`SECURITY.md`), its README, its own GitHub issue tracker for real, closed
reports of measured memory use and of the Socket.dev supply-chain finding
(section 4), the GitHub REST API for the repository's and owner's own
metadata (creation dates, contributor/commit counts, commit-signature
verification), the npm registry API for the published package's metadata
and download counts, the public GitHub Advisory Database, this repository's
own existing `workloads/` manifests (`workloads/immich/`, including
`workloads/immich/secrets/immich-postgres.sops.yaml` and
`server-deployment.yaml`'s `secretKeyRef` usage), `docs/adr/0009-secrets-sops-age.md`
as the SOPS+age precedent being compared against, `docs/adr/0011-cloudflare-tunnel-traefik-acme-tailscale.md`
and `workloads/immich/server-service.yaml` as the exposure-mechanism
precedent (section 5), `ansible/roles/tailscale/` as this platform's own
Tailscale provisioning, and, for section 5's OAuth redirect-URI check,
Google's own OAuth 2.0 documentation
(<https://developers.google.com/identity/protocols/oauth2/web-server>) and
Tailscale's own HTTPS documentation
(<https://tailscale.com/kb/1153/enabling-https>), and, for section 6's
cost/routing check, `docs/reference/FREE_TIERS.md`'s per-provider table and
ToS-attention table, the repository's own top-level README banner (its
provider/model count claim), and Anthropic's own Claude Code documentation
on connecting to an LLM gateway
(<https://code.claude.com/docs/en/llm-gateway-connect>). Every claim carries
its URL inline. Figures pulled via API are timestamped to this check
(2026-08-19); they move as the project grows.

---

## 1. Resource footprint

### 1.1 No published footprint claim

Unlike Capacitor's Kubernetes-native 128Mi/512Mi requests/limits
(`research-flux-ui-dashboard.md` section 2.1), OmniRoute (`diegosouzapw/OmniRoute`)
publishes no resource-footprint figure anywhere checked: not in the README,
not in its Docker guide, not as a `deploy.resources` block in
`docker-compose.yml`. The word "lightweight" does not appear anywhere in the
README (checked in full,
<https://raw.githubusercontent.com/diegosouzapw/OmniRoute/main/README.md>);
the closest the project's own framing comes to an efficiency claim is about
token compression, not resource use: "RTK+Caveman compression saves 15-95%
tokens" (repository description,
<https://github.com/diegosouzapw/OmniRoute>). There is no published
"lightweight" number to weigh against a measurement here — only an absence,
which is itself the finding.

### 1.2 What's configured, not measured: the Node heap ceiling

The `Dockerfile` sets a default runtime ceiling, not a measurement of actual
use:

```
ARG OMNIROUTE_BUILD_MEMORY_MB=4096   # build-time only, webpack pass
ENV OMNIROUTE_MEMORY_MB=1024          # runtime default
ENV NODE_OPTIONS="--max-old-space-size=${OMNIROUTE_MEMORY_MB}"
```

Base image: `node:26-trixie-slim`, not Alpine
(<https://github.com/diegosouzapw/OmniRoute/blob/main/Dockerfile>). The
Dockerfile's own comment on the runtime default: "1024MB is enough for
normal traffic but can be tight for large fusion-combo panels (many models
fanned out in parallel, each response buffered in full)" — overridable via
`-e OMNIROUTE_MEMORY_MB=2048` or higher at container run time.

Two further soft ceilings are documented in `docs/reference/ENVIRONMENT.md`
section 17 (Memory Optimization), both application-level self-limits, not
container-level resource controls:

| Variable | Default | Effect |
| --- | --- | --- |
| `OMNIROUTE_MEMORY_THRESHOLD_MB` | 80 | triggers aggressive in-process cleanup above this heap use |
| `OMNIROUTE_CACHE_MAX_SIZE_MB` | 256 | LRU eviction ceiling for the in-memory cache |

(<https://github.com/diegosouzapw/OmniRoute/blob/main/docs/reference/ENVIRONMENT.md>)

`docker-compose.yml` sets no `deploy.resources.limits` or `.reservations`
for any service, checked in full
(<https://github.com/diegosouzapw/OmniRoute/blob/main/docker-compose.yml>):
an operator deploying the shipped compose file gets no floor or ceiling from
it at all. ADR-0002's standard slot allocates a workload's Application
component 1 GiB out of its 2 GiB total
(`docs/adr/0002-resource-budget-and-feasibility-verdict.md`, "The standard
slot — 2 GiB"): OmniRoute's documented *default* (1024 MiB) happens to land
almost exactly on that line. Section 1.3 below is why that match is not
reassuring.

### 1.3 What was actually measured: two closed issues, real load

No official benchmark exists, but the project's own issue tracker records
two independent, closed (`state_reason: completed`) reports of memory
actually measured under concurrent-agent load — the traffic shape this
repo would send it (Claude Code, and per #164 potentially Hermes/OpenClaw,
routing concurrent coding-agent requests through the gateway):

- **#4041** (closed 2026-06-25): a `bunx omniroute` install on Windows 11,
  no container, no `REDIS_URL` set (falls back to in-memory rate limiting).
  Heap plateaus at "the default ~6.1 GB old-space ceiling" under multiple
  concurrent coding-agent requests (200-350 KB JSON bodies), producing a V8
  heap-out-of-memory crash-loop (exit 134): `FATAL ERROR: Ineffective
  mark-compacts near heap limit ... Mark-Compact 6137.x (6160.x) -> 6137.x
  (6160.x) MB` (<https://github.com/diegosouzapw/OmniRoute/issues/4041>).
- **#4425** (closed 2026-06-22): a systemd-managed instance (Node 22,
  `NODE_OPTIONS=--max-old-space-size=4096`, cgroup `MemoryMax=6G`) measured
  RSS ranging **3.7-8 GB** with 54 MB-1.1 GB swap, across 24+
  restart-counter resets and 70 `EADDRINUSE` errors inside a 48-hour window
  (<https://github.com/diegosouzapw/OmniRoute/issues/4425>).

Both closed `completed` (a fix landed), but three later issues on the same
concurrency/memory boundary are open or recently active as of the versions
checked (August 2026) — #9012 (docs for tuning heavyweight-chat
concurrency), #9176 (bounded phase-aware admission control replacing the
prior binary heavyweight lease), #10183 (a 3.8.48 → 3.8.49 regression where
admission control rejects requests "even on a healthy heap") — so this is
an area of ongoing churn, not a number the project has since closed the
book on.

Read against 1.2: the documented default (1 GiB Node heap) is not what gets
used under exactly the load pattern this ticket's own use case would
generate. Measured peaks in both reports (3-8 GB) blow past ADR-0002's
entire 2 GiB standard slot on the Node process alone — before Redis or
SQLite (1.4) are counted at all, and before whatever this repo's own
concurrent-agent traffic shape would add on top of the levels that already
crashed these two reporters' instances.

### 1.4 The audit-log and Redis lines (story 7): not folded into "lightweight"

Two components need their own line, not folding into "OmniRoute":

**SQLite (audit trail / primary datastore).** All persistence goes through
`better-sqlite3` at `DATA_DIR` (default `~/.omniroute/`, overridden to
`/app/data` by the Compose file's `x-common` block), described in the
README's privacy section as "a local audit trail in your own SQLite"
(<https://raw.githubusercontent.com/diegosouzapw/OmniRoute/main/README.md>)
and in `docs/reference/ENVIRONMENT.md` section 2 as covering "all
persistence." No retention policy, rotation, or size-growth figure is
published anywhere checked; disk use scales with logged request volume, a
number this repo has no baseline for yet, and nothing found caps it.

**Redis: framed as optional, wired as mandatory.** The README lists
"one-click local Redis" under recent "Local performance & infra" features —
worded as a convenience add-on. `docker-compose.yml` says otherwise: the
`redis` service (`redis:7-alpine`, named volume `omniroute-redis-data`)
carries **no `profiles:` key**, unlike the genuinely opt-in `qdrant` and
`bifrost` sidecars, both explicitly gated behind `profiles: [memory]` /
`[bifrost]` and both commented "Off by default." A Compose service with no
profile list starts under every `docker compose --profile <x> up`
invocation regardless of which profile is named, so Redis is not an
opt-in extra for any Docker-based install — it is mandatory infrastructure.
`docs/architecture/cluster-decisions.md` confirms the intent is permanence,
not convenience: `redis:7-alpine` "handles the rate-limit/cache workload at
production scale" with "no ceiling to break," given as the reason to keep
it rather than replace it with an alternative, not as a toggle a deployer
is expected to leave off. And per #4041 above, running *without* Redis (the
npm/`bunx` path, which has no compose file to define one) is named as one
of the contributing factors to that instance's OOM crash-loop: state that
would otherwise live in Redis accumulates in the Node heap instead. Redis
carries no published footprint of its own and no `deploy.resources` limit
in the shipped compose file either — the same absence documented for the
app container in 1.2.

---

## 2. Deployment shape: npm vs. Docker for this platform

### 2.1 Five install modes, three already out of scope

The README documents five install modes: npm/`bunx` global install, Docker /
Docker Compose, an Electron desktop app (`npm run electron:build`, "Native
window + system tray — Windows / macOS / Linux"), a PWA ("Add to Home
Screen" from a browser, "Fullscreen, offline, installable from browser"),
and Termux on Android (`pkg install nodejs && npx -y omniroute`, "Runs on
your phone, 24/7, no root")
(<https://raw.githubusercontent.com/diegosouzapw/OmniRoute/main/README.md>).
The last three each require a GUI, a browser session, or a phone, none of
which this platform's one headless k3s node has (#164's own scoping already
excludes them: "the Electron desktop app, PWA, and Termux modes target
other kinds of machines"). Sections 2.2-2.5 below cover only the two
self-hosted server modes: npm global install and Docker.

### 2.2 npm global install: no container image, no daemonization story

`npm install -g omniroute && omniroute` starts a foreground Node process; it
produces no container image and ships no systemd unit, `pm2` config, or
equivalent for keeping itself running unattended. Checked in
`docs/guides/SETUP_GUIDE.md`
(<https://raw.githubusercontent.com/diegosouzapw/OmniRoute/main/docs/guides/SETUP_GUIDE.md>):
the only background-service instruction in the whole guide is `systemctl
--user enable --now omniroute.service` for the Arch Linux AUR package
specifically, not for the npm global install path, and this platform is not
Arch (ADR-0013 provisions node1 by USB autoinstall, not a package manager
this AUR unit would exist under). The guide's "Headless server
(CI/automation)" section covers `omniroute setup --non-interactive`, i.e.
unattended *configuration*, not unattended *supervision*: something else
still has to keep the process alive and restart it.

This platform has no answer for "something else" outside of Kubernetes
itself: every existing workload here is a container running under k3s
(ADR-0007), restarted by the kubelet, not by a hand-rolled systemd unit
authored per workload. Fitting the npm path in would mean either writing a
bespoke systemd unit on node1 (a supervision mechanism this repo doesn't use
for any other workload, breaking the "every workload is a Kustomization"
pattern) or wrapping the npm install in a custom Dockerfile of this repo's
own authorship, at which point it's not really the npm mode being deployed
in favour of the Docker one below, since OmniRoute already publishes one.

### 2.3 Docker: the only shape that mechanically fits this platform

Every existing workload here is declared as a plain-manifest `workloads/`
Kustomization referencing a container image: Immich's
`server-deployment.yaml`, `postgres-statefulset.yaml`, and
`redis-statefulset.yaml` are the concrete precedent (`workloads/immich/`),
and #160/#161/#162 (observability, backup, ingress) follow the same shape.
Flux's `workloads` Kustomization has no `kustomization.yaml` of its own;
kustomize-controller's directory walk picks up any subdirectory that
supplies one, so a new `workloads/omniroute/` directory slots in with no
edit to the parent tree (`workloads/immich/kustomization.yaml`'s own
comment on this mechanism, citing #133).

OmniRoute's Docker image is the only artefact of the project that plugs
directly into that pattern: `diegosouzapw/omniroute:latest`, multi-platform
manifest `linux/amd64` + `linux/arm64`, ~250MB
(`docs/guides/DOCKER_GUIDE.md` "Image Tags" table,
<https://raw.githubusercontent.com/diegosouzapw/OmniRoute/main/docs/guides/DOCKER_GUIDE.md>).
`docker-compose.yml` itself is not something this repo runs as-is (this
platform has no `docker compose` step anywhere, only k3s manifests), but its
four profiles show which image target a hand-authored `Deployment` should
point at:

| Profile | Stage/image | When to use (project's own wording) |
| --- | --- | --- |
| `base` (default) | `runner-base` | "Headless server / minimal runtime, no provider CLIs bundled" |
| `cli` | `runner-cli` | "Agentic workflows that call `omniroute providers/setup/doctor` and bundled CLIs (Codex, Claude Code, Droid, OpenClaw)" |
| `host` | `omniroute-host` | Mounts host CLI binaries read-only, Linux-specific |
| `cliproxyapi` | `cliproxyapi` sidecar | Upstream CLI proxying on port 8317 |

(same source as above). `base`/`runner-base` is the fit: per #164's own
scoping, this platform's only current or prospective consumers (Claude
Code, potentially Hermes/OpenClaw) call OmniRoute over the network as an
HTTP gateway, from the operator's own machine or another workload: nothing
on this platform needs OmniRoute to run a coding-agent CLI *inside* its own
container, which is what `cli`/`host`/`cliproxyapi` add. Translating that
into a `Deployment` means pointing `image:` at
`diegosouzapw/omniroute:latest` (or a pinned version tag, the `latest` vs.
`3.8.0` choice is a #164-06/#164-07 concern, not this ticket's) built from
or equivalent to the `runner-base` target, not `runner-cli`.

### 2.4 What the Docker shape still requires this repo to author itself

No Kubernetes manifest or Helm chart is published anywhere in the project:
checked the full `docs/` directory listing on GitHub (24 entries under
`docs/guides/`, none named for Kubernetes or Helm;
<https://api.github.com/repos/diegosouzapw/OmniRoute/contents/docs/guides>)
and `docs/guides/DOCKER_GUIDE.md`'s own "See Also" section, which links a
`VM_DEPLOYMENT_GUIDE.md` and a `FLY_IO_DEPLOYMENT_GUIDE.md` under
`docs/ops/` and nothing else. This is the same position Immich was in here
(no Helm chart used; `workloads/immich/` is entirely hand-authored plain
manifests), so it sets no new precedent, but it does mean a
`workloads/omniroute/` Kustomization must be written from scratch, same
scope of work as Immich's: `namespace.yaml`, a `Deployment` for the
`base`-profile image, a `Service`, a `PersistentVolume`/`PersistentVolumeClaim`
pair for `/app/data` (ADR-0014: static local PV, no CSI, matching
`postgres-pv.yaml`/`postgres-pvc.yaml`), and, because Redis carries no
profile gate and is "always defined" regardless of which Compose profile is
chosen (`docs/guides/DOCKER_GUIDE.md` "Redis Sidecar" section, same source;
corroborates section 1.4 above), a second `Deployment`/`StatefulSet` for
`redis:7-alpine` with its own PV/PVC, the same shape as
`redis-statefulset.yaml` already in `workloads/immich/`. None of this is
OmniRoute-specific complexity; it's the standard translation this repo
already performs for every containerized workload that ships no Kubernetes
manifests of its own.

### 2.5 Verdict

Docker is the only deployment shape that fits this platform. npm global
install has no container image and no daemonization mechanism this repo's
supervision model (k3s/kubelet, ADR-0007) or provisioning (ADR-0013, not
Arch) can hook into without inventing a one-off systemd unit that breaks
the "every workload is a Kustomization" pattern; Docker's `runner-base`
image drops straight into that pattern the same way Immich's images did.
The image target is `diegosouzapw/omniroute:latest` (`base`/`runner-base`,
not `cli`), plus a mandatory `redis:7-alpine` sidecar, as a hand-authored
`workloads/omniroute/` Kustomization: no upstream Kubernetes manifest or
Helm chart exists to shortcut that authoring.

---

## 3. Secrets inventory: provider keys, keyless options

### 3.1 Keyless by default: the baseline install needs no provider secret

The README's own framing is unambiguous: "Works the second you install it —
no keys, no config," with "Keyless free providers OpenCode Free and Felo
... pre-wired into the auto combo, so a fresh install responds out of the
box"
(<https://raw.githubusercontent.com/diegosouzapw/OmniRoute/main/README.md>).
The Quick Start section repeats the same pattern for the first
Dashboard-driven provider connection: "Connect a FREE provider (no
signup)," either Kiro AI ("free Claude, ~50 credits/month per account") or
OpenCode Free ("no auth"), same source. Neither of these two onboarding
paths asks for a provider API key at all: OmniRoute's minimum viable
deployment carries zero provider-credential secrets. `docs/reference/FREE_TIERS.md`'s
own "TL;DR" table gives the same picture at scale: its "documented
recurring grant (steady)" of ~1.53B tokens/month, aggregated across 43
free-tier pools
(<https://raw.githubusercontent.com/diegosouzapw/OmniRoute/main/docs/reference/FREE_TIERS.md>),
is reached the same way: most of that pool is either fully keyless or
reached through a Dashboard-driven OAuth/cookie connection (3.4 below), not
a static key an operator has to source and hold.

### 3.2 What's required regardless of provider choice: four app secrets, one recommended

`docs/reference/ENVIRONMENT.md` section 1 ("Required Secrets") names four
variables the application "will either refuse to start or operate with
insecure defaults" without:

| Variable | Default | What it protects |
| --- | --- | --- |
| `JWT_SECRET` | _(none)_ | "Signs/verifies all dashboard session cookies (JWT)" |
| `API_KEY_SECRET` | _(none)_ | "AES encryption key for API key values at rest in SQLite" |
| `INITIAL_PASSWORD` | `CHANGEME` | Initial admin dashboard password ("kept obviously insecure to force a change") |
| `OMNIROUTE_WS_BRIDGE_SECRET` | _(unset)_ | Internal Codex Responses WebSocket bridge auth, "**REQUIRED in production** — when unset, all WS bridge requests are rejected" |

(<https://raw.githubusercontent.com/diegosouzapw/OmniRoute/main/docs/reference/ENVIRONMENT.md>,
section 1 and section 4). None of these four depend on which providers get
connected: they gate the dashboard and the gateway's own API-key issuance,
present in every deployment including the fully keyless one in 3.1.

A fifth variable is recommended, not required: `STORAGE_ENCRYPTION_KEY`,
"AES key for full SQLite database encryption at rest," _(empty = disabled)_
by default (ENVIRONMENT.md section 2). ENVIRONMENT.md's unnumbered
"Deployment Scenarios" section (after section 23, "GitHub Integration")
includes it in "Docker Production" and "VPS with Reverse Proxy" alongside
the four required secrets, but omits it from "Minimal Local Development"
and "Air-Gapped / CI." Section 3.3 below is why leaving it unset matters
here specifically.

### 3.3 Provider credentials: three storage paths, only one covered by encryption-at-rest

`API_KEY_SECRET` (3.2) encrypts "API key values ... in SQLite": this is
scoped to the API keys OmniRoute itself issues to its own `/v1` clients
(Claude Code, in this platform's case), not to the upstream provider
credentials OmniRoute holds on the client's behalf. Those are a separate
concern, and ENVIRONMENT.md section 14 states plainly where they live:

> API keys for providers that use direct authentication. **Preferred
> setup:** Dashboard → Providers → Add API Key. Setting via environment
> variables is an alternative for Docker or headless deployments.

with a note attached to the (now largely retired) env-var path: "those
providers rely exclusively on Dashboard / `data/provider-credentials.json`
/ the encrypted DB" (same source, section 14). That sentence names three
storage locations for a Dashboard-added provider credential, not one:
the Dashboard UI itself is the entry point, not a store; "the encrypted
DB" is SQLite, and *encrypted* here is conditional on `STORAGE_ENCRYPTION_KEY`
being set (3.2): with it unset (the default), the DB is plaintext SQLite
on disk; and `data/provider-credentials.json` is named as a distinct file
under `DATA_DIR`, with no encryption claim attached to it anywhere checked
in ENVIRONMENT.md, the README, or the Docker/setup guides, a second gap
alongside the SQLite-encryption default already being off. Practically, for
this platform: leaving `STORAGE_ENCRYPTION_KEY` unset means any
Dashboard-added provider key ends up as plaintext on the same `/app/data`
persistent volume as the audit-log SQLite database from section 1.4.
Setting it is the one action that closes both gaps at once for the
DB-resident path; nothing found closes the `provider-credentials.json` path
specifically, which argues for treating the PV itself, not just the DB
file, as secret-adjacent storage.

Only two providers still accept a static `{PROVIDER_ID}_API_KEY` environment
variable as of the version checked: `DEEPSEEK_API_KEY` (DeepSeek) and
`NVIDIA_API_KEY` (NVIDIA NIM). Nine others (Groq, xAI, Mistral, Perplexity,
Together AI, Fireworks, Cerebras, Cohere, Nebius, and Qianfan) had their
static env-var form removed in v3.8.0 "because the runtime no longer reads
them" (ENVIRONMENT.md section 14 and its "Audit: Removed / Dead Variables"
appendix); connecting any of those now goes exclusively through the
Dashboard, landing in one of the two storage paths above.

### 3.4 OAuth-based provider connections: mostly public clients, a few need a registered secret

Section 11 ("OAuth Provider Credentials") lists the coding-agent and
assistant providers OmniRoute can connect via OAuth. Most ship as public
OAuth clients needing no secret at all: Claude Code/Anthropic ("Public
client — no secret needed"), Codex/OpenAI ("Public client"), Kimi Coding
("Public client"), GitHub Copilot ("Public client"), but three need a
matching `_CLIENT_SECRET` registered by the operator: Gemini (Google),
Antigravity (Google), and GitLab Duo. The section's own framing caps how far
"built-in" goes: "Built-in credentials for **localhost development**. For
remote deployments, register your own at each provider's developer console"
(ENVIRONMENT.md section 11). This platform's default exposure posture is
Tailscale-only per #164's own scoping, not `localhost` from the operator's
browser. Whether a Tailscale-only origin counts as "remote" for a given
provider's OAuth redirect-URI validation (and therefore requires the
operator to register their own client + secret before that specific
provider connects) is a fact this ticket did not check per-provider; it is
handed to #193 (164-05, exposure posture) as a concrete dependency, not
assumed either way here.

### 3.5 Out of scope for this deployment: cloud sync, GitHub issue reporting

Two further secret-shaped variables exist but gate features this platform
has no reason to turn on: `OMNIROUTE_CLOUD_SYNC_SECRET` verifies a "Cloud
Sync" premium feature (`CLOUD_URL` empty by default, ENVIRONMENT.md section
7) that this self-hosted deployment has no account for, and
`GITHUB_ISSUES_TOKEN`/`GITHUB_TOKEN` only power an opt-in "report issues
directly from the Dashboard" button (ENVIRONMENT.md section 23). Neither is
required, and neither should be added to the secret inventory below unless
a later ticket turns that feature on.

### 3.6 SOPS+age boundary translation

ADR-0009 settles the encryption mechanism (SOPS+age); this repo's own
`workloads/immich/` already sets the concrete precedent for what a workload
does with it: one SOPS-encrypted `Secret` manifest under the workload's own
`secrets/` directory (`workloads/immich/secrets/immich-postgres.sops.yaml`),
consumed by `server-deployment.yaml` via `valueFrom.secretKeyRef` per
variable, not `envFrom`. A `workloads/omniroute/secrets/omniroute-app.sops.yaml`
following that same shape covers the whole *required* inventory from 3.2 in
one file: `JWT_SECRET`, `API_KEY_SECRET`, `INITIAL_PASSWORD`,
`OMNIROUTE_WS_BRIDGE_SECRET`, plus `STORAGE_ENCRYPTION_KEY`. That fifth
variable is recommended rather than required by upstream, but per 3.3 it is
the only lever this repo has over whether provider credentials sitting in
OmniRoute's own SQLite are plaintext on the PV, which makes it worth
treating as required for this deployment even though OmniRoute's own docs
don't. `DEEPSEEK_API_KEY` / `NVIDIA_API_KEY` (3.3) and any OAuth client
secret from 3.4 would join the same Secret only if and when those specific
providers actually get connected: this ticket found no provider connection
this deployment currently plans to make through an env-var-backed key, per
#164's own scoping (Claude Code as the only committed consumer so far,
itself an OAuth public client per 3.4).

One boundary this deployment cannot draw the same way Immich's is: Immich's
DB credentials are the *entire* secret surface for that workload, so one
SOPS file closes the loop. Here, a provider credential added through the
Dashboard UI after deployment (the "preferred setup" per 3.3) lands inside
OmniRoute's own SQLite or `provider-credentials.json`, i.e. inside the
workload's data volume, not in a file this repo's Git history or SOPS
tooling ever sees or manages.

`STORAGE_ENCRYPTION_KEY` bounds that risk for the DB-resident half; nothing
checked here bounds it for `provider-credentials.json`. That residual gap
is a fact for #195 (164-07) to weigh, not something this ticket's own scope
resolves.

---

## 4. Provenance check: maintainer, commits, advisories

### 4.1 Maintainer identity: an established personal account, not a throwaway

The GitHub account is `diegosouzapw`, created 2014-06-29 (12 years old as of
this check), not a fresh account spun up around the repository: 1,345
followers, 70 public repositories, profile name "Diego Rodrigues de Sa e
Souza," company "CDWA Solutions," location "São Paulo - Brasil," a personal
blog domain (`omniroute.online`), and a Twitter handle
(`@diegosouzapw`)(`GET /users/diegosouzapw`,
<https://api.github.com/users/diegosouzapw>). The bio self-describes as
"Creator & maintainer of OmniRoute ... built with 460+ contributors,"
consistent with the repository being a personal-account project the same
account has driven since creation, not an anonymous or corporate front. The
bio's "460+" is somewhat higher than the 412 distinct contributor logins
this check actually counted (4.2); the gap is small enough, and this kind
of promotional-copy figure inconsistent enough elsewhere (search coverage
in 4.4 separately turned up "450+" and "over 280" for the same claim in
different write-ups from different months), to read as an unmaintained
round number rather than a fabricated one, but it was not reconciled to an
exact source.

The npm package's sole listed maintainer email
(`diegosouza.pw@outlook.com`) matches the GitHub profile's public email
exactly, and the package's `repository` field points back at
`git+https://github.com/diegosouzapw/OmniRoute.git`
(`GET https://registry.npmjs.org/omniroute`): the npm publisher and the
GitHub account are the same identity by two independent registries
agreeing, not just by the README's say-so.

### 4.2 Commit and contributor authorship: one dominant author, real breadth beneath

`GET /repos/diegosouzapw/OmniRoute/contributors` lists 412 distinct
contributor logins (paginated, counted in full). Contribution counts are
sharply concentrated: `diegosouzapw` alone shows 4,202 contributions; the
next-highest, `oyi77`, shows 217, then `backryun` at 216, `dependabot[bot]`
at 139, and a long tail down to single-digit counts
(<https://api.github.com/repos/diegosouzapw/OmniRoute/contributors>). That
shape, one author an order of magnitude ahead of everyone else, is
consistent with a maintainer-led project that does receive real outside
contributions, not with either a solo project dressed up to look
collaborative (the next 30+ logins each show double-digit real
contribution counts, not padding) or a project actually run by a diffuse
team (no second author is remotely close to the top).

The most recent 30 commits as of this check
(<https://api.github.com/repos/diegosouzapw/OmniRoute/commits>) name eleven
distinct authors across a 19-hour window, `diegosouzapw` interleaved with
`backryun`, `adevwithpurpose`, `hartmark`, and others: day-to-day activity,
not a history that goes quiet between periodic solo pushes. Of the sample
checked, commits authored through GitHub's own web-merge flow (committer
`GitHub <noreply@github.com>`) carry a GitHub-signed `verified: true`
status; this confirms the merge went through GitHub's UI, not that the
named author independently holds a personal signing key, a distinction
worth keeping since "verified" badges here attest to the platform, not to
the contributor.

One operational oddity, noted but not weighted as a trust signal either
way: the repository's `default_branch` is `release/v3.8.50`, not `main` or
`master` (`GET /repos/diegosouzapw/OmniRoute` →
`.default_branch`). A `main` branch does exist and is kept current (used
throughout sections 1-3 above and this section for raw-file fetches); the
project simply points GitHub's default view at its current release branch
instead.

### 4.3 Scale, re-measured: #164's cited figures against this check's numbers

#164's own framing cited "49.5k stars / 6.7k forks / 412 open issues on a
six-month-old repository." Re-measured today: 50,812 stargazers, 6,926
forks, 388 open issues, 294 subscribers, repository created 2026-02-13
(<https://api.github.com/repos/diegosouzapw/OmniRoute>), a little over six
months old as of this check (2026-08-19). Stars and forks are both
slightly higher than #164's figures, consistent with continued growth
rather than a stat that was inflated once and has since stalled; open
issues moved the other way, down from 412 to 388, which reads as normal
issue-tracker churn (closures outpacing new reports over the intervening
period) rather than as evidence either way on the provenance question.
The 412-contributor count in 4.2 lands, by coincidence, on the exact
number #164 cited for open issues at the time it was written; they are two
unrelated metrics that happened to match on that earlier date, not a
corroboration of each other, and the open-issues figure has since moved
off it while the contributor count is independent of it.

Per this repository's own prior finding on Omniroute, Hermes, and OpenClaw
(recorded outside this doc: the operator has independently verified these
three candidates through channels of their own before #163-165 were
opened), whether a growth curve this fast is itself plausible for a
six-month-old personal-account project is a base-rate question this
provenance check cannot settle by re-counting stars; it is not re-argued
here. What follows (4.4-4.6) is what a provenance check *can* settle:
whether the identity behind the project is real and consistent, and how it
behaved the one time independent tooling raised a concrete concern.

### 4.4 Independent coverage: mostly SEO-shaped, one substantive signal

Search coverage returns several third-party write-ups (compsmag.com,
aitoolly.com, a Medium post, a SourceForge mirror listing, a Pinggy.io blog
post), all published within the repository's own lifetime (2026), generally
positive, and shaped like SEO/affiliate content rather than independent
security or engineering review: none were found performing their own
technical verification of a claim, each substantially restates the
README. None is cited further here, consistent with this repo's
primary-source-only convention; they are named only to record that the
"independent coverage" check in #164's story 6 was performed and came back
thin.

One genuinely independent, primary-sourced signal exists: an automated
supply-chain scan by a third-party tool (Socket.dev) against the published
npm artifact, raised as a GitHub issue against the repository itself.
Section 4.5 covers it in full, since it is the substantive part of this
provenance check.

### 4.5 The Socket.dev finding and the maintainer's response

Socket.dev's automated scanner detected the finding against
`omniroute@3.8.5` at 2026-05-27T10:31 UTC (timestamp given in the issue
body below): a Supply Chain Security score of 48 and six "AI-detected
potential malware" alerts, plus separate obfuscated-code and
install-script alerts. A user (`a-dmx`) opened it as GitHub issue #2863
the next day, at 2026-05-28T15:29 UTC
(<https://github.com/diegosouzapw/OmniRoute/issues/2863>). The flagged
code paths, quoted from the issue: a root-CA/MITM installer, a route
reading OS-keychain credentials for a "Zed import" feature, an elevated
PowerShell/process-spawn helper, an embedded-service supervisor
(`9router`), and a route synchronizing provider credentials to an
operator-configured `CLOUD_URL`. Read cold, that is exactly the kind of
behavior that would matter for a tool proxying provider API keys, which is
why this ticket treats it as the central finding rather than a footnote.

The maintainer's first reply followed at 2026-05-28T18:45 UTC, about three
hours after the issue was opened, and addressed each of the six findings
individually: four were characterized as documented, opt-in features
gated behind loopback-only route classification (enforced before any auth
check, per the reply's own routing table) and behind explicit user action
in the dashboard, not code that runs on install or unattended, with the
"obfuscated code" alert attributed to Next.js's own standalone-build
minification rather than deliberate obfuscation. Two of the six were
acknowledged as real gaps: a Cloud Sync credential-overwrite path with no
signature check, and a single-step keychain-import flow with no
per-credential confirmation. A fix PR was opened the same evening (#2871,
created 2026-05-28T19:56 UTC, referenced in a second comment at
2026-05-28T19:58 UTC), but did not merge to `release/v3.8.6` until
2026-05-29T11:42 UTC (`GET /repos/diegosouzapw/OmniRoute/pulls/2871`),
about 15 hours after the issue itself was already closed (below): the
issue was closed on the strength of an open, not-yet-merged PR, not a
landed fix, a distinction the maintainer's own comment names in the future
tense ("PR #2871 is open and will merge into release/v3.8.6 ... [o]nce
merged you can git pull and rebuild locally to validate"). Once merged, the
Cloud Sync path now requires an
`HMAC-SHA256` signature (`crypto.timingSafeEqual`) before accepting a
credential overwrite, defaulting off unless
`OMNIROUTE_CLOUD_SYNC_SECRETS=true` is set; the keychain import became a
two-step discover-then-confirm flow with per-credential fingerprint
matching. The fix shipped with 24 new unit tests named in the reply, a
maintainer-authored attestation document
(`docs/security/SOCKET_DEV_FINDINGS.md`), and a new opt-in build flag,
`OMNIROUTE_BUILD_PROFILE=minimal`, that physically replaces the four
sensitive modules with stub files at webpack-compile time so the flagged
code paths are absent from the published bundle entirely. The reporter's
own follow-up comment called it "a really responsible maintainer response."

This ticket verified the durable parts of that claim rather than taking
the issue thread's word for it: `docs/security/SOCKET_DEV_FINDINGS.md`
exists on the current `main` branch and its content matches the reply's
description (per-finding source-file map and attestation), `SECURITY.md`
still carries the linked "Supply-chain scanner findings" section, and
`OMNIROUTE_BUILD_PROFILE` is still documented in the current
`docs/reference/ENVIRONMENT.md` (row 277 as checked) exactly as described.
One promised follow-through was checked and not found: the reply frames
`OMNIROUTE_BUILD_PROFILE=minimal` output as "intended to be published as
`omniroute-secure`," but no such package exists on the npm registry as of
this check (`GET https://registry.npmjs.org/omniroute-secure` → 404). The
hardening is real and usable today (an operator can set the env var and
build from source), but the separately-publishable, separately-auditable
artifact the reply floated has not shipped: a gap between what was
promised and what exists, not a gap in the fix itself.

No formal security advisory was ever filed over this finding: the
repository's own Security Advisories list is empty
(`GET /repos/diegosouzapw/OmniRoute/security-advisories` → `[]`), and a
targeted query against the public GitHub Advisory Database for packages
affecting `omniroute` returns no results
(`GET https://api.github.com/advisories?affects=omniroute` → `[]`). The
Socket.dev flag never escalated to a GHSA. Measured end to end: the issue
closed at 2026-05-28T20:25 UTC, under five hours after it was opened and
about 34 hours after Socket.dev's own detection timestamp; the fix PR
itself did not merge until 2026-05-29T11:42 UTC, about 49 hours after
detection and roughly 15 hours after the issue closed (above), a gap
between "issue resolved" and "fix landed" worth keeping separate rather
than treating the issue-closure timestamp as the fix-shipped timestamp.

### 4.6 npm package integrity

`omniroute` on the npm registry: 288 published versions since
2026-02-14, most recent `3.8.49` (`dist-tags.latest`), MIT license, sole
maintainer email matching the GitHub owner (4.1)
(<https://registry.npmjs.org/omniroute>). 288 versions over roughly six
months is close to 1.6 releases/day, an extremely high cadence that
corroborates, from an independent angle, section 1.3's finding of ongoing
churn on the concurrency/memory boundary (issues opening and closing
across adjacent point releases) rather than a project that ships rarely
and carefully. Download volume is real: 272,196 downloads in the 30 days
ending 2026-08-18, 58,710 in the trailing week
(<https://api.npmjs.org/downloads/point/last-month/omniroute>), usage at
a scale that would be unusual to fabricate and consistent with the
star/fork counts in 4.3, though this check cannot separate genuine
installs from CI/bot traffic.

### 4.7 What this check did not do

No line-by-line diff review of PR #2871 or any other individual commit was
performed; the fix was verified by confirming its described artifacts
(attestation doc, env var, SECURITY.md section) exist and match the
description, not by re-deriving the security properties from source. No
scan of the current `3.8.49` npm artifact was run against Socket.dev, Snyk,
or an equivalent scanner directly: 4.5 relies on the historical issue
thread and the currently-published documentation, not a fresh scan. npm's
provenance-attestation and 2FA status for the `omniroute` package are not
exposed by the public registry API and were not checked by another means.
Several similarly-named, unrelated repositories surfaced during search
(other authors' own `omniroute`-named forks and clones) were not
cross-checked for shared code or maintainer overlap with
`diegosouzapw/OmniRoute`; nothing found suggests a connection, but it was
not actively ruled out either.

One name from that search is not actually unrelated, a correction to how an
earlier pass through this section framed it: `decolua/9router` is not a
separate project that merely shares a name with a component OmniRoute
happens to also call "9router." OmniRoute's own architecture doc names
`9router` as one of five registered router backends, `supervised` lifecycle,
"a local child process OmniRoute installs/starts/stops/health-checks"
(`docs/architecture/ROUTER_BACKENDS.md`,
<https://raw.githubusercontent.com/diegosouzapw/OmniRoute/main/docs/architecture/ROUTER_BACKENDS.md>),
and the npm registry confirms it is the identical package: `9router` on npm
has exactly one maintainer, `decolua`
(<https://registry.npmjs.org/9router>). The CVE `docs/security/ROUTE_GUARD_TIERS.md`
cites as its own justification for gating `/api/services/` LOCAL_ONLY,
GHSA-fhh6-4qxv-rpqj, is filed against that exact package: "9router:
Unauthenticated Remote Code Execution via unprotected MCP custom plugin
routes," source `github.com/decolua/9router`
(<https://github.com/advisories/GHSA-fhh6-4qxv-rpqj>). So OmniRoute embeds a
third-party service with a known unauthenticated-RCE advisory against it,
by design, as an opt-in "companion service" the maintainer's own attestation
document names directly: "9router is an optional locally-installable
companion service (think: WordPress-style plugin) — strict opt-in," shipped
`not_installed` by default, spawned only from a fixed binary allowlist, and
gated LOCAL_ONLY before any auth check
(`docs/security/SOCKET_DEV_FINDINGS.md` §4/§6,
<https://raw.githubusercontent.com/diegosouzapw/OmniRoute/main/docs/security/SOCKET_DEV_FINDINGS.md>).
That is a materially different fact than "unrelated, not cross-checked": the
dependency is real, the maintainer is transparent about embedding a
component with a known CVE against it, and the stated mitigation (opt-in,
not-installed-by-default, loopback-gated) is the same LOCAL_ONLY mechanism
section 5.4 verifies independently. It does not reverse 4.8's verdict below,
if anything it is a second, concrete instance of the same "responds
substantively, mitigates rather than hides" pattern 4.5 already found, but
it is not the same claim as "nothing found suggests a connection," and this
section's earlier pass should not have said so.

### 4.8 Verdict

The identity behind the project is real, consistent across GitHub and npm,
and has maintained the account for over a decade: not an anonymous or
disposable presence assembled around one repository. Commit and
contributor history shows one clearly dominant author with a genuine,
daily-active outside contributor base beneath that account, not a solo
project dressed up with padding. No open security advisory exists against
the package. The one substantive independent scrutiny event found, an
automated supply-chain scan flagging credential-adjacent code paths
(exactly the category of concern that would matter most for a gateway
that proxies provider API keys), produced a same-day, per-finding
technical reply and a fix PR opened the same evening, merged about 49
hours after Socket.dev's detection (4.5) with tests and a public
attestation document, and durable documentation that still matches the
claim three months later. That is evidence of a maintainer who
responds substantively to scrutiny rather than one who goes quiet or
hand-waves when actually challenged, which is the part of "provenance"
this ticket's checklist (maintainer identity, commit authorship,
independent coverage, advisories) can speak to directly.

What it does not do is resolve the base-rate question #164 itself raised:
whether this growth curve is ordinary for a six-month-old, personal-account
project. This check does not attempt to, consistent with the note in
4.3. Within the scope this ticket actually asks a provenance check to
cover, nothing found here argues against proceeding to #193-195; the
Socket.dev episode is the one fact from this section worth carrying
forward into #195's recommendation explicitly, since it is the closest
thing to a real incident this project has had.

The cost/routing impact against calling Anthropic directly is covered in
section 6 below (#194/164-06); the recommendation (#195/164-07) is a
follow-on ticket.

---

## 5. Exposure posture

### 5.1 ADR-0011's default already answers this, absent a new argument

ADR-0011 states the platform's exposure default plainly: "Any future,
not-yet-known service defaults to private until a ticket argues it out"
(`docs/adr/0011-cloudflare-tunnel-traefik-acme-tailscale.md`, "Exposure
posture"). #164's own problem statement pre-commits to the same answer for
OmniRoute specifically, story 4: "this is a tool that proxies API keys and
routes coding-agent traffic, so it defaults private (Tailscale-only,
matching Immich and the Flux-UI ticket's default) unless a reason to expose
it publicly is argued." Nothing found across sections 1-4 argues the other
way. OmniRoute is not one of ADR-0011's two named public exceptions (the
showcase web stacks, outward-facing by design); it is an operator-facing
proxy sitting in front of provider credentials and coding-agent traffic,
the same shape ADR-0011 already private-gates Immich for (credential and
CVE-surface exposure) and the Flux-UI research private-gates every
in-cluster dashboard candidate for (`research-flux-ui-dashboard.md`
section 4.3). **Private, Tailscale-only, never through the Cloudflare
tunnel, is the default this ticket confirms rather than re-derives.** What
this section adds beyond restating that default is what "private" actually
means once OmniRoute's own access-control code is read against it: the
mechanism this repo uses for "private" (5.2) is not the same thing as the
loopback boundary OmniRoute's own security model relies on (5.4), and that
gap has a concrete consequence for which of OmniRoute's routes actually
work under this posture.

### 5.2 The mechanism: NodePort, which is LAN-and-Tailscale, not a Tailscale-only network

This repo's existing precedent for "private, Tailscale-only" is not a
Tailscale-scoped network boundary; it is a plain Kubernetes `NodePort`
Service with no ingress route and no Tailscale-aware access control of its
own. Immich's own `Service` manifest states this outright: "NodePort, not
Ingress: ADR-0011 keeps Immich private-only, reachable over LAN or
Tailscale, never through the public Cloudflare tunnel. A NodePort ... is
reachable at `<node-LAN-IP>:32283` and `<node-Tailscale-IP>:32283` alike,
since both addresses terminate on the same node1 kubelet"
(`workloads/immich/server-service.yaml`). "Private" here means "off the
public tunnel," not "inside a Tailscale-only network": anything already on
the LAN reaches the NodePort exactly as anything on the tailnet does, the
same boundary ADR-0011's own "Segmentation" section names as a limit, not
an omission ("this buys isolation from the internet, and nothing else...
[a]ny device already on the LAN can still reach the NAS"). A
`workloads/omniroute/` `Service` built the same way (the only exposure
mechanism this repo has used for a private workload so far) inherits the
same shape: reachable from the LAN and the tailnet alike, unauthenticated
at the network layer, with no VPN-side check gating who is calling. Whether
that is an acceptable boundary for a credential-proxying tool is exactly
what OmniRoute's own `REQUIRE_API_KEY` setting has to answer (5.3), since
the network layer this repo has does not answer it on its own.

Confirmed against `ansible/roles/tailscale/`: this platform's Tailscale
role installs the client and joins the tailnet with an auth key
(`ansible/roles/tailscale/tasks/main.yml`); nothing in it enables MagicDNS
or provisions an HTTPS certificate for node1's tailnet name. node1 is
reached at its Tailscale IP, plain HTTP, the same as its LAN address. That
fact is not a footnote here; it is the reason section 5.5's OAuth
redirect-URI question resolves the way it does.

### 5.3 REQUIRE_API_KEY: the setting that actually gates the traffic this deployment carries

The route that matters most for this deployment, the `/v1/*` proxy path
Claude Code would call, is classified `CLIENT_API` by OmniRoute's own
authorization pipeline, and its auth requirement is conditional, not fixed:
"Bearer key when the effective `REQUIRE_API_KEY` feature flag is enabled"
(`docs/architecture/AUTHZ_GUIDE.md`, "Route Classes" table,
<https://raw.githubusercontent.com/diegosouzapw/OmniRoute/main/docs/architecture/AUTHZ_GUIDE.md>).
`REQUIRE_API_KEY` itself defaults to `false`
(`docs/reference/ENVIRONMENT.md` section 4, "Security & Authentication"),
and the same section's own "Hardening Checklist" lists it as the second of
five variables under "Production security minimum" (`AUTH_COOKIE_SECURE=true`
comes first), which is still the plainest signal available that the shipped
default is not the hardened one. `API_HOST`,
`HOST`, and `OMNIROUTE_SERVER_HOST` (the three variables that matter
depending on which server-start path is used) all default to `0.0.0.0`
(ENVIRONMENT.md section 3): nothing at the application layer binds
OmniRoute to loopback on its own. Put together with 5.2: a
`workloads/omniroute/` `Service` deployed exactly like Immich's, with
`REQUIRE_API_KEY` left at its shipped default, would accept unauthenticated
`/v1/chat/completions` calls from anything already on the LAN or the
tailnet, spending whatever provider quota or paid-provider credentials
OmniRoute holds on the operator's behalf. This is not a defect specific to
this platform's network shape; it is the same "off by default, on by
operator action" pattern the Dockerfile's memory ceiling (section 1.2) and
the OAuth-secret table (section 3.4) already showed for other settings.
The action this ticket's exposure posture requires, beyond the network
placement itself, is setting `REQUIRE_API_KEY=true` (and issuing Claude
Code its own key via the dashboard) as part of whatever manifest a future
deployment ticket writes; NodePort placement on the tailnet alone does not
supply that gate.

### 5.4 LOCAL_ONLY routes: private exposure here does not mean loopback

OmniRoute's own security documentation draws a narrower boundary than
"private network" for a specific set of routes, and this repo's NodePort
mechanism sits on the wrong side of it. `docs/security/ROUTE_GUARD_TIERS.md`
defines a `LOCAL_ONLY` tier, "enforced by `isLocalOnlyPath(path)` → loopback
host check," applied unconditionally, before any auth check, to every
"spawn-capable" route: `/api/cli-tools/runtime/`, `/api/services/`
(embedded Redis/9router install), `/api/tools/agent-bridge/`,
`/api/tools/traffic-inspector/`, `/api/plugins/`, `/api/local/` (1-click
Redis launcher), `/api/oauth/cursor/auto-import`, and
`/api/providers/{id}/login` (a headful Playwright browser launched for
web-cookie provider logins), among others named in the tier's own table
(<https://raw.githubusercontent.com/diegosouzapw/OmniRoute/main/docs/security/ROUTE_GUARD_TIERS.md>).
The stated reason is a named CVE class (GHSA-fhh6-4qxv-rpqj): a
management endpoint that spawns a subprocess is remote code execution the
moment it is reachable off-host, so the loopback check runs "before auth
runs" specifically so a leaked JWT or API key cannot reach it, and the
document's own operator guidance names Tailscale explicitly as one of the
tunnel/proxy shapes this check is designed to survive: "If you run
OmniRoute behind a reverse proxy or tunnel (nginx, Caddy, Cloudflare
Tunnel, Tailscale, Ngrok), the loopback check still protects the
spawn-capable routes above." A narrow carve-out exists
(`LOCAL_ONLY_MANAGE_SCOPE_BYPASS_PREFIXES`, a `manage`-scoped Bearer key),
but it applies to exactly one prefix, `/api/mcp/`; the document is explicit
that `/api/cli-tools/runtime/` and `/api/services/` are "intentionally
excluded because they can spawn arbitrary subprocesses," with no bypass
available at any privilege level.

The consequence for this platform: a request arriving at a NodePort Service
does not originate from `127.0.0.1` inside the container, whether it
crosses the LAN or the tailnet to get there, so every `LOCAL_ONLY` route
above returns `403 LOCAL_ONLY` for every caller under the exposure posture
5.1 settles on, including the operator's own browser over Tailscale. This
is the correct outcome from OmniRoute's own threat model (it is exactly the
"exposed behind Tailscale" case the guard is written to survive, per the
quoted operator guidance), not a bug this deployment introduces, but it is
an operational fact worth stating plainly for whichever ticket writes the
actual manifest: the web-cookie provider-login flow, the embedded-Redis
one-click launcher, the CLI-tools runtime, and the traffic
inspector/agent-bridge tools are unreachable through the standing NodePort
exposure, by design, at any privilege level. Reaching them requires an
actual loopback connection to the pod, which this repo already has
precedent for through a different, existing mechanism: `kubectl
port-forward`, used elsewhere in this repo to reach a pod's own port
without a `Service` (`docs/how-to/quarterly-postgres-restore-drill.md`).
Nothing found suggests this repo needs any `LOCAL_ONLY` route for its
stated use case (Claude Code calling `/v1/*`, a `CLIENT_API` route, not
`LOCAL_ONLY`), so this is recorded as a fact for whoever operates the
deployment later, not a gap this ticket needs to close.

### 5.5 The OAuth redirect-URI question from section 3.4: resolved, not moot

Section 3.4 left one dependency open: whether a Tailscale-only origin
counts as "remote" for the three providers needing an operator-registered
OAuth client and secret (Gemini, Antigravity, GitLab Duo), since
`docs/reference/ENVIRONMENT.md` section 11 only distinguishes "built-in
credentials for localhost development" from "remote deployments," without
defining "remote" further. Read against 5.2, the answer for node1's actual
address does not turn on that definition at all: node1 is reached by its
raw Tailscale IP over plain HTTP, and Google's own OAuth documentation
states two independent rules that a raw-IP, HTTP origin fails regardless of
how "remote" is defined: "Redirect URIs must use the HTTPS scheme, not
plain HTTP. Localhost URIs (including localhost IP address URIs) are
exempt from this rule," and separately, "Hosts cannot be raw IP addresses.
Localhost IP addresses are exempted from this rule"
(<https://developers.google.com/identity/protocols/oauth2/web-server>).
node1's Tailscale IP is neither `localhost` nor an HTTPS hostname, so
Gemini and Antigravity's OAuth redirect URI cannot be registered against
this platform's current exposure mechanism at all, independent of the
"remote" question 3.4 raised.

A fix exists but is not in place: Tailscale itself can issue a real HTTPS
certificate for a MagicDNS name (`https://machine-name.tailnet-name.ts.net`)
via `tailscale cert`, gated on enabling MagicDNS and the "HTTPS
Certificates" toggle in the tailnet admin console
(<https://tailscale.com/kb/1153/enabling-https>), which would give node1 an
HTTPS, non-raw-IP address Google's rules accept. Checked against this
platform's own provisioning: `ansible/roles/tailscale/` installs the client
and joins the tailnet with an auth key only; neither MagicDNS nor an HTTPS
certificate is provisioned anywhere in this repo today (5.2). Standing up
that path would be new platform infrastructure, not an OmniRoute-specific
configuration change, and per #164's own scoping this deployment's only
committed consumer is Claude Code, a public OAuth client needing no secret
and no HTTPS-specific redirect URI (ENVIRONMENT.md section 11). Section
3.6 already found no planned provider connection that would need Gemini,
Antigravity, or GitLab Duo's secret-bearing OAuth path. This section closes
3.4's open dependency with a concrete answer rather than carrying it
forward: those three providers are not reachable through this platform's
exposure mechanism as it exists today, a fact for a future ticket to
re-open only if one of them is ever proposed as an actual consumer, not
something #195's recommendation needs to resolve now.

### 5.6 Verdict

**Private, Tailscale-only, never through the Cloudflare tunnel**, confirming
ADR-0011's default and #164's own pre-commitment (5.1): nothing found in
sections 1-4 or this section argues for public exposure. Concretely, that
means a `workloads/omniroute/` `Service` shaped like
`workloads/immich/server-service.yaml`, a plain `NodePort` with no ingress
route (5.2). Two things this ticket adds beyond confirming the default,
both facts for whichever ticket writes the deployment manifest rather than
blockers to #195's recommendation: `REQUIRE_API_KEY=true` has to be set
explicitly, since the network placement alone leaves the `/v1/*` proxy
path open to anything already on the LAN or tailnet (5.3); and OmniRoute's
own `LOCAL_ONLY` route tier, node1's NodePort exposure, and Google's OAuth
redirect-URI rules combine to put several of OmniRoute's own features
(the web-cookie provider-login flow, the embedded-Redis one-click launcher,
and Gemini/Antigravity's OAuth connection specifically) out of reach under
this posture unless the operator reaches the pod directly via `kubectl
port-forward` or this platform later stands up Tailscale MagicDNS/HTTPS
(5.4, 5.5). None of this changes the exposure default itself; it is the
concrete shape "private by default" takes once OmniRoute's own access
model is read against the mechanism this repo actually has for it.

---

## 6. Cost/routing impact against Claude Code and Hermes/OpenClaw

### 6.1 The "1200+ models, 340 providers" claim, and what it actually covers

Story 5 asks whether the "1200+ models, 340 providers" headline improves on
calling Anthropic directly for Claude Code, or whether the value is entirely
in fronting Hermes/OpenClaw's provider costs. The headline figure is the
repository's own top banner: "one endpoint, 340 providers (90+ free), 1200+
models" (<https://github.com/diegosouzapw/OmniRoute>). That count is the
full catalog OmniRoute can proxy to, most of it reachable only by supplying
the operator's own paid API key for that specific provider, per section
3.3's finding that most provider connections go through the Dashboard, not a
free pool. The keyless portion is a much smaller, separately documented
number: `docs/reference/FREE_TIERS.md`'s own TL;DR counts "290 AI providers"
with "90+ free", aggregated into "43 provider pools / 516 models" for the
actual free-tier grant already cited in section 3.1 (~1.53B tokens/month
recurring)
(<https://raw.githubusercontent.com/diegosouzapw/OmniRoute/main/docs/reference/FREE_TIERS.md>).
The provider count itself has already drifted between the two documents
(340 in the README banner, 290 in `FREE_TIERS.md`'s body text), the same
kind of README-runs-ahead-of-the-rest-of-the-docs churn section 4.6 already
found in the npm release cadence, not a contradiction worth resolving here.
What matters for story 5 is smaller than either number: this deployment's
own use case, per #164's scoping, is Claude Code and potentially
Hermes/OpenClaw, none of which has a reason to buy access to 1200 paid
models through a gateway instead of directly. If the free-tier-aggregation
argument holds at all, it has to hold on the free 516-model slice, and
section 6.2 checks whether Claude is in it.

### 6.2 Anthropic and Claude are absent from OmniRoute's free-tier pool

`FREE_TIERS.md`'s full free-tier table (43 pools) names no Anthropic or
Claude entry anywhere: not in the TL;DR summary, not in the per-provider
table, not in the ToS-attention table (checked in full, same source as 6.1).
The one route to a genuine Claude response with no Anthropic API key is Kiro
AI, already named in section 3.1 as one of the two keyless onboarding paths
("free Claude, ~50 credits/month per account", README's Quick Start
section). `FREE_TIERS.md`'s own per-provider row for Kiro gives the real
figure for that path: "~25K" steady tokens/month, and its ToS-attention
table flags Kiro at the document's strongest caution level, "avoid": the
row states the Kiro FAQ "explicitly prohibits use with 'OpenClaw and similar
tools that leverage third-party harnesses'", naming a self-hosted AI proxy
like OmniRoute as exactly the kind of routing that clause forbids (same
source). Two independent facts rule this path out for this deployment: 25K
tokens/month is a fraction of what a single Claude Code turn consumes, let
alone a working session, and OmniRoute's own documentation flags the exact
use case this ticket is evaluating as a terms-of-service violation of the
underlying free tier it would draw from. Every other route to a Claude
response through OmniRoute goes through the Dashboard's Anthropic OAuth
connection (3.4, "public client, no secret needed") or a supplied API key,
both metered against the same Anthropic pricing an operator would pay
calling Anthropic directly, not against any free pool gained by adding
OmniRoute in front.

### 6.3 What routing Claude Code through OmniRoute actually changes: the auth swap

Claude Code's own documentation states the mechanism plainly: pointing
Claude Code at any gateway via `ANTHROPIC_BASE_URL` makes it "authenticate
to the gateway with a credential your organization issues instead of your
personal claude.ai login" ("Connect Claude Code to an LLM gateway",
<https://code.claude.com/docs/en/llm-gateway-connect>). That is the same
mechanism OmniRoute's own docs describe for Claude Code: "Point your coding
tool" at OmniRoute's local endpoint with an API key copied from its
Dashboard (README, Quick Start, same source as 6.1). This is not an
optimization sitting alongside Claude Code's normal login; it replaces it. A
Claude Code session authenticates one of two ways: the personal claude.ai
OAuth login tied to a Pro/Max subscription, billed as a flat monthly fee
regardless of token volume, or a directly configured `ANTHROPIC_API_KEY`,
metered per token at Anthropic's own published rates. Once
`ANTHROPIC_BASE_URL` points at OmniRoute, the subscription OAuth login is
not used at all; every request goes out under whatever credential
OmniRoute's own Anthropic connection is metered against, which per 6.2 is
either a supplied Anthropic API key (the same per-token rate as calling
Anthropic directly, no savings) or the ToS-barred, five-figure-token Kiro
trickle (not viable at any usage volume this repo's own agentic workload
would produce).

### 6.4 Does OmniRoute improve on calling Anthropic directly for Claude Code specifically?

No, on either of the two ways this deployment's Claude Code usage could be
billed today, a distinction this ticket did not need to resolve since
neither branch changes the answer (this repo's own docs record no evidence
either way; checked `CONTEXT.md` and `docs/reference/platform-state.md` in
full, neither mentions Claude Code's billing arrangement):

- If Claude Code here runs on the personal claude.ai subscription (the
  common case for an individual Pro/Max user): routing through OmniRoute
  cannot preserve that entitlement at all, per 6.3, since the subscription
  login is bypassed the moment `ANTHROPIC_BASE_URL` is set. The only way to
  keep talking to real Claude models through OmniRoute is metered API
  billing, a materially worse cost position than a flat subscription fee for
  anyone whose usage exceeds the metered-equivalent cost, which routine
  coding-agent usage typically does.
- If Claude Code here already runs on a metered `ANTHROPIC_API_KEY`:
  OmniRoute changes nothing about the per-token cost, since Anthropic is not
  in its free pool (6.2) and its Dashboard connection is billed at the same
  Anthropic rates either way. The only thing added is a second component in
  the request path holding or proxying the same credential, for the
  resource-footprint (section 1), secrets-boundary (section 3), and
  exposure-posture (section 5) costs this research doc already prices in,
  in exchange for no routing or cost benefit on this specific traffic.

The "1200+ models, 340 providers" claim does not change either branch:
Claude Code's whole reason for existing is Claude-quality output on coding
tasks, so a gateway's access to 1200 non-Claude models is not a substitute
this deployment would use for Claude Code's own calls, only a number
describing traffic this deployment has no plan to send.

### 6.5 The value case is entirely in Hermes/OpenClaw, and #165 has not settled it

#164's own Further Notes said this plainly before this ticket started: "if
neither Hermes nor OpenClaw is adopted, Omniroute's only remaining consumer
is Claude Code itself, which changes whether the gateway is worth its
footprint at all." Section 6.4 above is the concrete answer to that question
for the Claude Code half: no upside, only added footprint and secrets
surface. Whatever value case OmniRoute has left rests entirely on Hermes
and/or OpenClaw actually needing multi-provider free-tier aggregation,
which depends on whether either tool's own model requirements tolerate the
non-Claude models that make up nearly all of OmniRoute's free pool (6.2).
#165 ("Investigate a personal AI assistant: Hermes vs OpenClaw") is still
open with no research doc written (checked via `gh issue view 165`,
2026-08-19), so this ticket cannot resolve that question, only state what it
depends on: a "yes" for OmniRoute at all requires a "yes, and it doesn't
need Claude-quality output" from #165 first.

### 6.6 Verdict

Against calling Anthropic directly for Claude Code specifically, OmniRoute
has no cost or routing upside found anywhere in this check: Anthropic is
absent from its free-tier pool, its one keyless route to a genuine Claude
response (Kiro) is both too small to matter and explicitly barred by Kiro's
own terms for this exact proxy use case, and pointing Claude Code at
OmniRoute replaces the subscription login with metered billing rather than
adding a cheaper path alongside it. The "1200+ models, 340 providers"
headline describes a paid catalog this deployment has no reason to call
through Claude Code, not a free-tier win. What remains of #164's original
premise, aggregating free-tier quota across tools instead of paying per
tool, applies only to whatever of Hermes/OpenClaw's own traffic can
tolerate a non-Claude model, a question #165 has not yet answered. This is
a concrete argument for closing this ticket "no" on Claude Code's own
account alone, independent of #195's final recommendation, which per #164's
own story 9 is an acceptable outcome for this whole investigation.
