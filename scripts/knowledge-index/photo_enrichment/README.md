# Photo enrichment and group review

Implements [#217](https://github.com/homeiac/home/issues/217) alongside the existing media-summary worker. Reads the existing knowledge-index catalog and originals without modifying them. Owns a separate DuckDB database for extracted metadata, detected faces and human annotations; exports Parquet for downstream queries.

## Run locally

Python 3.11–3.13 is supported by the pinned dependencies. From the repository root:

```bash
bash scripts/knowledge-index/setup-photo-enrichment.sh /tmp/photo-enrichment-venv
/tmp/photo-enrichment-venv/bin/python scripts/knowledge-index/photo-enrich.py \
  --index /path/to/knowledge-index --library /path/to/library \
  --state /path/to/photo-enrichment serve
```

Open `http://127.0.0.1:8765`. The library root contains `Google Photos/`; the index contains `knowledge.duckdb` built by `kidx.py`. The state directory must be outside both source directories. Use only one process per enrichment state directory: stop the GUI before running extraction/export/query CLI commands against that same state. A running source-catalog writer may also require finishing its rebuild before this reader can open the catalog.

For a synthetic eight-photo demonstration, without access to personal photos:

```bash
cd scripts/knowledge-index
/tmp/photo-enrichment-venv/bin/python -m photo_enrichment.demo /tmp/photo-enrichment-demo
/tmp/photo-enrichment-venv/bin/python photo-enrich.py \
  --index /tmp/photo-enrichment-demo/index --library /tmp/photo-enrichment-demo/library \
  --state /tmp/photo-enrichment-demo/state serve
```

The GUI groups photos by capture date in a chosen IANA timezone. Select individual photos or the current page, enter event/location/venue/tags/notes, then save. Dates only suggest groups: annotations apply to the explicit selection, including selections across pages. Existing groups can be edited or deleted. `Review photo` shows the caption, metadata provenance and face labels. Imported whole-photo people tags are displayed separately from face assignments.

Read EXIF for selected photos before grouping files whose capture date is unknown. Recognized Takeout album duplicates are hidden; this does not perform content-hash deduplication. The tool currently handles photos (JPEG, HEIC, PNG, GIF, WebP), not video container metadata or video face tracking.

## EXIF recovery

The GPS precedence is valid Takeout `geoData`, then `geoDataExif`, then embedded EXIF latitude/longitude. Missing, invalid and zero/zero pairs remain unknown; compass direction alone is not a coordinate. Camera make/model, dimensions and capture time are also extracted. EXIF orientation is applied consistently to previews and face coordinates. Originals are never rewritten.

Capture time uses Takeout `photoTakenTime` first, then EXIF `DateTimeOriginal`/`DateTime`. Explicit EXIF offsets are preserved. An offset-free EXIF date uses the selected timezone and records that assumption. Location text supplied by a person stays in group annotations; it never becomes fabricated GPS or replaces a model caption.

Extraction is bounded and resumable by path, file size, mtime and extractor version. Metadata records include errors and provenance. Reindex source files after modifying them and rerun extraction: the catalog join is keyed by path and indexed size, not a content hash. Do not replace same-size originals in place without re-extracting. Confirmed faces are checked against current file size/mtime before use.

```bash
/tmp/photo-enrichment-venv/bin/python scripts/knowledge-index/photo-enrich.py \
  --index /path/to/knowledge-index --library /path/to/library \
  --state /path/to/photo-enrichment extract --limit 100 --timezone America/New_York
```

Add `--date YYYY-MM-DD` to target one date. Without a date, pending extraction is prioritized; each call handles at most `--limit` files. `--force` rereads metadata while preserving confirmed face labels for unchanged images.

## Faces and Frigate

Download models explicitly before using **Find faces in selection** or CLI `extract --faces`:

```bash
/tmp/photo-enrichment-venv/bin/python scripts/knowledge-index/photo-enrich.py \
  --state /path/to/photo-enrichment models
```

The default backend uses OpenCV YuNet for detection and SFace for embeddings, explicitly on CPU. Downloads from the official OpenCV model repository are verified with pinned SHA-256 hashes. Models and embeddings stay in the separate state directory. Model licenses: [YuNet (MIT)](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet), [SFace (Apache 2.0)](https://github.com/opencv/opencv_zoo/tree/main/models/face_recognition_sface).

Name a detected face to create a confirmed reference. Other faces can show ranked candidates, each requiring an explicit **Confirm** or **Reject**. A cosine score is not a probability. The default 0.363 threshold comes from the [OpenCV example](https://docs.opencv.org/4.13.0/d0/dd4/tutorial_dnn_face.html); it has not been calibrated on this library. No suggested identity is silently applied. Reruns preserve confirmed labels. Audit history records group edits and identity changes.

Frigate's object detector and identity recognizer perform different jobs. [Frigate+ models](https://docs.frigate.video/plus/) can locate objects/faces; [face recognition](https://docs.frigate.video/configuration/face_recognition/) uses FaceNet (small/CPU) or ArcFace (large/GPU). A Coral detector therefore does not itself supply person identities. The checked-in Frigate configuration currently specifies a CPU detector plus large face recognition, while a backup has Coral enabled. Live runtime and paid-model compatibility must be verified before choosing to reuse the object detector. No Frigate or Coral configuration is changed here.

An optional **Ask Frigate** action reuses its existing face library through [POST /api/faces/recognize](https://docs.frigate.video/integrations/api/recognize-face-faces-recognize-post/). Set `PHOTO_FRIGATE_URL` to the trusted internal Frigate origin and `PHOTO_FRIGATE_TOKEN` to an authenticated admin bearer token when required, sourced from your existing protected environment. Never put credentials in source or command-line arguments. This action sends only the selected face crop to that configured service; it does not train Frigate. Redirects are refused. Its candidate still requires confirmation. Live validation on 2026-11-18 passed API reachability, blank-image handling and three expected-identity matches from five sampled reference crops after a several-minute cold reference build (scores 0.82–0.93). Two crops had no detected face. This is an integration smoke test using existing references, not independent photo-library accuracy validation.

The summary worker and this enrichment process can run independently: GPU captions and CPU metadata/faces join by photo identity. They do not share the writable enrichment database. The worker command continuously processes bounded batches; GUI and worker must not run concurrently against the same state directory. Frigate GPU lookups could compete with summary inference; benchmark a representative photo sample before enabling bulk integration. Security-camera-trained Frigate+ object models also need evaluation on personal photos before replacing YuNet.

### Live validation

Run `check-frigate-enrichment.py --recognize-reference` with the same virtualenv. It reads runtime configuration and aggregate library counts, checks a blank image, then recognizes at most five existing training crops. It never registers or modifies faces, and logs no names, image paths or credentials. It requires at least one expected reference match; this smoke test is not a library accuracy benchmark. Frigate's HTTP 400 negative results are handled explicitly; `unknown` is treated as no identity. Authentication, disabled recognition and server errors remain errors.

When Frigate is intentionally scaled to zero, the API returns HTTP 503. The operator-approved helper `validate-frigate-temporarily.py --allow-temporary-start` backs up replica/pause settings, starts only Frigate, runs the probe, then restores replicas even on failure. Adding `--keep-running` explicitly retains one replica once the deployment is ready, including after a failed recognition probe for diagnosis. Existing Flux pause annotations are preserved in either case; other GPU tenants are untouched.

## Background worker deployment

The persistent `photo-enrichment-worker.service` runs on the Proxmox host beside the existing catalog, not inside the Kubernetes VM. It uses an isolated, versioned virtualenv, reads the catalog/originals, and writes only its own state and node-exporter textfile. CPU is capped at two cores, memory at 2 GiB, with low scheduling priority and no network access during extraction.

```bash
CB_HOST=root@<inventory-address> python3 scripts/knowledge-index/deploy-photo-worker.py --inspect
CB_HOST=root@<inventory-address> python3 scripts/knowledge-index/deploy-photo-worker.py --deploy
CB_HOST=root@<inventory-address> python3 scripts/knowledge-index/deploy-photo-worker.py --status
```

Deployment discovers the source index/library from the caption worker, installs pinned dependencies without changing system Python, verifies the face-model checksums, backs up prior service/state files and runs a three-photo smoke batch before enabling the service. A startup failure restores the previous service; successfully committed enrichment facts are retained. Source files, captions and Frigate configuration are unchanged.

The service uses `/local-3TB-backup/photo-enrichment/enrichment.duckdb` and exports six tables under its `parquet/` directory after each 25-photo batch. It retries failed photos after one hour, avoiding a tight retry loop that blocks other photos. `worker_attempts` is internal retry state and is not exported. Empty queues are polled every minute; DB connections close between batches so source catalog rebuilds can acquire their write lock. A temporary catalog lock can cause a service restart; systemd retries after 60 seconds. Queue selection uses catalog path/size and extractor/model versions; the existing same-size replacement caveat still applies.

The worker extracts EXIF and CPU face embeddings. It does not bulk-send images to Frigate or automatically assign identities. Confirm names through review. Dates lacking an explicit offset use UTC and retain `exif.assumed:UTC` provenance; choose a known timezone explicitly for a targeted re-extraction rather than inferring it from an event location.

To run locally, add `--prom /path/to/photo_enrichment.prom worker --batch-size 25` to the normal CLI invocation. `--max-batches 1` is a bounded smoke run; `--metadata-only` skips faces. Stop the host worker before opening the GUI or CLI against its writable DuckDB state, then restart it afterwards. During processing, query the Parquet snapshots without competing for the DB writer lock.

## Value stream dashboard

The existing Knowledge Index dashboard from PR #216 is extended, with **Pipeline bottlenecks / Value stream map** immediately after **Value delivered**. It preserves existing panel IDs and summary progress line graphs. The map shows the independently measured summary and photo branches, followed by backlog, durable output, stage-operation throughput, error and duration charts.

Enable the photo branch by adding a writable node-exporter textfile path before the CLI command:

```bash
/tmp/photo-enrichment-venv/bin/python scripts/knowledge-index/photo-enrich.py \
  --index /path/to/knowledge-index --library /path/to/library \
  --state /path/to/photo-enrichment \
  --prom /var/lib/prometheus/node-exporter/photo_enrichment.prom serve
```

Use a dedicated `.prom` file per process, never the summary worker's file. The containing directory must already exist and be scraped by node-exporter. Instrumentation publishes every five seconds, including in-flight stage time, independently of the DB lock. Stage measurements cover catalog/queue queries, EXIF reads, CPU face inference, DuckDB writes, annotation saves, optional Frigate requests and Parquet export. Counters reset per process; rate queries handle resets. Metrics use only fixed stage/status labels and aggregate counts, never paths, names, GPS or embeddings.

Backlogs are snapshots of indexed photos missing successful EXIF or a current face scan, plus unnamed detected faces. They refresh at startup and after mutations; restart the reader after a source-catalog rebuild. A successful scan containing zero faces still leaves the scan queue. Recoverable EXIF errors appear in an inventory gauge; thrown operation errors have a separate counter. Telemetry output failures do not fail committed annotations or enrichment.

Map percentages are normalized separately for each worker. Frigate service nodes use explicitly labeled milliseconds and API reachability (1/0), not worker percentages. Review time measures saving annotations, not human thought/waiting time. Idle time, queue residence time and full end-to-end lead time are not measured; the dashboard does not claim flow efficiency from these partial timings. Uninstrumented photo stages are absent from the map and the photo stat tiles display **Not instrumented**; missing metrics are not evidence that a stage is idle. The CPU branch becomes visible after its worker is deployed with `--prom`; publishing the dashboard alone does not deploy it.

### Native Frigate service telemetry

The standalone `export-frigate-metrics.py` polls only aggregate `/api/stats` every five seconds. It emits API reachability, poll age, detector/face processing milliseconds and available frame rates. Missing fields remain absent; a reported face time of zero means no native face processing recorded, not that the identity classifier is ready. These are camera-service measurements, not uploaded-photo enrichment throughput.

Install the backed-up systemd poller with `CB_HOST=root@<inventory-address> python3 scripts/knowledge-index/deploy-frigate-metrics.py`. It uses the existing node-exporter textfile directory. An optional protected `/opt/knowledge-index/frigate-metrics.env` supplies `PHOTO_FRIGATE_URL` and `PHOTO_FRIGATE_TOKEN`; neither belongs in git. Dashboard nodes and processing series are suppressed after 60 seconds without polling. The dashboard includes processing-time and frame-rate line graphs.

The live 0.16.0 instance reports a CPU object detector and large face recognition. Available ONNX providers are OpenVINO and CPU, with no CUDA provider. Starting this instance therefore does not demonstrate GPU-accelerated face recognition. It was left running at the user's request with its existing per-object Flux pause retained. The independent CPU photo worker is deployed separately with the service below.

## Storage and DuckDB

`STATE/enrichment.duckdb` is authoritative. Tables are `extracted`, `photo_groups`, `group_members`, `faces`, `face_scans`, `rejected_matches` and `annotation_history`; the session view `enriched_media` joins extracted facts with the read-only catalog and latest successful captions. Keep backups of the state directory while the application is stopped.

Use the GUI **Export to Parquet** or CLI `export`. Exports include every table except the internal resumability table `face_scans`. Each `STATE/parquet/*.parquet` file is atomically replaced, but the collection is not a transactional snapshot for concurrent external readers; wait for export completion before joining multiple files. CLI extraction exports on completion. GUI annotations persist immediately in DuckDB and reach Parquet on explicit export.

```bash
/tmp/photo-enrichment-venv/bin/python scripts/knowledge-index/photo-enrich.py \
  --index /path/to/knowledge-index --library /path/to/library \
  --state /path/to/photo-enrichment query \
  'SELECT path, capture_ts, latitude, longitude, gps_source FROM enriched_media LIMIT 20'
```

`query` is an administrator CLI accepting one SELECT, not a SQL security sandbox. It is not exposed over HTTP. Names, coordinates, face embeddings and audit records are private data: keep state, model files, real photos and exports out of git.

## Serving and verification

Default binding is loopback. The server checks Host, uses a per-run CSRF token and blocks cross-origin writes. It has no user authentication. For any shared deployment, place it behind the existing internal Traefik gateway with access control, pass the exact HTTPS `--public-origin`, and follow the homelab GitOps workflow. Do not expose it to the internet. The host worker deployment below is included; a shared GUI deployment still requires internal access control.

```bash
/tmp/photo-enrichment-venv/bin/python scripts/knowledge-index/test-photo-enrichment.py
PYTHON=/tmp/photo-enrichment-venv/bin/python bash scripts/knowledge-index/test-knowledge-index.sh
```

Tests use generated fixtures and a mock recognizer to check GPS precedence, timezone handling, traversal rejection, annotation isolation, face confirmation, resumability, Parquet and HTTP controls. They verify the source catalog remains byte-for-byte unchanged. The actual CPU model backend was also exercised on the synthetic demo; this tests loading/inference, not recognition accuracy on real faces. Chrome verification covered selecting a date, saving shared context to two photos and reading it back in photo details.

## PostgreSQL authority and delayed analytics (#217)

The deployed backend uses the existing PostgreSQL service in a dedicated
`photo_enrichment` database. The original EXIF reader, CPU face models, stable
face IDs, labels, group annotations and review UI are retained. The GPU caption
worker keeps its existing output path; an hourly catalog refresh imports its
latest captions and source-index rows into PostgreSQL without rerunning models.

Photo enrichment workers claim durable PostgreSQL jobs with `SKIP LOCKED`, a
lease and a fencing token. Image/model work happens outside transactions. Facts,
zero-face scan completion and successful job completion commit together. Expired
claims cannot publish results; failures retry after an hour. PostgreSQL also owns
immediate face review and group edits, so saving a label updates review filters
without waiting for analytics.

A separate five-minute systemd timer uses DuckDB's official PostgreSQL extension
to export one repeatable-read, read-only PostgreSQL transaction. It publishes an
immutable Parquet generation through `analytics/current.json` only after every
table validates. Failed exports retain the previous manifest. Analytical queries
pin a generation; the bundled reader holds a filesystem lease until it closes.
Old generations are retained for at least 24 hours and at least three generations;
pinned readers prevent cleanup. External readers should use the bundled query
entry point or hold the same `.readers` shared lock for long-running queries.

```bash
# Credentials are in protected libpq files, never CLI arguments or Git.
CB_HOST=root@<inventory-address> python3 scripts/knowledge-index/deploy-photo-postgres.py inspect
CB_HOST=root@<inventory-address> python3 scripts/knowledge-index/deploy-photo-postgres.py prepare
CB_HOST=root@<inventory-address> python3 scripts/knowledge-index/deploy-photo-postgres.py cutover
CB_HOST=root@<inventory-address> python3 scripts/knowledge-index/deploy-photo-postgres.py status
```

Preparation leaves the current worker running. Cutover stops it, backs up the
legacy DuckDB/WAL and unit files under `/opt/photo-enrichment/backups/`, imports
all eight state tables in one PostgreSQL transaction, runs three smoke jobs and
publishes the first snapshot before starting the worker and GUI. Migration has
an idempotency ledger and refuses to overwrite a nonempty untracked destination.
The original state and legacy Parquet exports remain recovery material.

If cutover fails, writers stay stopped. Do not blindly restart the legacy writer
after PostgreSQL has accepted work: reconcile PG-only facts and edits first.
Restore the saved unit/release only after choosing and validating the authoritative
state. Existing PostgreSQL backups include the dedicated database; a successful
backup job alone is not evidence of a tested restore.

The GUI is `https://photos.app.home.panderosystems.com`, served through the existing
Traefik wildcard certificate and private-network middleware. PR previews use
`scripts/knowledge-index/deploy-photo-route.sh`: a Flux source scoped to the
feature branch and only `apps/photo-enrichment`, not the entire unmerged branch.
At merge, transfer route ownership to the main Flux source and remove the preview
objects without pruning the transferred resources.

Grafana retains the existing summary and Frigate branches. New panels show leased
jobs, retries, oldest unfinished job age, export status/duration/size, snapshot
freshness and GUI review operations. Node titles explicitly distinguish percent,
job counts and seconds. Snapshot age is not query execution time or GPU time.

Validation: `TEST_PYTHON=<venv>/bin/python bash scripts/knowledge-index/test-photo-postgres.sh`
uses a disposable loopback PostgreSQL container and synthetic photos. It checks
migration preservation, zero-face completion, retry backoff, claim fencing,
concurrent-edit snapshot consistency, stale edit rejection and failed publication.
