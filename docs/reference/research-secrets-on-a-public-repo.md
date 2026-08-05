# Secrets management for a public GitOps repository, operated by one person

**Researched:** 2026-08-05
**Status:** Reference. No decision is made here.

## Question

For a repository that is public, is the GitOps source of truth, and is operated
by a single person on one 24/7 machine with a 32 GB RAM ceiling and no budget,
how do these three approaches compare?

- **SOPS + age**
- **Sealed Secrets** (Bitnami)
- **External Secrets Operator** (ESO) backed by a self-hosted vault

The comparison is scoped to the three things that actually cost a solo operator
time: bootstrap, rotation, and recovery after key loss. Secondary axes:
resident memory, whether Kubernetes is required at all (the orchestrator is not
yet chosen), and maintenance status.

## Method and source rules

Only primary sources: official documentation, official release notes, upstream
GitHub issues with maintainer replies, project source code, project security
docs, and the GitHub API for release and archive status. No blogs, no
aggregators, no forums. Where a fact could not be established from a primary
source, this document says so rather than filling the gap.

Release and archive status were read from the GitHub API on 2026-08-05.

---

## 1. Identity and maintenance status

### SOPS

- Repository [`getsops/sops`](https://github.com/getsops/sops). Not archived;
  last push 2026-08-03 (GitHub API).
- Latest release **v3.13.3, 2026-07-23**
  ([releases](https://github.com/getsops/sops/releases/tag/v3.13.3)).
- Licence MPL 2.0. The README states SOPS "was initially launched as a project
  at Mozilla in 2015 and has been graciously donated to the CNCF as a Sandbox
  project in 2023, now under the stewardship of a new group of maintainers"
  ([README.rst](https://github.com/getsops/sops/blob/main/README.rst)).
- CNCF lists **SOPS (accepted to CNCF on 5/17/2023)** under Security &
  Compliance ([CNCF Sandbox projects](https://www.cncf.io/sandbox-projects/)).

### age

- Repository [`FiloSottile/age`](https://github.com/FiloSottile/age). Not
  archived; last push 2026-03-20 (GitHub API).
- Latest release **v1.3.1, 2025-12-28**
  ([releases](https://github.com/FiloSottile/age/releases)).
- Slower cadence than SOPS, but age is a small, finished-by-design tool: "small
  explicit keys, no config options"
  ([README](https://github.com/FiloSottile/age/blob/main/README.md)).

### Sealed Secrets — checked carefully, as instructed

- The repository has **moved organisation**. `bitnami-labs/sealed-secrets` now
  resolves to [`bitnami/sealed-secrets`](https://github.com/bitnami/sealed-secrets)
  (the GitHub API returns `"full_name": "bitnami/sealed-secrets"` for the old
  path). Old links still redirect.
- **Not archived, not in maintenance mode.** Last push 2026-08-04. Releases are
  roughly monthly: v0.38.4 (2026-07-03), v0.38.3, v0.38.2, helm-v2.19.1,
  v0.38.1 and v0.38.0 (2026-06-18), v0.37.0 (2026-05-21), v0.36.6 (2026-04-09)
  ([releases](https://github.com/bitnami/sealed-secrets/releases)).
- **On its future:** the concern is real and upstream addressed it directly.
  Bitnami announced that from 2025-08-28 the public `docker.io/bitnami` catalog
  would be gutted, with versioned tags moved to `docker.io/bitnamilegacy` and
  no further updates
  ([bitnami/charts#35164](https://github.com/bitnami/charts/issues/35164)).
  That same announcement carries the carve-out:

  > Sealed Secrets and minideb remain unaffected by these changes. Container
  > images for both projects will continue to be released on docker.io/bitnami
  > as usual without any modifications.

  The maintainers restated it in
  [#1785](https://github.com/bitnami/sealed-secrets/issues/1785): "Sealed
  Secrets operations remain completely unaffected by Bitnami's recent Docker Hub
  policy changes… Sealed Secrets controller images and Helm Charts are built and
  distributed independently from the general Bitnami container catalog. The
  project maintains its own release cycle and image distribution strategy." A
  maintainer confirmed again in
  [#1790](https://github.com/bitnami/sealed-secrets/issues/1790) and
  [#1773](https://github.com/bitnami/sealed-secrets/issues/1773).
- Corroborating evidence that the carve-out still holds a year later: the chart
  shipped with v0.38.4 still pins a **versioned** tag in the main catalog —
  `registry: docker.io`, `repository: bitnami/sealed-secrets-controller`,
  `tag: 0.38.4`
  ([values.yaml](https://github.com/bitnami/sealed-secrets/blob/main/helm/sealed-secrets/values.yaml)).
  Under the general policy that tag would not exist.
- **Governance is single-vendor.** All three listed maintainers are affiliated
  to VMware (now Broadcom)
  ([MAINTAINERS.md](https://github.com/bitnami/sealed-secrets/blob/main/MAINTAINERS.md)),
  and the security contact is `sealed-secrets.pdl@broadcom.com`
  ([SECURITY.md](https://github.com/bitnami/sealed-secrets/blob/main/SECURITY.md)).
  Sealed Secrets is **not** a CNCF project — it does not appear in the CNCF
  Sandbox, Incubating or Graduated listings
  ([CNCF](https://www.cncf.io/projects/), [Sandbox](https://www.cncf.io/sandbox-projects/)).
  The project is healthy today; the structural risk is that its continuation is
  one company's decision, and that company has just demonstrated willingness to
  withdraw free distribution of adjacent artefacts.

### External Secrets Operator

- Repository
  [`external-secrets/external-secrets`](https://github.com/external-secrets/external-secrets).
  Not archived; last push 2026-08-05.
- Latest release **v2.8.0, 2026-07-18** (chart `helm-chart-2.8.0`, same day).
- CNCF lists **external-secrets (accepted to CNCF on 7/26/2022)** under Security
  & Compliance ([CNCF Sandbox projects](https://www.cncf.io/sandbox-projects/)).
  Security reports go to `cncf-ExternalSecretsOp-maintainers@lists.cncf.io`
  ([SECURITY.md](https://github.com/external-secrets/external-secrets/blob/main/SECURITY.md)).
- **Support policy is narrow.** Only the current minor version is supported; the
  previous minor reaches end of life the moment the next one ships
  ([stability and support](https://external-secrets.io/latest/introduction/stability-support/)).
  Minors ship roughly monthly (v2.3.0 April, v2.4.0 April, v2.5.0 May, v2.6.0
  June, v2.7.0 June, v2.8.0 July 2026). For a solo operator this is a **monthly
  forced-upgrade treadmill** on a security-critical component.
- **Provider stability matters here.** On the same page: HashiCorp Vault is
  **Stable** (maintained by external-secrets); **Infisical is Alpha**
  (maintained by a single individual, @akhilmhdh); **Bitwarden Secrets Manager
  is Alpha** (maintained by a single individual, @skarlso). Two of the three
  vaults named in the question are Alpha-tier providers with a bus factor of one.

---

## 2. Bootstrap — how the first secret reaches the cluster

### SOPS + age

The private key must exist somewhere before anything can decrypt. There is no
way around this; the question is only how many times you do it by hand.

With Flux, the documented sequence is
([Flux SOPS guide](https://fluxcd.io/flux/guides/mozilla-sops/)):

```sh
age-keygen -o age.agekey
# Public key: age1helqcqsh9464r8chnwc2fzj8uv7vr5ntnsft0tn45v2xtz0hpfwq98cmsg

cat age.agekey |
kubectl create secret generic sops-age \
  --namespace=flux-system \
  --from-file=age.agekey=/dev/stdin
```

The key filename must end in `.agekey` to be detected. Then the Kustomization
points at it:

```yaml
spec:
  decryption:
    provider: sops
    secretRef:
      name: sops-age
```

The Secret must live in the same namespace as the Kustomization, and age private
keys are recognised by the `.agekey` suffix on the `.data` entry
([kustomize-controller decryption](https://fluxcd.io/flux/components/kustomize/kustomizations/#decryption)).
Decryption is built into kustomize-controller — "The only supported encryption
provider is SOPS" — so there is no extra pod.

**Chicken-and-egg cost: exactly one out-of-band `kubectl create secret`, once.**
Everything downstream is then reconciled from git.

Outside Kubernetes there is no chicken-and-egg at all: SOPS reads the identity
from `SOPS_AGE_KEY`, `SOPS_AGE_KEY_FILE`, `SOPS_AGE_KEY_CMD`, or by default from
`$XDG_CONFIG_HOME/sops/age/keys.txt` (`$HOME/.config/sops/age/keys.txt` on
Linux) ([age identities](https://getsops.io/docs/usage/identities/age/)), and
feeds any process directly via `sops exec-env` / `sops exec-file`
([advanced usage](https://getsops.io/docs/usage/advanced/)).

### Sealed Secrets

**This is the one option with no bootstrap secret at all.** The controller
manufactures its own key material on first start. From the README
([Sealed Secrets README](https://github.com/bitnami/sealed-secrets/blob/main/README.md)):

> The controller maintains a set of private/public key pairs as kubernetes
> secrets. Keys are labeled with `sealedsecrets.bitnami.com/sealed-secrets-key`
> and identified in the label as either `active` or `compromised`. On startup,
> The sealed secrets controller will…
> 1. Search for these keys and add them to its local store if they are labeled as active.
> 2. Create a new key
> 3. Start the key rotation cycle

The sequence is therefore: install the controller → it generates a key → you
retrieve the *public* certificate → you seal secrets offline and commit them.
Retrieving the certificate is the only interactive step, and what you retrieve
is not secret:

> `kubeseal` will fetch the certificate from the controller at runtime (requires
> secure access to the Kubernetes API server), which is convenient for
> interactive use, but it's known to be brittle when users have clusters with
> special configurations…

with the offline alternative `kubeseal --fetch-cert >mycert.pem` then
`kubeseal --cert mycert.pem`; `kubeseal` also accepts an HTTPS URL and the
`SEALED_SECRETS_CERT` environment variable, and "The certificate is also printed
to the controller log on startup."

**Chicken-and-egg cost: none.** No private material ever has to be injected.

### External Secrets Operator

ESO does not eliminate the chicken-and-egg; it **relocates it** and adds a
second system that must already be up.

The operator installs without credentials
([getting started](https://external-secrets.io/latest/introduction/getting-started/)),
but a `SecretStore` needs an authentication credential, and for the vaults in
question that credential is a pre-existing Kubernetes Secret:

- **Infisical** — the docs say plainly "Create a Kubernetes secret containing
  your Universal Auth credentials", then the store references it via
  `auth.universalAuthCredentials.clientId` / `.clientSecret`
  ([Infisical provider](https://external-secrets.io/latest/provider/infisical/)).
- **Bitwarden Secrets Manager** — `auth.secretRef.credentials` pointing at a
  Secret holding the machine-account access token
  ([Bitwarden provider](https://external-secrets.io/latest/provider/bitwarden-secrets-manager/)).
- **HashiCorp Vault** — token, AppRole secret-id, LDAP, UserPass, JWT/OIDC and
  static AWS credentials all reference a Secret (`tokenSecretRef`, `secretRef`,
  …). Only **Kubernetes auth** (`serviceAccountRef` / the mounted service
  account token) and cloud pod-identity avoid a pre-existing Secret
  ([Vault provider](https://external-secrets.io/latest/provider/hashicorp-vault/)).

So the best case (Vault + Kubernetes auth) removes the stored credential, but
only by requiring that Vault is already running, already initialised, already
unsealed, and already configured to trust the cluster's service account issuer.
Which brings the real bootstrap cost:

> "When you start a Vault server, it starts in a sealed state. In this state,
> Vault can access the physical storage, but it cannot decrypt any of the data
> on it." … "Once you unseal a Vault node, it remains unsealed until one of the
> following happens: 1. You reseal it using the API. 2. You restart the server.
> 3. Vault's storage layer encounters an unrecoverable error."
> ([Vault seal concepts](https://developer.hashicorp.com/vault/docs/concepts/seal))

`vault operator init` defaults are `-key-shares (int: 5)` and
`-key-threshold (int: 3)`
([operator init](https://developer.hashicorp.com/vault/docs/commands/operator/init)).
Auto-unseal "delegates the responsibility of securing the unseal key from users
to a trusted device or service" — i.e. it requires yet another trusted service.

**Chicken-and-egg cost: a credential Secret injected out of band (same as SOPS),
plus a whole vault that must be reachable and unsealed before the first secret
resolves.** On a single machine that reboots, "unsealed" is a recurring manual
event unless auto-unseal is built.

#### One decisive finding on the "free Bitwarden" path

Vaultwarden is the obvious zero-budget stand-in for Bitwarden. **It will not
work with ESO.** ESO's provider targets Bitwarden *Secrets Manager*, and the
Vaultwarden maintainer closed the request to implement it
([vaultwarden#3793](https://github.com/dani-garcia/vaultwarden/issues/3793),
BlackDex, 2023-08-25):

> Will not happen unless it's moved out-off the licensed bitwarden directory.
> Closing this as not going to happen.

Separately, the ESO Bitwarden provider requires deploying an **additional**
in-cluster service, `bitwarden-sdk-server`, because "the bitnami Rust SDK
libraries are over 150MB in size", and that service "_NEEDS_ to run as an HTTPS
service", ideally with cert-manager
([Bitwarden provider](https://external-secrets.io/latest/provider/bitwarden-secrets-manager/)).
So the Bitwarden path means: a paid/hosted Bitwarden Secrets Manager account, an
extra pod, and cert-manager.

---

## 3. Rotation

### Rotating the key that encrypts everything

| | Cost | Whole-tree re-encryption? |
|---|---|---|
| SOPS + age | manual, per file | **Yes** |
| Sealed Secrets | automatic, every 30 days | **No** |
| ESO | n/a — nothing in git is encrypted | **No** |

**SOPS.** `sops rotate` "reencrypt[s] the file with a new data key, which is
then encrypted with the various KMS and PGP master keys defined in the file";
`sops updatekeys` applies the key list from `.sops.yaml` *without* rotating the
data key. The docs are explicit that removing a key is not enough on its own:

> When removing keys, it is recommended to rotate the data key using `-r`,
> otherwise, owners of the removed key may have add access to the data key in
> the past.

(quoted verbatim; "may have add access" is a typo in the upstream page)

and prescribe the order for a compromised key:

```sh
sops updatekeys secret.sops.yaml
sops rotate --in-place secret.sops.yaml
```

([key management](https://getsops.io/docs/usage/key-management/)). Both commands
are **per file**. Rotating the age key therefore means iterating over every
encrypted file in the tree and producing one commit that touches all of them.
Note that `.sops.yaml` supports `key_groups` and `shamir_threshold`, so a file
can be encrypted to several identities at once with an N-of-M threshold
([key groups](https://getsops.io/docs/usage/identities/key-groups/)).

**Sealed Secrets.** Renewal is automatic and requires no re-encryption:

> Sealing keys are automatically renewed every 30 days. Which means a new sealing
> key is created and appended to the set of active sealing keys the controller
> can use to unseal `SealedSecret` resources.

> …old `SealedSecret` resources can be still decrypted (that's because old
> sealing keys are not deleted).

Tunable with `--key-renew-period` (`0` disables it). Early renewal on suspected
compromise is `--key-cutoff-time` / `SEALED_SECRETS_KEY_CUTOFF_TIME` in RFC1123
format. Re-encryption is only needed to *retire* old keys, and it is manual and
git-visible:

```sh
kubeseal --re-encrypt <my_sealed_secret.json >tmp.json
```

> …in your version control system (`kubeseal --re-encrypt` doesn't update the
> in-cluster object).

Upstream is emphatic that none of this rotates the actual secret values:

> SealedSecret key renewal and re-encryption features are **not a substitute**
> for periodical rotation of your actual secret values.

> …re-encryption is not a substitute for periodically rotating your actual
> secrets.

(all from the [README](https://github.com/bitnami/sealed-secrets/blob/main/README.md)).

**ESO.** There is no encryption key in the repository, so this row is empty by
construction. The equivalent operation is rotating the *bootstrap credential*,
which means replacing one Kubernetes Secret. How the backing vault rotates its
own root/encryption key is a vault concern and is **not established from ESO's
primary sources** — ESO does not document it, correctly, as it is out of scope.

### Rotating a single secret

- **SOPS** — re-encrypt one file. One small, reviewable diff. The value's
  ciphertext changes, the surrounding structure does not.
- **Sealed Secrets** — re-run `kubeseal` with the current public certificate,
  commit the changed `SealedSecret`. Also one small diff. Requires having the
  current certificate to hand (it renews every 30 days; the README advises "you
  and your team update your offline certificate periodically").
- **ESO** — change the value in the vault. **No commit at all.** The controller
  re-reads at `spec.refreshInterval`; "RefreshInterval is the amount of time
  before the values reading again from the SecretStore provider", and setting it
  to zero means the Secret is created once and never updated
  ([ExternalSecret API](https://external-secrets.io/latest/api/externalsecret/)).

This is the axis where ESO wins outright, and it is not close.

---

## 4. Recovery after key loss, and key backup

This is the failure mode the question is most concerned with. All three answers
are, at bottom, "you cannot recover; you can only have made a backup".

### Sealed Secrets — the only project with an explicit, documented answer

The README FAQ asks the exact question and answers it without hedging:

> **Will you still be able to decrypt if you no longer have access to your cluster?**
>
> No, the private keys are only stored in the Secret managed by the controller
> (unless you have some other backup of your k8s objects). There are no
> backdoors - without that private key used to encrypt a given SealedSecrets,
> you can't decrypt it. If you can't get to the Secrets with the encryption
> keys, and you also can't get to the decrypted versions of your Secrets live in
> the cluster, then you will need to regenerate new passwords for everything,
> seal them again with a new sealing key, etc.

Backup is documented, with a warning that matters enormously for a solo operator:

```sh
kubectl get secret -n kube-system -l sealedsecrets.bitnami.com/sealed-secrets-key -o yaml >main.key
```

> NOTE: This file will contain the controller's public + private keys and should
> be kept omg-safe!

> NOTE: **After sealing key renewal you should recreate your backup.** Otherwise,
> your backup won't be able to decrypt new sealed secrets.

Because renewal is automatic every 30 days, **the backup silently goes stale on
a 30-day cycle**. A backup taken once and filed away will not decrypt secrets
sealed after the next renewal. This is the single most under-appreciated
operational trap in the Sealed Secrets model for a one-person operation.

Restore is documented (`kubectl apply -f main.key`, then delete the controller
pod so it reloads), and offline decryption from a backup key is supported:

```sh
kubeseal --recovery-unseal --recovery-private-key file1.key,file2.key,...
```

though upstream frames it as an exception: "treating sealed-secrets as long term
storage system for secrets is not the recommended use case".

### SOPS + age — no documented recovery, thin documented backup

- The **age README documents nothing** about key loss, backup, escrow or
  recovery ([age README](https://github.com/FiloSottile/age/blob/main/README.md)).
  There is no recovery mechanism; that is a design position, not an omission.
- The **SOPS security page** covers the threat model (compromised AWS
  credentials, compromised PGP keys, factorised RSA keys, weaknesses in
  AES256-GCM) but contains **no key rotation or recovery section**
  ([SOPS security](https://getsops.io/docs/security/)).
- The only backup guidance found in a primary source is a single sentence in the
  Flux guide: "It's a good idea to back up this secret-key/K8s-Secret with a
  password manager or offline storage."
  ([Flux SOPS guide](https://fluxcd.io/flux/guides/mozilla-sops/)) — and that
  guide also suggests deleting the private key from the workstation afterwards
  (`gpg --delete-secret-keys`, in the GPG variant).

**"Not established from primary sources": SOPS documents no recovery procedure
for a lost age identity.** What it *does* document is a structural mitigation
that is stronger than a procedure — encrypt every file to more than one
recipient, or use `key_groups` with `shamir_threshold`, so that losing one
identity is survivable
([key groups](https://getsops.io/docs/usage/identities/key-groups/)). This has
to be decided *before* the first secret is encrypted, or retrofitted with a
tree-wide `updatekeys` pass.

### ESO — the loss moves, it does not disappear

Nothing in the repository is encrypted, so there is no key whose loss bricks the
repository. The exposure relocates entirely into the vault: lose the vault and
you lose every secret value, because git never held them. For Vault
specifically, recovering the vault itself requires the unseal or recovery key
shares (default 3 of 5), which are themselves material a solo operator must back
up offline
([seal concepts](https://developer.hashicorp.com/vault/docs/concepts/seal),
[operator init](https://developer.hashicorp.com/vault/docs/commands/operator/init)).

**"Not established from primary sources": ESO documents nothing about backing up
or recovering the backing store** — it is out of scope for the operator, and the
burden lands on whichever vault is chosen.

---

## 5. Resident memory of in-cluster components

| Component | Official figure | Best primary evidence |
|---|---|---|
| SOPS decryption (with Flux) | — | **No component.** Built into kustomize-controller |
| SOPS CLI (no orchestrator) | — | **No resident process** |
| Sealed Secrets controller | **None published** | order of tens of MB; ~60 MB safe |
| ESO (3 pods) | **None published** | chart comment suggests 32Mi for the controller |
| HashiCorp Vault | **8–16 GB RAM** ("small") | official reference architecture |
| Infisical self-hosted | **4 GB RAM** minimum | official, includes Postgres + Redis |

**SOPS.** Nothing runs. Decryption is a feature of the GitOps controller you
already run ("The only supported encryption provider is SOPS",
[kustomize-controller](https://fluxcd.io/flux/components/kustomize/kustomizations/#decryption)).
Marginal resident cost: zero.

**Sealed Secrets.** The chart ships **no defaults** — `resources: { limits: {},
requests: {} }`
([values.yaml](https://github.com/bitnami/sealed-secrets/blob/main/helm/sealed-secrets/values.yaml)).
No official sizing exists. The only primary data is upstream issue
[#1289](https://github.com/bitnami/sealed-secrets/issues/1289), open since
2023-08-15: memory went "from ~7mb to ~50+ mb" at v0.19.1; the reporter ran
"controllers with 20MB limits/requests… new version went to OOMKilled and only
runs now with at least 60MB or more". A maintainer attributed it to the Secret
informer added to re-create manually deleted secrets. A 2024 follow-up on the
same issue: "up to ~10x higher memory usage is still there, but now possible to
mitigate by `skipRecreate: true`". That switch is exposed by the chart as
`skipRecreate` (default `false`), documented as skipping "recreating removed
secrets". So roughly 60 MB by default, roughly 10x less if you accept that the
controller will not re-create a Secret someone deletes by hand.

**ESO.** Three deployments by default — core controller, webhook, cert
controller — each `replicaCount: 1`
([values.yaml](https://github.com/external-secrets/external-secrets/blob/main/deploy/charts/external-secrets/values.yaml)).
`resources: {}` with a commented-out suggestion of `cpu: 10m` / `memory: 32Mi`
for the controller. The docs describe the webhook and cert-controller as
"optional but highly recommended" and give the switches to remove them —
`certController.create=false`, `webhook.create=false`,
`crds.conversion.enabled=false`
([components](https://external-secrets.io/latest/api/components/)) — with the
chart warning that disabling the webhook without also disabling conversion
means "the kubeapi will be hammered". **No official memory figure is published
for any of the three.**

**The backing vault dominates the budget.** On a 32 GB machine:

- HashiCorp Vault's own reference architecture puts a "small" cluster at
  **2–4 cores and 8–16 GB RAM per server**, large at 4–8 cores and 32–64 GB
  ([Vault reference architecture](https://developer.hashicorp.com/vault/tutorials/day-one-raft/raft-reference-architecture)).
  That is 25–50% of the machine for the secrets store alone.
- Infisical self-hosted states a minimum of **2 cores, 4 GB RAM, 20 GB disk**,
  and notes those "requirements include resources for Infisical, PostgreSQL, and
  Redis containers"; the Docker Compose path is "not designed for
  high-availability production scenarios"
  ([Infisical Docker Compose](https://infisical.com/docs/self-hosting/deployment-options/docker-compose)).
- Vaultwarden's own README gives **no memory figure**, and in any case cannot
  serve ESO (see §2).

---

## 6. Does it require Kubernetes?

The orchestrator is not yet chosen, so this is a live constraint, not a detail.

- **SOPS + age — no.** It is a file-level CLI. It has a Kubernetes integration
  (Flux) but no dependency on one. `sops exec-env out.json 'sh'` and
  `sops exec-file out.json 'cat {}'` hand decrypted material to any process,
  with `--user` to drop privileges first
  ([advanced usage](https://getsops.io/docs/usage/advanced/)). It works
  identically under Docker Compose, systemd, Nomad, or a shell script.
  **Choosing SOPS does not constrain the orchestrator decision.**
- **Sealed Secrets — yes, mandatory.** It is a CRD plus an in-cluster
  controller, and the entire security property depends on that controller: "the
  SealedSecret can be decrypted only by the controller running in the target
  cluster and nobody else (not even the original author)"
  ([README](https://github.com/bitnami/sealed-secrets/blob/main/README.md)).
- **ESO — yes, mandatory.** It is a Kubernetes operator; minimum supported
  Kubernetes is 1.16.0
  ([getting started](https://external-secrets.io/latest/introduction/getting-started/)).

**Choosing Sealed Secrets or ESO now silently decides the orchestrator
question.**

---

## 7. What a hostile full read of the public repository actually sees

Distinct from the three axes, but decisive given the repository's threat model.

**SOPS.** The security documentation is explicit that structure is not hidden:
"in YAML, JSON, ENV, and INI modes, keys are stored in cleartext, and values are
encrypted" ([SOPS security](https://getsops.io/docs/security/)) — a deliberate
choice so that diffs stay meaningful. The `sops` metadata block is also
cleartext and carries the recipient identifiers, as seen in a real encrypted
fixture in the SOPS repository
([functional-tests/res/comments.enc.yaml](https://github.com/getsops/sops/blob/main/functional-tests/res/comments.enc.yaml)):
`lastmodified`, `mac` (itself encrypted), `version`, and per-backend recipient
lists (`age: []`, `pgp: [{fp: FBC7B9E2A4F9289AC0C1D4843D16CEE4A27381B4, …}]`).
With Flux's recommended
`--encrypted-regex '^(data|stringData)$'`, only the Secret payload is encrypted;
`metadata.name`, `metadata.namespace`, labels and annotations all stay readable
([Flux SOPS guide](https://fluxcd.io/flux/guides/mozilla-sops/)). A reader
learns your key names, your manifest structure, and your age public key or PGP
fingerprint. None of that is secret material, but it is inventory.

**Sealed Secrets.** A `SealedSecret` exposes `metadata.name`,
`metadata.namespace` and the *names* of `encryptedData` entries; values are
opaque ciphertext
([README](https://github.com/bitnami/sealed-secrets/blob/main/README.md)).
Comparable inventory exposure to SOPS. One extra property in its favour: in the
default `strict` scope, name and namespace "become *part of the encrypted data*
and thus changing name and/or namespace would lead to 'decryption error'", so a
`SealedSecret` copied out of the repo cannot be replayed into another namespace.

**ESO.** Git holds only `ExternalSecret` and `SecretStore` manifests — no
ciphertext at all, which is the least secret-material exposure of the three.
But the `SecretStore` publishes the vault's address. The provider examples show
it inline: `spec.provider.vault.server: "http://my.vault.server:8200"`
([Vault provider](https://external-secrets.io/latest/provider/hashicorp-vault/)).
For a self-hosted vault that value is a private endpoint, which runs directly
against the "no exploitable network topology in the repository, ever, including
history" constraint — unless it is deliberately kept out of git, which
reintroduces a piece of untracked, hand-managed state.

**CI constraint.** None of the three requires a credential in GitHub Actions to
*validate*: SOPS files can be checked for the presence of the `sops` metadata
block and for absence of plaintext without any key; `kubeseal` validation needs
only the public certificate, which the README describes as "not secret
information"; ESO manifests are plain YAML. The "GitHub Actions validates, it
never deploys" rule is compatible with all three.

---

## 8. Not established from primary sources

Stated explicitly rather than guessed:

1. **No official resident-memory figure exists for the Sealed Secrets
   controller.** Both the chart and the docs ship empty `resources`. The only
   numbers come from an open upstream issue.
2. **No official resident-memory figure exists for any ESO component.** The
   chart's commented `cpu: 10m / memory: 32Mi` is a suggestion in a comment, not
   a published requirement, and covers only the controller.
3. **SOPS documents no recovery procedure for a lost age identity.** Neither the
   SOPS security page nor the age README addresses key loss, backup or escrow.
   The only backup advice found is one sentence in Flux's guide.
4. **ESO documents nothing about what happens when the backing vault is
   unreachable** — no statement about whether previously-synced Secrets persist,
   no retry or fallback behaviour, in the `ExternalSecret` API reference.
5. **ESO documents nothing about backing up or recovering the backing store.**
   Out of scope for the operator by design; the burden is entirely on the vault.
6. **Infisical's licensing for self-hosted use was not established.** The
   repository's licence resolves to `NOASSERTION` via the GitHub API, and the
   self-hosting pages consulted carry no licensing statement.
7. **The precise date and rationale of the `bitnami-labs` → `bitnami`
   organisation move for Sealed Secrets was not found** in release notes or an
   upstream announcement; only the resulting redirect is observable via the API.

---

## What the evidence supports

Not a decision. The trade-offs, and what each choice gives up.

### SOPS + age

**What the evidence supports.** It is the only option that does not require
Kubernetes, so it is the only one that leaves the orchestrator question open. It
has zero resident memory cost. Bootstrap is one manual step, once. Single-secret
rotation is a one-file diff. It is CNCF-governed with a multi-vendor maintainer
group and a current release. Its recovery story is weak on documentation but
strong on mechanism: multi-recipient encryption and `key_groups` /
`shamir_threshold` make key loss survivable *if configured before the first
secret is encrypted*.

**What you give up.**
- **Rotating the age key is a tree-wide operation.** `updatekeys` and `rotate`
  are per-file; rotating means touching every encrypted file and producing one
  enormous commit. This is the cost that grows with the repository.
- **Ciphertext lives in the public repository forever, including in history.** A
  future break in age or in your key means every secret ever committed is
  retroactively exposed. Neither Sealed Secrets nor ESO fully avoids this, but
  ESO does.
- **No documented recovery procedure.** You are relying on your own discipline
  to have set up a second recipient and to have stored the identity offline.
- **Key names and structure are cleartext by design.** You publish an inventory
  of what secrets exist.

### Sealed Secrets

**What the evidence supports.** Uniquely, **nothing has to be injected to
bootstrap** — the controller mints its own key and you only ever handle a public
certificate. Key renewal is automatic every 30 days and requires no
re-encryption, because old keys are retained. Recovery is the best-documented of
the three, including offline decryption via `--recovery-unseal`. The project is
actively released (v0.38.4, July 2026), is not archived, and is explicitly
carved out of Bitnami's Docker Hub catalog deletion in three separate upstream
statements.

**What you give up.**
- **Kubernetes becomes mandatory**, which retroactively decides an architecture
  question that is currently open.
- **Your backup goes stale every 30 days.** Upstream says it directly: after
  renewal, "your backup won't be able to decrypt new sealed secrets." A solo
  operator must therefore automate backup capture, or disable renewal
  (`--key-renew-period=0`) and give up the property that makes renewal valuable.
- **Single-vendor governance.** Three maintainers, all Broadcom-affiliated, not a
  CNCF project. It is healthy today, but its continuation is one company's
  decision — and that company has just demonstrated it will withdraw free
  distribution of adjacent artefacts on short notice.
- **Ciphertext in public history**, same as SOPS.
- **Roughly 60 MB resident** by default, with no official figure to plan against
  — reducible ~10x via `skipRecreate: true` at the cost of self-healing deleted
  Secrets.

### External Secrets Operator + self-hosted vault

**What the evidence supports.** It is the only option where **no secret material
ever enters the repository**, so the public-history exposure problem disappears
entirely. Single-secret rotation costs nothing — change the value in the vault,
no commit. Argo CD's own documentation "strongly recommend[s]" this
destination-cluster style over manifest-generation approaches
([Argo CD secret management](https://github.com/argoproj/argo-cd/blob/master/docs/operator-manual/secret-management.md)).
ESO is CNCF-accepted with a broad contributor base.

**What you give up.**
- **The 32 GB budget.** Vault's own "small" reference architecture asks for
  8–16 GB RAM; Infisical asks for 4 GB including Postgres and Redis. Plus ESO's
  own three pods. This is by far the most expensive option in the constraint
  that binds hardest.
- **A monthly upgrade treadmill.** Only the current minor is supported, and
  minors ship roughly monthly. For one person, on a security-critical component,
  that is a standing obligation.
- **A second system that can fail, and whose failure mode is worse.** Vault
  starts sealed on every restart and needs 3-of-5 shares to unseal. On one
  machine that reboots, that is recurring manual work — or you build auto-unseal,
  which needs yet another trusted service.
- **Two of the three named vaults are Alpha-tier providers** maintained by a
  single individual each (Infisical, Bitwarden Secrets Manager). Only Vault is
  Stable — and Vault is the heaviest.
- **The free Bitwarden path does not exist.** Vaultwarden will not implement
  Secrets Manager ("Closing this as not going to happen"), and the ESO Bitwarden
  provider additionally needs a separate HTTPS `bitwarden-sdk-server` plus
  cert-manager.
- **Kubernetes becomes mandatory.**
- **The `SecretStore` publishes your vault's address** into a public repository,
  which collides with the no-network-topology rule unless that value is kept out
  of git — reintroducing untracked hand-managed state.

### The cross-cutting observation

The three options are not three answers to one question. They answer different
questions:

- SOPS asks *"how do I keep ciphertext safely in git?"* and leaves the
  orchestrator free.
- Sealed Secrets asks *"how do I keep ciphertext safely in git without ever
  handling a private key?"* and costs the orchestrator decision plus a 30-day
  backup cadence.
- ESO asks *"how do I keep ciphertext out of git entirely?"* and costs the
  orchestrator decision plus a substantial share of the RAM ceiling plus a
  second failure domain.

The 32 GB ceiling and the open orchestrator question bear on this far more than
any cryptographic property does.
