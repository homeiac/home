// Verify failure handling and Kubernetes quantity conversion without Redis or a cluster.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {quantity, queueMetrics, recommendationMetrics, queues, states} from './immich-queue-metrics.mjs';
test('resource quantities retain CPU cores and memory bytes', () => {
  for(const [input, expected] of [['500m',0.5],['250000000n',0.25],['2Gi',2147483648],['1536Mi',1610612736],['4',4]])assert.equal(quantity(input), expected);
  assert.throws(()=>quantity('invalid'));
});
test('actual empty queues emit zero, failed reads never become zero', () => {
  const result=Array(Object.keys(queues).length*Object.keys(states).length).fill(null).map(()=>[null,0]);
  result[18]=[null,52100];
  const text=queueMetrics(result);
  assert.match(text,/immich_queue_jobs\{queue="thumbnail_generation",state="waiting"\} 52100/);
  assert.match(text,/queue="library",state="waiting"\} 0/);
  result[1]=[Error('unavailable'),null];
  assert.throws(()=>queueMetrics(result));
  assert.throws(()=>queueMetrics([]));
});
test('missing VPA recommendation is not synthesized as zero', () => {
  const item={spec:{targetRef:{name:'immich-server'},updatePolicy:{updateMode:'Off'}}};
  assert.doesNotMatch(recommendationMetrics([item]),/immich_vpa_recommendation\{/);
  item.status={recommendation:{containerRecommendations:[{containerName:'main',target:{cpu:'1500m',memory:'2Gi'}}]}};
  assert.match(recommendationMetrics([item]),/bound="target",resource="cpu"\} 1.5/);
  assert.match(recommendationMetrics([item]),/mode="Off"\} 1/);
});
