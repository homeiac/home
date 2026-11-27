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
CREATE TABLE IF NOT EXISTS waffles.instances (
  id text PRIMARY KEY, worker text NOT NULL, reported_at timestamptz NOT NULL DEFAULT now(),
  device text, ready boolean NOT NULL DEFAULT false, draining boolean NOT NULL DEFAULT false,
  rss_bytes bigint NOT NULL DEFAULT 0, exit_code integer
);
CREATE TABLE IF NOT EXISTS waffles.tuning_events (
  id bigserial PRIMARY KEY, worker text NOT NULL, slots integer NOT NULL,
  changed_at timestamptz NOT NULL DEFAULT now(), note text NOT NULL DEFAULT ''
);
INSERT INTO waffles.settings(key,value) VALUES('tuning',
 '{"mac":{"slots":1},"pve":{"slots":1},"still-fawn":{"slots":1},"fun-bedbug":{"slots":1},"chief-horse":{"slots":1}}')
 ON CONFLICT(key) DO NOTHING;
ALTER TABLE waffles.jobs ADD COLUMN IF NOT EXISTS pool text NOT NULL DEFAULT 'base';
ALTER TABLE waffles.jobs ADD COLUMN IF NOT EXISTS device text;
ALTER TABLE waffles.jobs ADD COLUMN IF NOT EXISTS apply_attempts integer NOT NULL DEFAULT 0;
UPDATE waffles.jobs SET device=CASE WHEN worker='mac' THEN 'mps' ELSE 'cpu' END WHERE worker IS NOT NULL AND device IS NULL;
CREATE INDEX IF NOT EXISTS waffles_active_pool ON waffles.jobs(worker,pool) WHERE status='running';
ALTER TABLE waffles.instances ADD COLUMN IF NOT EXISTS pool text NOT NULL DEFAULT 'base';
ALTER TABLE waffles.instances ADD COLUMN IF NOT EXISTS cpu_seconds double precision NOT NULL DEFAULT 0;
ALTER TABLE waffles.instances ADD COLUMN IF NOT EXISTS accelerator_bytes bigint NOT NULL DEFAULT 0;
ALTER TABLE waffles.instances ADD COLUMN IF NOT EXISTS cpu_affinity integer;
ALTER TABLE waffles.instances ADD COLUMN IF NOT EXISTS cpu_threads integer;
INSERT INTO waffles.settings(key,value) VALUES('burst',
 '{"mac":{"slots":0,"mode":"production"},"pve":{"slots":0,"mode":"production"},"still-fawn":{"slots":0,"mode":"production"},"fun-bedbug":{"slots":0,"mode":"production"},"chief-horse":{"slots":0,"mode":"production"}}')
 ON CONFLICT(key) DO NOTHING;

-- Schema v5: FIFO selection stops at the first ready row, not a backlog sort.
CREATE INDEX IF NOT EXISTS waffles_ready_fifo ON waffles.jobs(run_id,ordinal,asset_id)
 WHERE status='pending' AND attempts<4;
CREATE INDEX IF NOT EXISTS waffles_expired_leases ON waffles.jobs(lease_until)
 WHERE status='running';
