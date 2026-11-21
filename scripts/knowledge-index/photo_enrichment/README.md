# Photo enrichment and group review

Implements [#217](https://github.com/homeiac/home/issues/217) alongside the existing media-summary worker. Reads the existing knowledge-index catalog and originals without modifying them. The deployed pipeline uses PostgreSQL for jobs, enrichment facts and review edits; immutable Parquet snapshots and DuckDB serve gallery browsing and analytics. The standalone DuckDB writable mode below remains available for local demos and migration compatibility.

## Deployed gallery queries and incident diagnostics

Photo lists, capture-date grouping, face filters and counts query Parquet with a private in-memory DuckDB connection per request. A generation lease keeps all files consistent. PostgreSQL supplies only recent face review changes for the gallery overlay, so confirmation, renaming and clearing a label appear immediately. Point lookups, matching references and writes still use PostgreSQL. New enrichment becomes visible after the five-minute snapshot export; source catalog imports run hourly. Neither the GUI nor the worker writes a shared DuckDB database in PostgreSQL mode.

The November 18 hang came from a PostgreSQL gallery plan repeatedly scanning captions before pagination while holding the shared application lock. Static files also waited for that lock. Static/config/health/diagnostic requests now bypass it, socket writes happen after release, lock acquisition times out after three seconds, and GUI PostgreSQL statements have a fifteen-second timeout. The gallery read path now uses DuckDB. A bootstrap path before the first snapshot retains PostgreSQL pagination before caption lookup.

A second contention source was whole-library matching inside face-list requests (measured at 20 seconds), plus thumbnail decoding under the same lock. Matching and automatic acceptance now use a separate PostgreSQL connection and lock. Browser requests consume the latest completed suggestion cache; a cold start shows a background-refresh notice and polls until similarities appear. The matcher starts immediately and checks again thirty seconds after each pass. Gallery reads hold the PostgreSQL connection lock only during a query; DuckDB and image I/O run outside it. Preview decoding is limited to two concurrent originals, with a 32 MiB / 256-entry cache keyed by original path, size, modification time and face box. This avoids the observed memory-pressure spike from simultaneous original decodes. Slow completed request logs include stage durations, the bottleneck stage and the slowest SQL-template fingerprint; background matching has its own trace and completion event.

HTTP requests borrow connections from psycopg pools: reads have 2 warm connections and at most 12; writes have 1 warm connection and at most 2. Each queue is limited to 32 waiters, with a five-second checkout timeout. Read sessions enforce `default_transaction_read_only=on`; they see committed review edits through MVCC without waiting for confirmation batches. Connections are checked on checkout, reset on return, recycled after fifteen minutes and trimmed after one idle minute. Exceptions return connections and unfinished transactions are rolled back by the pool. Background matching and ingestion retain their separate persistent sessions. Transactions and row revision checks still protect writes; no dual authority or shared DuckDB writer is introduced. OTel exposes pool size, idle/limit/waiting/error counts and `pg.pool.wait` spans; automated triage identifies pool exhaustion separately from SQL and Python lock contention.

- [Photo App dashboard](https://grafana.app.home.panderosystems.com/d/photo-app/photo-app): request rates, p95 latency, errors, PostgreSQL/DuckDB time, lock waits, unfinished requests and automatic diagnostic logs.
- [Knowledge Index value stream map](https://grafana.app.home.panderosystems.com/d/knowledge-index/knowledge-index): processing stages plus snapshot-to-gallery and live-review data flow, with explicitly labeled query p95 seconds.
- Grafana Explore data sources **Photo traces** and **Photo logs**: correlated trace IDs; HTTP response headers include `X-Trace-ID`.

OpenTelemetry spans start before lock acquisition and cover SQL, DuckDB, thumbnail processing and response writes. Every five seconds a watchdog checks unfinished requests; after ten seconds it logs the current stage and trace ID without waiting for the span to finish. Metrics export every five seconds. Traces/logs exclude query parameters, names, image paths, embeddings and SQL parameter values. SQL templates are hashed. Bounded asynchronous exporters have a three-second network timeout.

The independent `photo-enrichment-triage.timer` runs once a minute. It probes health/API/diagnostics, collects PostgreSQL wait/blocker metadata when needed, checks GUI cgroup pressure, and records an evidence-based category such as `postgres_blocked`, `slow_duckdb_query` or `application_lock`. It does not restart services or edit photo data. Latest evidence is `/local-3TB-backup/photo-enrichment/observability/triage-latest.json`; the same event goes to structured journald/OTel logs. Health, freshness and incident gauges are scraped through node exporter. `/healthz` tests HTTP liveness, while the independent API probe tests database-backed readiness.

Private Traefik OTLP ingestion feeds an OTel collector, Tempo and Loki on `k3s-vm-still-fawn`. Tempo retains traces for 48 hours; Loki retains logs for 72 hours. Each backend has a 5 GiB PVC. These are photo-app signals; existing processing-worker metrics continue to populate the pipeline dashboard.

Read-only operational checks from the worktree:

```bash
CB_HOST=root@<inventory-address> python3 scripts/knowledge-index/triage-photo-app.py
python3 scripts/knowledge-index/check-photo-service.py
python3 scripts/knowledge-index/check-photo-observability.py
```

The last command checks actual stored traces/logs, collector and Prometheus metrics, and dashboard PromQL. `deploy-photo-postgres.py gui` installs the versioned GUI, exporter and triage units with rollback backups, preserving review data and the worker. Kubernetes observability and the app dashboard deploy through the feature branch's Flux preview.

## Run locally (standalone DuckDB mode)

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

## Legacy standalone worker deployment

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

## Legacy standalone storage and DuckDB

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

### Review previously processed faces together

The PostgreSQL GUI compares saved embeddings with confirmed named faces when
loading the face library. No original photos, EXIF, face detections, embeddings,
confirmed names or rejections are rewritten by that matching pass. Suggestions
are grouped by person under **Suggested matches**. Inspect the crops and select
individual faces or a page. **Confirm suggested matches** saves each selected
face’s displayed name, including selections spanning different people. Selection
persists across pages and collections. **Select all above threshold** selects
all suggestions meeting a minimum similarity (default 90 on a 0–100 scale),
across every page of the selected suggested-person collection or the entire
library. This replaces the current selection and shows per-name counts before
confirmation; it never saves automatically. Similarity is not a probability. Faces without suggestions need a manual name.
**Assign this name to all selected** remains a separate action for shared labels.
The API accepts per-face names and revisions; the GUI confirms large selections
in batches of 100 with progress. Each batch commits its labels and audit entries
atomically, or none do if any face was edited elsewhere. On failure, completed
batches remain saved and the remaining selection is retained with an error;
refresh before retrying. The selection snapshot excludes already-named faces. Confirmation uses the
displayed suggestions, never freshly recomputed names behind the scenes.

Only compatible model/dimension vectors are compared. Zero/non-finite vectors
are skipped. Initial suggestion settings are cosine similarity >= 0.55 and a
margin >= 0.08 over the next distinct person; these are review heuristics, not
calibrated identity probabilities. Rejected references suppress that person's
suggestion for the candidate. Ambiguous faces stay unnamed. A 30-second cache is
invalidated immediately when confirmed labels or rejections change; new worker
results become eligible on the next uncached pass. Matching is measured separately
from model inference in Grafana.

The GUI can be updated independently with `deploy-photo-postgres.py gui`; this
backs up its unit/release and restarts only the GUI. It does not restart ingestion,
invoke recognition models or rerun migration. PostgreSQL remains the durable
owner of review decisions when these services later move into pods. Pending
suggestions are derived data and can be regenerated.

### Optional automatic acceptance

Open **Automatic acceptance** in the GUI, choose a minimum similarity (default
90/100) and enable the rule. New installations start disabled. The rule and its
latest status live in PostgreSQL and survive service restarts or a future move
to pods. A background loop in the GUI service checks every 30 seconds without
requiring an open browser. Each pass processes up to 100 candidates, using only
human-confirmed references and the existing distinct-person ambiguity margin.

Names accepted by the rule have `label_source=automatic`, are separately marked
in the GUI and are not reference examples. They become references only after
explicit human confirmation. Existing names and rejections are preserved;
removing a name records `user_cleared`, which prevents automatic reassignment.
Human edits and auto-acceptance retain revision guards, audit entries and Parquet
provenance. The rule checks reference names and rejections again before writing.
Pausing stops future passes and retains names already accepted. Failed passes
roll back their transaction and expose an error in the settings panel; earlier
successful passes stay saved. A rotating cursor prevents stale/unreadable photos
from indefinitely blocking later candidates. Refresh the library to see changes.

Grafana measures matching and automatic acceptance as separate stages in the
value stream map; stage percentages describe processing time, not match quality.

### Names, GPS context and searchable groups

`context-worker` is independent of face extraction and the original caption worker.
It reads a pinned DuckDB/Parquet generation, queues already-captioned GPS photos and photos with saved person labels in
PostgreSQL, caches nearby Wikimedia articles, and sends the image, prior caption,
saved names with face-box positions and nearby candidates to the local Ollama model.
Names and photos never go to Wikimedia. Names alone qualify without GPS; no GPS
means no external lookup. Changes to saved labels requeue contextual captions after
the next snapshot. The GUI immediately hides a contextual caption whose person
labels no longer match, preserving the original caption while it regenerates. Existing captions and all human annotations are retained.
The gallery prefers the separate contextual caption after the next snapshot export;
photo details retain the original and link the lookup sources. Saved face labels
also appear on gallery cards without guessing identity from the caption.

Wikimedia receives only coordinates rounded to 0.001 degrees, not photos, names,
paths or timestamps. Rounding reduces precision; it does not anonymize location.
Lookups use a 1.5 km radius and at most eight candidates. Candidates are explicitly
unverified subjects: camera position does not establish what the camera sees.
Short descriptions come from Wikidata (CC0); source URL, Wikidata ID, provider
version and retrieval time are retained. Positive and empty lookups are cached.
One worker holds a PostgreSQL advisory lock, so network requests are serialized.
The durable budget permits 1,000 uncached requests per UTC database day, reserves
20 seconds between starts and at least five seconds after completion, and honors
Retry-After/maxlag. Calls run outside transactions. Failed jobs retry with bounded
backoff and stop after five failures; throttling does not consume that limit.
A process restart recovers unfinished jobs under the singleton lock. Changed input,
model or context version requeues a photo without overwriting the original summary.

Deploy using `CB_HOST` from the inventory:
`python3 scripts/knowledge-index/deploy-photo-postgres.py context`
An optional `--first-photo FILENAME` prioritizes a rollout example. Deployment
reuses the active summary worker's endpoint/model and writes a versioned systemd
service. The pipeline value stream map and Photo App dashboard show context queue,
lookup, LLM, commit, cache use and structured errors. No location or photo identity
appears in telemetry. Context results and the place cache join immutable exports.

Provider references: [nearby places](https://www.mediawiki.org/wiki/API:Nearby_places_viewer),
[robot policy](https://wikitech.wikimedia.org/wiki/Robot_policy),
[rate limits](https://www.mediawiki.org/wiki/Wikimedia_APIs/Rate_limits),
[Wikidata licensing](https://www.wikidata.org/wiki/Wikidata:Licensing).

### Network attribution and catalog refresh

`CB_HOST=... python3 scripts/knowledge-index/check-photo-network.py` reports network
counter deltas, PostgreSQL socket bytes, service start times and catalog errors.
The November 18 17:39:47 Pacific PostgreSQL cutover matches the traffic change
around commit cc6b220. Physical NIC, bridge and VM TAP counters overlap and must
not be summed as independent traffic. Repeated remote embedding reads were an
avoidable contributor. Matching now reads embeddings from local Parquet/DuckDB,
overlays recent review labels, and reuses results until faces/reviews/snapshot change.
New face detections appear after the next analytical snapshot.

Catalog refresh uses transactional DELETE/COPY instead of TRUNCATE and avoids
replacing an unchanged view. This allows existing MVCC readers to continue while
refreshing the catalog, eliminating the observed AccessExclusiveLock deadlock path.
The prior catalog remains visible until commit; a failed refresh rolls back.

The export builds `photo_search.parquet` and `photo_group_index.parquet` locally
from the same immutable generation. They index dates, saved names, inferred nearby
places, original/enriched captions, model tags and user group annotations. Group
index dates use UTC; selection suggestions respect the GUI timezone. Manual
locations override derived nearby labels. Grouping never assigns identities to
unlabelled faces. DuckDB serves global multi-term search and selection suggestions;
the GUI prefills shared date/location/tags while retaining edits and saved groups.
The search/group index refreshes with the five-minute export and is fully rebuildable.
Cached nearby-place results also populate the index for every photo in the same
rounded coordinate cell, without waiting for its contextual caption. Short search
terms (such as a one-letter saved name) match whole words, avoiding accidental
substring matches across file extensions and captions.

### Closest matches and review groups

Every face card and face detail shows its closest manually confirmed candidate,
cosine similarity and qualification result. Low-score, ambiguous and rejected
candidates remain visible but cannot enter suggested-name confirmation or automatic
acceptance. Missing/invalid embeddings, incompatible reference models, no references
and background calculation have explicit reasons instead of a fabricated zero.
A confirmed face never compares to itself; its saved identity stays unchanged.

The default **Review groups** collection displays one representative per repeated group,
with the number of member detections. Single detections remain accessible in the
separate **Ungrouped faces** collection and in **All faces**, with closest-match
explanations. Counts distinguish groups, ungrouped faces and total detections. Qualifying suggestions form collections by
suggested person. Other faces are grouped conservatively using their existing
embeddings: an exact cosine comparison must reach 0.80 against a fixed anchor.
Approximate, bounded candidate lookup may split similar appearances into separate
groups; it does not bypass the threshold or chain distant faces together. Invalid
vectors remain separate. No inference rerun, deletion or implicit labeling occurs.
**All faces** retains access to every detection, including named faces.

Open **Review group** to inspect its members. **Select all faces in this group**
selects current unnamed members across pages; the user must then explicitly
confirm suggested names or assign a name. Selection carries the current group
generation and each face's revision. A changed group requires refresh; existing
per-face write conflict checks still apply. Selecting a representative does not
silently label its group. Group and detection counts are presented separately.

Ranking and grouping run in the existing background matching pass, not HTTP
requests. The GUI reads the last completed pass; startup displays a pending state
until it exists. Candidates stream from a single local analytical query in bounded
batches; each batch no longer rescans and sorts the entire Parquet face table.
Normalized reference embeddings are reused across all batches.
The cache is invalidated when faces, human reviews, rejections
or the analytical snapshot change. Existing automatic-acceptance preferences and
its minimum-score setting are preserved.

Validation: `test-face-review-groups.py`, `test-photo-review.js` and
`test-photo-postgres.sh`. `audit-face-review.py` reports live aggregate counts
without outputting names, embeddings, photos or captions.
