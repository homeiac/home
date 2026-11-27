// Read-only Immich probes; only confirmed unavailable pending jobs leave the queue.
export const SCHEMA = `CREATE TABLE IF NOT EXISTS waffles.preview_checks (
 run_id text NOT NULL, asset_id uuid NOT NULL, ordinal integer NOT NULL,
 state text NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','available','unavailable','unresolved')),
 attempts integer NOT NULL DEFAULT 0, not_found integer NOT NULL DEFAULT 0,
 last_status integer, checked_at timestamptz, next_check timestamptz NOT NULL DEFAULT now(),
 removed boolean NOT NULL DEFAULT false,
 PRIMARY KEY(run_id,asset_id),
 FOREIGN KEY(run_id,asset_id) REFERENCES waffles.jobs(run_id,asset_id)
);
CREATE INDEX IF NOT EXISTS waffles_preview_due ON waffles.preview_checks(run_id,(not_found>0) DESC,ordinal) WHERE state='pending';`;

export async function probe(base, key, asset, fetcher=fetch) {
  // GET has the same semantics as the workers; HEAD can be routed differently.
  // Discard the stream immediately after headers, without decoding/downloading images.
  const response=await fetcher(base+'/api/assets/'+asset+'/thumbnail?size=preview',{
    headers:{'x-api-key':key},redirect:'manual',signal:AbortSignal.timeout(10000)});
  await response.body?.cancel();
  return response.status;
}

export function outcome(previous,status) {
  if(status===401||status===403)throw Error('authentication');
  const attempts=previous.attempts+1;
  const notFound=status===404?previous.not_found+1:0;
  const state=status===200?'available':notFound===4?'unavailable':attempts>=4?'unresolved':'pending';
  return {attempts,not_found:notFound,state};
}

export async function save(db,job,status) {
  const result=outcome(job,status);
  await db.query('BEGIN');
  try {
    let removed=false;
    if(result.state==='unavailable') {
      // Fence both a currently claimed job and a claim/fail race that returned it
      // to pending since this probe started. Inference counters remain honest.
      removed=(await db.query(`UPDATE waffles.jobs SET status='failed',last_error='thumbnail_http_404'
       WHERE run_id=$1 AND asset_id=$2 AND status='pending' AND attempts=$3
       AND claim IS NOT DISTINCT FROM $4::uuid`,[job.run_id,job.asset_id,job.job_attempts,job.claim])).rowCount===1;
    }
    await db.query(`UPDATE waffles.preview_checks SET attempts=$3,not_found=$4,state=$5,
      last_status=$6,checked_at=now(),next_check=now()+interval '30 seconds',removed=$7
      WHERE run_id=$1 AND asset_id=$2`,[job.run_id,job.asset_id,result.attempts,result.not_found,result.state,status,removed]);
    await db.query('COMMIT');return {...result,removed};
  } catch(error) {await db.query('ROLLBACK');throw error;}
}

export const NEXT = `SELECT p.*,j.attempts AS job_attempts,j.claim FROM waffles.preview_checks p
 JOIN waffles.jobs j USING(run_id,asset_id)
 WHERE p.run_id=$1 AND p.state='pending' AND p.next_check<=now() AND j.status='pending'
 ORDER BY (p.not_found>0) DESC,p.ordinal LIMIT $2`;
