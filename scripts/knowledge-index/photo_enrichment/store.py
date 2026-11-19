"""Separate writable enrichment store over a read-only knowledge-index catalog."""
import datetime as dt
import io
import json
import math
from pathlib import Path
import threading
import uuid
from functools import wraps
from zoneinfo import ZoneInfo

import duckdb

from .faces import MODEL_ID, similarity
from .metadata import VERSION, PHOTO_EXTENSIONS, contained, oriented_image, read_metadata
from .metrics import Metrics


UPSERT_COLUMNS = {
    'extracted': 'path size_bytes mtime_ns capture_ts capture_source latitude longitude altitude gps_source camera_make camera_model width height error version'.split(),
    'photo_groups': 'id event location venue notes tags timezone'.split(),
    'face_scans': 'path size_bytes mtime_ns model'.split(),
}


SCHEMA_SQL = """
            CREATE TABLE IF NOT EXISTS extracted (
                path VARCHAR PRIMARY KEY, size_bytes BIGINT, mtime_ns BIGINT, capture_ts DOUBLE,
                capture_source VARCHAR, latitude DOUBLE, longitude DOUBLE, altitude DOUBLE, gps_source VARCHAR,
                camera_make VARCHAR, camera_model VARCHAR, width INTEGER, height INTEGER,
                error VARCHAR, version VARCHAR, updated_at TIMESTAMP DEFAULT current_timestamp);
            CREATE TABLE IF NOT EXISTS photo_groups (
                id VARCHAR PRIMARY KEY, event VARCHAR, location VARCHAR, venue VARCHAR, notes VARCHAR,
                tags VARCHAR[], timezone VARCHAR, updated_at TIMESTAMP DEFAULT current_timestamp);
            CREATE TABLE IF NOT EXISTS group_members (
                group_id VARCHAR, path VARCHAR, size_bytes BIGINT, PRIMARY KEY(group_id, path));
            CREATE TABLE IF NOT EXISTS faces (
                id VARCHAR PRIMARY KEY, path VARCHAR, size_bytes BIGINT, mtime_ns BIGINT,
                box DOUBLE[], confidence DOUBLE, embedding DOUBLE[], model VARCHAR,
                person VARCHAR, label_source VARCHAR, updated_at TIMESTAMP DEFAULT current_timestamp);
            CREATE TABLE IF NOT EXISTS face_scans (
                path VARCHAR PRIMARY KEY, size_bytes BIGINT, mtime_ns BIGINT, model VARCHAR);
            CREATE TABLE IF NOT EXISTS rejected_matches (
                face_id VARCHAR, reference_id VARCHAR, PRIMARY KEY(face_id, reference_id));
            CREATE TABLE IF NOT EXISTS annotation_history (
                id VARCHAR, action VARCHAR, payload VARCHAR, created_at TIMESTAMP DEFAULT current_timestamp);
        """

MEDIA_VIEW_SQL = """
            CREATE OR REPLACE TEMP VIEW enriched_media AS
            SELECT m.*, coalesce(e.capture_ts, m.taken_ts) AS capture_ts,
                   coalesce(e.capture_source, CASE WHEN m.taken_ts IS NOT NULL THEN 'takeout.photoTakenTime' END) AS capture_source,
                   CASE WHEN e.path IS NOT NULL THEN e.latitude
                        WHEN s.geo_lat BETWEEN -90 AND 90 AND s.geo_lon BETWEEN -180 AND 180
                             AND NOT(s.geo_lat=0 AND s.geo_lon=0) THEN s.geo_lat END AS latitude,
                   CASE WHEN e.path IS NOT NULL THEN e.longitude
                        WHEN s.geo_lat BETWEEN -90 AND 90 AND s.geo_lon BETWEEN -180 AND 180
                             AND NOT(s.geo_lat=0 AND s.geo_lon=0) THEN s.geo_lon END AS longitude,
                   CASE WHEN e.path IS NOT NULL THEN e.gps_source
                        WHEN s.geo_lat BETWEEN -90 AND 90 AND s.geo_lon BETWEEN -180 AND 180
                             AND NOT(s.geo_lat=0 AND s.geo_lon=0) THEN 'takeout.geoData' END AS gps_source,
                   e.camera_make, e.camera_model, e.error AS extraction_error, e.version AS extraction_version,
                   summary.summary, summary.tags AS summary_tags, summary.model AS summary_model
            FROM catalog.gphotos_media m
            LEFT JOIN catalog.gphotos_sidecars s ON s.path=m.sidecar_path
            LEFT JOIN extracted e ON e.path=m.path AND e.size_bytes=m.size_bytes
            LEFT JOIN (
                SELECT * FROM catalog.media_summaries WHERE status='ok'
                QUALIFY row_number() OVER (PARTITION BY path ORDER BY created_at DESC, enricher DESC)=1
            ) summary ON summary.path=m.path AND summary.size_bytes=m.size_bytes
            WHERE m.kind='media' AND m.ext IN ('jpg','jpeg','heic','png','gif','webp');
        """


