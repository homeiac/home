// Read-only diagnosis using mounted credentials; no keys or photo metadata printed.
import {createRequire} from 'node:module';
import fs from 'node:fs/promises';
import {mapAsset} from '/code/core.mjs';
const {Client}=createRequire('/usr/src/app/server/package.json')('pg');
const db=new Client();await db.connect();
try {
 const identity=(await db.query("SELECT value FROM immich_sync.state WHERE key='identity'")).rows[0].value;
 const jobs=(await db.query("SELECT source_path,asset_id,payload FROM immich_sync.jobs WHERE state='error' LIMIT 10")).rows;
 const key=(await fs.readFile('/credentials/api-key','utf8')).trim();
 for(const job of jobs){
  const response=await fetch('http://immich-server:2283/api/assets/'+job.asset_id,{headers:{'x-api-key':key}});
  if(!response.ok){console.log(JSON.stringify({http:response.status}));continue;}
  const asset=await response.json();
  const match=mapAsset({path:job.source_path,size_bytes:job.payload.sizeBytes},[asset],identity.ownerId,identity.libraryId);
  console.log(JSON.stringify({reason:match.reason??'matched',offline:asset.isOffline,trashed:asset.isTrashed,sourceSize:job.payload.sizeBytes,targetSize:asset.exifInfo?.fileSizeInByte}));
 }
}finally{await db.end();}
