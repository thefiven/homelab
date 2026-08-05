# Immich data classes: physical layout, demands, and network-storage support

**Researched: 2026-08-05.** Sources are Immich's official documentation, the
`immich-app/immich` repository on branch `main`, and upstream issues. Nothing
here comes from blogs, aggregators, or forums.

**Target deployment this was researched against**: one node (Ryzen 5 5600X,
32 GB RAM, RTX 3070 Ti with 8 GB VRAM), ~1.5 TB of family photos, 2x 1 TB
DRAM-less NVMe local, plus a Synology DS412+ (Atom D2700, 1 GB RAM) exported
over NFS on gigabit.

**Working hypothesis under test**: originals on the NAS over NFS, database and
generated derivatives on local NVMe.

**Reading convention.** Every factual claim carries a URL. Where the primary
sources do not answer a question, the section says so explicitly and is
labelled **Not established from primary sources**. Where a number is arithmetic
applied to a documented ratio, or a conclusion drawn from documented mechanics,
it is labelled **Inference**.

---

## 0. Summary table

| Data class | Path | Env var | Documented size | Documented on NFS? |
|---|---|---|---|---|
| Originals (uploaded) | `UPLOAD_LOCATION/upload/<userID>` or `UPLOAD_LOCATION/library/<userID>` | `UPLOAD_LOCATION` | the corpus itself | No statement either way |
| Originals (external library) | anywhere on a mounted path; never copied | n/a (mount + import path) | the corpus itself | Watching documented not to work; periodic scan documented as the fallback |
| Thumbnails / previews | `UPLOAD_LOCATION/thumbs/<userID>` | `UPLOAD_LOCATION` | part of the documented "10-20%" | No statement either way |
| Transcoded video | `UPLOAD_LOCATION/encoded-video/<userID>` | `UPLOAD_LOCATION` | part of the documented "10-20%" | No statement either way |
| PostgreSQL + VectorChord | `DB_DATA_LOCATION` | `DB_DATA_LOCATION` | "typically between 1-3 GB" | **Explicitly excluded**: "never a network share of any kind" |
| DB dumps | `UPLOAD_LOCATION/backups` | `UPLOAD_LOCATION` | not stated | No statement either way |
| ML models + cache | `/cache` in the ML container, a Docker named volume `model-cache` | `MACHINE_LEARNING_CACHE_FOLDER` | not stated | Not applicable by default (named volume) |

---

## 1. Where each class lives on disk

### 1.1 The documented folder structure

