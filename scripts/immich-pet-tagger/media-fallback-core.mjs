// Recover a still image when Immich's generated preview is absent.
import {createRequire} from 'node:module';
import fs from 'node:fs/promises';
import {spawn} from 'node:child_process';
import path from 'node:path';
import crypto from 'node:crypto';
const require=createRequire('/usr/src/app/server/package.json');
export const error=(reason,status=502)=>Object.assign(Error(reason),{status});

export async function download(response,destination,maxBytes=128*1024*1024) {
  if(!response.ok){await response.body?.cancel();throw error('source_http_'+response.status,response.status);}
  if(Number(response.headers.get('content-length'))>maxBytes){await response.body?.cancel();throw error('media_too_large',413);}
  const file=await fs.open(destination,'wx');let bytes=0;
  try {for await(const chunk of response.body){bytes+=chunk.length;if(bytes>maxBytes)throw error('media_too_large',413);await file.writeFile(chunk);}return bytes;}
  finally {await file.close();}
}

export function extractFrame(input,output) {
  return new Promise((resolve,reject)=>{
    // First displayed frame, one decode thread, autorotation enabled by ffmpeg.
    // Paths are generated internally; credentials and URLs never enter argv/logs.
    const child=spawn('ffmpeg',['-nostdin','-hide_banner','-loglevel','error','-threads','1','-i',input,
      '-map','0:v:0','-frames:v','1','-vf',"scale=w='min(1600,iw)':h='min(1600,ih)':force_original_aspect_ratio=decrease",
      '-threads','1','-q:v','2','-y',output],{stdio:'ignore'});
    const timer=setTimeout(()=>{child.kill('SIGKILL');reject(error('frame_timeout',504));},15000);
    child.once('error',()=>{clearTimeout(timer);reject(error('frame_spawn_failed'));});
    child.once('exit',code=>{clearTimeout(timer);code===0?resolve():reject(error('frame_decode_failed',422));});
  });
}

export async function recover({base,key,id,directory,fetcher=fetch,frame=extractFrame,normalize}) {
  const fetchAsset=suffix=>fetcher(base+'/api/assets/'+id+suffix,{headers:{'x-api-key':key},redirect:'error',signal:AbortSignal.timeout(20000)});
  const metadata=await fetchAsset('');if(!metadata.ok)throw error('metadata_http_'+metadata.status,metadata.status);
  const asset=await metadata.json();
  if(!['IMAGE','VIDEO'].includes(asset.type))throw error('unsupported_asset_type',422);
  const work=await fs.mkdtemp(path.join(directory,'working-'));
  try {
    const input=path.join(work,'input');const jpeg=path.join(work,'frame.jpg');
    const source=asset.type==='VIDEO'?'video/playback':'original';
    await download(await fetchAsset('/'+source),input,asset.type==='VIDEO'?128*1024*1024:32*1024*1024);
    if(asset.type==='VIDEO')await frame(input,jpeg);
    else {
      const convert=normalize??(async(source,target)=>require('sharp')(source,{limitInputPixels:40000000}).rotate().resize({width:1600,height:1600,fit:'inside',withoutEnlargement:true}).jpeg({quality:90}).toFile(target));
      await convert(input,jpeg);
    }
    const bytes=await fs.readFile(jpeg);
    if(bytes.length<4||bytes[0]!==0xff||bytes[1]!==0xd8)throw error('invalid_fallback_image',422);
    return {bytes,source:asset.type==='VIDEO'?'video_first_frame':'original_image',sha256:crypto.createHash('sha256').update(bytes).digest('hex')};
  } finally {await fs.rm(work,{recursive:true,force:true});}
}
