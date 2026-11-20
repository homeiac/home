-- Knowledge index views (issue #212). Applied by kidx.py rebuild; @INDEX@ = the index dataset mount point.
-- No data lives in knowledge.duckdb: every view reads the immutable Parquet below @INDEX@, so a rule
-- change (e.g. the quota cutoff) never needs a re-ingest.

-- ---- common facts: latest row wins when a later unit re-delivers a path (a re-exported, replaced file)
CREATE OR REPLACE VIEW files AS
SELECT * FROM read_parquet('@INDEX@/files/*/*.parquet', union_by_name = true)
QUALIFY row_number() OVER (PARTITION BY source, path ORDER BY ingested_at DESC, unit DESC) = 1;

-- ---- Photos raw sidecar fields (one row per .json), same latest-wins rule (the newer unit's file name sorts later: units are archive names / backfill-YYYYMMDD)
CREATE OR REPLACE VIEW gphotos_sidecars AS
SELECT * EXCLUDE (filename) FROM read_parquet('@INDEX@/gphotos_sidecars/*.parquet', union_by_name = true, filename = true)
QUALIFY row_number() OVER (PARTITION BY path ORDER BY filename DESC) = 1;

-- ---- mutable per-location inventory (Phase 2 fills it; empty and typed until then)
CREATE OR REPLACE VIEW copies AS
SELECT * FROM read_parquet('@INDEX@/copies/*.parquet', union_by_name = true);

-- ---- Photos: library files vs. replaced older copies kept under .versions/
CREATE OR REPLACE VIEW gphotos_files AS
SELECT * FROM files WHERE source = 'gphotos' AND path NOT LIKE '.versions/%';

CREATE OR REPLACE VIEW gphotos_versions AS
SELECT * FROM files WHERE source = 'gphotos' AND path LIKE '.versions/%';

-- ---- sidecars that carry a title AND an upload time (the only ones that identify a photo's upload date),
-- ---- each with the two file names it can describe: the title itself and "<stem>-edited<ext>"
CREATE OR REPLACE VIEW gphotos_sidecar_targets AS
SELECT s.*,
       regexp_replace(path, '/[^/]+$', '') AS folder,
       CASE WHEN regexp_matches(target_name, '^.+\.[^.]*$')
            THEN regexp_replace(target_name, '^(.+)(\.[^.]*)$', '\1-edited\2')
            ELSE target_name || '-edited' END AS edited_name
FROM gphotos_sidecars s
WHERE title IS NOT NULL AND upload_ts IS NOT NULL;

-- ---- every non-sidecar library file (kind media or other, as gphotos-quota-list.py: it treats every
-- ---- non-.json file as media) joined to its sidecar by (folder, title incl. "(n)" suffix, "-edited")
CREATE OR REPLACE VIEW gphotos_media AS
WITH m AS (
  SELECT f.*, regexp_replace(f.path, '/[^/]+$', '') AS folder FROM gphotos_files f WHERE f.kind <> 'sidecar'
), cand AS (
  SELECT m.path AS media_path, t.path AS sidecar_path,
         CASE WHEN m.name = t.target_name THEN 1 ELSE 2 END AS prio
  FROM m JOIN gphotos_sidecar_targets t
    ON t.folder = m.folder AND (m.name = t.target_name OR m.name = t.edited_name)
), best AS (
  SELECT media_path, sidecar_path FROM cand
  QUALIFY row_number() OVER (PARTITION BY media_path ORDER BY prio, sidecar_path) = 1
)
SELECT m.path, m.name, m.ext, m.kind, m.size_bytes, m.mtime, m.unit, m.folder,
       regexp_extract(m.folder, '[^/]+$') AS folder_name,
       b.sidecar_path,
       t.upload_ts, t.taken_ts, t.url, t.description, t.device_type, t.favorited, t.people,
       NOT (coalesce(t.geo_lat, 0) = 0 AND coalesce(t.geo_lon, 0) = 0) AS has_geo,
       CASE WHEN regexp_matches(regexp_extract(m.folder, '[^/]+$'), '^Photos from [0-9]{4}$') THEN NULL
            ELSE regexp_extract(m.folder, '[^/]+$') END AS album,
       regexp_matches(m.name, '-edited(\.[^.]*)?$') AS is_edited
FROM m
LEFT JOIN best b ON b.media_path = m.path
LEFT JOIN gphotos_sidecar_targets t ON t.path = b.sidecar_path;

-- ---- album duplicate: a media file in an album folder with the same (name, size) as one in a "Photos from YYYY" folder
CREATE OR REPLACE VIEW gphotos_album_dup AS
SELECT a.* FROM gphotos_media a
WHERE a.album IS NOT NULL
  AND EXISTS (SELECT 1 FROM gphotos_media y WHERE y.album IS NULL AND y.name = a.name AND y.size_bytes = a.size_bytes);

-- ---- counts against Google quota: uploaded on/after 2021-06-01 UTC (epoch 1622505600) or no sidecar, minus album
-- ---- duplicates; the matched sidecar files ride along (kind = 'sidecar'), exactly the set gphotos-quota-list.py prints
CREATE OR REPLACE VIEW gphotos_quota AS
WITH sel AS (
  SELECT m.*, CASE WHEN m.upload_ts IS NULL THEN 'no-sidecar' ELSE 'uploaded-on-or-after-cutoff' END AS quota_reason
  FROM gphotos_media m
  WHERE (m.upload_ts IS NULL OR m.upload_ts >= 1622505600)
    AND NOT EXISTS (SELECT 1 FROM gphotos_album_dup d WHERE d.path = m.path)
)
SELECT path, name, kind, size_bytes, taken_ts, upload_ts, quota_reason FROM sel
UNION
SELECT s.path, f.name, 'sidecar', f.size_bytes, NULL, NULL, s.quota_reason
FROM (SELECT DISTINCT sidecar_path AS path, quota_reason FROM sel WHERE sidecar_path IS NOT NULL) s
JOIN gphotos_files f ON f.path = s.path;

-- ---- AI enrichment (photo/video summaries from a local GPU model): written by enrichers, one Parquet per
-- ---- (enricher, batch) under summaries/<enricher>/; typed and empty until the first enricher runs.
-- ---- Latest row wins per (source, path, enricher); `size_bytes` records which bytes were summarized.
CREATE OR REPLACE VIEW media_summaries AS
SELECT * FROM read_parquet('@INDEX@/summaries/*/*.parquet', union_by_name = true)
QUALIFY row_number() OVER (PARTITION BY source, path, enricher ORDER BY created_at DESC) = 1;

-- ---- work queue for an enricher: media with no successful summary for their current bytes, with the context the
-- ---- prompt needs. A table macro (not a view) so a brand-new enricher id works before it has any rows:
-- ----   SELECT path FROM gphotos_to_summarize('qwen25vl-3b-p1') ORDER BY taken_ts DESC LIMIT 500
CREATE OR REPLACE MACRO gphotos_to_summarize(enr) AS TABLE
SELECT m.path, m.name, m.ext, m.size_bytes, m.taken_ts, m.album, m.has_geo, m.people, m.description
FROM gphotos_media m
LEFT JOIN media_summaries s
  ON s.source = 'gphotos' AND s.path = m.path AND s.enricher = enr AND s.size_bytes = m.size_bytes AND s.status = 'ok'
WHERE m.kind = 'media' AND s.path IS NULL;