The data directory is the host path bound to `UPLOAD_LOCATION`, mounted into
the server container at `/data`
([`docker/docker-compose.yml`](https://github.com/immich-app/immich/blob/main/docker/docker-compose.yml)):

```yaml
volumes:
  # Do not edit the next line. If you want to change the media storage location on your system, edit the value of UPLOAD_LOCATION in the .env file
  - ${UPLOAD_LOCATION}:/data
```

The in-container path is `IMMICH_MEDIA_LOCATION`, default `/data`, and the docs
carry a warning against setting it:
"Media location inside the container ⚠️**You probably shouldn't set this**⚠️",
with the footnote "This path is where the Immich code looks for the files,
which is internal to the docker container. Setting it to a path on your host
will certainly break things, you should use the `UPLOAD_LOCATION` variable
instead."
([environment variables](https://docs.immich.app/install/environment-variables),
[source](https://github.com/immich-app/immich/blob/main/docs/docs/install/environment-variables.md)).

The subfolder set is fixed in the source as a `StorageFolder` enum
([`server/src/enum.ts`](https://github.com/immich-app/immich/blob/main/server/src/enum.ts)):

```ts
export enum StorageFolder {
  EncodedVideo = 'encoded-video',
  Library = 'library',
  Upload = 'upload',
  Profile = 'profile',
  Thumbnails = 'thumbs',
  Backups = 'backups',
}
```

The backup documentation maps each folder to its content
([backup and restore](https://docs.immich.app/administration/backup-and-restore),
[source](https://github.com/immich-app/immich/blob/main/docs/docs/administration/backup-and-restore.md)):

- **Source Assets** — "Original assets uploaded through the browser interface &
  mobile & CLI." Stored in `UPLOAD_LOCATION/upload/<userID>` with the storage
  template off (the default), or `UPLOAD_LOCATION/library/<userID>` with it on.
- **Avatar Images** — "User profile images." `UPLOAD_LOCATION/profile/<userID>`.
- **Thumbs Images** — "Preview images (small thumbnails and large previews) for
  each asset and thumbnails for recognized faces."
  `UPLOAD_LOCATION/thumbs/<userID>`.
- **Encoded Assets** — "Videos that have been re-encoded from the original for
  wider compatibility. The original is not removed."
  `UPLOAD_LOCATION/encoded-video/<userID>`.
- **Database Dump Backups** — `UPLOAD_LOCATION/backups/`.
- **Postgres** — `DB_DATA_LOCATION`.

Note the storage template caveat: "The `UPLOAD_LOCATION/library` folder is not
used by default on new machines running version 1.92.0. It is used only if the
system administrator activated the storage template engine." Turning the engine
on "will move all assets to `UPLOAD_LOCATION/library/<userID>`"; turning it off
again "will leave the assets in `UPLOAD_LOCATION/library/<userID>` and will not
return them to `UPLOAD_LOCATION/upload`."
([backup and restore](https://docs.immich.app/administration/backup-and-restore))

The docs split the folders into critical and regenerable: "Immich stores two
types of content in the filesystem: (a) original, unmodified assets (photos and
videos), and (b) generated content. We recommend backing up the entire contents
of `UPLOAD_LOCATION`, but only the original content is critical, which is stored
in the following folders: 1. `UPLOAD_LOCATION/library` 2. `UPLOAD_LOCATION/upload`
3. `UPLOAD_LOCATION/profile`. If you choose to back up only those folders, you
will need to rerun the transcoding and thumbnail generation jobs for all assets
after you restore from a backup."
([backup and restore](https://docs.immich.app/administration/backup-and-restore))

There is a documented precedent for splitting folders across devices, in a
caution on the same page: "If you moved some of these folders onto a different
storage device, such as `profile/`, make sure to adjust the backup path to
match your setup." This is the only primary-source acknowledgement that
splitting the data directory across devices is a thing people do. It does not
endorse any particular split.

### 1.2 Derivative file naming

Derivative image paths are constructed in
[`server/src/cores/storage.core.ts`](https://github.com/immich-app/immich/blob/main/server/src/cores/storage.core.ts):

```ts
static getPersonThumbnailPath(person: ThumbnailPathEntity) {
  return StorageCore.getNestedPath(StorageFolder.Thumbnails, person.ownerId, `${person.id}.jpeg`);
}

static getImagePath(asset: ThumbnailPathEntity, { fileType, format, isEdited }: ImagePathOptions) {
  return StorageCore.getNestedPath(
    StorageFolder.Thumbnails,
    asset.ownerId,
    `${asset.id}_${fileType}${isEdited ? '_edited' : ''}.${format}`,
  );
}

static getEncodedVideoPath(asset: ThumbnailPathEntity) {
  return StorageCore.getNestedPath(StorageFolder.EncodedVideo, asset.ownerId, `${asset.id}.mp4`);
}
```

The `fileType` values come from `AssetFileType` in
[`server/src/enum.ts`](https://github.com/immich-app/immich/blob/main/server/src/enum.ts):

```ts
export enum AssetFileType {
  /**
   * An full/large-size image extracted/converted from RAW photos
   */
  FullSize = 'fullsize',
  Preview = 'preview',
  Thumbnail = 'thumbnail',
  Sidecar = 'sidecar',
  EncodedVideo = 'encoded_video',
}
```

Face thumbnails are one file per **person**, `${person.id}.jpeg`, not one per
detected face instance.

### 1.3 The database

`DB_DATA_LOCATION` is described simply as "Host path for Postgres database"
([environment variables](https://docs.immich.app/install/environment-variables)).
It is bound into the database container at `/var/lib/postgresql/data`
([`docker-compose.yml`](https://github.com/immich-app/immich/blob/main/docker/docker-compose.yml)).

The shipped image pins Postgres and the vector extension together:

```yaml
image: ghcr.io/immich-app/postgres:14-vectorchord0.4.3-pgvectors0.2.0@sha256:bcf63357191b76a916ae5eb93464d65c07511da41e3bf7a8416db519b40b1c23
...
POSTGRES_INITDB_ARGS: '--data-checksums'
...
shm_size: 128mb
```

For anyone running Postgres themselves, the requirements are: "Immich is known
to work with Postgres versions `>= 14, < 20`", VectorChord in range `>= 0.3,
< 2.0` with pgvector `>= 0.7, < 0.9`, `shared_preload_libraries = 'vchord.so'`,
and the `earthdistance` extension during non-superuser setup
([standalone Postgres](https://docs.immich.app/administration/postgres-standalone),
[source](https://github.com/immich-app/immich/blob/main/docs/docs/administration/postgres-standalone.md)).

Critically, the database is **not** derivable from the files: "Immich stores
file paths and user metadata in the database. It does not scan the library
folder, so database backups are essential."
([backup and restore](https://docs.immich.app/administration/backup-and-restore))

### 1.4 Machine learning models and cache

Models live in a Docker **named volume**, not in `UPLOAD_LOCATION`
([`docker-compose.yml`](https://github.com/immich-app/immich/blob/main/docker/docker-compose.yml)):

```yaml
  immich-machine-learning:
    ...
    volumes:
      - model-cache:/cache
...
volumes:
  model-cache:
```

The path inside the container is `MACHINE_LEARNING_CACHE_FOLDER`, "Directory
where models are downloaded", default `/cache`
([environment variables](https://docs.immich.app/install/environment-variables)).

Models are downloaded from Hugging Face at runtime: "If models are failing to
download entirely, you can manually download them from [Hugging Face] and place
them in the cache folder."
([FAQ](https://docs.immich.app/FAQ),
[source](https://github.com/immich-app/immich/blob/main/docs/docs/FAQ.mdx))

---

## 2. Volume as a fraction of the corpus, and file count per original

### 2.1 The only documented ratio

There is exactly one ratio in the official documentation, and it covers
thumbnails and transcoded video together:

> "The generation of thumbnails and transcoded video can increase the size of
> the photo library by 10-20% on average."
> — [requirements](https://docs.immich.app/install/requirements)
> ([source](https://github.com/immich-app/immich/blob/main/docs/docs/install/requirements.md))

**Inference (arithmetic on the documented figure).** For a 1.5 TB corpus this
is 150-300 GB of `thumbs/` + `encoded-video/`. The documentation gives no
breakdown between the two folders, and the figure is stated as an average over
unspecified libraries — a photo-dominated corpus with few videos will sit
differently in that band than a video-heavy one, and the docs do not say which
way.

### 2.2 The database size

> "The Postgres database files are typically between 1-3 GB in size."
> — [requirements](https://docs.immich.app/install/requirements)

The docs do not state what library size that range corresponds to, nor how it
scales with asset count. Given a 1.5 TB corpus is likely well beyond the
implied typical instance, treat 1-3 GB as a floor rather than a bound.
**Not established from primary sources**: the growth of the database, or of the
CLIP and face vector indexes, as a function of asset count.

### 2.3 File count per original

Derivative generation is documented in the FAQ:

> ### Why are there so many thumbnail generation jobs?
>
> There are three thumbnail jobs for each asset:
>
> - Blurred (thumbhash)
> - Preview (Webp)
> - Thumbnail (Jpeg)
>
> — [FAQ](https://docs.immich.app/FAQ)

Two corrections from the source, both load-bearing for sizing:

1. **Only two of those three are files.** The blurred thumbhash is a database
   column, not a file on disk —
   [`server/src/schema/tables/asset.table.ts`](https://github.com/immich-app/immich/blob/main/server/src/schema/tables/asset.table.ts):

   ```ts
   @Column({ type: 'bytea', nullable: true })
   thumbhash!: Buffer | null;
   ```

2. **The FAQ has the two formats the wrong way round.** The defaults in
   [`server/src/config.ts`](https://github.com/immich-app/immich/blob/main/server/src/config.ts)
   are:

   ```ts
   image: {
     thumbnail: {
       format: ImageFormat.Webp,
       size: 250,
       quality: 80,
       progressive: false,
     },
     preview: {
       format: ImageFormat.Jpeg,
       size: 1440,
       quality: 80,
       progressive: false,
     },
     colorspace: Colorspace.P3,
     extractEmbedded: false,
     fullsize: {
       enabled: false,
       format: ImageFormat.Jpeg,
       quality: 80,
       progressive: false,
     },
   },
   ```

   So the **thumbnail** is WebP at 250 px and the **preview** is JPEG at
   1440 px, both at quality 80. `fullsize` is **disabled by default**.

So, per still-image asset at defaults: **2 derivative files** in `thumbs/`
(`<assetId>_thumbnail.webp` at 250 px, `<assetId>_preview.jpeg` at 1440 px),
plus 1 `bytea` blob in the database. Enabling `fullsize` adds a third file.
Editing an asset adds `_edited` variants (`isEdited` in `getImagePath`).
Video assets additionally get one `encoded-video/<userID>/<assetId>.mp4` when
transcoding applies. Recognised people add one `thumbs/<userID>/<personId>.jpeg`
each.

**Not established from primary sources**: the on-disk byte size of a typical
250 px WebP or 1440 px JPEG derivative, and therefore the split of the
documented 10-20% between `thumbs/` and `encoded-video/`.

---

## 3. Access patterns

The documentation does not characterise IO as sequential or random for any
class. What follows is what the sources do state, with inferences marked.

### 3.1 Originals

Documented reads of originals:

- **Metadata Extraction**, first in the documented job chain for a new asset
  ([jobs and workers](https://docs.immich.app/administration/jobs-workers),
  [source](https://github.com/immich-app/immich/blob/main/docs/docs/administration/jobs-workers.md)).
- **Thumbnail Generation** and **Video Transcoding**, which must read the
  original to produce derivatives.
- Serving the original to a client on download or original-quality view.

**Inference**: originals are write-once then read-rarely after the initial job
chain, because every subsequent consumer is documented to work off derivatives
(section 3.4). Whole-file sequential reads dominate: each job reads one file
end to end.

### 3.2 Thumbnails and previews

**Inference**: `thumbs/` is the hot path. Every timeline scroll fetches many
250 px thumbnails; every asset open fetches a 1440 px preview; and — see 3.4 —
every machine-learning job reads a preview. This is small-file, high-IOPS,
latency-sensitive, read-dominated access, with a write burst during import.

The docs support the latency claim indirectly, warning about storage as the
bottleneck for job throughput: "On a normal machine, 2 or 3 concurrent jobs can
probably max the CPU. Storage speed and latency can quickly become the limiting
factor beyond this, particularly when using HDDs."
([FAQ](https://docs.immich.app/FAQ))

### 3.3 Database

The one primary-source statement on database IO shape is the
`DB_STORAGE_TYPE` variable: "Optimize concurrent IO on SSDs or sequential IO on
HDDs ([`SSD`, `HDD`])", default `SSD`
([environment variables](https://docs.immich.app/install/environment-variables)).
The shipped compose file repeats it as a comment: "Uncomment the
`DB_STORAGE_TYPE: 'HDD'` var if your database isn't stored on SSDs"
([`docker-compose.yml`](https://github.com/immich-app/immich/blob/main/docker/docker-compose.yml)).

That is Immich telling you, in its own defaults, that it expects **concurrent
(random) IO on an SSD** for the database. The requirements page states the
consequence: "Good performance and a stable connection to the Postgres database
is critical to a smooth Immich experience."
([requirements](https://docs.immich.app/install/requirements))

### 3.4 Machine learning reads derivatives, not originals

Two independent statements in the docs:

> "The server container will send requests containing the image preview to the
> remote machine learning container for processing."
> — [remote machine learning](https://docs.immich.app/guides/remote-machine-learning)
> ([source](https://github.com/immich-app/immich/blob/main/docs/docs/guides/remote-machine-learning.md))

> "Immich's machine learning feature operates on the generated thumbnail. If a
> face is visible in the video's thumbnail it will be picked up by facial
> recognition."
> — [FAQ](https://docs.immich.app/FAQ)

(The two pages say "preview" and "thumbnail" respectively; either way it is a
generated derivative, not the original.)

**This is the single most consequential access-pattern fact for the hypothesis.**
Smart Search, Face Detection and OCR — the jobs that will run hundreds of
thousands of times during a bulk import, and again whenever a model changes —
do not touch originals at all. They read from `thumbs/`.

Facial Recognition does not even read files: "Facial Recognition uses the
_outputs_ of these models that have already been saved to the database. As
such, its processing is between the server container and the database."
([remote machine learning](https://docs.immich.app/guides/remote-machine-learning))

### 3.5 Model cache

Models are read once per load and held in memory until the TTL expires:
`MACHINE_LEARNING_MODEL_TTL`, "Inactivity time (s) before a model is unloaded
(disabled if <= 0)", default `300`
([environment variables](https://docs.immich.app/install/environment-variables)).
Cold-start reads only.

---

## 4. Does Immich officially support NFS, per class?

### 4.1 Database on network storage — explicitly ruled out

This is the clearest statement in the whole body of Immich documentation:

> "Good performance and a stable connection to the Postgres database is critical
> to a smooth Immich experience. The Postgres database files are typically
> between 1-3 GB in size. For this reason, the Postgres database
> (`DB_DATA_LOCATION`) should ideally use local SSD storage, and **never a
> network share of any kind**. Additionally, if Docker resource limits are used,
> the Postgres database requires at least 2GB of RAM."
> — [requirements](https://docs.immich.app/install/requirements) (emphasis added)

The same prohibition is repeated in the shipped `.env` template, where an
operator is most likely to read it
([`docker/example.env`](https://github.com/immich-app/immich/blob/main/docker/example.env)):

```
# The location where your database files are stored. Network shares are not supported for the database
DB_DATA_LOCATION=./postgres
```

And it is named as a **cause of data corruption** in the FAQ:

> "The causes of possible corruption are many, but can include unexpected
> poweroffs or unmounts, **use of a network share for Postgres data**, or a poor
> storage medium such an SD card or failing HDD/SSD."
> — [FAQ](https://docs.immich.app/FAQ) (emphasis added)

Upstream corroboration: [issue #14054, "Website not working when DB on NFS
share"](https://github.com/immich-app/immich/issues/14054) (closed), reported
against v1.120.1 with `DB_DATA_LOCATION=/mnt/nfs/immich/postgres`. The reporter
had to `chmod 777` the whole tree just to get past a `chown` failure, and the
server then refused connections.

There is a related but distinct filesystem constraint: the database directory
"must be located on a filesystem that supports user/group ownership and
permissions (EXT2/3/4, ZFS, APFS, BTRFS, XFS, etc.). It will not work on any
filesystem formatted in NTFS or ex/FAT/32."
([requirements](https://docs.immich.app/install/requirements))

**Verdict: placing the database on the NAS is contradicted by three separate
primary sources, one of which frames it as a corruption risk.**

### 4.2 Originals and derivatives on network storage — no blanket statement

The prohibition above is scoped to `DB_DATA_LOCATION`. The `example.env` comment
for `UPLOAD_LOCATION` carries no such warning — it reads only "The location
where your uploaded files are stored". A repository-wide code search for
"network share" returns exactly three files: `docs/docs/install/requirements.md`,
`docs/docs/FAQ.mdx`, and `docker/example.env` — all three are the database
statements quoted above.

So: **Immich neither blesses nor forbids NFS for `UPLOAD_LOCATION`.** That
silence is itself the finding. The closest thing to an endorsement is the
scaling guide, in a passage explicitly disclaiming detail: "In some cases
scaling up can be as easy as incrementing the amount of replicas on a Kubernetes
deployment, in others it might need you to configure network tunnels or NFS
mounts."
([scaling Immich](https://docs.immich.app/guides/scaling-immich))

The requirements page states a filesystem expectation that applies to all of it:
"Recommended Unix-compatible filesystem (EXT4, ZFS, APFS, etc.) with support for
user/group ownership and permissions."
([requirements](https://docs.immich.app/install/requirements))

### 4.3 External libraries on network storage — one documented failure mode

External libraries are the mechanism for leaving originals where they already
are: "External libraries track assets stored in the filesystem outside of
Immich. When the external library is scanned, Immich will load videos and photos
from disk and create the corresponding assets."
([libraries](https://docs.immich.app/features/libraries),
[source](https://github.com/immich-app/immich/blob/main/docs/docs/features/libraries.md))

The docs state a network-storage limitation directly:

> "### Automatic watching (EXPERIMENTAL)
>
> This feature is considered experimental and for advanced users only. If
> enabled, it will allow automatic watching of the filesystem which means new
> assets are automatically imported to Immich without needing to rescan.
>
> **If your photos are on a network drive, automatic file watching likely won't
> work.** In that case, you will have to rely on a periodic library refresh to
> pull in your changes."
> — [libraries](https://docs.immich.app/features/libraries) (emphasis added)

The documented fallback is the nightly scan: "There is an automatic scan job
that is scheduled to run once a day. Its schedule is configurable."
([libraries](https://docs.immich.app/features/libraries))

### 4.4 Upstream NFS issues

A search of `immich-app/immich` issues with NFS in the title returns six:

| Issue | State | Title |
|---|---|---|
| [#20858](https://github.com/immich-app/immich/issues/20858) | **open** | External library watching - excessive CPU load and NFS traffic |
| [#27676](https://github.com/immich-app/immich/issues/27676) | closed (duplicate) | [Bug] Library watcher generates continuous EACCES errors on Synology NFS shares with @eaDir folders since v2.7.0 |
| [#16896](https://github.com/immich-app/immich/issues/16896) | closed | NFS issues with XMP |
| [#14054](https://github.com/immich-app/immich/issues/14054) | closed | Website not working when DB on NFS share |
| [#9967](https://github.com/immich-app/immich/issues/9967) | closed | External Library - Permissions Denied on NFS shares, and mkdir on existing folders |
| [#66](https://github.com/immich-app/immich/issues/66) | closed | Server storage report is wrong for NFS mounted UPLOAD_LOCATION |

Two of these are directly on the nose for this deployment.

**[#20858](https://github.com/immich-app/immich/issues/20858) — open.** The
reporter's NAS is a Synology. "After upgrade to version v1.137.x I noticed
increased CPU consumption by the immich-server container and very high
load/traffic on the NFS server." The suspected cause is a `chokidar` bump "from
3.5.3 to 4.0.3". The library watcher is the component at fault.

**[#27676](https://github.com/immich-app/immich/issues/27676) — closed as
duplicate.** Also Synology over NFS. "Since upgrading from v2.6.3 to v2.7.x, the
library watcher generates a continuous flood of EACCES permission errors when
monitoring external libraries located on a Synology NAS mounted via NFS." The
watcher "generates hundreds of EACCES errors per second against `@eaDir` folders
(Synology internal thumbnail folders), even when `**/@eaDir/**` is set as an
exclusion pattern" — the exclusion pattern is ignored. The reporter's own
workaround: "Disabling the library
watcher (experimental feature) stops the errors. **Periodic scan works
correctly.**"

Both point the same way: the *watcher* is the part that abuses an NFS-mounted
Synology, and the documented periodic scan is the part that works. That matches
the documentation's own advice in 4.3.

There is also a documented inotify ceiling that a 1.5 TB library would run into
if watching were enabled anyway: "If you encounter an `ENOSPC` error, you need
to increase your file watcher limit. In sysctl, this key is called
`fs.inotify.max_user_watches` and has a default value of 8192. Increase this
number to a suitable value greater than the number of files you will be
watching. Note that Immich has to watch all files in your import paths including
any ignored files."
([libraries](https://docs.immich.app/features/libraries))

---

## 5. RAM requirements

### 5.1 What is officially stated

> - **RAM**: Minimum 6GB, recommended 8GB.
> - **CPU**: Minimum 2 cores, recommended 4 cores.
>
> :::note RAM requirements
> For a smooth experience, especially during asset upload, Immich requires at
> least 6GB of RAM. For systems with only 4GB of RAM, Immich can be run with
> machine learning features disabled.
> :::
>
> — [requirements](https://docs.immich.app/install/requirements)

And for the database specifically: "if Docker resource limits are used, the
Postgres database requires at least 2GB of RAM."
([requirements](https://docs.immich.app/install/requirements))

Note the phrasing: 6 GB is the figure for the whole stack including ML, and the
4 GB figure is what remains viable once ML is removed. **Inference**: the docs
therefore imply roughly 2 GB attributable to the ML container in the default
configuration — consistent with the measured 1004 MiB for the default CLIP model
plus a face model (section 6.2).

### 5.2 Machine-learning container RAM

There is no separate stated RAM requirement for the ML container. What exists is
the per-model peak RSS table in the search docs, whose column is defined as:

> "**Memory (MiB)**: The peak RSS usage of the process after performing the above
> timing benchmark. Does not include image decoding, concurrent processing, the
> web server, etc., which are relatively constant factors."
>
> "Memory and execution time estimates were obtained without acceleration on a
> 7800x3D processor running bare metal Linux. All testing and evaluation was
> done at f32 precision (the default in Immich)."
>
> — [searching](https://docs.immich.app/features/searching)
> ([source](https://github.com/immich-app/immich/blob/main/docs/docs/features/searching.md))

The default CLIP model is `ViT-B-32__openai`
([`server/src/config.ts`](https://github.com/immich-app/immich/blob/main/server/src/config.ts)),
which the table lists at **1004 MiB / 2.26 ms / 69.9% recall**. The largest
model in the table, `ViT-gopt-16-SigLIP2-384__webli`, is **6585 MiB**;
`ViT-SO400M-16-SigLIP2-384__webli` is **3854 MiB**.

Multipliers documented elsewhere:

- Concurrency: "You may want to increase concurrency past the default for higher
  utilization. However, keep in mind that this will also increase VRAM
  consumption."
  ([ML hardware acceleration](https://docs.immich.app/features/ml-hardware-acceleration))
- Workers: `MACHINE_LEARNING_WORKERS`, "Number of worker processes to spawn",
  default `1`
  ([environment variables](https://docs.immich.app/install/environment-variables)).
- Mixed models: "using different models will lead to higher peak memory usage."
  ([remote machine learning](https://docs.immich.app/guides/remote-machine-learning))

Immich actively sheds ML memory when idle, and this is normal behaviour, not a
fault: "If the error says the worker is exiting, then this is normal. This is a
feature intended to reduce RAM consumption when the service isn't being used."
([FAQ](https://docs.immich.app/FAQ))

Out-of-memory has a documented signature: "If the error mentions SIGKILL or
error code 137, it most likely means the service is running out of memory.
Consider either increasing the server's RAM or moving the service to a server
with more RAM."
([FAQ](https://docs.immich.app/FAQ))

### 5.3 RAM during a bulk import

> "The initial backup is the most intensive due to the number of jobs running.
> The most CPU-intensive ones are transcoding and machine learning jobs (Smart
> Search, Face Detection), and to a lesser extent thumbnail generation."
> — [FAQ](https://docs.immich.app/FAQ)

The documented levers, in the order the FAQ gives them:

1. "Lower the job concurrency for these jobs to 1."
2. "Under Settings > Transcoding Settings > Threads, set the number of threads
   to a low number like 1 or 2."
3. "Under Settings > Machine Learning Settings > Facial Recognition > Model
   Name, you can change the facial recognition model to `buffalo_s` instead of
   `buffalo_l`. The former is a smaller and faster model, albeit not as good."
   — with the caveat "For facial recognition on new images to work properly, You
   must re-run the Face Detection job for all images after this."
4. Container resource constraints — but "Note that memory constraints work by
   terminating the container, so this can introduce instability if set too low."
5. Disable ML entirely.

**Not established from primary sources**: any peak-RAM figure for a bulk import
of a specific library size. The docs give qualitative guidance and levers, not
numbers.

Default job concurrencies, from
[`server/src/config.ts`](https://github.com/immich-app/immich/blob/main/server/src/config.ts):

```ts
job: {
  [QueueName.BackgroundTask]: { concurrency: 5 },
  [QueueName.SmartSearch]: { concurrency: 2 },
  [QueueName.MetadataExtraction]: { concurrency: 5 },
  [QueueName.FaceDetection]: { concurrency: 2 },
  [QueueName.Search]: { concurrency: 5 },
  [QueueName.Sidecar]: { concurrency: 5 },
  [QueueName.Library]: { concurrency: 5 },
  [QueueName.Migration]: { concurrency: 5 },
  [QueueName.ThumbnailGeneration]: { concurrency: 3 },
  [QueueName.VideoConversion]: { concurrency: 1 },
  [QueueName.Notification]: { concurrency: 5 },
  [QueueName.Ocr]: { concurrency: 1 },
  [QueueName.Workflow]: { concurrency: 5 },
  [QueueName.IntegrityCheck]: { concurrency: 1 },
  [QueueName.Editor]: { concurrency: 2 },
}
```

---

## 6. GPU and machine learning

### 6.1 Supported acceleration

> ## Supported Backends
>
> - ARM NN (Mali)
> - CUDA (NVIDIA GPUs with compute capability 5.2 or higher)
> - ROCm (AMD GPUs)
> - OpenVINO (Intel GPUs such as Iris Xe and Arc)
> - RKNN (Rockchip)
>
> — [ML hardware acceleration](https://docs.immich.app/features/ml-hardware-acceleration)
> ([source](https://github.com/immich-app/immich/blob/main/docs/docs/features/ml-hardware-acceleration.md))

CUDA prerequisites: "The GPU must have compute capability 5.2 or greater. The
server must have the official NVIDIA driver installed. The installed driver must
be >= 545 (it must support CUDA 12.3). On Linux (except for WSL2), you also need
to have NVIDIA Container Toolkit installed."

Immich rates it the most reliable path: "Some models may not be compatible with
certain backends. **CUDA is the most reliable.**"

Transcoding acceleration is a separate feature with its own backends and its own
compose overlay (`hwaccel.transcoding.yml` vs `hwaccel.ml.yml`)
([`docker-compose.yml`](https://github.com/immich-app/immich/blob/main/docker/docker-compose.yml)).

### 6.2 VRAM — what is and is not documented

**Immich documents no VRAM figure anywhere.** A repository-wide code search for
"VRAM" scoped to `docs/` returns exactly one file,
`docs/docs/features/ml-hardware-acceleration.md`, and every mention in it is
qualitative:

- "You may want to increase concurrency past the default for higher utilization.
  However, keep in mind that this will also increase VRAM consumption."
- "Larger models benefit more from hardware acceleration, if you have the VRAM
  for them."
- "each GPU must be able to load all models. It is not possible to distribute a
  single model to multiple GPUs that individually have insufficient VRAM, or to
  delegate a specific model to one GPU."

**Not established from primary sources**: the VRAM footprint of any Immich
model. The nearest documented proxy is the CPU peak-RSS table (section 5.2),
measured at f32 on CPU — 1004 MiB for the default `ViT-B-32__openai`, up to
6585 MiB for the largest model offered — with the explicit caveat that it "does
not include image decoding, concurrent processing, the web server, etc."

### 6.3 What happens with 8 GB, per upstream reports

Three upstream issues bear on low- and mid-VRAM behaviour:

**[#11979](https://github.com/immich-app/immich/issues/11979), "Improve machine
learning resilience in low VRAM scenarios (CUDA)"** (closed), reported on a
4 GiB vGPU against v1.112.1. Under simultaneous face detection, smart search and
transcoding:

> "- Especially the smart search query allocates a lot of VRAM
> - When the smart search query request fails due to low memory:
>   1. A corresponding exception (failed to allocate memory) is logged in the container
>   2. The smart search container seems to **leak** the VRAM (it's only released when the container gets restarted)
>   3. The smart search container does not seem to continue processing the remaining assets (face recognition, smart search)
>   4. Not even re-running the smart search job for all assets helps in this case (only after a container restart)"

The failure mode is not graceful degradation — it is a stall that survives job
requeueing and needs a container restart.

**[#23462](https://github.com/immich-app/immich/issues/23462), "ML OCR memory
leaks?"** — **open** as of this research, reported against v2.2.0. The reporter's
CPU is an AMD Ryzen 5600X and the GPU is an RTX 4070 Super with 12 GB. Running
OCR with the `PP-OCRv5_server` model overnight:

> "- CPU: 99.97% (AMD Ryzen 5600X 6c/12t)
> - RAM (container): 12.32GB / 15.58GB
> - GPU VRAM: 11.7/12GB Dedicated, 15.5/16GB Shared, 27.2/28GB Total memory (ReBAR?)
> You can see from logs that it all happened in just one hour"

and "This behavior is not isolated to Docker desktop, WSL or CUDA." The reporter
notes `PP-OCRv5_mobile` — which is Immich's default, `modelName: 'PP-OCRv5_mobile'`
in [`config.ts`](https://github.com/immich-app/immich/blob/main/server/src/config.ts)
— "doesn't have such issue". There is an open PR against it,
[#30332, "(partially) fix #23462: configure onnxruntime to stop VRAM usage from
growing"](https://github.com/immich-app/immich/issues/30332).

**[#24024](https://github.com/immich-app/immich/issues/24024), "Machine Learning:
GPU VRAM management"** (closed).

**Inference.** Immich publishes no VRAM budget, so 8 GB cannot be checked
against a requirement — only against reported behaviour. The reported behaviour
is that VRAM pressure produces leaks and stalls rather than clean fallback, that
the growth is unbounded in at least one still-open case, and that a *12 GB* card
was filled by a non-default OCR model. A 3070 Ti's 8 GB shared with any other
GPU consumer is squarely in the region where these reports originate.

The documented mitigations that exist: keep concurrency at defaults (raising it
"will also increase VRAM consumption"); stay on the default models; and
`MACHINE_LEARNING_MODEL_TTL` (default `300` s) unloads idle models, though
issue #11979 reports the VRAM is not actually released on the failure path.

There is also a **documented escape hatch that removes the GPU contention
entirely**: the ML container can be moved to another host. "you may also host
Immich's machine learning container on a more powerful system... The server
container will send requests containing the image preview to the remote machine
learning container." With the security caveat: "as an internal service, the
machine learning container has no security measures whatsoever."
([remote machine learning](https://docs.immich.app/guides/remote-machine-learning))

### 6.4 Can ML be disabled, and what is lost?

Yes, at two levels.

> :::info
> Disabling machine learning will result in a poor experience for searching and
> the 'Explore' page, as these are reliant on it to work as intended.
> :::
>
> "Machine learning can be disabled under Administration > Settings > Machine
> Learning Settings, either entirely or by model type. For instance, you can
> choose to disable smart search with CLIP, but keep facial recognition enabled.
> This means that the machine learning service will only process the enabled
> jobs.
>
> However, disabling all jobs will not disable the machine learning service
> itself. To prevent it from starting up at all in this case, you can comment out
> the `immich-machine-learning` section of the docker-compose.yml."
> — [FAQ](https://docs.immich.app/FAQ)

The per-model granularity is real: `clip`, `facialRecognition` and `ocr` each
have an independent `enabled` flag in
[`config.ts`](https://github.com/immich-app/immich/blob/main/server/src/config.ts),
defaulting to `true`, with defaults `ViT-B-32__openai`, `buffalo_l` and
`PP-OCRv5_mobile` respectively.

**What is lost, from the docs**: semantic/smart search (CLIP), the Explore page,
facial recognition and people grouping, OCR, and — by dependency — duplicate
detection. The dependency chain is stated on the remote-ML page: "tasks dependent
on these features—Duplicate Detection and Facial Recognition—will not run for
affected assets."
([remote machine learning](https://docs.immich.app/guides/remote-machine-learning))
Filename, date, album and metadata search are unaffected — CLIP produces "no
'tags', 'labels', or 'descriptions'"
([FAQ](https://docs.immich.app/FAQ)), so nothing else depends on it.

There is a source-level kill switch not present in the environment-variables
table: `enabled: process.env.IMMICH_MACHINE_LEARNING_ENABLED !== 'false'` in
[`config.ts`](https://github.com/immich-app/immich/blob/main/server/src/config.ts).
`IMMICH_MACHINE_LEARNING_ENABLED` and `IMMICH_MACHINE_LEARNING_URL` do **not**
appear in
[the environment variables page](https://docs.immich.app/install/environment-variables)
— they work, but they are undocumented, so do not build on them.

---

## 7. Bulk import and jobs that re-read originals

### 7.1 Bulk import of an existing library

Immich documents two distinct routes, and they differ in where the bytes end up:

**Route A — External Library.** Originals stay where they are; Immich indexes
them in place (section 4.3). "Can I add my existing photo library? Yes, using an
External Library feature."
([FAQ](https://docs.immich.app/FAQ))

Documented consequences of this route:

- Read-only external libraries cannot write sidecars: "Read-only external
  libraries cannot create `.xmp` sidecar files", so "metadata edits like
  timestamp, location, description, and ratings cannot be saved."
  ([FAQ](https://docs.immich.app/FAQ))
- Deduplication is weaker: "Duplicate checking exists only for upload libraries
  using file hash and is per-library, not global."
  ([FAQ](https://docs.immich.app/FAQ))
- One owner per library: "Currently an external library can only belong to a
  single user which is selected when the library is initially created."
  ([libraries](https://docs.immich.app/features/libraries))
  — **this bears directly on the multiple-family-users requirement.**
- Metadata added inside Immich is not written back: "If you add metadata to an
  external asset in any way (i.e. add it to an album or edit the description),
  that metadata is only stored inside Immich and will not be persisted to the
  external asset file. If you move an asset to another location within the
  library all such metadata will be lost upon rescan."
  ([libraries](https://docs.immich.app/features/libraries))
- Deletion asymmetry: in read-only libraries "files re-appear in the timeline
  when trash is emptied since deletion isn't possible."
  ([FAQ](https://docs.immich.app/FAQ))

**Route B — CLI upload.** Copies originals into `UPLOAD_LOCATION`.
`immich upload` supports `--recursive`, `--concurrency <number>` (default 4),
`--album` ("Automatically create albums based on folder name"), `--album-name`,
`--ignore <pattern>`, `--dry-run`, and `--skip-hash`
([CLI](https://docs.immich.app/features/command-line-interface),
[source](https://github.com/immich-app/immich/blob/main/docs/docs/features/command-line-interface.md)).
On hashing: "By default, the upload command will hash the files before uploading
them... Note that Immich always performs its own deduplication through hashing,
so this is merely a performance consideration."

Album structure is preserved on this route: "Can I keep my existing album
structure while importing assets into Immich? Yes, by using the Immich CLI along
with the `--album` flag."
([FAQ](https://docs.immich.app/FAQ))

For Google Takeout specifically the docs point at a third-party tool: "If you
are looking to import your Google Photos takeout, we recommend this community
maintained tool immich-go."
([CLI](https://docs.immich.app/features/command-line-interface))

**Not established from primary sources**: any throughput figure, expected
duration, or resource envelope for importing a library of a given size.

### 7.2 The job chain per asset

> "When a new asset is uploaded it kicks off a series of jobs, which include
> metadata extraction, thumbnail generation, machine learning tasks, and storage
> template migration."
> — [jobs and workers](https://docs.immich.app/administration/jobs-workers)

Documented order: Metadata Extraction → Storage Template Migration → Thumbnail
Generation → (Smart Search, Face Detection, OCR, Video Transcoding in parallel)
→ Duplicate Detection → Facial Recognition.

### 7.3 Scheduled jobs that re-read data

> "Some jobs (such as memories generation) run on a schedule, which is every
> night at midnight by default."
> — [jobs and workers](https://docs.immich.app/administration/jobs-workers)

The nightly task set and its defaults, from
[`config.ts`](https://github.com/immich-app/immich/blob/main/server/src/config.ts):

```ts
nightlyTasks: {
  startTime: '00:00',
  databaseCleanup: true,
  generateMemories: true,
  syncQuotaUsage: true,
  missingThumbnails: true,
  clusterNewFaces: true,
},
```

`missingThumbnails` is the one that matters for a NAS: it runs nightly by
default and, for any asset lacking a derivative, the fix requires re-reading the
original.

Separately scheduled:

- **External library scan** — "There is an automatic scan job that is scheduled
  to run once a day. Its schedule is configurable."
  ([libraries](https://docs.immich.app/features/libraries)). This job stats the
  entire import path tree; on a read-only NFS export from a 1 GB-RAM NAS with
  almost no dentry cache, that is a full nightly metadata walk of the corpus.
- **Database dump** — "default: keep last 14 backups, create daily at 2:00 AM",
  written to `UPLOAD_LOCATION/backups`
  ([backup and restore](https://docs.immich.app/administration/backup-and-restore)).

### 7.4 Operations that force a full re-read of every original

Documented triggers, each of which walks the entire corpus:

- **Restoring from a partial backup**: "If you choose to back up only those
  folders, you will need to rerun the transcoding and thumbnail generation jobs
  for all assets after you restore from a backup."
  ([backup and restore](https://docs.immich.app/administration/backup-and-restore))
- **Changing the storage template**: "Template changes will only apply to _new_
  assets. To retroactively apply the template to previously uploaded assets, run
  the Storage Migration Job."
  ([FAQ](https://docs.immich.app/FAQ)) — this **moves** every original.
- **Changing the face model**: "You must re-run the Face Detection job for all
  images after this."
  ([FAQ](https://docs.immich.app/FAQ)) — reads derivatives, not originals
  (section 3.4).
- **Failed metadata extraction**: "Rerun the storage migration job."
  ([FAQ](https://docs.immich.app/FAQ))

### 7.5 Reindexing at scale

Relevant to a large library, from the upgrade guide: "it's normal for the server
logs to be seemingly stuck at `Reindexing clip_index` and `Reindexing face_index`
for some time if you have over 100k assets in Immich and/or Immich is on a
relatively weak server."
([upgrading](https://github.com/immich-app/immich/blob/main/docs/docs/install/upgrading.md))
This is database work, and it is another argument for the database being on the
fastest device available.

---

## 8. What is not established from primary sources

Collected here so nothing is silently upgraded to fact later:

1. **VRAM requirements for any Immich model.** No figure is published. Only the
   CPU peak-RSS table and qualitative warnings exist.
2. **The split of the documented 10-20% between `thumbs/` and `encoded-video/`**,
   and the byte size of an individual derivative.
3. **Database growth as a function of asset count.** "1-3 GB" is stated with no
   library size attached.
4. **Any peak-RAM figure for a bulk import**, at any library size.
5. **Whether `UPLOAD_LOCATION` on NFS is supported.** No statement exists either
   way. The prohibition is scoped to `DB_DATA_LOCATION` alone.
6. **Sequential vs random IO characterisation** for any class. The only signal is
   `DB_STORAGE_TYPE`'s "concurrent IO on SSDs or sequential IO on HDDs".
7. **Import throughput or duration** for a library of a given size.
8. **The on-disk size of the model cache.** The FAQ acknowledges "The
   `immich_model-cache` volume takes up a lot of space" without quantifying it.

Two documentation defects found along the way, both worth knowing before
trusting a secondary summary:

- The FAQ states "Preview (Webp), Thumbnail (Jpeg)"; `config.ts` has thumbnail =
  WebP 250 px and preview = JPEG 1440 px. The FAQ has them inverted.
- The FAQ lists three thumbnail jobs per asset; only two produce files, the
  thumbhash being a `bytea` column.

---

## What the evidence supports

**The hypothesis holds for the database, and holds decisively.** Putting
PostgreSQL anywhere but local NVMe is contradicted by three independent primary
sources — the requirements page ("never a network share of any kind"), the
shipped `.env` template ("Network shares are not supported for the database"),
and the FAQ, which names network shares as a **cause of database corruption**.
Upstream [#14054](https://github.com/immich-app/immich/issues/14054) is the
lived version. This half of the hypothesis is not a judgement call; it is
following instructions the project wrote down three times.

**The hypothesis holds for derivatives, and for a reason stronger than the one
it was formed on.** Derivatives were assumed to belong on NVMe because they are
hot. The sources establish something better: **machine learning reads the
generated preview, never the original**
([remote ML](https://docs.immich.app/guides/remote-machine-learning),
[FAQ](https://docs.immich.app/FAQ)). Smart Search, Face Detection and OCR — the
jobs that run once per asset during import and again on every model change —
therefore generate zero NAS traffic if `thumbs/` is local. Combined with the
documented 10-20% growth, the entire hot working set of a 1.5 TB corpus is
150-300 GB, which fits local NVMe with room to spare. Keeping derivatives local
is what makes the NAS survivable at all.

**The hypothesis is neither confirmed nor destroyed for originals on NFS, because
Immich takes no position.** A repository-wide search for "network share" finds
only the three database statements. That silence is the honest answer: originals
on NFS is unsupported in the sense of undocumented, not in the sense of
forbidden. What the sources *do* supply is a precise map of the failure surface,
and it is narrower than feared: originals are read during the initial job chain
and rarely afterwards, since every downstream consumer works off derivatives.

**What is given up by putting originals on the NAS:**

- **The library watcher.** Documented as unreliable on network drives ("If your
  photos are on a network drive, automatic file watching likely won't work"), and
  demonstrated twice on Synology-over-NFS specifically —
  [#20858](https://github.com/immich-app/immich/issues/20858) (open, "very high
  load/traffic on the NFS server") and
  [#27676](https://github.com/immich-app/immich/issues/27676) ("hundreds of
  EACCES errors per second" against `@eaDir`, exclusion patterns ignored). The
  documented and field-confirmed fallback is the nightly scan — "Periodic scan
  works correctly". Cost: new files appear within a day, not within seconds. On a
  finished 1.5 TB archive that is close to free.
- **A nightly full metadata walk of the corpus** by that scan job, on a NAS that
  caches almost no dentries. This is the recurring cost, and it is unavoidable on
  the external-library route.
- **If the external-library route is taken specifically**: sidecar writes on
  read-only mounts, global deduplication, and — most sharply against the stated
  requirement of multiple family users with separate galleries — **one owner per
  external library** ("an external library can only belong to a single user").
  Separate galleries would mean one library per person, each a separate import
  path, each scanned nightly.
- **Nightly `missingThumbnails`** (on by default) will re-read originals from the
  NAS for any asset whose derivative went missing.
- **Storage Migration**, if the storage template is ever changed, rewrites every
  original's location — a full-corpus move across NFS.

**What is given up by not putting originals on the NAS:** 1.5 TB does not fit on
2× 1 TB NVMe alongside 150-300 GB of derivatives and the database, without
pooling the two drives and accepting no local redundancy. That is the actual
trade, and it is a capacity fact, not a documentation one.

**Separately, and orthogonal to the storage question: the GPU is the weakest
part of this plan, and the sources say so only obliquely.** Immich publishes no
VRAM requirement at all, so 8 GB cannot be validated against anything. What can
be read is upstream behaviour: VRAM exhaustion produces *leaks and stalls that
survive job requeueing and need a container restart*
([#11979](https://github.com/immich-app/immich/issues/11979)), and one
**still-open** report ([#23462](https://github.com/immich-app/immich/issues/23462))
has an OCR model filling **11.7 of 12 GB** on a Ryzen 5600X — the same CPU as
this node. Sharing 8 GB with another GPU workload is not covered by any
documented guarantee. The documented mitigations are: stay on default models
(`ViT-B-32__openai` at 1004 MiB, `buffalo_l`, `PP-OCRv5_mobile`), do not raise
ML job concurrency, or move the ML container to another host entirely — which
the project documents and which also removes ML from the RAM budget.

**Finally, on RAM: 32 GB is not the constraint here.** Immich asks for a minimum
of 6 GB and recommends 8 GB, with 2 GB reserved for Postgres under Docker
limits. The ceiling that will actually be hit is VRAM, and after that, NAS IOPS
during the nightly scan — not system memory.
