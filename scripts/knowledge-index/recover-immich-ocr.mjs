// One-shot recovery after GPU maintenance. Native Immich handler, no DB writes.
import {createRequire} from 'node:module';
const require = createRequire('/usr/src/app/server/package.json');
const {Queue} = require('bullmq');
const queue = new Queue('ocr', {prefix:'immich_bull', connection:{host:'immich-valkey',port:6379}});
const id = 'gpu-driver-580-missing-ocr-v1';
try {
  let job = await queue.getJob(id);
  if (!job && process.env.APPLY === 'true') {
    // FIFO: scan after the existing OCR work. Completed results are never reset.
    job = await queue.add('OcrQueueAll', {force:false}, {
      jobId:id, lifo:false, attempts:3, backoff:{type:'fixed',delay:5000},
      removeOnComplete:false, removeOnFail:false,
    });
  }
  console.log(JSON.stringify({event:'ocr.missing_recovery', apply:process.env.APPLY === 'true',
    scan:job ? await job.getState() : 'not_queued', force:false,
    counts:await queue.getJobCounts('waiting','active','failed','paused')}));
} finally {
  await queue.close();
}
