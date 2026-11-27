// Pure validation checks run locally; --postgres also exercises real concurrent claims.
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {claim,finish,validateResult,validateTuning} from './queue-core.mjs';
const value={seconds:1.2,size:[100,80],matches:[{box:[0.1,0.1,0.8,0.9],probability:0.95}],unknown:0,low_confidence:0,out_of_range:0};
assert.equal(validateResult(value).seconds,1.2);
assert.deepEqual(validateTuning('mac',4),{slots:4});
assert.deepEqual(validateTuning('still-fawn',0),{slots:0});
for(const [worker,slots] of [['mac',5],['pve',2],['still-fawn',-1],['rtx',1],['mac',1.5]])assert.throws(()=>validateTuning(worker,slots));
const calls=[];
const connection={query:async(sql)=>{calls.push(sql);return {rows:sql.includes('RETURNING')?[{asset_id:'test'}]:[]};},release:()=>calls.push('release')};
assert.equal((await claim({connect:async()=>connection},'mac')).asset_id,'test');
assert.equal(calls[0],'BEGIN');assert(calls[1].includes('pg_advisory_xact_lock'));assert(calls[2].includes('count(*)'));assert.equal(calls[3],'COMMIT');assert.equal(calls[4],'release');
for(const bad of [{...value,seconds:NaN},{...value,matches:[{box:[0.8,0,0.1,1],probability:0.95}]},{...value,matches:[{box:[0,0,1,1],probability:0.89}]}])
  assert.throws(()=>validateResult(bad));
if(process.argv.includes('--postgres')) {
  const {Pool}=createRequire('/usr/src/app/server/package.json')('pg');
  const db=new Pool({max:3});const id='queue-test-'+Date.now();
  try {
    await db.query("INSERT INTO waffles.runs(id,mode,state,workers,config) VALUES($1,'benchmark','running',ARRAY['pve','still-fawn'],'{}')",[id]);
    for(let n=1;n<=2;n++)await db.query("INSERT INTO waffles.jobs(run_id,asset_id,taken_at,ordinal) VALUES($1,$2,'2020-01-01',$3)",[id,'00000000-0000-4000-8000-'+String(n).padStart(12,'0'),n]);
    const [a,b]=await Promise.all([claim(db,'pve'),claim(db,'still-fawn')]);
    assert(a&&b&&a.asset_id!==b.asset_id,'Workers must receive distinct assets');
    await db.query("UPDATE waffles.jobs SET lease_until=now()-interval '1 second' WHERE run_id=$1 AND asset_id=$2",[id,a.asset_id]);
    assert.equal(await finish(db,a,value),false,'Expired claims cannot commit');
    const retry=await claim(db,'pve');assert.equal(retry.asset_id,a.asset_id);assert.notEqual(retry.claim,a.claim);
    assert.equal(await finish(db,a,value),false,'Old fencing token cannot commit');
    assert.equal(await finish(db,retry,value),true);
    assert.equal(await finish(db,retry,value),false,'Duplicate completion cannot commit twice');
    assert.equal(await finish(db,b,value),true);
    assert.equal((await db.query("SELECT count(*)::int n FROM waffles.jobs WHERE run_id=$1 AND status='complete'",[id])).rows[0].n,2);
    console.log('PostgreSQL concurrency, lease expiry, fencing and duplicate completion tests passed');
  } finally {
    await db.query('DELETE FROM waffles.jobs WHERE run_id=$1',[id]);
    await db.query('DELETE FROM waffles.runs WHERE id=$1',[id]);await db.end();
  }
}
console.log('Result validation checks passed');
