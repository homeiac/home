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

An optional **Ask Frigate** action reuses its existing face library through [POST /api/faces/recognize](https://docs.frigate.video/integrations/api/recognize-face-faces-recognize-post/). Set `PHOTO_FRIGATE_URL` to the trusted internal Frigate origin and `PHOTO_FRIGATE_TOKEN` to an authenticated admin bearer token when required, sourced from your existing protected environment. Never put credentials in source or command-line arguments. This action sends only the selected face crop to that configured service; it does not train Frigate. Redirects are refused. Its candidate still requires confirmation. Live Frigate integration has not been validated by this change.

The summary worker and this enrichment process can run independently: GPU captions and CPU metadata/faces join by photo identity. They do not share the writable enrichment database. There is no automatic scheduler in this change. Frigate GPU lookups could compete with summary inference; benchmark a representative photo sample before enabling bulk integration. Security-camera-trained Frigate+ object models also need evaluation on personal photos before replacing YuNet.

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

Default binding is loopback. The server checks Host, uses a per-run CSRF token and blocks cross-origin writes. It has no user authentication. For any shared deployment, place it behind the existing internal Traefik gateway with access control, pass the exact HTTPS `--public-origin`, and follow the homelab GitOps workflow. Do not expose it to the internet. No deployment is included in this worktree.

```bash
/tmp/photo-enrichment-venv/bin/python scripts/knowledge-index/test-photo-enrichment.py
PYTHON=/tmp/photo-enrichment-venv/bin/python bash scripts/knowledge-index/test-knowledge-index.sh
```

Tests use generated fixtures and a mock recognizer to check GPS precedence, timezone handling, traversal rejection, annotation isolation, face confirmation, resumability, Parquet and HTTP controls. They verify the source catalog remains byte-for-byte unchanged. The actual CPU model backend was also exercised on the synthetic demo; this tests loading/inference, not recognition accuracy on real faces. Chrome verification covered selecting a date, saving shared context to two photos and reading it back in photo details.
