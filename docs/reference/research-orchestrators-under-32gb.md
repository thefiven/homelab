# Orchestrators under a 32 GB ceiling: resident cost, second-node cost, and maintenance burden

**Date:** 2026-08-05
**Status:** Research note. No decision is made here.
**Method:** Primary sources only — official documentation, official release notes, upstream
repository contents, and project source code. Every claim carries a direct URL. Where the
primary sources do not answer the question, this note says so rather than substituting an
estimate.

---

## 1. Scope and why the numbers are hard to compare

The question asked for **idle resident memory of the control plane plus agent on a single
node**. Only two of the five candidates publish a measured memory figure at all, and both
measured something subtly different from what was asked:

| Candidate | Publishes a *measured* memory figure? | Publishes *minimum requirements*? |
|---|---|---|
| Docker Compose + GitOps manager (Komodo / Dockge) | No | Partially (OS/arch only) |
| HashiCorp Nomad | No | Yes (production sizing, not minimums) |
| k0s | Yes (controller node, k0s v1.22 era) | Yes |
| k3s | Yes (whole host, k3s v1.26.5) | Yes |
| Kubernetes / kubeadm | No | Yes |

**Read this before using any number below.** A "minimum system requirement" is a support
statement, not a measurement. A measured figure is only comparable to another measured
figure taken the same way. The two measured datasets here — k0s's and k3s's — were taken with
different tools, on different hardware, on Kubernetes releases four years apart, and one of
them (k3s) includes a monitoring stack in the total. They should not be subtracted from one
another.

Hardware context this note is written against: one Ryzen 5 5600X (6C/12T), **32 GB DDR4 as a
hard ceiling**, 2× Kingston NV2 1 TB NVMe (DRAM-less), NFS from a Synology DS412+, one
unmanaged gigabit switch, single operator, no HA wanted, public GitHub repository that may
never hold a cluster credential.

---

## 2. Docker Compose + a GitOps manager (Komodo, Dockge)

### 2.1 Idle memory footprint

**Not established from primary sources.** Neither the Docker Compose documentation, the
Komodo documentation, nor the Dockge README publishes a measured or expected memory figure
for the daemon, the manager, or its agent.

What *is* established, and matters more than the missing number:

- Docker Compose is documented as "a tool for defining and running multi-container
  applications" ([docs.docker.com/compose](https://docs.docker.com/compose/)). It is a client
  that drives an already-running Docker Engine; it is not itself a resident control plane.
