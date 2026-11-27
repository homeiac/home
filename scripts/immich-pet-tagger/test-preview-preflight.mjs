import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {SCHEMA,NEXT,probe,outcome,save} from './preview-preflight-core.mjs';

let cancelled=false;
assert.equal(await probe('http://example.invalid','test','fixture',async(url,options)=>{
  assert.equal(options.redirect,'manual');assert(options.signal);
  return {status:200,body:{cancel:async()=>{cancelled=true;}}};
}),200);
assert(cancelled,'Successful GET must stop reading the image body');
for(const [type,lastStatus,expectedSuffix] of [['VIDEO',200,'/video/playback'],['IMAGE',403,'/original'],['VIDEO',404,'/video/playback']]) {
  let call=0;
  assert.equal(await probe('http://example.invalid','test','fixture',async url=>{
    call++;if(call===1)return new Response('',{status:404});
    if(call===2)return Response.json({type});
    assert(url.endsWith(expectedSuffix));return new Response('',{status:lastStatus});
  }),lastStatus,'Missing preview alone must not be treated as missing media');
}
assert.throws(()=>outcome({attempts:0,not_found:0},401),/authentication/);
assert.throws(()=>outcome({attempts:0,not_found:0},403),/authentication/);
assert.equal(outcome({attempts:3,not_found:3},404).state,'unavailable');
assert.equal(outcome({attempts:3,not_found:3},200).state,'available');
assert.equal(outcome({attempts:3,not_found:3},500).state,'unresolved');

if(process.argv.includes('--postgres')) {
  const {Client}=createRequire('/usr/src/app/server/package.json')('pg');
  const db=new Client();await db.connect();const suffix=String(Date.now());
  const tables={jobs:'waffles.test_preview_jobs_'+suffix,preview_checks:'waffles.test_preview_checks_'+suffix};
  const rewrite=sql=>Object.entries(tables).reduce((s,[old,name])=>s.replaceAll('waffles.'+old,name),sql)
    .replaceAll('waffles_preview_due','test_preview_due_'+suffix);
  const isolated={query:(sql,args)=>db.query(rewrite(sql),args)};
  try {
    await db.query(`CREATE TABLE ${tables.jobs} (LIKE waffles.jobs INCLUDING ALL)`);
    await isolated.query(SCHEMA);
    for(let n=1;n<=5;n++){
      const asset='00000000-0000-4000-8000-'+String(n).padStart(12,'0');
      await isolated.query("INSERT INTO waffles.jobs(run_id,asset_id,taken_at,ordinal) VALUES('fixture',$1,'2020-01-01',$2)",[asset,n]);
      await isolated.query("INSERT INTO waffles.preview_checks(run_id,asset_id,ordinal) VALUES('fixture',$1,$2)",[asset,n]);
    }
    const read=async n=>(await isolated.query(`SELECT p.*,j.attempts job_attempts,j.claim,j.status job_status
      FROM waffles.preview_checks p JOIN waffles.jobs j USING(run_id,asset_id) WHERE p.ordinal=$1`,[n])).rows[0];
    await save(isolated,await read(3),404);
    assert.equal((await isolated.query(NEXT,['fixture',1])).rows[0].ordinal,1,'404 recheck must respect its delay');
    await isolated.query("UPDATE waffles.preview_checks SET next_check=now()-interval '1 second' WHERE ordinal=3");
    assert.equal((await isolated.query(NEXT,['fixture',1])).rows[0].ordinal,3,'Due 404 retries precede a large untouched backlog');
    await isolated.query("UPDATE waffles.preview_checks SET attempts=0,not_found=0,next_check=now() WHERE ordinal=3");
    for(let n=0;n<4;n++){
      const row=await read(1);await save(isolated,row,404);
      assert.equal((await read(1)).job_status,n===3?'failed':'pending');
    }
    assert.equal((await read(1)).job_attempts,0,'Preflight attempts must not fabricate inference claims');
    assert.equal((await read(1)).attempts,4);assert.equal((await read(1)).removed,true);
    for(let n=0;n<3;n++)await save(isolated,await read(2),404);
    await save(isolated,await read(2),200);assert.equal((await read(2)).job_status,'pending');
    assert.equal((await read(2)).state,'available');
    for(let n=0;n<4;n++)await save(isolated,await read(3),500);
    assert.equal((await read(3)).state,'unresolved');assert.equal((await read(3)).job_status,'pending');
    for(let n=0;n<3;n++)await save(isolated,await read(4),404);
    const racing=await read(4);
    await isolated.query("UPDATE waffles.jobs SET status='running',attempts=1,claim='00000000-0000-4000-8000-000000000099' WHERE ordinal=4");
    assert.equal((await save(isolated,racing,404)).removed,false,'Active worker claim wins');
    assert.equal((await read(4)).job_status,'running');
    for(let n=0;n<3;n++)await save(isolated,await read(5),404);
    const retryRace=await read(5);
    await isolated.query("UPDATE waffles.jobs SET attempts=1 WHERE ordinal=5");
    assert.equal((await save(isolated,retryRace,404)).removed,false,'Claim/fail/pending race is fenced by attempt count');
    assert.equal((await read(5)).job_status,'pending');
    console.log('PASS: real PostgreSQL four-404 removal, success recovery, bounded transient failures, active claims and claim/fail race fencing');
  } finally {
    for(const name of ['preview_checks','jobs'])await db.query(`DROP TABLE IF EXISTS ${tables[name]}`);
    await db.end();
  }
}
console.log('PASS: stream cancellation, auth guard and 404-only classification');
