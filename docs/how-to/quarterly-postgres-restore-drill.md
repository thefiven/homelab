# Quarterly Postgres restore drill

**Date: 2026-08-18**

ADR-0012's rehearsal schedule names two checks: a monthly automated
`restic check` (structure and index only, `workloads/backup/restic-check-cronjob.yaml`)
and this drill, quarterly and manual, ~30-60 minutes inside #11's 4-hour/month
operational budget. "A backup that has never been restored does not exist":
the monthly check proves the repository's index is consistent, not that the
bytes it points at are readable, and not that they add up to a database
Immich can open. This drill proves both, and is the acceptance test #161
names for "restore actually works."

Everything here is scratch: new Deployments and Jobs in the `backup`
namespace, `emptyDir` storage only, deleted at the end. Nothing in this
procedure ever writes to `immich-postgres`, the production StatefulSet, or
its PVC; the whole point is proving the backup works without touching the
thing it backs up.

## What this proves, and what it doesn't

- **Step 1** (`restic check --read-data`) reads and re-hashes every pack file
  in the repository. The monthly automated check deliberately skips this
  (`restic-check-cronjob.yaml` calls it out as this drill's job, not its own),
  because it's the expensive check appropriate to a quarterly cadence, not a
  monthly one.
- **Steps 2-3** restore the most recent dump into a throwaway Postgres and
  point a throwaway Immich server at it. This is the only way to catch a
  dump that reads back cleanly as bytes but is missing a table, has a broken
  extension, or predates a schema migration Immich now expects.
- Photo thumbnails will not render in step 3: the scratch server has no
  `upload/`/`library/` mount, deliberately (ADR-0012 keeps the originals out
  of this ticket's scope). The proof this step is after is the *database*:
  the timeline, albums and user list coming from Postgres, not the images
  themselves.

## Before you start

- `kubectl` context reaching the cluster.
- The `backup` namespace's secrets exist and decrypt (161-02): `restic-repository`,
  `immich-postgres`, `healthchecks-pings`.
- Grab the image digests this drill reuses fresh from the manifests that pin
  them, rather than copying values into this doc that would go stale the next
  time one of those manifests bumps a version:
  - restic: `workloads/backup/restic-check-cronjob.yaml`
  - Postgres: `workloads/immich/postgres-statefulset.yaml`
  - Redis: `workloads/immich/redis-statefulset.yaml`
  - Immich server: `workloads/immich/server-deployment.yaml`

Every manifest below is applied ad hoc with `kubectl apply -f -`, never
committed, this is the "human gesture" ADR-0012 deliberately keeps out of
GitOps. Every resource carries `drill: quarterly-restore` so the whole thing
tears down with one label selector at the end.

## Step 1: full repository integrity (`restic check --read-data`)

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: restore-drill-check
  namespace: backup
  labels:
    drill: quarterly-restore
spec:
  backoffLimit: 0
  template:
    metadata:
      labels:
        drill: quarterly-restore
    spec:
      restartPolicy: Never
      nodeSelector:
        homelab.local/node: node1
      containers:
        - name: check
          image: restic/restic:<digest from restic-check-cronjob.yaml>
          args: [check, --read-data]
          env:
            - name: RESTIC_REPOSITORY
              value: /srv/backup
            - name: RESTIC_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: restic-repository
                  key: RESTIC_PASSWORD
          volumeMounts:
            - name: backup-repo
              mountPath: /srv/backup
      volumes:
        - name: backup-repo
          hostPath:
            path: /srv/backup
            type: Directory
```

```
kubectl apply -f - <<EOF
<manifest above>
EOF
kubectl logs -f job/restore-drill-check -n backup
kubectl get job/restore-drill-check -n backup -o jsonpath='{.status.conditions[*].type}{"\n"}'
```

`logs -f` streams until the pod exits, so a fast failure shows up in
minutes instead of being masked behind a `kubectl wait --for=condition=complete`
that would otherwise sit for the full timeout on a Job whose terminal state
is `Failed`, not `Complete` (the condition it's waiting for never arrives).
Reading and re-hashing the full ~20 GB repository over NFS has never been
timed (ADR-0012 names this as unmeasured), so budget up to 30 minutes for a
successful run, but there's nothing to guess about whether it's stuck: the
log stream itself is the progress signal. `Failed` from the `get job` line
above, or any `error:`/`Pack ID does not match` line in the log, is a
failed drill: stop here, see "If the drill fails" below, and don't proceed
to step 2 against a repository just proven inconsistent.

## Step 2: restore the latest dump into a scratch Postgres

Start the scratch database first, it needs to be ready before anything
tries to load into it:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: restore-drill-postgres
  namespace: backup
  labels:
    drill: quarterly-restore
    app: restore-drill-postgres
spec:
  replicas: 1
  selector:
    matchLabels:
      app: restore-drill-postgres
  template:
    metadata:
      labels:
        drill: quarterly-restore
        app: restore-drill-postgres
    spec:
      nodeSelector:
        homelab.local/node: node1
      containers:
        - name: postgres
          image: ghcr.io/immich-app/postgres:<digest from postgres-statefulset.yaml>
          env:
            - name: POSTGRES_USER
              valueFrom:
                secretKeyRef: {name: immich-postgres, key: DB_USERNAME}
            - name: POSTGRES_PASSWORD
              valueFrom:
                secretKeyRef: {name: immich-postgres, key: DB_PASSWORD}
            - name: POSTGRES_DB
              valueFrom:
                secretKeyRef: {name: immich-postgres, key: DB_DATABASE_NAME}
          readinessProbe:
            exec:
              command: [pg_isready, -U, $(POSTGRES_USER)]
            initialDelaySeconds: 5
            periodSeconds: 5
          volumeMounts:
            - {name: data, mountPath: /var/lib/postgresql/data}
      volumes:
        - name: data
          emptyDir: {}
---
apiVersion: v1
kind: Service
metadata:
  name: restore-drill-postgres
  namespace: backup
  labels:
    drill: quarterly-restore
spec:
  selector:
    app: restore-drill-postgres
  ports:
    - {port: 5432, targetPort: 5432}
```

Same `immich-postgres` secret the production database and the daily dump
job already use (duplicated into `backup` per 161-02/03): same username,
same database name, so the dump's own `ALTER TABLE ... OWNER TO` statements
land on a role that actually exists, with no separate scratch credentials to
invent.

```
kubectl apply -f - <<EOF
<manifest above>
EOF
kubectl wait --for=condition=available deployment/restore-drill-postgres -n backup --timeout=5m
```

A Deployment stuck in `CrashLoopBackOff` also blocks here for the full
timeout rather than failing fast (there's no Job-style terminal `Failed`
condition to wait on instead); `kubectl get pods -n backup -l
app=restore-drill-postgres` explains a wait that doesn't return quickly.

Confirm the dump's exact path inside the snapshot before scripting a restore
against a guessed name (`--stdin-filename immich-postgres.sql` in
`postgres-dump-cronjob.yaml` names it, but check it directly):

```
kubectl run restore-drill-ls --rm -it --restart=Never -n backup \
  --image=restic/restic:<digest from restic-check-cronjob.yaml> \
  --overrides='{"spec":{"nodeSelector":{"homelab.local/node":"node1"},"containers":[{"name":"restore-drill-ls","image":"restic/restic:<digest>","args":["ls","latest"],"env":[{"name":"RESTIC_REPOSITORY","value":"/srv/backup"},{"name":"RESTIC_PASSWORD","valueFrom":{"secretKeyRef":{"name":"restic-repository","key":"RESTIC_PASSWORD"}}}],"volumeMounts":[{"name":"repo","mountPath":"/srv/backup"}]}],"volumes":[{"name":"repo","hostPath":{"path":"/srv/backup","type":"Directory"}}]}}'
```

`restic snapshots` (same pattern, `args: [snapshots]`) is also worth a look
first: confirm the latest snapshot is from the last day, not stale. The
daily job's own Healthchecks ping already covers this, but a quarterly drill
running against a week-old snapshot because the ping silently stopped firing
is exactly the gap this drill exists to catch.

Then restore straight into the scratch database, streaming rather than
writing the ~20 GB dump to disk first, same `install-restic`-then-run shape
as `postgres-dump-cronjob.yaml`, inverted (`restic dump` instead of `restic
backup`, `psql` instead of `pg_dump`):

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: restore-drill-load
  namespace: backup
  labels:
    drill: quarterly-restore
spec:
  backoffLimit: 0
  template:
    metadata:
      labels:
        drill: quarterly-restore
    spec:
      restartPolicy: Never
      nodeSelector:
        homelab.local/node: node1
      initContainers:
        - name: install-restic
          image: restic/restic:<digest from restic-check-cronjob.yaml>
          command: [sh, -c, "cp /usr/bin/restic /restic-bin/restic && chmod +x /restic-bin/restic"]
          volumeMounts:
            - {name: restic-bin, mountPath: /restic-bin}
      containers:
        - name: load
          image: ghcr.io/immich-app/postgres:<digest from postgres-statefulset.yaml>
          command:
            - bash
            - -c
            - |
              set -euo pipefail
              export PATH="/restic-bin:$PATH"
              restic dump latest immich-postgres.sql | psql
          env:
            - name: RESTIC_REPOSITORY
              value: /srv/backup
            - name: RESTIC_PASSWORD
              valueFrom:
                secretKeyRef: {name: restic-repository, key: RESTIC_PASSWORD}
            - name: PGHOST
              value: restore-drill-postgres
            - name: PGUSER
              valueFrom:
                secretKeyRef: {name: immich-postgres, key: DB_USERNAME}
            - name: PGPASSWORD
              valueFrom:
                secretKeyRef: {name: immich-postgres, key: DB_PASSWORD}
            - name: PGDATABASE
              valueFrom:
                secretKeyRef: {name: immich-postgres, key: DB_DATABASE_NAME}
          volumeMounts:
            - {name: restic-bin, mountPath: /restic-bin}
            - {name: backup-repo, mountPath: /srv/backup}
      volumes:
        - {name: restic-bin, emptyDir: {}}
        - name: backup-repo
          hostPath: {path: /srv/backup, type: Directory}
```

```
kubectl apply -f - <<EOF
<manifest above>
EOF
kubectl logs -f job/restore-drill-load -n backup
kubectl get job/restore-drill-load -n backup -o jsonpath='{.status.conditions[*].type}{"\n"}'
```

Same reasoning as step 1: `logs -f` surfaces a fast failure immediately
instead of sitting out a 30-minute `kubectl wait` timeout that a `Failed`
Job would never satisfy. `Failed` from the `get job` line, or any `psql:`
error in the log, is a failed drill, most likely a `pg_dump` produced by a
schema Immich's current version no longer matches, which is precisely the
drift this step exists to catch before an actual disaster restore hits it.

## Step 3: confirm Immich can read it

A scratch Redis and a scratch Immich server, pointed at
`restore-drill-postgres`, no `upload:`/`library:` mounts:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: restore-drill-redis
  namespace: backup
  labels:
    drill: quarterly-restore
    app: restore-drill-redis
spec:
  replicas: 1
  selector:
    matchLabels: {app: restore-drill-redis}
  template:
    metadata:
      labels: {drill: quarterly-restore, app: restore-drill-redis}
    spec:
      nodeSelector:
        homelab.local/node: node1
      containers:
        - name: redis
          image: docker.io/valkey/valkey:<digest from redis-statefulset.yaml>
          readinessProbe:
            exec: {command: [redis-cli, ping]}
            initialDelaySeconds: 5
            periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: restore-drill-redis
  namespace: backup
  labels: {drill: quarterly-restore}
spec:
  selector: {app: restore-drill-redis}
  ports: [{port: 6379, targetPort: 6379}]
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: restore-drill-immich
  namespace: backup
  labels:
    drill: quarterly-restore
    app: restore-drill-immich
spec:
  replicas: 1
  selector:
    matchLabels: {app: restore-drill-immich}
  template:
    metadata:
      labels: {drill: quarterly-restore, app: restore-drill-immich}
    spec:
      nodeSelector:
        homelab.local/node: node1
      containers:
        - name: server
          image: ghcr.io/immich-app/immich-server:<digest from server-deployment.yaml>
          ports: [{name: http, containerPort: 2283}]
          env:
            - name: DB_HOSTNAME
              value: restore-drill-postgres
            - name: REDIS_HOSTNAME
              value: restore-drill-redis
            - name: DB_USERNAME
              valueFrom:
                secretKeyRef: {name: immich-postgres, key: DB_USERNAME}
            - name: DB_PASSWORD
              valueFrom:
                secretKeyRef: {name: immich-postgres, key: DB_PASSWORD}
            - name: DB_DATABASE_NAME
              valueFrom:
                secretKeyRef: {name: immich-postgres, key: DB_DATABASE_NAME}
          readinessProbe:
            exec: {command: [immich-healthcheck]}
            initialDelaySeconds: 5
            periodSeconds: 10
            timeoutSeconds: 10
          volumeMounts:
            - {name: data, mountPath: /data}
      volumes:
        - name: data
          emptyDir: {}
```

```
kubectl apply -f - <<EOF
<manifest above>
EOF
kubectl wait --for=condition=available deployment/restore-drill-immich -n backup --timeout=5m
kubectl port-forward -n backup deployment/restore-drill-immich 2283:2283
```

Same caveat as `restore-drill-postgres` above: a crash-looping pod here
blocks for the full 5-minute timeout rather than failing fast; `kubectl get
pods -n backup -l app=restore-drill-immich` explains a slow return.

Open `http://localhost:2283` and log in with a real account's credentials.
Confirm the timeline, albums and user list populate; that data comes only
from Postgres, so seeing it is the confirmation this whole drill exists to
produce. Thumbnails will not render (no photo originals mounted); that's
expected, not a failure. Failing to log in, or an empty library for an
account known to have one, is a failed drill.

## Teardown

```
kubectl delete deployment,service,job -n backup -l drill=quarterly-restore
```

One command, everything scratch this drill created; the production
`immich-postgres`/`immich-redis`/`immich-server` resources live in the
`immich` namespace and were never touched.

## If the drill fails

Stop, don't retry into a green result: a drill that fails is the thing it
exists to surface. Note which step failed and why (integrity, restore,
or Immich read), then treat it the same as any other platform defect: an
issue against this repository, not a silent re-run next quarter. Check the
daily dump's and monthly check's own Healthchecks.io history first: a
failing drill after weeks of green pings points at the dump or the schema,
not the pipeline; a drill failing alongside recent missed pings points at
the same root cause both are already flagging.
