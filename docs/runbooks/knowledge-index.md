# Knowledge index (DuckDB over Parquet)

One queryable inventory of everything the homelab ingests (issue #212). Phase 1: Google Photos. Drive/OneDrive
adapters and the `copies` refresher are Phase 2; document text search is Phase 3.

Never run index builds or queries inside K3s VM 105 (bulk disk writes there stall etcd). Everything runs **on the host**
via `scripts/knowledge-index/knowledge-index-ctl.sh` (`CB_HOST=root@<host>` from the laptop).

## Layout

```
<host>/local-3TB-backup/knowledge-index/      dataset: recordsize 1M, lz4
  files/<source>/<unit>.parquet               facts, immutable per unit (+ <unit>.versions.parquet for .versions/)
  gphotos_sidecars/<unit>.parquet             raw Takeout sidecar fields, one row per .json
  copies/<location>.parquet                   mutable; Phase 2 (an empty typed file until then)
  knowledge.duckdb                            views only, no data; `ctl rebuild` recreates it
/opt/knowledge-index/                         venv (duckdb 1.5.6), adapters/, kidx.py, knowledge.sql, index-unit.sh
```

`unit` = Takeout archive file name, `backfill-YYYYMMDD` for the one-off pass, a sync-run id for rclone sources.
Parquet is written to `<name>.tmp` and renamed, so re-running a unit replaces its file. When two units deliver the same
path the later one wins in the views (`files`, `gphotos_sidecars`).

## Common schema: `files`

| column | type | meaning |
|---|---|---|
| source | VARCHAR | `gphotos` / `gdrive` / `onedrive` |
| unit | VARCHAR | archive or run that delivered it |
| path | VARCHAR | relative to the source root as stored in the primary, e.g. `Google Photos/Photos from 2023/IMG_1.jpg` (`.versions/<date>/...` for replaced older copies) |
| name, ext | VARCHAR | file name; lower-case extension without dot |
| size_bytes | BIGINT | |
| mtime | TIMESTAMP | mtime in the primary (UTC) |
| kind | VARCHAR | `media` (jpg jpeg heic png gif webp mp4 mov 3gp avi mpg m4v) / `sidecar` (.json) / `other` |
| hash_algo, hash | VARCHAR NULL | only when free (Drive md5, OneDrive sha1/quickxor); not computed for Photos |
| origin_id | VARCHAR NULL | Photos: the sidecar's `url` (on the sidecar row); Drive/OneDrive: rclone `ID` |
| ingested_at | TIMESTAMP | |

`gphotos_sidecars`: `path`, `title`, `target_name` (media file the sidecar describes, `(n)` duplicate suffix re-inserted),
`description`, `upload_ts` (`creationTime`), `taken_ts` (`photoTakenTime`), `geo_lat/lon/alt`, `url`, `device_type`,
`device_folder`, `app_package`, `views`, `favorited`, `people[]`, `parse_error` (unparseable sidecar: NULLs + the error).

## Views (knowledge.sql)

`files`, `gphotos_sidecars`, `copies` (latest-wins / typed), `gphotos_files` (library), `gphotos_versions` (`.versions/`),
`gphotos_media` (every non-sidecar library file joined to its sidecar **across the whole library**, so a photo and sidecar
from different archives still match; exposes `upload_ts`, `taken_ts`, `has_geo`, `album`, `is_edited`),
`gphotos_album_dup`, `gphotos_quota`.

Quota rule (ported exactly from `scripts/backup/host/gphotos-quota-list.py`, which stays the oracle): a file counts when
uploaded on/after 2021-06-01 UTC (`quota_reason = uploaded-on-or-after-cutoff`) or it has no usable sidecar (`no-sidecar`: a
sidecar needs a title and an upload time), excluding album duplicates (a file in a non-`Photos from YYYY` folder with the
same (name, size) as one in a year folder). Like the oracle, every non-`.json` file is a candidate (`kind` `media` or `other`),
and the matched sidecars ride along as `kind = 'sidecar'` rows.

## Adapter contract (source #4 is cheap)

`scripts/knowledge-index/adapters/<source>.py` exposes `emit(unit, root, out_dir)` that

- writes `files/<source>/<unit>.parquet` (+ source-specific tables) with exactly the `files` schema above;
- is idempotent (tmp + atomic rename), reads only from `root` (read-only), never writes outside `out_dir`;
- prints one summary line: `rows=N bytes=B seconds=S`.

The Photos adapter also takes `--paths-from FILE` (index only what an archive just delivered) and `--versions DIR`.

## Operations

```bash
export CB_HOST=root@<host>                          # laptop: DNS is hijacked by a VPN, use the host's address
scripts/knowledge-index/install-duckdb.sh           # once: pinned duckdb venv
scripts/knowledge-index/knowledge-index-ctl.sh install       # copy adapter + SQL, create the dataset (idempotent)
scripts/knowledge-index/knowledge-index-ctl.sh backfill start   # index the existing library as backfill-<date>
scripts/knowledge-index/knowledge-index-ctl.sh backfill status
scripts/knowledge-index/knowledge-index-ctl.sh quota-diff    # index vs gphotos-quota-list.py: must be empty
scripts/knowledge-index/knowledge-index-ctl.sh status        # counts, parquet files, index_pending units
scripts/knowledge-index/knowledge-index-ctl.sh query "SELECT ..."
```

### Ingest hook and `index_pending`

`gphotos-ingest-host.sh` writes the library-relative paths an archive delivered to `_staging/<archive>.moved`, then calls
`/opt/knowledge-index/index-unit.sh` **before** appending to `_ingested.tsv`. If indexing fails the ingest continues, library
and ledger are untouched, and the unit is appended to `<photos dataset>/_index_pending.tsv`. Fix: `ctl backfill start`
re-walks the whole library (latest unit wins, no duplicates) and clears the list. `gphotos-ingest-ctl.sh start` installs the
index files first.

## Example queries (these double as checks)

```sql
-- quota set, same as gphotos-quota-list.py (library-relative paths: the oracle prints them with a "gphotos/library/" prefix)
SELECT path FROM gphotos_quota ORDER BY path;
-- what would deleting a year free (counted media, GB)
SELECT strftime(to_timestamp(taken_ts),'%Y') y, count(*) n, round(sum(size_bytes)/1e9,2) gb FROM gphotos_quota WHERE kind='media' GROUP BY 1 ORDER BY 1;
-- media without a sidecar
SELECT count(*) FROM gphotos_media WHERE upload_ts IS NULL;
-- counted by Google but missing on the SSK (the pre-delete safety check; needs Phase 2 copies)
SELECT q.path FROM gphotos_quota q LEFT JOIN copies c ON c.source='gphotos' AND c.path=q.path AND c.location='ssk' WHERE c.path IS NULL;
```

Note: the per-year query groups by `taken_ts`; the issue's "Photos from YYYY" year table (`scripts/backup/gphotos-quota-by-year.sh`)
groups by folder. To reproduce that table: `GROUP BY regexp_extract(path, 'Photos from ([0-9]{4})', 1)`.

## Golden numbers (2026-11-16, for the real-library acceptance run)

Library 243,088 files + `.versions` 6,753 = ledger 249,841; media 118,987; `.json` 119,670. Quota selection 18,264 paths / 88,693 MB;
2023 counted media 1,940 files / 26.55 GB.

## Tests

`scripts/knowledge-index/test-knowledge-index.sh` (local, python3 + duckdb): same fixture as `test-gphotos-quota-list.sh`
plus cross-archive sidecars, corrupt sidecar, re-run idempotency, later-unit-wins, and the hook's forced-failure path.
