// Read-only Immich queue/VPA telemetry. No photo content, credentials or IDs exported.
import http from 'node:http';
import https from 'node:https';
import fs from 'node:fs';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';

// ConfigMap volumes use symlinks; Node resolves the module URL to the real path.
export const isEntryPoint = (file, url) => Boolean(file) && url === pathToFileURL(fs.realpathSync(file)).href;

export const queues = {
  library: 'library', sidecar: 'sidecar', metadataExtraction: 'metadata',
  thumbnailGeneration: 'thumbnail_generation', faceDetection: 'face_detection',
  facialRecognition: 'facial_recognition', smartSearch: 'smart_search',
  ocr: 'ocr', videoConversion: 'video_conversion', duplicateDetection: 'duplicate_detection',
};
export const states = {waiting: ['llen','wait'], active: ['llen','active'],
  delayed: ['zcard','delayed'], prioritized: ['zcard','prioritized'],
  failed: ['zcard','failed'], paused: ['llen','paused']};

export function quantity(value) {
  const m = /^([0-9]+(?:\.[0-9]+)?)(Ki|Mi|Gi|Ti|n|u|m|k|M|G|T)?$/.exec(String(value));
  if (!m) throw Error('Unsupported resource quantity');
  return Number(m[1])*({Ki:1024,Mi:1024**2,Gi:1024**3,Ti:1024**4,n:1e-9,u:1e-6,m:1e-3,k:1e3,M:1e6,G:1e9,T:1e12}[m[2]]??1);
}
const labels = value => JSON.stringify(String(value));
export function queueMetrics(results) {
  const lines=['# HELP immich_queue_jobs Jobs currently held in each BullMQ state.',
    '# TYPE immich_queue_jobs gauge'];
  let index=0;
  for (const queue of Object.values(queues)) {
    for (const state of Object.keys(states)) {
      const [error,value]=results[index++];
      if (error || !Number.isFinite(Number(value))) throw Error('Queue read failed');
      lines.push(`immich_queue_jobs{queue=${labels(queue)},state=${labels(state)}} ${Number(value)}`);
    }
  }
  return lines.join('\n');
}
export function recommendationMetrics(items) {
  const lines=['# HELP immich_vpa_recommendation Recommended requests in CPU cores or memory bytes.',
    '# TYPE immich_vpa_recommendation gauge','# HELP immich_vpa_policy_info VPA policy update mode.',
    '# TYPE immich_vpa_policy_info gauge'];
  for (const item of items) {
    const workload=item.spec.targetRef.name;
    lines.push(`immich_vpa_policy_info{workload=${labels(workload)},mode=${labels(item.spec.updatePolicy.updateMode)}} 1`);
    for (const c of item.status?.recommendation?.containerRecommendations??[]) {
      for (const bound of ['target','lowerBound','upperBound','uncappedTarget']) {
        for (const resource of ['cpu','memory']) {
          if(c[bound]?.[resource]!==undefined) lines.push(`immich_vpa_recommendation{workload=${labels(workload)},container=${labels(c.containerName)},bound=${labels(bound)},resource=${labels(resource)}} ${quantity(c[bound][resource])}`);
        }
      }
    }
  }
  return lines.join('\n');
}

function readVpa(name) {
  const root='/var/run/secrets/kubernetes.io/serviceaccount/';
  return new Promise((resolve,reject)=>{
    const req=https.get({hostname:'kubernetes.default.svc',port:443,
      path:'/apis/autoscaling.k8s.io/v1/namespaces/immich-pilot/verticalpodautoscalers/'+name,
      ca:fs.readFileSync(root+'ca.crt'),headers:{Authorization:'Bearer '+fs.readFileSync(root+'token','utf8').trim()}},r=>{
        let body=''; r.setEncoding('utf8'); r.on('data',c=>body+=c);
        r.on('end',()=>{try {if(r.statusCode!==200)throw Error('VPA read failed');resolve(JSON.parse(body));}catch(e){reject(e);}});
      });
    req.setTimeout(5000,()=>req.destroy(Error('VPA read timed out')));req.on('error',reject);
  });
}

async function main() {
  const require=createRequire('/usr/src/app/server/package.json');
  const Redis=require('ioredis');
  const redis=new Redis({host:'immich-valkey',port:6379,maxRetriesPerRequest:1,
    connectTimeout:3000,commandTimeout:5000,enableReadyCheck:false});
  redis.on('error',()=>{}); // Errors surface as health metrics without private connection details.
  let output='',queueUp=0,vpaUp=0,lastQueue=0,lastVpa=0,busy=false;
  async function collect() {
    if(busy)return;busy=true;
    const lines=[];
    try {
      const batch=redis.pipeline();
      for(const key of Object.keys(queues))for(const [method,suffix] of Object.values(states))batch[method](`immich_bull:${key}:${suffix}`);
      lines.push(queueMetrics(await batch.exec()));queueUp=1;lastQueue=Date.now()/1000;
    } catch {queueUp=0;}
    try {
      lines.push(recommendationMetrics(await Promise.all(['immich-server','immich-machine-learning','immich-pet-tagger','waffles-worker-pve','waffles-worker-still-fawn','waffles-burst-pve','waffles-burst-still-fawn'].map(readVpa))));
      vpaUp=1;lastVpa=Date.now()/1000;
    } catch {vpaUp=0;}
    lines.push('# HELP immich_observer_source_up Whether the last collection succeeded.','# TYPE immich_observer_source_up gauge',
      `immich_observer_source_up{source="queues"} ${queueUp}`,`immich_observer_source_up{source="vpa"} ${vpaUp}`,
      '# HELP immich_observer_last_success_timestamp_seconds Time of last successful collection.','# TYPE immich_observer_last_success_timestamp_seconds gauge',
      `immich_observer_last_success_timestamp_seconds{source="queues"} ${lastQueue}`,`immich_observer_last_success_timestamp_seconds{source="vpa"} ${lastVpa}`);
    output=lines.join('\n')+'\n';busy=false;
  }
  await collect();setInterval(collect,15000);
  http.createServer((req,res)=>{
    if(req.url==='/healthz'){res.end('ok');return;}
    if(req.url!=='/metrics'){res.writeHead(404);res.end();return;}
    res.setHeader('Content-Type','text/plain; version=0.0.4');res.end(output);
  }).listen(9199,'0.0.0.0');
}
if(isEntryPoint(process.argv[1], import.meta.url))await main();