def observed(stage: str | None = None):
    """Serialize mutations and refresh aggregate telemetry after the transaction."""
    def decorate(function):
        @wraps(function)
        def wrapped(self, *args, **kwargs):
            with self.lock:
                try:
                    if stage:
                        with self.metrics.measure(stage):
                            return function(self, *args, **kwargs)
                    return function(self, *args, **kwargs)
                finally:
                    self.refresh_metrics()
        return wrapped
    return decorate


def sql_path(path: Path) -> str:
    return "'" + str(path.resolve()).replace("'", "''") + "'"


class Store:
    """Serialize local writes; keep original media and source DuckDB untouched."""
    def __init__(self, index: Path, library: Path, state: Path, metrics: Metrics | None = None,
                 memory: bool = False):
        self.library = library.resolve()
        self.state = state.resolve()
        if self.state.is_relative_to(index.resolve()) or self.state.is_relative_to(self.library):
            raise ValueError("Use a separate state directory outside the source library and index root")
        self.state.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.metrics = metrics or Metrics()
        self.index = index
        self.db = duckdb.connect(":memory:" if memory else str(self.state / "enrichment.duckdb"))
        if memory:
            self.db.execute("SET threads=2; SET memory_limit='768MB'; ATTACH ':memory:' AS catalog")
            self.refresh_catalog()
        else:
            self.db.execute(f"ATTACH {sql_path(index / 'knowledge.duckdb')} AS catalog (READ_ONLY)")
        self.db.execute(SCHEMA_SQL)
        self.db.execute(MEDIA_VIEW_SQL)

    def upsert(self, table: str, values: list) -> None:
        """Use the same explicit upserts for local recovery and PostgreSQL stores."""
        columns = UPSERT_COLUMNS[table]
        assignments = ','.join(f'{c}=excluded.{c}' for c in columns[1:])
        if table != 'face_scans':
            assignments += ',updated_at=now()'
        self.db.execute(f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)}) ON CONFLICT ({columns[0]}) DO UPDATE SET {assignments}", values)

    def refresh_catalog(self) -> None:
        """Snapshot Parquet-backed source views in memory; release the source DB lock."""
        with self.lock:
            self.db.execute(f"ATTACH {sql_path(self.index / 'knowledge.duckdb')} AS source_catalog (READ_ONLY)")
            try:
                self.db.execute("BEGIN")
                for name in ("gphotos_media", "gphotos_sidecars", "gphotos_album_dup", "media_summaries"):
                    self.db.execute(f"CREATE OR REPLACE TABLE catalog.{name} AS SELECT * FROM source_catalog.{name}")
                self.db.execute("COMMIT")
            except Exception:
                self.db.execute("ROLLBACK")
                raise
            finally:
                self.db.execute("DETACH source_catalog")

    def face_library(self, person: str = "", status: str = "unreviewed", offset: int = 0, limit: int = 48) -> dict:
        """Paginate current face crops with named collections and review counts."""
        if status not in ("all", "unreviewed", "named") or not 0 <= offset or not 1 <= limit <= 100:
            raise ValueError("Invalid face filter")
        base = """FROM faces f JOIN face_scans fs ON fs.path=f.path AND fs.size_bytes=f.size_bytes
            AND fs.mtime_ns=f.mtime_ns AND fs.model=f.model
            JOIN enriched_media m ON m.path=f.path AND m.size_bytes=f.size_bytes
            WHERE NOT EXISTS (SELECT 1 FROM catalog.gphotos_album_dup d WHERE d.path=f.path)"""
        filters, params = "", []
        if status == "unreviewed": filters += " AND f.person IS NULL"
        if status == "named": filters += " AND f.person IS NOT NULL"
        if person:
            filters += " AND f.person=?"
            params.append(person)
        people = self.rows("SELECT person,count(*) AS faces " + base + " AND person IS NOT NULL GROUP BY person ORDER BY lower(person)")
        total = self.rows("SELECT count(*) n " + base + filters, params)[0]["n"]
        counts = self.rows("SELECT count(*) AS total, count(*) FILTER(WHERE f.person IS NULL) AS unreviewed " + base)[0]
        items = self.rows("SELECT f.id,f.path,f.box,f.confidence,f.person,f.label_source,f.updated_at AS revision,m.capture_ts,m.latitude,m.longitude,m.summary " + base + filters + " ORDER BY m.capture_ts DESC NULLS LAST,f.id LIMIT ? OFFSET ?", [*params,limit,offset])
        return dict(faces=items, people=people, total=total, offset=offset, counts=counts)

    def refresh_metrics(self) -> None:
        """Count current indexed facts without reading every original file."""
        if not self.metrics.path:
            return
        try:
            with self.lock, self.metrics.measure("queue"):
                counts = self.rows("""WITH photos AS (
                    SELECT * FROM enriched_media m WHERE NOT EXISTS
                    (SELECT 1 FROM catalog.gphotos_album_dup d WHERE d.path=m.path))
                    SELECT count(*) AS photos,
                    count(*) FILTER (WHERE e.path IS NOT NULL) AS exif,
                    count(*) FILTER (WHERE m.latitude IS NOT NULL) AS gps,
                    count(*) FILTER (WHERE e.error IS NOT NULL) AS exif_errors,
                    count(*) FILTER (WHERE e.path IS NULL OR e.error IS NOT NULL OR e.version<>?) AS pending_exif,
                    count(*) FILTER (WHERE fs.path IS NULL) AS pending_faces
                    FROM photos m LEFT JOIN extracted e ON e.path=m.path AND e.size_bytes=m.size_bytes
                    LEFT JOIN face_scans fs ON fs.path=m.path AND fs.size_bytes=m.size_bytes AND fs.model=?""", [VERSION, MODEL_ID])[0]
                faces = self.rows("""SELECT count(*) AS faces, count(f.person) AS named_faces
                    FROM faces f JOIN face_scans s ON s.path=f.path AND s.size_bytes=f.size_bytes
                    AND s.mtime_ns=f.mtime_ns AND s.model=f.model JOIN enriched_media m
                    ON m.path=f.path AND m.size_bytes=f.size_bytes""")[0]
                groups = self.rows("SELECT count(*) AS n FROM photo_groups")[0]["n"]
                self.metrics.snapshot({"exif": counts["pending_exif"], "faces": counts["pending_faces"],
                    "review": faces["faces"]-faces["named_faces"]}, {**counts, **faces, "groups": groups})
        except Exception:
            # Metrics must never turn a committed annotation into a failed request.
            import logging
            logging.warning("Photo telemetry inventory refresh failed")

    def rows(self, sql: str, parameters=()) -> list[dict]:
        with self.lock:
            result = self.db.execute(sql, parameters)
            names = [item[0] for item in result.description]
            return [dict(zip(names, values)) for values in result.fetchall()]

    def photo(self, path: str) -> dict:
        rows = self.rows("SELECT * FROM enriched_media WHERE path=?", [path])
        if not rows:
            raise ValueError("Unknown photo")
        return rows[0]

    def source_file(self, path: str) -> Path:
        row = self.photo(path)
        file = contained(self.library, path)
        if file.stat().st_size != row["size_bytes"]:
            raise ValueError("Photo changed since indexing; re-index it before enrichment")
        return file

    def dates(self, timezone: str) -> list[dict]:
        ZoneInfo(timezone)
        return self.rows("""
            SELECT coalesce(CAST(CAST(timezone(?, to_timestamp(capture_ts)) AS DATE) AS VARCHAR), 'unknown') AS date,
                   count(*) AS photos, count(*) FILTER (WHERE latitude IS NOT NULL) AS with_gps
            FROM enriched_media m
            WHERE NOT EXISTS (SELECT 1 FROM catalog.gphotos_album_dup d WHERE d.path=m.path)
            GROUP BY 1 ORDER BY 1 DESC
        """, [timezone])

    def photos(self, date: str, timezone: str, offset: int = 0, limit: int = 100) -> dict:
        ZoneInfo(timezone)
        if date != "unknown":
            dt.date.fromisoformat(date)
        if offset < 0 or not 1 <= limit <= 200:
            raise ValueError("Invalid pagination")
        condition = """coalesce(CAST(CAST(timezone(?,to_timestamp(capture_ts)) AS DATE) AS VARCHAR),'unknown')=?
            AND NOT EXISTS (SELECT 1 FROM catalog.gphotos_album_dup d WHERE d.path=m.path)"""
        total = self.rows("SELECT count(*) AS n FROM enriched_media m WHERE " + condition, [timezone, date])[0]["n"]
        photos = self.rows("SELECT * FROM enriched_media m WHERE " + condition + " ORDER BY capture_ts NULLS LAST, path LIMIT ? OFFSET ?",
                           [timezone, date, limit, offset])
        return dict(photos=photos, total=total, offset=offset)

    def detail(self, path: str) -> dict:
        photo = self.photo(path)
        photo["groups"] = self.rows("SELECT g.* FROM photo_groups g JOIN group_members m ON m.group_id=g.id WHERE m.path=? AND m.size_bytes=? ORDER BY g.updated_at DESC", [path, photo["size_bytes"]])
        file = self.source_file(path)
        photo["faces"] = self.rows("SELECT id, box, confidence, model, person, label_source, updated_at AS revision FROM faces WHERE path=? AND size_bytes=? AND mtime_ns=? ORDER BY id",
                                   [path, photo["size_bytes"], file.stat().st_mtime_ns])
        return photo

    def _history(self, action: str, payload: dict) -> None:
        self.db.execute("INSERT INTO annotation_history(id,action,payload) VALUES (?,?,?)",
                        [uuid.uuid4().hex, action, json.dumps(payload)])

    @observed("review")
    def save_group(self, data: dict) -> dict:
        paths = list(dict.fromkeys(data.get("paths", [])))
        if not paths or len(paths) > 1000 or not all(isinstance(p, str) for p in paths):
            raise ValueError("Select between 1 and 1000 photos")
        fields = {}
        for key in ("event", "location", "venue", "notes"):
            value = data.get(key, "")
            if not isinstance(value, str) or len(value) > 4000:
                raise ValueError("Invalid " + key)
            fields[key] = value.strip()
        tags = data.get("tags", [])
        if not isinstance(tags, list) or len(tags) > 50 or not all(isinstance(t, str) and 0 < len(t) <= 100 for t in tags):
            raise ValueError("Invalid tags")
        timezone = data.get("timezone", "UTC")
        ZoneInfo(timezone)
        if not any(fields.values()) and not tags:
            raise ValueError("Add at least one annotation")
        group_id = data.get("id") or uuid.uuid4().hex
        with self.lock:
            members = [(group_id, path, self.photo(path)["size_bytes"]) for path in paths]
            if data.get("id") and not self.rows("SELECT id FROM photo_groups WHERE id=?", [group_id]):
                raise ValueError("Unknown group")
            self.db.execute("BEGIN")
            try:
                self.upsert("photo_groups", [group_id, fields["event"], fields["location"], fields["venue"], fields["notes"], tags, timezone])
                self.db.execute("DELETE FROM group_members WHERE group_id=?", [group_id])
                self.db.executemany("INSERT INTO group_members VALUES (?,?,?)", members)
                self._history("save_group", dict(id=group_id, paths=paths, **fields, tags=tags, timezone=timezone))
                self.db.execute("COMMIT")
            except Exception:
                self.db.execute("ROLLBACK")
                raise
        return dict(id=group_id, photos=len(paths))

    def groups(self) -> list[dict]:
        return self.rows("SELECT g.*, (SELECT count(*) FROM group_members m WHERE m.group_id=g.id) AS photos FROM photo_groups g ORDER BY updated_at DESC")

    def group(self, group_id: str) -> dict:
        groups = self.rows("SELECT * FROM photo_groups WHERE id=?", [group_id])
        if not groups:
            raise ValueError("Unknown group")
        groups[0]["paths"] = [r["path"] for r in self.rows("SELECT path FROM group_members WHERE group_id=? ORDER BY path", [group_id])]
        return groups[0]

    @observed("review")
    def delete_group(self, group_id: str) -> None:
        with self.lock:
            original = self.group(group_id)
            self.db.execute("BEGIN")
            try:
                self.db.execute("DELETE FROM group_members WHERE group_id=?", [group_id])
                self.db.execute("DELETE FROM photo_groups WHERE id=?", [group_id])
                self._history("delete_group", {"id": group_id, "paths": original["paths"]})
                self.db.execute("COMMIT")
            except Exception:
                self.db.execute("ROLLBACK")
                raise

    @observed()
    def extract(self, paths: list[str], timezone: str, engine=None, force: bool = False) -> dict:
        ZoneInfo(timezone)
        if not paths or len(paths) > 1000:
            raise ValueError("Choose 1–1000 photos per extraction")
        results = dict(processed=0, skipped=0, faces=0, errors=[])
        # Batch catalog lookup avoids rescanning the Parquet-backed caption view twice
        # for every photo. Only the source identity and sidecar are needed to extract.
        with self.metrics.measure("queue"):
            sources = {row["path"]: row for row in self.rows("""SELECT path, size_bytes, sidecar_path
                FROM catalog.gphotos_media WHERE kind='media'
                AND ext IN ('jpg','jpeg','heic','png','gif','webp')
                AND path IN (SELECT unnest(?))""", [list(dict.fromkeys(paths))])}
        for path in dict.fromkeys(paths):
            try:
                with self.metrics.measure("queue"):
                    row = sources.get(path)
                    if row is None:
                        raise ValueError("Unknown photo")
                    file = contained(self.library, path)
                    st = file.stat()
                    if st.st_size != row["size_bytes"]:
                        raise ValueError("Photo changed since indexing; re-index it before enrichment")
                    previous = self.rows("SELECT * FROM extracted WHERE path=?", [path])
                unchanged = previous and previous[0]["size_bytes"] == st.st_size and previous[0]["mtime_ns"] == st.st_mtime_ns and previous[0]["version"] == VERSION and not previous[0]["error"]
                # Offset-free dates must be reinterpreted when the user changes timezone.
                if unchanged and (previous[0]["capture_source"] or "").startswith("exif.assumed:"):
                    unchanged = previous[0]["capture_source"] == "exif.assumed:" + timezone
                if not unchanged or force:
                    sidecar = contained(self.library, row["sidecar_path"]) if row["sidecar_path"] else None
                    with self.metrics.measure("exif"):
                        meta = read_metadata(file, sidecar, timezone)
                    after = file.stat()
                    if (after.st_size, after.st_mtime_ns) != (st.st_size, st.st_mtime_ns):
                        raise ValueError("Photo changed during extraction")
                    with self.lock, self.metrics.measure("persist"):
                        self.upsert("extracted", [path, st.st_size, st.st_mtime_ns] + list(meta.values()))
                    results["processed"] += 1
                    if meta["error"]:
                        results["errors"].append({"path": path, "error": meta["error"]})
                else:
                    results["skipped"] += 1
                if engine:
                    scan = self.rows("SELECT * FROM face_scans WHERE path=?", [path])
                    if scan and (scan[0]["size_bytes"], scan[0]["mtime_ns"], scan[0]["model"]) == (st.st_size, st.st_mtime_ns, MODEL_ID):
                        continue  # Never discard existing confirmed labels on a rerun.
                    with self.metrics.measure("faces"):
                        detected = engine.detect(file)
                    after = file.stat()
                    if (after.st_size, after.st_mtime_ns) != (st.st_size, st.st_mtime_ns):
                        raise ValueError("Photo changed during face detection")
                    with self.lock, self.metrics.measure("persist"):
                        self.db.execute("BEGIN")
                        try:
                            # Keep older face records as history, but only expose matching file identities.
                            for face in detected:
                                self.db.execute("INSERT INTO faces VALUES (?,?,?,?,?,?,?,?,NULL,NULL,current_timestamp)",
                                                [face["id"], path, st.st_size, st.st_mtime_ns, face["box"], face["confidence"], face["embedding"], face["model"]])
                            self.upsert("face_scans", [path, st.st_size, st.st_mtime_ns, MODEL_ID])
                            self.db.execute("COMMIT")
                        except Exception:
                            self.db.execute("ROLLBACK")
                            raise
                    results["faces"] += len(detected)
            except Exception as exc:
                results["errors"].append({"path": path, "error": str(exc)[:250]})
        return results

    def face(self, face_id: str) -> dict:
        rows = self.rows("SELECT * FROM faces WHERE id=?", [face_id])
        if not rows:
            raise ValueError("Unknown face")
        face = rows[0]
        st = self.source_file(face["path"]).stat()
        if (face["size_bytes"], face["mtime_ns"]) != (st.st_size, st.st_mtime_ns):
            raise ValueError("Face belongs to an older version of this photo")
        return face

    @observed("review")
    def label_face(self, face_id: str, person: str, revision=None) -> None:
        if not isinstance(person, str) or len(person) > 200:
            raise ValueError("Invalid person name")
        with self.lock:
            face = self.face(face_id)
            if revision is not None and str(face["updated_at"]) != str(revision):
                raise ValueError("This face was edited elsewhere; refresh before saving")
            self.db.execute("BEGIN")
            try:
                self.db.execute("UPDATE faces SET person=?,label_source=?,updated_at=current_timestamp WHERE id=?",
                                [person.strip() or None, "user" if person.strip() else None, face_id])
                self._history("label_face", {"id": face_id, "person": person.strip(), "previous": face["person"]})
                self.db.execute("COMMIT")
            except Exception:
                self.db.execute("ROLLBACK")
                raise

    def suggestions(self, face_id: str, threshold: float = 0.363) -> list[dict]:
        if not math.isfinite(threshold) or not -1 <= threshold <= 1:
            raise ValueError("Invalid similarity threshold")
        face = self.face(face_id)
        references = self.rows("""SELECT * FROM faces f WHERE person IS NOT NULL AND label_source='user' AND model=? AND id<>?
            AND NOT EXISTS (SELECT 1 FROM rejected_matches r WHERE r.face_id=? AND r.reference_id=f.id)""", [face["model"], face_id, face_id])
        candidates = []
        for reference in references:
            try:
                self.face(reference["id"])
            except (OSError, ValueError):
                continue
            score = similarity(face["embedding"], reference["embedding"])
            if score >= threshold:
                candidates.append(dict(reference_id=reference["id"], person=reference["person"], score=score, confirmed=False))
        return sorted(candidates, key=lambda row: -row["score"])[:10]

    def reject(self, face_id: str, reference_id: str) -> None:
        with self.lock:
            self.face(face_id); self.face(reference_id)
            self.db.execute("INSERT INTO rejected_matches VALUES (?,?) ON CONFLICT DO NOTHING", [face_id, reference_id])

    def thumbnail(self, path: str, face_id: str | None = None) -> bytes:
        image = oriented_image(self.source_file(path))
        if face_id:
            face = self.face(face_id)
            if face["path"] != path:
                raise ValueError("Face does not belong to this photo")
            x1, y1, x2, y2 = face["box"]
            image = image.crop((round(x1*image.width), round(y1*image.height), round(x2*image.width), round(y2*image.height)))
        image.thumbnail((960, 960))
        buffer = io.BytesIO()
        image.save(buffer, "JPEG", quality=85)  # Preview only; no EXIF copied into browser thumbnails.
        return buffer.getvalue()

    @observed("export")
    def export(self) -> dict:
        """Publish atomic Parquet snapshots for downstream DuckDB readers."""
        output = self.state / "parquet"
        output.mkdir(exist_ok=True)
        tables = ("extracted", "photo_groups", "group_members", "faces", "rejected_matches", "annotation_history")
        with self.lock:
            for table in tables:
                target = output / (table + ".parquet")
                temporary = target.with_suffix(".parquet.tmp")
                self.db.execute(f"COPY {table} TO {sql_path(temporary)} (FORMAT parquet, COMPRESSION zstd)")
                temporary.replace(target)
        return {"directory": str(output), "tables": list(tables)}

    def close(self) -> None:
        self.db.close()
