import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {download,recover} from './media-fallback-core.mjs';
const directory=await fs.mkdtemp(path.join(os.tmpdir(),'waffles-media-test-'));
const jpeg=Buffer.from([255,216,255,217]);
try {
  await assert.rejects(()=>download(new Response('denied',{status:403}),directory+'/denied'),e=>e.status===403);
  await assert.rejects(()=>download(new Response('large',{headers:{'content-length':'20'}}),directory+'/large',4),e=>e.status===413);
  await assert.rejects(()=>download(new Response('large'),directory+'/stream',4),e=>e.status===413);
  for(const type of ['VIDEO','IMAGE']) {
    const requested=[];let frames=0,images=0;
    const result=await recover({base:'http://fixture',key:'test',id:'asset',directory,
      fetcher:async(url,options)=>{requested.push(url);assert.equal(options.redirect,'error');assert(options.signal);
        return requested.length===1?Response.json({type}):new Response('source');},
      frame:async(input,output)=>{assert.equal(await fs.readFile(input,'utf8'),'source');frames++;await fs.writeFile(output,jpeg);},
      normalize:async(input,output)=>{assert.equal(await fs.readFile(input,'utf8'),'source');images++;await fs.writeFile(output,jpeg);}});
    assert.equal(result.source,type==='VIDEO'?'video_first_frame':'original_image');
    assert.equal(frames,type==='VIDEO'?1:0);assert.equal(images,type==='IMAGE'?1:0);
    assert(requested[1].endsWith(type==='VIDEO'?'/video/playback':'/original'));
    assert.deepEqual(result.bytes,jpeg);
  }
  let calls=0;
  await assert.rejects(()=>recover({base:'http://fixture',key:'test',id:'asset',directory,
    fetcher:async()=>++calls===1?Response.json({type:'VIDEO'}):new Response('bad'),
    frame:async()=>{throw Error('decoder failed');}}),/decoder failed/);
  assert(!(await fs.readdir(directory)).some(name=>name.startsWith('working-')),'Temporary media is removed on success and failure');
  console.log('PASS: type routing, permission errors, body byte limits, frame conversion and temporary-file cleanup');
} finally {await fs.rm(directory,{recursive:true,force:true});}
