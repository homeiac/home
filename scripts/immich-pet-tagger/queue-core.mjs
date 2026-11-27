// Fenced claims adapted from photo_enrichment/postgres.py; inference is outside transactions.
import crypto from 'node:crypto';
export const WORKERS=['mac','pve','still-fawn'];
export const CLAIM_SQL=`WITH candidate AS (
 SELECT j.run_id,j.asset_id FROM waffles.jobs j JOIN waffles.runs r ON r.id=j.run_id
 WHERE r.state='running' AND $1=ANY(r.workers)
 AND ((j.status='pending' AND j.available_at<=now()) OR (j.status='running' AND j.lease_until<now()))
 AND j.attempts<4
 ORDER BY r.created_at,j.ordinal FOR UPDATE OF j SKIP LOCKED LIMIT 1)
 UPDATE waffles.jobs j SET status='running',claim=$2,worker=$1,lease_until=now()+interval '90 seconds',attempts=attempts+1
 FROM candidate c WHERE j.run_id=c.run_id AND j.asset_id=c.asset_id RETURNING j.*,
 (SELECT config FROM waffles.runs WHERE id=j.run_id) AS config`;

export async function claim(db,worker) {
  if(!WORKERS.includes(worker))throw Error('Invalid worker');
  return (await db.query(CLAIM_SQL,[worker,crypto.randomUUID()])).rows[0]??null;
}

export function validateResult(value) {
  if(!value || !Number.isFinite(value.seconds) || value.seconds<0 || value.seconds>3600)throw Error('Invalid duration');
  if(!Array.isArray(value.matches) || value.matches.length>100)throw Error('Invalid matches');
  if(!Array.isArray(value.size) || value.size.length!==2 || value.size.some(v=>!Number.isInteger(v)||v<1||v>100000))throw Error('Invalid size');
  for(const match of value.matches) {
    if(!Number.isFinite(match.probability)||match.probability<0.9||match.probability>1)throw Error('Invalid confidence');
    const b=match.box;
    if(!Array.isArray(b)||b.length!==4||b.some(v=>!Number.isFinite(v)||v<0||v>1)||b[0]>=b[2]||b[1]>=b[3])throw Error('Invalid box');
  }
  for(const key of ['unknown','low_confidence','out_of_range'])
    if(!Number.isInteger(value[key])||value[key]<0||value[key]>100)throw Error('Invalid outcome');
  return {seconds:value.seconds,size:value.size,matches:value.matches,
          unknown:value.unknown,low_confidence:value.low_confidence,out_of_range:value.out_of_range};
}

export async function finish(db,job,value) {
  const result=validateResult(value);
  return (await db.query(`UPDATE waffles.jobs j SET
    status=CASE WHEN r.mode='benchmark' THEN 'complete' ELSE 'classified' END,
    result=$4,processing_seconds=$5,lease_until=NULL,
    completed_at=CASE WHEN r.mode='benchmark' THEN now() ELSE NULL END
    FROM waffles.runs r WHERE j.run_id=r.id AND j.run_id=$1 AND j.asset_id=$2 AND j.claim=$3
    AND j.status='running' AND j.lease_until>now() RETURNING j.asset_id`,
    [job.run_id,job.asset_id,job.claim,result,result.seconds])).rowCount===1;
}
