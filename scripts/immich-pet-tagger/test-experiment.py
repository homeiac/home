#!/usr/bin/env python3
"""Check quality rejection and independent restoration after a failed API call."""
import copy
import experiment as e

truth={'positive':[str(i) for i in range(13)],'negative':[str(i) for i in range(13,26)]}
rows=[{'asset_id':str(i),'result':{'matches':[{}] if i<9 else []},'completed_at':'2026-11-27T00:01:00+00:00',
       'started_at':'2026-11-27T00:00:00+00:00','processing_seconds':1.0,'attempts':1,'worker':'mac'} for i in range(26)]
summary,baseline=e.summarize(rows,truth,None)
assert summary['valid'] and summary['photos_per_minute']==26
bad=copy.deepcopy(rows);bad[13]['result']['matches']=[{}]
assert not e.summarize(bad,truth,baseline)[0]['valid'],'New false positive must fail'
bad=copy.deepcopy(rows);bad[0]['result']['matches']=[]
assert not e.summarize(bad,truth,baseline)[0]['valid'],'Lost positive must fail'
bad=copy.deepcopy(rows);bad[0]['attempts']=2
assert not e.summarize(bad,truth,baseline)[0]['valid'],'Retried trial must fail'
before={'workers':[{'unexpected_exits':0}],'metrics':{'k8s_restarts':[{'value':'0'}]}}
after=copy.deepcopy(before);after['metrics']['k8s_restarts'][0]['value']='1'
e.resource_gate(summary,before,after);assert not summary['valid'],'Restart must fail'
calls=[]
def request(path,body):
    calls.append(path)
    if path=='fail':raise RuntimeError('Simulated outage')
e.request=request;e.record=lambda *a,**k:None;e.time.sleep=lambda _:None
try:e.cleanup([('fail',{},'rollback'),('resume',{},'resume')])
except RuntimeError:pass
else:raise AssertionError('Restoration failure must be visible')
assert calls==['fail','fail','fail','resume'],'One failed cleanup must not prevent production resume'
print('Experiment accuracy, retry, restart and independent cleanup gates passed')
