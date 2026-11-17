## ADDED Requirements

### Requirement: Summaries are stored per file, enricher and batch
The system SHALL store each summary as a row identified by source, path and enricher id, with the model, prompt version, summary
text, tags, status, error text, creation time, and the size in bytes of the file that was summarized. For videos it SHALL also store
the number of frames sampled and the clip duration. Rows SHALL be written as immutable Parquet batches under the index; a re-run of a
batch SHALL replace that batch's file and SHALL NOT create duplicate rows.

#### Scenario: Latest summary wins
- **WHEN** the same file has been summarized twice by the same enricher id
- **THEN** queries on `media_summaries` return only the row with the later creation time

#### Scenario: A new model or prompt does not destroy old results
- **WHEN** a run uses a different enricher id
- **THEN** earlier summaries remain queryable under their own enricher id

### Requirement: The work queue is derived from the index
The system SHALL select files to summarize with a SQL view over the index: media files that have no row with status `ok` for the
same enricher id and the same file size. A file whose bytes changed SHALL re-enter the queue. A file whose last attempt failed SHALL stay
in the queue.

#### Scenario: Summarized file leaves the queue
- **WHEN** a file has an `ok` summary for the current enricher id and size
- **THEN** it is absent from the queue for that enricher

#### Scenario: Failed file is retried
- **WHEN** the only row for a file has status `error`
- **THEN** the file is still in the queue

### Requirement: Photos and videos are both described
The system SHALL produce a summary and tags for each photo and each video. A photo summary SHALL use the image plus known context
(date, place, people names, album). A video summary SHALL use frames sampled across the clip, the audio transcript when speech is
present, and the same context. A video without audio SHALL still be summarized from frames.

#### Scenario: Silent video
- **WHEN** a video has no audio track
- **THEN** a summary is produced from its frames and the row has status `ok`

#### Scenario: Unreadable file
- **WHEN** a file cannot be decoded
- **THEN** a row with status `error` and the error text is written and the run continues with the next file

### Requirement: The GPU is handed over from Frigate and always handed back
While a summary run is active the system SHALL stop Frigate to free the GPU, and SHALL restore Frigate when the run ends for any
reason (queue empty, failure, stop request, or time limit). A run SHALL have a maximum duration after which it hands the GPU back
and resumes later. Frigate's desired state in Git SHALL NOT be modified by a run, and the GitOps controller SHALL NOT undo the stop mid-run.

#### Scenario: Normal run
- **WHEN** a run starts with a non-empty queue
- **THEN** Frigate is scaled down before the model loads and scaled back up after the last batch

#### Scenario: Run crashes
- **WHEN** the run process fails or is killed
- **THEN** Frigate is restored automatically (no operator action) and the failure is reported

#### Scenario: Time limit
- **WHEN** a run reaches its maximum duration with files still queued
- **THEN** it finishes the current batch, restores Frigate, and leaves the rest for the next trigger

### Requirement: New photos trigger a run automatically
The system SHALL start a summary run after an ingest adds media files that have no `ok` summary, and SHALL NOT start one when the
queue is empty. Triggers arriving while a run is active SHALL NOT start a second concurrent run.

#### Scenario: Ingest delivers new media
- **WHEN** an archive ingest finishes indexing and the queue is non-empty
- **THEN** a summary run is started without operator action

#### Scenario: Nothing new
- **WHEN** an ingest delivers no new media
- **THEN** Frigate is not stopped

### Requirement: Runs are safe for the data
The system SHALL read media read-only and write only below the index dataset. It SHALL process in bounded batches so stopping a run
loses at most one batch. It SHALL NOT send any media, metadata or summaries to a service outside the home network.

#### Scenario: Stopped mid-run
- **WHEN** a run is stopped
- **THEN** all completed batches are intact and the next run continues from the queue

### Requirement: Operators can sample before a full run
The system SHALL offer a sample mode that summarizes N queued files, prints the results, and writes nothing to the index, and a
status command that reports queue size, completed count, errors, and seconds per item.

#### Scenario: Dry run
- **WHEN** an operator runs a sample of 20 files
- **THEN** 20 summaries are printed and `media_summaries` is unchanged

### Requirement: Index, enrichment and disk health are published as metrics
The system SHALL publish metrics at least every 10 minutes for the index (file counts and bytes by kind, sidecars, units, files that failed to index), the Google quota selection (counts and bytes, by year taken), the ingest pipeline (archives, last run status and time), the enrichment (rows by status, queue size, last batch time, run active) and the SMART health of the host's data disks. Collection SHALL NOT fail when the index cannot be read: it SHALL report an unhealthy status instead.

#### Scenario: Index unreadable
- **WHEN** the index cannot be opened
- **THEN** the exporter still writes its health metric with value 0

### Requirement: The dashboard shows the value delivered
The dashboard SHALL lead with value measures: files indexed and items summarized per minute, how long the quota question takes against how long it took before the index, index size against library size, and an equivalent cloud cost. The cloud cost SHALL be labelled illustrative and SHALL use prices the operator can edit, because no cloud service performs this work.

#### Scenario: Cloud comparison assumptions
- **WHEN** the operator changes the per-photo or per-video-minute price variable
- **THEN** the cost panel recomputes from the unchanged counts of described photos and video minutes

### Requirement: Dashboard and alerts are stored in Git
The system SHALL provide a dashboard and alert rules for these metrics, both stored in Git and applied by the GitOps controller. An alert SHALL fire when metrics go stale, when ingested units are not indexed, when enrichment stalls or mostly fails, when a data disk reports pending sectors, and when a host reboots.

#### Scenario: Failing disk
- **WHEN** a data disk reports pending or uncorrectable sectors
- **THEN** a warning alert names the disk by model

#### Scenario: Dashboard matches the code
- **WHEN** the dashboard generator is run
- **THEN** its output equals the committed dashboard, and every metric used by the dashboard and alerts is one the exporter provides
