import assert from 'node:assert/strict';
import {discover} from './discovery.mjs';

async function exercise(pages, settings={enabled:true,since:'2026-11-26T00:00:00Z'}) {
  const writes=[],requests=[];
  const db={async query(sql,args=[]) {
    writes.push([sql,args]);
    if(sql.includes('pg_try_advisory_lock'))return {rows:[{locked:true}]};
    if(sql.includes("key='discovery'")&&sql.startsWith('SELECT'))return {rows:[{value:settings}]};
    if(sql.includes("key='config'"))return {rows:[{value:{person_id:'test'}}]};
    if(sql.includes('INSERT INTO waffles.jobs'))return {rowCount:JSON.parse(args[0]).length};
    return {rows:[]};
  },release(){writes.push(['release']);}};
  await discover({connect:async()=>db},async(path,method,body)=>{
    requests.push({path,method,body});
    if(path==='/users/me')return {json:async()=>({id:'owner'})};
    const page=pages.shift();if(page instanceof Error)throw page;
    return {json:async()=>page};
  });
  return {writes,requests};
}
const good={id:'00000000-0000-4000-8000-000000000001',ownerId:'owner',fileCreatedAt:'2017-01-01'};
const foreign={...good,id:'00000000-0000-4000-8000-000000000002',ownerId:'other'};
const success=await exercise([{assets:{items:[good,foreign],nextCursor:'next'}},{assets:{items:[]}}]);
assert.equal(success.requests.length,3);
assert.equal(success.requests[2].body.cursor,'next');
const inserted=success.writes.filter(([sql])=>sql.includes('INSERT INTO waffles.jobs'));
assert.deepEqual(JSON.parse(inserted[0][1][0]),[{id:good.id,date:good.fileCreatedAt}]);
assert(inserted[0][0].includes("r.mode='production'"),'Deduplicate against historical jobs');
const saved=success.writes.find(([sql])=>sql.startsWith('UPDATE waffles.settings SET value=$1'))[1][0];
assert.equal(saved.last_added,1);assert.equal(saved.error,false);assert(saved.last_success);
const failure=await exercise([{assets:{items:[good],nextCursor:'next'}},Error('network')]);
assert(!failure.writes.some(([sql])=>sql.startsWith('UPDATE waffles.settings SET value=$1')),'A partial crawl must not advance its cursor');
assert(failure.writes.some(([sql])=>sql.includes("'{error}','true'")));
assert.equal(failure.writes.at(-1)[0],'release');
const paused=await exercise([],{enabled:false});assert.equal(paused.requests.length,0);
const recent=await exercise([],{enabled:true,last_success:new Date().toISOString()});assert.equal(recent.requests.length,0);
console.log('Discovery owner filtering, pagination, deduplication, cursor recovery and interval checks passed');
