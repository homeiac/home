-- This schema belongs to reconciliation, in photo_enrichment, never Immich's DB.
CREATE SCHEMA IF NOT EXISTS immich_sync;
CREATE TABLE IF NOT EXISTS immich_sync.jobs (
 source_path text PRIMARY KEY, source_hash text NOT NULL, payload jsonb NOT NULL,
 asset_id text, state text NOT NULL DEFAULT 'pending', reason text,
 applied jsonb, intent jsonb, content_sha256 text, file_mtime_ms double precision,
 attempts integer NOT NULL DEFAULT 0, available_at timestamptz NOT NULL DEFAULT now(),
 discovered_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 applied_at timestamptz, verified_at timestamptz, cycle_id text NOT NULL,
 CHECK(state IN ('pending','applied','conflict','error','excluded','missing'))
);
CREATE TABLE IF NOT EXISTS immich_sync.state (
 key text PRIMARY KEY,value jsonb NOT NULL,updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS immich_sync.people (
 source_person text PRIMARY KEY,person_id text NOT NULL,evidence jsonb NOT NULL,updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS immich_sync.faces (
 source_face text PRIMARY KEY,source_path text NOT NULL,asset_id text NOT NULL,face_id text,
 person_id text,source_hash text NOT NULL,state text NOT NULL,reason text,updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS immich_sync.albums (
 source_group text PRIMARY KEY,album_id text,source_hash text,state text NOT NULL,
 intent jsonb,updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS immich_sync.operations (
 source_path text NOT NULL,kind text NOT NULL,version text NOT NULL,intent jsonb NOT NULL,
 result jsonb,verified_at timestamptz,PRIMARY KEY(source_path,kind,version)
);
CREATE INDEX IF NOT EXISTS immich_sync_jobs_pending ON immich_sync.jobs(state,available_at);
