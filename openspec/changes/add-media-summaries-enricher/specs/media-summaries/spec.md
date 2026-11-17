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

### Requirement: Runs are safe for the shared GPU and the data
The system SHALL read media read-only and write only below the index dataset. It SHALL check free GPU memory before loading a model
and SHALL stop or wait instead of starving the Frigate detector. It SHALL process in bounded batches so stopping a run loses at most
one batch. It SHALL NOT send any media, metadata or summaries to a service outside the home network.

#### Scenario: Not enough GPU memory
- **WHEN** free GPU memory is below the configured minimum
- **THEN** the run does not start the model and reports why

#### Scenario: Stopped mid-run
- **WHEN** a run is stopped
- **THEN** all completed batches are intact and the next run continues from the queue

### Requirement: Operators can sample before a full run
The system SHALL offer a sample mode that summarizes N queued files, prints the results, and writes nothing to the index, and a
status command that reports queue size, completed count, errors, and seconds per item.

#### Scenario: Dry run
- **WHEN** an operator runs a sample of 20 files
- **THEN** 20 summaries are printed and `media_summaries` is unchanged
