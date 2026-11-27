// Hourly upload discovery with durable cursor; private owner scope is checked on every asset.
export async function discover(pool, api) {
  const db=await pool.connect();
  let locked=false;
  try {
    locked=(await db.query('SELECT pg_try_advisory_lock(244,2) AS locked')).rows[0].locked;
    if(!locked)return;
    const settings=(await db.query("SELECT value FROM waffles.settings WHERE key='discovery'")).rows[0]?.value;
    if(!settings?.enabled||Date.now()-Date.parse(settings.last_success??0)<3600000)return;
    const owner=(await(await api('/users/me')).json()).id;
    if(!owner)throw Error('Owner unavailable');
    const config=(await db.query("SELECT value FROM waffles.settings WHERE key='config'")).rows[0].value;
    const until=new Date().toISOString();
    await db.query(`INSERT INTO waffles.runs(id,mode,state,workers,config,started_at)
      VALUES('new-uploads','production','running',ARRAY['mac','pve','still-fawn'],$1,now()) ON CONFLICT(id) DO NOTHING`,[config]);
    let cursor=null,added=0;
    const seen=new Set();
    do {
      const body={size:1000,filter:{trashedAt:{eq:null},createdAt:{gte:settings.since,lte:until}},orderBy:{field:'fileCreatedAt',direction:'asc'}};
      if(cursor)body.cursor=cursor;
      const response=await(await api('/search/metadata','POST',body)).json();
      const block=response.assets??response;
      if(!Array.isArray(block.items))throw Error('Unexpected search response');
      const items=block.items.filter(a=>a.ownerId===owner).map(a=>({id:a.id,date:a.fileCreatedAt}));
      // Page insertion is atomic and idempotent. Cursor advances only after all
      // pages succeed; a retry overlaps safely with historical and prior uploads.
      added+=(await db.query(`INSERT INTO waffles.jobs(run_id,asset_id,taken_at,ordinal)
        SELECT 'new-uploads',x.id,x.date,coalesce((SELECT max(ordinal)+1 FROM waffles.jobs WHERE run_id='new-uploads'),0)+row_number() OVER()::int
        FROM jsonb_to_recordset($1::jsonb) x(id uuid,date text)
        WHERE NOT EXISTS(SELECT 1 FROM waffles.jobs j JOIN waffles.runs r ON r.id=j.run_id WHERE r.mode='production' AND j.asset_id=x.id)
        ON CONFLICT DO NOTHING`,[JSON.stringify(items)])).rowCount;
      cursor=block.nextCursor??null;
      if(cursor&&seen.has(cursor))throw Error('Repeated search cursor');
      if(cursor)seen.add(cursor);
    }while(cursor);
    if(added)await db.query("UPDATE waffles.runs SET state='running',finished_at=NULL WHERE id='new-uploads' AND state='complete'");
    const next={...settings,since:new Date(Date.parse(until)-300000).toISOString(),last_success:until,last_added:added,error:false};
    await db.query("UPDATE waffles.settings SET value=$1 WHERE key='discovery'",[next]);
    console.log('Upload discovery complete:',added,'new jobs');
  }catch(e){
    await db.query("UPDATE waffles.settings SET value=jsonb_set(value,'{error}','true') WHERE key='discovery'");
    console.error('Upload discovery failed:',e.code??e.constructor.name);
  }finally{
    if(locked)await db.query('SELECT pg_advisory_unlock(244,2)');
    db.release();
  }
}