- **Komodo is not a single process.** Its documented architecture is a **Core** (web server
  hosting the API and UI) plus a **Periphery** agent ("a stateless agent deployed on each
  connected server") — [komo.do/docs/intro](https://komo.do/docs/intro).
- **Komodo requires a document database.** The official setup page offers exactly two
  supported deployments: "Using MongoDB" or "Using FerretDB (Postgres)"
  ([docsite/docs/setup/index.mdx](https://github.com/moghtech/komodo/blob/main/docsite/docs/setup/index.mdx)).
  There is no embedded/SQLite option in the documented setup path.
- **The database is the memory risk, and Komodo already knows it.** Komodo's own reference
  compose file starts MongoDB with `command: --quiet --wiredTigerCacheSizeGB 0.25`
  ([compose/mongo.compose.yaml](https://github.com/moghtech/komodo/blob/main/compose/mongo.compose.yaml)).
  That override matters: MongoDB's documented default WiredTiger internal cache is
  "50% of (RAM − 1 GB)" or 0.256 GB, whichever is larger
  ([mongodb.com/docs/manual/core/wiredtiger](https://www.mongodb.com/docs/manual/core/wiredtiger/)).
  On a 32 GB host, the *default* would be ≈ 15.5 GB of cache — roughly half the machine.
  Komodo's shipped file pins it to 0.25 GB. Anyone deploying Mongo outside that file, or
  reverting that flag, hands half the RAM ceiling to the database.

### 2.2 Minimum system requirements

- Komodo: "To run Komodo, you will need Docker"
  ([setup/index.mdx](https://github.com/moghtech/komodo/blob/main/docsite/docs/setup/index.mdx)).
  No CPU/RAM/disk figures are stated anywhere in the docs site.
- Dockge: "Docker 20+ / Podman", major Linux distributions, "Arch: armv7, arm64, amd64"
  ([README.md](https://github.com/louislam/dockge/blob/master/README.md)). No CPU/RAM figures.

### 2.3 Cost of adding a second node

There are two distinct answers, and conflating them is the trap.

**(a) Federating a second independent Docker host.** This is what Komodo and Dockge actually
do. Komodo's Periphery is "deployed on each connected server"
([komo.do/docs/intro](https://komo.do/docs/intro)); as of v2.0.0 Periphery can also initiate
the connection outbound to Core
([v2.0.0 release notes](https://github.com/moghtech/komodo/releases/tag/v2.0.0)). Dockge added
"Multiple agents support — You can manage multiple stacks from different Docker hosts in one
single interface" in 1.4.0 ([README.md](https://github.com/louislam/dockge/blob/master/README.md)).
No quorum, no datastore change, no shared scheduler. **There is also no scheduler**: you place
each stack on a named host by hand. Heterogeneous CPUs are a non-issue because nothing is
scheduled across them.

**(b) Building an actual cluster** means Docker Swarm mode, which is a different product
surface: "Swarm mode is an advanced feature for managing a cluster of Docker daemons"
([docs.docker.com/engine/swarm](https://docs.docker.com/engine/swarm/)). Swarm managers use
Raft: "Raft tolerates up to `(N-1)/2` failures and requires a majority or quorum of `(N/2)+1`
members" ([docs.docker.com/engine/swarm/raft](https://docs.docker.com/engine/swarm/raft/)).
So Swarm *does* impose a quorum story; the Komodo/Dockge federation model does not. Komodo
v2.0.0 added first-class Swarm management as a separate feature
([v2.0.0 release notes](https://github.com/moghtech/komodo/releases/tag/v2.0.0)).

### 2.4 Declarative-change story

**Komodo: yes, with a documented diff-and-alert loop.** Resource Syncs are TOML files that can
live in a git repo, and the reconciliation is explicitly *pull* from inside the network:

> "Komodo is able to create, update, delete, and deploy resources declared in TOML files by
> diffing them against the existing resources, and apply updates based on the diffs. … The
> Komodo Core backend will poll the files for any updates, and alert about pending changes
> when diffs are detected."
> — [docsite/docs/automate/sync-resources.md](https://github.com/moghtech/komodo/blob/main/docsite/docs/automate/sync-resources.md)

Two caveats from the same page, both material:

- "The UI will display the computed sync actions and **only execute them upon manual
  confirmation**." Automatic execution requires configuring a git webhook — which is an
  *inbound* push from GitHub, not a pull, and therefore has network-exposure implications for
  a home network behind NAT.
- Drift detection here means *declaration drift* (repo vs. Komodo's own resource records), not
  container-runtime drift in the general sense.

**Dockge: no.** The README's feature list is create/edit/start/stop/delete of `compose.yaml`
files, an interactive editor, a web terminal, agents, and `docker run` conversion. Git is not a
feature ([README.md](https://github.com/louislam/dockge/blob/master/README.md)). It advertises
the opposite property — "File based structure - Dockge won't kidnap your compose files" — which
means the source of truth is the local filesystem, and any git story is one you build yourself
with a cron job.

### 2.5 Maintenance burden

- **Komodo** is under active, fast development. Tagged releases: v2.0.0 on 2026-03-24, v2.1.0
  2026-04-01, v2.2.0 2026-05-07, v2.3.0 2026-07-29, v2.3.1 2026-07-31
  ([releases](https://github.com/moghtech/komodo/releases)). The v2.0.0 notes list a breaking
  change — "The v2 images are only available with `:2` tags. The `:latest` tag is now
  deprecated" — plus an auth model replacement ("PKI authentication… Passkeys are deprecated")
  ([v2.0.0](https://github.com/moghtech/komodo/releases/tag/v2.0.0)). There is **no published
  support window and no LTS**. Licence: GPL-3.0, and the README states plainly: "while we make
  a best effort to ensure releases are stable and bug-free, there are no warranties"
  ([readme.md](https://github.com/moghtech/komodo/blob/main/readme.md)).
- **Dockge** shows a release/commit split worth noticing. Last tagged release is **1.5.0 on
  2025-03-30**, and before that 1.4.2 on 2024-01-21
  ([releases](https://github.com/louislam/dockge/releases)) — i.e. two tagged releases in
  roughly two and a half years. But `master` is alive: commits on 2026-04-18 and 2026-04-19
  include an XSS fix ("fixed missed v-html xss warning vulnerability")
  ([commits](https://github.com/louislam/dockge/commits/master/)). 117 issues are open
  ([GitHub issue search](https://github.com/louislam/dockge/issues?q=is%3Aissue+is%3Aopen)).
  The practical reading: **fixes land in `master` but are not being cut into tagged releases**,
  so a user pinning to a release tag is 16 months behind a known XSS fix.

---

## 3. HashiCorp Nomad

### 3.1 Idle memory footprint

**Not established from primary sources.** HashiCorp publishes no measured idle memory figure
for a Nomad server or client agent. The only memory numbers in the official docs are
*production sizing recommendations*, which are enormous relative to this hardware and were
written for cloud fleets:

- Servers: "CPU 4-8+ cores, RAM 16-32 GB+, Disk 40-80 GB+ of fast storage"
  ([nomad/docs/deploy/production/requirements](https://developer.hashicorp.com/nomad/docs/deploy/production/requirements)).
- Reference architecture sizing table: Small = 2–4 core, 8–16 GB RAM, 50 GB disk; Large =
  8–16 core, 32–64 GB RAM, 100 GB
  ([reference-architecture](https://developer.hashicorp.com/nomad/docs/deploy/production/reference-architecture)).
  "The small size would be appropriate for most initial production deployments."
- The reason given is architectural, not incidental: Nomad servers keep all state in memory
  and take two disk snapshots, producing high I/O under load
  ([requirements](https://developer.hashicorp.com/nomad/docs/deploy/production/requirements)).

**Nomad clients have no documented minimum at all.** The client section of the requirements
page discusses reserving resources away from Nomad rather than what Nomad itself needs.

Do not read "16-32 GB" as "Nomad needs 16 GB". It is a sizing recommendation for a loaded
production server, and the same page says "These recommendations are guidelines and operators
should always monitor the resource usage of Nomad to determine if the machines are under or
over-sized." But it is the *only* first-party number, and the gap between it and a homelab is
unquantified by HashiCorp.

### 3.2 Minimum system requirements

See above — HashiCorp publishes recommendations, not minimums. Nomad is distributed as a
single self-contained binary: "Nomad runs as a single binary and is entirely self contained -
combining resource management and scheduling into a single system", and "requires no external
services for coordination or storage"
([what-is-nomad](https://developer.hashicorp.com/nomad/docs/what-is-nomad)). No etcd, no
database, no CNI to install — a genuine and relevant simplification.

### 3.3 Cost of adding a second node

**Adding a client is cheap; adding a server is a quorum event.**

The consensus documentation is unusually blunt about the single-server case:

> "A single server deployment is _**highly**_ discouraged as data loss is inevitable in a
> failure scenario."
> — [nomad/docs/architecture/cluster/consensus](https://developer.hashicorp.com/nomad/docs/architecture/cluster/consensus)

The failure-tolerance table from that page: 1 server → quorum 1, tolerance 0; 2 → 2, 0; 3 → 2,
1; 5 → 3, 2. "The recommended configuration is to either run 3 or 5 Nomad servers per region."
The outage-recovery page repeats the consequence: "In the case of an unrecoverable server
failure in a single server cluster, data loss is inevitable since data was not replicated to
any other servers"
([outage-recovery](https://developer.hashicorp.com/nomad/docs/manage/outage-recovery)).

This is a direct collision with the stated growth path. Adding *one* cheap mini-PC gets you
two servers — quorum 2, tolerance 0, i.e. **strictly worse than one server** (either machine
dying stops the control plane). To get any benefit you must reach three servers, meaning the
first two additions buy nothing in control-plane terms. Adding the mini-PCs as *clients* only
sidesteps this entirely and is the sane path, but then the SPOF is unchanged.

Heterogeneity: Nomad is documented as running "a diverse workload of Docker,
non-containerized, microservice, and batch applications" and is "supported on macOS, Windows,
and Linux" ([what-is-nomad](https://developer.hashicorp.com/nomad/docs/what-is-nomad)). Mixed
CPU generations are not called out as an issue anywhere in the primary docs.

Upgrade sequencing when nodes multiply: servers first, then clients, and Nomad "maintains
backward compatibility for at least 2 point release"; the documented procedure is sequential
with health checks between steps ([nomad/docs/upgrade](https://developer.hashicorp.com/nomad/docs/upgrade)).

### 3.4 Declarative-change story

**Partially — and the missing part is exactly the part this repository needs.**

Nomad jobs are declarative HCL specifications, and `nomad job plan` produces a diff before
apply. But **no first-party pull-based git reconciler is documented**. The official submission
path is push: CLI or API. I found no HashiCorp-documented component that sits inside the
network, polls a git repository, and reconciles drift the way Flux or Komodo Resource Sync do.

**This is a "not established from primary sources" finding, and it is load-bearing.** The
repository constraint is that no cluster credential may exist as a CI secret, which forces a
pull model. With Nomad, that pull loop is something you would have to build and then maintain
yourself.

GPU: the NVIDIA device plugin is **external to Nomad** — you download or compile the binary and
place it in the plugin directory; jobs then request `device "nvidia/gpu" { count = 1 }`
([nomad/plugins/devices/nvidia](https://developer.hashicorp.com/nomad/plugins/devices/nvidia)).
**Whether one GPU can be shared between multiple allocations is not addressed in that
documentation** — an unresolved question for an 8 GB RTX 3070 Ti meant to be a shared,
schedulable platform resource.

### 3.5 Maintenance burden

This is where Nomad has changed the most, and the changes are recent.

**Licence.** Nomad CE is under the Business Source License 1.1. The current `LICENSE` file
names the licensor as **International Business Machines Corporation**, with a Change Date of
"Four years from the date the Licensed Work is published" and a Change License of MPL 2.0
([LICENSE](https://github.com/hashicorp/nomad/blob/main/LICENSE)). Nomad is no longer open
source under an OSI licence, and it is now an IBM product.

**Versioning and support.** From 2.0.0, Nomad abandoned semantic versioning for IBM's
Version-Modification-Fix model: April is the "V" milestone that "starts a new support
lifecycle", October is the "M" milestone that "adds new features but does not start a new
support lifecycle", and monthly "F" patch releases carry fixes. Community Edition gets "a
2-year base CE backport policy"
([nomad/docs/ce-license-support](https://developer.hashicorp.com/nomad/docs/ce-license-support)).
Published end dates from that page: 1.8.x (LTS) 2026-04-30; 1.11.x 2026-10-31; 1.10.x (LTS)
2027-04-30; 2.0.x base support 2028-04-28 (extended to 2029/2032 tiers). **LTS is enterprise
tiering, and 1.10.x is described as the last LTS release.**

**Breaking-change history, last ~2 years** — all from
[upgrade-specific](https://developer.hashicorp.com/nomad/docs/upgrade/upgrade-specific):

- **1.9.0** — servers dropped support for clients older than 1.6.0 (older nodes fail
  heartbeats and their workloads get rescheduled); Workload-Identity/Variables keyring moved
  into Raft; **HCLv1 job specifications removed**, `-hcl1` no longer functions.
- **1.10.0** — Vault and Consul token-based authentication *removed*; tasks must use workload
  identity. `vault.allow_unauthenticated`, `vault.task_token_ttl`, `vault.token`,
  `vault.policies`, `consul.allow_unauthenticated` all removed. Remote task driver support
  removed. Plugins in `plugin_dir` now require matching `plugin` blocks or they are skipped.
  `max_client_disconnect`, `stop_after_client_disconnect`, `prevent_reschedule_on_lost`
  removed in favour of a `disconnect` block.
- **1.11.0** — sysbatch jobs with a `reschedule` block now error instead of being ignored; ACL
  policies with duplicate/invalid keys now rejected; job allocation count capped by
  `job_max_count` (default 50,000); Node API `Resources`/`Reserved` deprecated.
- **2.0.0** (released 2026-04-21) — licensing error/log output reformatted; `raft_boltdb`
  deprecated in favour of `raft_logstore`. In 2.0.1, task drivers with filesystem isolation
  (including Docker) now bind-mount allocation log directories **read-only**, and two CVEs were
  fixed (CVE-2026-6959 logmon symlink, CVE-2026-7474 dynamic host volume validation). In
  2.0.4, `server.retry_join`, `server.retry_interval`, `server.retry_max` and
  `server.start_join` are deprecated and slated for removal in 2.1.0
  ([v2-0-x release notes](https://developer.hashicorp.com/nomad/docs/release-notes/v2-0-x)).

That is a heavier removal record over two years than any of the Kubernetes distributions below.

---

## 4. k0s

### 4.1 Idle memory footprint

**Measured, but from a v1.22-era test and for a controller-only node.** The system-requirements
page publishes a "controller node measured memory consumption" table
([docs.k0sproject.io/stable/system-requirements](https://docs.k0sproject.io/stable/system-requirements/),
source: [docs/system-requirements.md](https://github.com/k0sproject/k0s/blob/main/docs/system-requirements.md)):

| Worker nodes | Additional pods | Memory (MB) |
|---|---|---|
| 1 | 0 | **510** |
| 1 | 100 | 600 |
| 20 | 0 | 660 |
| 20 | 2,000 | 1,000 |
| 100 | 10,000 | 2,300 |

Test conditions stated on the same page: k0s **v1.22.4+k0s.2** with default etcd
configuration, Ubuntu Server 20.04.3 LTS (the OS itself consumed ~180 MB), AWS t3.xlarge
(4 vCPU / 16 GB), pod image `nginx:1.21.4`.

Three honest caveats:

1. The measurement is of a **controller node**, not the combined controller+worker role this
   homelab would run. The worker's own consumption is not in this table.
2. k0s v1.22 shipped in late 2021. The current line is v1.36. The figure has not been refreshed
   in the docs.
3. The page prefaces the whole section with "The minimum requirements for k0s detailed below
   are approximations, and thus your results may vary."

The 510 MB figure is nonetheless the **lowest measured control-plane number any of these five
projects publishes**, and it is a control-plane-only measurement (unlike k3s's, below).

### 4.2 Minimum system requirements

From [system-requirements](https://docs.k0sproject.io/stable/system-requirements/):

| Role | RAM | vCPU | k0s disk usage | Minimum disk |
|---|---|---|---|---|
| Controller node | 1 GB | 1 | ~0.5 GB | ~0.5 GB |
| Worker node | 0.5 GB | 1 | ~1.3 GB | ~1.6 GB |
| Controller + worker | 1 GB | 1 | ~1.7 GB | ~2.0 GB |

"The operating system and application requirements must be considered in addition to the k0s
part." Architectures: `x86_64`, `aarch64`, `armv7l`, and `riscv64` — the last with "No
pre-compiled binaries, no CI coverage".

### 4.3 Cost of adding a second node

**There is a one-way door at install time, and it is easy to walk through by accident.**

The Quick Start Guide's headline command for a single node is
`sudo k0s install controller --single`. Immediately beneath it:

> "**Note**: The `--single` option disables features needed for multi-node clusters, so the
> cluster cannot be extended. To retain the ability to expand the cluster in the future, use:
> `sudo k0s install controller --enable-worker --no-taints`"
> — [docs/install.md](https://github.com/k0sproject/k0s/blob/main/docs/install.md)

For a project whose entire stated growth path is "add cheap mini-PCs one at a time over several
years", installing with the documented default `--single` is a trap. The correct incantation is
the second one.

Given the right install flag, adding a worker is genuinely two commands
([k0s-multi-node](https://docs.k0sproject.io/stable/k0s-multi-node/)):

```
# on the existing controller
sudo k0s token create --role=worker --expiry=100h > token-file
# on the new machine
sudo k0s install worker --token-file /path/to/token/file --start
```

No quorum change, no datastore change. Join tokens are documented as "base64-encoded
kubeconfigs" carrying CA info for mutual trust.

Adding a **controller** is the expensive path: "either etcd or an external data store (MySQL or
PostgreSQL) via kine must be in use to add new controller nodes to the cluster"
([k0s-multi-node](https://docs.k0sproject.io/stable/k0s-multi-node/)). k0s's `spec.storage.type`
accepts `etcd` or `kine`, and "Type `etcd` will cause k0s to create and manage an elastic etcd
cluster within the controller nodes"
([docs/configuration.md](https://github.com/k0sproject/k0s/blob/main/docs/configuration.md)).

**A second one-way door, unrelated to node count but decided at the same moment:** the CNI
provider. "Once you initialize the cluster with a network provider the only way to change
providers is through a full cluster redeployment" (default `kuberouter`; `calico` and `custom`
also available) — [docs/configuration.md](https://github.com/k0sproject/k0s/blob/main/docs/configuration.md).

Heterogeneous CPU generations are not flagged as a problem; mixed architectures are supported to
the extent that binaries exist per the architecture list above.

### 4.4 Declarative-change story

k0s itself is configured declaratively via a `k0s.yaml` cluster config
([configuration.md](https://github.com/k0sproject/k0s/blob/main/docs/configuration.md)), but k0s
ships **no git reconciler**. Application-level GitOps is the standard Kubernetes story — see
§7 on Flux — and is identical across k0s, k3s and kubeadm.

### 4.5 Maintenance burden

**Cadence and support window** ([docs.k0sproject.io/stable/releases](https://docs.k0sproject.io/stable/releases/)):
k0s follows upstream Kubernetes, "a few weeks behind the upstream Kubernetes version release
date", with new minors roughly every 4 months. Support window mirrors upstream: "upstream
Kubernetes provides support and patch releases for a minor version for roughly 14 months, it
means that k0s will follow this same model." Out-of-band critical fixes are marked by the
suffix (`v1.36.0+k0s.1` vs `v1.36.0+k0s.0`).

**Observed practice** ([releases](https://github.com/k0sproject/k0s/releases)): on 2026-07-27
k0s shipped v1.36.3, v1.35.7, v1.34.10 and v1.33.13 on the same day — **four minor lines
maintained in parallel**, patched in monthly batches. That is a healthy signal and it means a
homelab can sit two minors behind without being unsupported.

**Breaking-change history:** k0s does not publish a consolidated breaking-change page
equivalent to Nomad's `upgrade-specific`. Per-release notes exist on GitHub. **A systematic
two-year breaking-change record for k0s was not established from primary sources** in this
research; the two hard lock-ins I did find are documented above (`--single`, CNI provider).

**Certificates:** k0s exposes `ca.expiresAfter` (default 87600h = 10 years) and
`ca.certificatesExpireAfter` (default 8760h = 1 year) for both the API and etcd CAs
([configuration.md](https://github.com/k0sproject/k0s/blob/main/docs/configuration.md)).
**Whether k0s auto-renews leaf certificates before expiry is not established from primary
sources** — unlike k3s, which documents it explicitly (§5.5). For a 24/7 machine this is a
question worth resolving before committing, because a one-year leaf certificate that does not
self-renew is a scheduled outage.

---

## 5. k3s

### 5.1 Idle memory footprint

k3s publishes the most detailed measurements of the five — and they need the most careful
reading. From
[docs.k3s.io/reference/resource-profiling](https://docs.k3s.io/reference/resource-profiling)
(source: [resource-profiling.md](https://github.com/k3s-io/docs/blob/main/docs/reference/resource-profiling.md)):

| Components | Processor | Min CPU | Min RAM (Kine/SQLite) | Min RAM (embedded etcd) |
|---|---|---|---|---|
| K3s server with a workload | Intel 8375C @ 2.90 GHz | 6% of a core | **1596 M** | **1606 M** |
| K3s cluster with a single agent (server side) | Intel 8375C | 5% of a core | 1428 M | 1450 M |
| K3s agent | Intel 8375C | 3% of a core | **275 M** | 275 M |
| K3s server with a workload | Pi4B @ 1.50 GHz | 30% of a core | 1588 M | 1613 M |
| K3s agent | Pi4B | 10% of a core | 268 M | 268 M |

**Test bed:** k3s **v1.26.5** with all packaged components enabled, plus a Prometheus + Grafana
monitoring stack, plus the Kubernetes example nginx deployment. Host: AWS c6id.xlarge, 4 cores,
8 GB RAM, NVMe SSD, Ubuntu 22.04. Collection: standalone Prometheus v2.43.0 with
`prometheus-node-exporter`, spot-checked with `systemd-cgtop`, "Utilization figures were based
on 95th percentile readings from steady state operation."

**The document contradicts itself and you should know which half to trust.** It lists
Prometheus, Grafana and an nginx deployment among "the tested components", and describes the
figures as "baseline figures for a stable system … running a standard monitoring stack
(Prometheus and Grafana) and the Guestbook example app". Two sentences later it states:

> "Resource figures including IOPS are for the Kubernetes datastore and control plane only, and
> do not include overhead for system-level management agents or logging, container image
> management, or any workload-specific requirements."

Those two statements cannot both be true of the same number. The measurement method
(`prometheus-node-exporter` reading host memory) points strongly to the first reading:
**1596 M is a whole-host figure for a node running k3s *and* Prometheus *and* Grafana *and* an
example app** — not k3s alone at idle. The **275 M agent figure is the cleanest
control-plane-only number in this note**, and it is roughly consistent with k0s's 510 MB
controller figure once you account for the agent having no datastore or API server.

The page also notes CPU, not RAM, was the binding constraint in the server sizing tests: CPU hit
90% while RAM sat around 60%.

**Disk requirements are directly relevant to the DRAM-less NV2 drives:**

| Datastore | IOPS | KiB/sec | Latency |
|---|---|---|---|
| Kine/SQLite | 10 | 500 | < 10 ms |
| Embedded etcd | 50 | 250 | < 5 ms |

Embedded etcd is five times more IOPS-hungry and demands half the latency. On DRAM-less
consumer NVMe under sustained small synchronous writes, the sub-5 ms requirement is the number
to validate empirically before choosing etcd over SQLite.

### 5.2 Minimum system requirements

From [docs.k3s.io/installation/requirements](https://docs.k3s.io/installation/requirements):
server nodes 2 cores / 2 GB RAM; agent nodes 1 core / 512 MB RAM. Architectures: x86_64, armhf,
arm64/aarch64. "We recommend using an SSD when possible."

### 5.3 Cost of adding a second node

**Adding an agent is a single command and changes nothing about the datastore**
([docs.k3s.io/quick-start](https://docs.k3s.io/quick-start)):

```
curl -sfL https://get.k3s.io | K3S_URL=https://myserver:6443 K3S_TOKEN=mynodetoken sh -
```

with the token read from `/var/lib/rancher/k3s/server/node-token` on the server. This is the
cheapest second-node story of the five for the stated growth path (add worker capacity, keep one
control plane, accept the SPOF).

**Adding a second *server* is a datastore migration.** The default datastore for a single server
is SQLite, chosen automatically when "no other datastore configuration is present, and no
embedded etcd database files are present on disk", and "SQLite cannot be used on clusters with
multiple servers" ([docs.k3s.io/datastore](https://docs.k3s.io/datastore)). The conversion is
documented and unusually painless: "you can convert it to etcd by simply restarting your K3s
server with the `--cluster-init` flag"
([ha-embedded](https://docs.k3s.io/datastore/ha-embedded)).

But HA then requires "three or more server nodes", and "HA embedded etcd cluster must be
comprised of an odd number of server nodes for etcd to maintain quorum … for a cluster with n
servers, quorum is (n/2)+1" ([ha-embedded](https://docs.k3s.io/datastore/ha-embedded)). Same
arithmetic trap as Nomad: two servers is worse than one.

Upgrade order once there are multiple nodes: "upgrade server nodes first one at a time, then any
agent nodes", and "the Kubernetes version skew policy applies. Ensure that your plan does not
skip intermediate minor versions when upgrading"
([upgrades/manual](https://docs.k3s.io/upgrades/manual)).

### 5.4 Declarative-change story

Same as any Kubernetes — see §7. k3s adds one relevant convenience: it watches a manifests
directory and auto-applies, but the durable answer is Flux or Argo CD.

### 5.5 Maintenance burden

**Cadence** ([releases](https://github.com/k3s-io/k3s/releases)): k3s tracks upstream. On
2026-08-04 it shipped v1.36.3, v1.35.7, v1.34.10 and v1.33.13 — again **four minor lines in
parallel**, monthly, with `-rc` builds published ~10 days ahead. Release channels are `stable`
("recommended for production environments. These releases have been through a period of
community testing"), `latest`, and a per-minor channel — "There is a release channel tied to
each Kubernetes minor version, including versions that are end-of-life"
([upgrades/manual](https://docs.k3s.io/upgrades/manual)).

**Support window: not established from primary sources.** k3s's own `SECURITY.md` contains only
a disclosure address ("email security@k3s.io") and **no supported-versions table and no EOL
policy** ([.github/SECURITY.md](https://github.com/k3s-io/k3s/blob/main/.github/SECURITY.md)).
The docs site does not publish a support-window statement either. The observable behaviour —
four concurrent patched minors as of August 2026 — is consistent with following upstream's
~14-month window, but that inference is mine, not a k3s commitment. Contrast k0s, which states
the 14-month policy explicitly.

**Breaking-change history:** the k3s v1.36 release notes contain a single explicitly flagged
breaking change — a Traefik chart update where "the provider name changes from
`kubernetesIngressNginx` to `kubernetesIngressNGINX`" — and otherwise defer to upstream:
"read the Kubernetes Urgent Upgrade Notes"
([docs.k3s.io/release-notes/v1.36.X](https://docs.k3s.io/release-notes/v1.36.X)). k3s's own
breaking-change surface is thin; it inherits upstream's.

**Certificates — a genuine operational advantage.** k3s client and server certificates are valid
365 days, and "any certificates that are expired or within 120 days of expiring are
automatically renewed every time K3s starts" (the threshold was 90 days prior to the May 2025
releases). k3s also emits a Kubernetes Warning Event with `reason: CertificateExpirationWarning`
tied to the affected node ([docs.k3s.io/cli/certificate](https://docs.k3s.io/cli/certificate)).
For a single operator running 24/7 who may go months without touching the machine, automatic
renewal on restart removes a whole class of self-inflicted outage.

---

## 6. Full upstream Kubernetes (kubeadm)

### 6.1 Idle memory footprint

**Not established from primary sources.** The Kubernetes project publishes no measured idle
memory figure for a kubeadm control plane. `install-kubeadm` gives requirements, not
measurements.

The closest first-party datapoint is etcd's own hardware guidance, and it is a recommendation
rather than a measurement: for "a small cluster" — "fewer than 100 clients, fewer than 200 of
requests per second, and stores no more than 100MB of data (such as a 50-node Kubernetes
cluster)" — etcd recommends **2 vCPUs and 8 GB memory**. "An etcd server will aggressively cache
key-value data and spends most of the rest of its memory tracking watchers." Disk: "50 sequential
IOPS (e.g., a 7200 RPM disk) is required" as a floor; "Fast disks are the most critical factor
for etcd deployment performance and stability"
([etcd.io/docs/v3.6/op-guide/hardware](https://etcd.io/docs/v3.6/op-guide/hardware/)).

Treat the 8 GB as a ceiling-shaped recommendation for a *50-node* cluster, not as the resident
cost of a one-node homelab. But note that it is the only figure upstream offers, and it is a
quarter of the entire RAM budget.

### 6.2 Minimum system requirements

From
[install-kubeadm](https://kubernetes.io/docs/setup/production-environment/tools/kubeadm/install-kubeadm/):

- "2 GB or more of RAM per machine (any less will leave little room for your apps)"
- "2 CPUs or more for control plane machines"
- Unique hostname, MAC address and `product_uuid` per node
- Swap: "The default behavior of a kubelet is to fail to start if swap memory is detected on a
  node" — either `swapoff -a` or set `failSwapOn: false`
- kubeadm "uses dynamic linking and assumes your target system provides `glibc`"

### 6.3 Cost of adding a second node

**Adding a worker** ([kubeadm-join](https://kubernetes.io/docs/reference/setup-tools/kubeadm/kubeadm-join/)):

```
kubeadm token create --print-join-command
# then on the new node
kubeadm join --token <tok> --discovery-token-ca-cert-hash sha256:<hash> 1.2.3.4:6443
```

No quorum change. **Adding a control-plane node is a quorum event**: the join runs an
`etcd-join` phase that performs "Adding new local etcd member", i.e. the new machine becomes an
etcd voter. HA needs "Three or more machines" for the control plane, and "Having an odd number
of members in the etcd cluster is a requirement for achieving optimal voting quorum"
([high-availability](https://kubernetes.io/docs/setup/production-environment/tools/kubeadm/high-availability/)).
Two topologies are offered: stacked (etcd co-located, "requires less infrastructure") or
external etcd ("requires more infrastructure").

**Heterogeneity is a first-class Kubernetes property.** `kubernetes.io/arch` and
`kubernetes.io/os` are automatically populated by the kubelet on each node
([labels-annotations-taints](https://kubernetes.io/docs/reference/labels-annotations-taints/)),
so mixed-architecture and mixed-OS fleets are scheduled with node selectors and affinity
without extra machinery. Mixed x86 CPU *generations* are not a documented concern at all.

**Version skew is where the multi-node cost actually lands**
([version-skew-policy](https://kubernetes.io/releases/version-skew-policy/)):

- `kubelet` "may be up to three minor versions older than `kube-apiserver`" and "must not be
  newer" — generous, and good news for stragglers.
- Controller-manager/scheduler may be at most one minor behind the apiserver.
- "Project policies for API deprecation and API change guidelines require `kube-apiserver` to
  not skip minor versions when upgrading, **even in single-instance clusters**." You cannot jump
  1.33 → 1.36; you must walk it.

### 6.4 Declarative-change story

Same as k0s/k3s — see §7. kubeadm itself is imperative bootstrap tooling; the reconciliation
loop is Flux or Argo CD on top.

### 6.5 Maintenance burden

**This is the heaviest of the five, and the reason is the treadmill, not the API churn.**

**Cadence:** "Kubernetes releases currently happen approximately three times per year", on a
~14-week cycle (11 weeks development, ~2 weeks code freeze)
([kubernetes.io/releases/release](https://kubernetes.io/releases/release/)).

**Support window:** ~14 months per minor — 12 months of standard support plus 2 months of
maintenance mode covering only "critical fixes, security patches, and dependency updates". Patch
releases are monthly. Currently supported, with EOL dates: 1.36 (EOL 2027-06-28), 1.35
(2027-02-28), 1.34 (2026-10-27), 1.33 (in maintenance mode, EOL 2026-06-28)
([patch-releases](https://kubernetes.io/releases/patch-releases/)).

Combined with the no-skip rule: **three minor upgrades per year, each of which must be performed
in sequence, forever, on a machine with a single operator.** That is the real cost, and it is
identical in kind (though not in tooling) for k3s and k0s.

**Breaking-change history is milder than folklore suggests.** The Deprecated API Migration Guide
lists, for the versions in scope, only `flowcontrol.apiserver.k8s.io/v1beta3` removed in v1.32
(migrate to `flowcontrol.apiserver.k8s.io/v1`, available since v1.29), with the note that
`spec.limited.nominalConcurrencyShares` "only defaults to 30 when unspecified; an explicit value
of 0 is not changed to 30". **No API removals are listed for v1.33 through v1.36**
([deprecation-guide](https://kubernetes.io/docs/reference/using-api/deprecation-guide/)). For a
homelab running ordinary Deployments and Services, the last two years of Kubernetes API churn
would have been a non-event.

**Certificates — the sharpest edge for a low-touch operator.** "Client certificates generated by
kubeadm expire after 1 year." Leaf certificates default to 365 days, CA certificates to 3650
days. Kubelet certificates auto-renew; **other component certificates do not**. Renewal happens
as a side effect of `kubeadm upgrade apply`, so a cluster upgraded regularly never notices — but
a cluster left alone for twelve months requires `kubeadm certs renew all` by hand, and
`kubeadm certs check-expiration` to see it coming
([kubeadm-certs](https://kubernetes.io/docs/tasks/administer-cluster/kubeadm/kubeadm-certs/)).
**A kubeadm cluster that is not touched for a year breaks itself.** k3s does not have this
failure mode (§5.5).

---

## 7. Cross-cutting: the pull-based reconciliation constraint

The repository is public and may never hold a kubeconfig or decryption key as a CI secret.
That eliminates push-from-CI and forces an in-network agent that pulls. What each option offers:

| Option | In-network pull reconciler | First-party? |
|---|---|---|
| Compose + Komodo | Yes — Core polls git-hosted TOML, diffs, alerts on pending changes ([sync-resources.md](https://github.com/moghtech/komodo/blob/main/docsite/docs/automate/sync-resources.md)) | Yes |
| Compose + Dockge | No git story at all ([README](https://github.com/louislam/dockge/blob/master/README.md)) | — |
| Nomad | Not established from primary sources | No |
| k0s / k3s / kubeadm | Yes — Flux, Argo CD | Ecosystem, not distro |

**Flux's own cost, since it lands on the same 32 GB.** A default bootstrap installs seven
controllers: source-controller, source-watcher, kustomize-controller, helm-controller,
notification-controller, image-reflector-controller, image-automation-controller
([fluxcd.io/flux/installation](https://fluxcd.io/flux/installation/)). Flux is explicitly
pull-based: "after running the bootstrap command, any operation on the cluster(s) (including
Flux upgrades) can be done via Git push."

Upstream manifests set per-controller resources of `requests: cpu 50m–100m, memory 64Mi` with
`limits: cpu 1000m, memory 1Gi`
([source-controller](https://github.com/fluxcd/source-controller/blob/main/config/manager/deployment.yaml),
[kustomize-controller](https://github.com/fluxcd/kustomize-controller/blob/main/config/manager/deployment.yaml)).
So the *scheduler-visible reservation* for a full Flux install is ≈ 448 Mi, with a theoretical
limit ceiling of 7 Gi. **Requests and limits are not measured idle usage** — the Flux docs do
not publish measured figures, and the vertical-scaling page only gives examples of scaling *up*
("limits: cpu: 2000m memory: 2Gi" for hundreds of applications)
([vertical-scaling](https://fluxcd.io/flux/installation/configuration/vertical-scaling/)).
Flux also notes tmpfs-based Kustomize builds "will count against the controller's pod memory
usage". Flux requires Kubernetes ≥ 1.33 for Flux v1.33, ≥ 1.35 for v1.35+.

The practical point: on the Kubernetes options, the GitOps layer is **an additional resident
cost that must be budgeted alongside the control plane**, and it is not included in any of the
k3s or k0s figures above. On the Komodo option, the GitOps layer *is* the manager and is already
counted.

---

## 8. What was not established from primary sources

Stated plainly, because these gaps should not be papered over with estimates:

1. **Idle memory for Docker Engine, Komodo Core, Komodo Periphery, or Dockge.** No figures
   published anywhere in their documentation. Only the Mongo/FerretDB requirement and the
   `--wiredTigerCacheSizeGB 0.25` default are pinnable.
2. **Idle memory for a Nomad server or client agent.** HashiCorp publishes production sizing
   recommendations only.
3. **Idle memory for a kubeadm control plane.** Kubernetes publishes minimums only; etcd
   publishes a recommendation for a 50-node cluster.
4. **k3s's formal support window / EOL policy.** `SECURITY.md` has no supported-versions table;
   the docs site has no support-window statement. Only observable release behaviour.
5. **A consolidated k0s breaking-change record.** No `upgrade-specific` equivalent exists.
6. **Whether k0s auto-renews leaf certificates before expiry.** Only the configurable
   expiry durations are documented.
7. **Whether Nomad can share one GPU between multiple allocations.** The NVIDIA device plugin
   page does not address it — directly relevant to an 8 GB RTX 3070 Ti serving multiple
   containers.
8. **A first-party pull-based git reconciler for Nomad.** None found.

Additionally, the k3s resource-profiling page **contradicts itself** about whether its memory
figures include the test workload (§5.1). Both readings are quoted above; the measurement
methodology favours the "whole host, monitoring stack included" reading.

---

## 9. What the evidence supports

No decision is made here. What follows is the trade-off surface, with **what each option gives
up** named explicitly.

### The three constraints that discriminate hardest

1. **32 GB is a hard ceiling, and the control plane is not the biggest threat to it.** The
   measured control-plane numbers that exist are modest: 510 MB (k0s controller, v1.22 era),
   275 MB (k3s agent). Even k3s's contested 1596 M whole-host figure is 5% of the budget. The
   things that actually eat the ceiling are *defaults chosen by dependencies* — a MongoDB left
   at its default WiredTiger cache would claim ≈ 15.5 GB on this machine. **Memory is a real
   constraint, but the primary sources do not support "Kubernetes is too heavy for 32 GB".**
2. **"Add one cheap mini-PC at a time" is an arithmetic trap for every quorum-based option.**
   Nomad, k3s embedded etcd, kubeadm and Docker Swarm all use Raft or etcd; in all four, two
   control-plane members is *strictly worse* than one, and the benefit only arrives at three.
   Since HA is explicitly not wanted, the only coherent path is: **one control plane forever,
   additional machines join as workers/agents/clients.** Every option supports this; they differ
   in how cheap the worker join is.
3. **No CI secret means the reconciler lives inside the network.** This is a hard filter. It
   eliminates Dockge outright and makes Nomad a build-it-yourself proposition.

### Option by option — what you give up

**Docker Compose + Komodo.** You give up scheduling. There is no scheduler, so the GPU cannot be
a "schedulable platform resource" in any real sense — you pin GPU workloads to the GPU host by
hand, forever, and the second machine is a second inventory item rather than more capacity in a
pool. You give up a stated support window and any LTS (no published policy; GPL-3.0 "no
warranties"). You take on a MongoDB or FerretDB+Postgres dependency that no other option
requires, and with it the memory-default hazard above. You give up automatic sync execution
unless you expose a webhook inbound. In exchange you get the lowest conceptual overhead, the
smallest plausible footprint, no Kubernetes upgrade treadmill, and a first-party git-poll loop
that fits the no-CI-secret rule exactly.

**Docker Compose + Dockge.** On the evidence, this does not meet the stated requirements: no git
integration exists in its documented feature set, so the "purely a versioned declaration in a
repo" property is absent. Separately, the release/commit split (last tag 2025-03-30; XSS fix
committed 2026-04-19 and untagged) means a tag-pinned deployment is knowingly behind a security
fix. What you would give up is the entire declarative-change requirement.

**HashiCorp Nomad.** You give up open source (BUSL-1.1, licensor IBM, four-year change date to
MPL 2.0) and you accept IBM's V.M.F lifecycle with a 2-year CE backport and LTS positioned as an
enterprise concern. You give up a ready-made GitOps loop — you would build and maintain the
pull-reconciler yourself, which for a single operator is a second system to own. You give up
certainty on GPU sharing (undocumented). You accept the heaviest documented breaking-change
record of the five: HCLv1 removal, Vault/Consul token auth removal, remote task drivers removed,
`retry_join` deprecated, client-version floor raised — all within two years. In exchange you get
the genuinely simplest architecture — one self-contained binary, "requires no external services
for coordination or storage" — no CNI, no etcd to operate, no kubelet, and the freest hand with
non-container workloads.

**k0s.** You give up nothing structural relative to k3s, but you must get two decisions right at
install time or pay for them with a rebuild: `--single` permanently forecloses adding the mini-PCs
(use `--enable-worker --no-taints`), and the CNI provider "the only way to change providers is
through a full cluster redeployment". You give up k3s's documented automatic certificate renewal
— or rather, you give up *knowing* whether you have it, since it is undocumented. You give up
freshness in the published memory data (v1.22.4, controller-only). In exchange you get the
lowest measured control-plane memory figure of any option, an **explicitly stated 14-month
support window mirroring upstream**, four minor lines patched in parallel, and a two-command
worker join.

**k3s.** You give up datastore continuity if you ever do want a second server — SQLite cannot
serve multiple servers, though the `--cluster-init` conversion is documented and cheap. You give
up a stated support commitment: k3s's `SECURITY.md` has no supported-versions table and the docs
publish no EOL policy, so the 14-month assumption is inference from release behaviour, not a
promise (k0s does promise it). You give up clean data: the headline 1596 M figure is contaminated
by a monitoring stack, and the page contradicts itself about that. You should validate the
embedded-etcd disk requirement (50 IOPS, <5 ms latency) against DRAM-less NV2 drives before
choosing etcd over SQLite. In exchange you get the cheapest possible second node (one curl
command, no datastore change), the only documented **automatic certificate renewal** of the five
— which for a single operator on a 24/7 box removes a scheduled self-inflicted outage — and the
most detailed published resource data even with its flaws.

**Full upstream Kubernetes (kubeadm).** You give up the certificate safety net: client certs
expire after one year and only renew as a side effect of an upgrade, so **a kubeadm cluster left
untouched for twelve months breaks itself**. You give up batching upgrades: `kube-apiserver`
"must not skip minor versions when upgrading, even in single-instance clusters", against a
three-releases-a-year cadence and a 14-month window — roughly three sequential upgrades per year,
forever, with one operator. You give up the packaged batteries (CNI, ingress, storage class, load
balancer) that k3s and k0s bundle, and must select and maintain each. You take on operating etcd
directly, whose own guidance asks for 8 GB and <5 ms fsync latency. In exchange you get the
reference implementation with no distribution-specific surprises, the most portable knowledge,
and the mildest API-breakage record of all — no API removals at all in v1.33–v1.36.

### One finding that cuts against a common assumption

The Kubernetes API-churn fear is not supported by the primary sources for the period in question:
the Deprecated API Migration Guide lists **one** removal across v1.32–v1.36, and none at all in
the last three minors. The Kubernetes maintenance burden is real, but it is the **upgrade
treadmill and the certificate clock**, not applications breaking on API changes. Meanwhile the
option with by far the heaviest documented removal record over the same two years is **Nomad**.
