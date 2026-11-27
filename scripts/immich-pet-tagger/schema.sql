-- Reuse photo_enrichment's fenced SKIP LOCKED job pattern in an isolated schema.
CREATE TABLE IF NOT EXISTS waffles.settings (
  key text PRIMARY KEY, value jsonb NOT NULL
);
CREATE TABLE IF NOT EXISTS waffles.runs (
  id text PRIMARY KEY, mode text NOT NULL CHECK(mode IN ('benchmark','production')),
  state text NOT NULL DEFAULT 'paused' CHECK(state IN ('paused','running','complete')),
  workers text[] NOT NULL, config jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(), started_at timestamptz, finished_at timestamptz
);
CREATE TABLE IF NOT EXISTS waffles.jobs (
  run_id text NOT NULL REFERENCES waffles.runs(id), asset_id uuid NOT NULL,
  taken_at text NOT NULL, ordinal integer NOT NULL,
  status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','running','classified','complete','failed')),
  claim uuid, worker text, lease_until timestamptz,
  available_at timestamptz NOT NULL DEFAULT now(), attempts integer NOT NULL DEFAULT 0,
  result jsonb, processing_seconds double precision, completed_at timestamptz,
  applied integer NOT NULL DEFAULT 0, last_error text,
  PRIMARY KEY(run_id, asset_id)
);
CREATE INDEX IF NOT EXISTS waffles_jobs_claim ON waffles.jobs(run_id,status,available_at,ordinal);
CREATE TABLE IF NOT EXISTS waffles.workers (
  name text PRIMARY KEY, reported_at timestamptz NOT NULL DEFAULT now(), device text,
  ready boolean NOT NULL DEFAULT false, model_seconds double precision,
  rss_bytes bigint
);
