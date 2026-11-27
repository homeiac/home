// Pure validation checks run locally; --postgres also exercises real concurrent claims.
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {claim,finish,validateResult,validateTuning,validateBurst} from './queue-core.mjs';
const value={seconds:1.2,size:[100,80],matches:[{box:[0.1,0.1,0.8,0.9],probability:0.95}],unknown:0,low_confidence:0,out_of_range:0};
assert.equal(validateResult(value).seconds,1.2);
assert.deepEqual(validateTuning('mac',1),{slots:1});
for(const [worker,slots] of [['mac',4],['pve',2],['still-fawn',0],['rtx',1],['mac',1.5]])assert.throws(()=>validateTuning(worker,slots));
assert.deepEqual(validateBurst('mac',15,'benchmark'),{slots:15,mode:'benchmark',cpu_cores:0,device:'mps'});
assert.deepEqual(validateBurst('still-fawn',0,'production'),{slots:0,mode:'production',cpu_cores:3,device:'cpu'});
assert.deepEqual(validateBurst('still-fawn',2,'benchmark',1),{slots:2,mode:'benchmark',cpu_cores:1,device:'cpu'});
assert.throws(()=>validateBurst('still-fawn',2,'benchmark',4));
assert.equal(validateBurst('mac',1,'benchmark',0,'cpu').device,'cpu');
assert.throws(()=>validateBurst('still-fawn',1,'benchmark',1,'mps'));
assert.throws(()=>validateBurst('mac',1,'benchmark',0,'cuda'));
for(const [worker,slots,mode] of [['mac',16,'benchmark'],['pve',2,'production'],['chief-horse',1,'production'],['mac',-1,'production'],['mac',1,'other']])assert.throws(()=>validateBurst(worker,slots,mode));
const calls=[];
const connection={query:async(sql)=>{calls.push(sql);return {rows:sql.includes('RETURNING')?[{asset_id:'test'}]:[]};},release:()=>calls.push('release')};
assert.equal((await claim({connect:async()=>connection},'mac')).asset_id,'test');
assert.equal(calls[0],'BEGIN');assert(calls[1].includes('pg_advisory_xact_lock'));assert(calls[2].includes('count(*)'));assert.equal(calls[3],'COMMIT');assert.equal(calls[4],'release');
for(const bad of [{...value,seconds:NaN},{...value,matches:[{box:[0.8,0,0.1,1],probability:0.95}]},{...value,matches:[{box:[0,0,1,1],probability:0.89}]}])
  assert.throws(()=>validateResult(bad));
if(process.argv.includes('--postgres')) {
  const {Pool}=createRequire('/usr/src/app/server/package.json')('pg');
  const db=new Pool({max:4});const suffix=String(Date.now());
  const names=Object.fromEntries(['jobs','runs','settings'].map(n=>[n,'waffles.test_'+n+'_'+suffix]));
  const rewrite=sql=>Object.entries(names).reduce((s,[name,table])=>s.replaceAll('waffles.'+name,table),sql).replaceAll('pg_advisory_xact_lock(244,','pg_advisory_xact_lock(1244,');
  const isolated={query:(sql,args)=>db.query(rewrite(sql),args),connect:async()=>{const connection=await db.connect();return {query:(sql,args)=>connection.query(rewrite(sql),args),release:()=>connection.release()};}};
  try {
    for(const name of ['runs','jobs','settings'])await db.query(`CREATE TABLE ${names[name]} (LIKE waffles.${name} INCLUDING ALL)`);
    await db.query(`ALTER TABLE ${names.jobs} ADD COLUMN IF NOT EXISTS pool text NOT NULL DEFAULT 'base'`);
    await db.query(`ALTER TABLE ${names.jobs} ADD COLUMN IF NOT EXISTS device text`);
    await isolated.query("INSERT INTO waffles.settings VALUES('burst','{\"pve\":{\"slots\":2,\"mode\":\"benchmark\"}}')");
    for(const [id,mode] of [['bench','benchmark'],['prod','production']]) {
      await isolated.query("INSERT INTO waffles.runs(id,mode,state,workers,config) VALUES($1,$2,'running',ARRAY['pve'],'{}')",[id,mode]);
      for(let n=1;n<=3;n++)await isolated.query("INSERT INTO waffles.jobs(run_id,asset_id,taken_at,ordinal) VALUES($1,$2,'2020-01-01',$3)",[id,'00000000-0000-4000-8000-'+String(n).padStart(12,'0'),n]);
    }
    const [a,b,c]=await Promise.all([claim(isolated,'pve','burst'),claim(isolated,'pve','burst'),claim(isolated,'pve','burst')]);
    const leased=[a,b,c].filter(Boolean);assert.equal(leased.length,2,'Concurrent claims cannot exceed burst slots');
    assert.notEqual(leased[0].asset_id,leased[1].asset_id);
    const baseline=await claim(isolated,'pve');assert.equal(baseline.run_id,'prod','Baseline keeps serving production while burst slots are occupied');
    assert.equal(await claim(isolated,'pve'),null,'Baseline cap remains one');
    const old=leased[0];
    await isolated.query("UPDATE waffles.jobs SET lease_until=now()-interval '1 second' WHERE run_id=$1 AND asset_id=$2",[old.run_id,old.asset_id]);
    assert.equal(await finish(isolated,old,value),false,'Expired claims cannot commit');
    const retry=await claim(isolated,'pve','burst');assert.equal(retry.asset_id,old.asset_id);assert.notEqual(retry.claim,old.claim);
    assert.equal(await finish(isolated,old,value),false,'Old fencing token cannot commit');
    assert.equal(await finish(isolated,retry,value),true);
    assert.equal(await finish(isolated,retry,value),false,'Duplicate completion cannot commit twice');
    await isolated.query("UPDATE waffles.settings SET value='{\"pve\":{\"slots\":0,\"mode\":\"benchmark\"}}' WHERE key='burst'");
    assert.equal(await claim(isolated,'pve','burst'),null);
    assert.equal(await finish(isolated,baseline,value),true);
    assert.equal((await claim(isolated,'pve')).run_id,'prod','Zero burst slots must not stop baseline work');
    console.log('Isolated PostgreSQL pool separation, concurrent caps, fencing and baseline continuity passed');
  } finally {
    for(const name of ['jobs','runs','settings'])await db.query(`DROP TABLE IF EXISTS ${names[name]}`);
    await db.end();
  }
}
console.log('Result validation checks passed');
