# OmniRoute AI gateway: resource footprint and whether it's worth running here

**Date:** 2026-08-19
**Status:** in progress. Covers #189 (164-01, resource footprint, section 1
below) and #190 (164-02, deployment shape, section 2 below). Secrets
inventory (#191, 164-03), provenance check (#192, 164-04), exposure posture
(#193, 164-05), cost/routing impact (#194, 164-06), and the recommendation
(#195, 164-07) are follow-on tickets.
**Sources:** primary only, per this repo's `/research` convention: the
project's own repository (`docker-compose.yml`, `Dockerfile`,
`docs/reference/ENVIRONMENT.md`, `docs/architecture/cluster-decisions.md`,
`docs/guides/DOCKER_GUIDE.md`, `docs/guides/SETUP_GUIDE.md`), its README,
its own GitHub issue tracker for real, closed reports of measured memory
use, and this repository's own existing `workloads/` manifests
(`workloads/immich/`) as the deployment precedent being compared against.
Every claim carries its URL inline.

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

The secrets inventory (#191/164-03), the provenance check (#192/164-04),
the exposure posture (#193/164-05), cost/routing impact against calling
Anthropic directly (#194/164-06), and the recommendation (#195/164-07) are
follow-on tickets.
