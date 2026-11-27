"""Durable photo completion and backend distribution, using real queue outcomes."""
DS = {'type': 'prometheus', 'uid': 'prometheus'}
FRESH = '(max(waffles_queue_up)==1) and on() (time()-max(waffles_queue_report_timestamp_seconds)<60)'


def live(expr):
    return f'({expr}) and on() ({FRESH})'


def jobs(state='.*', worker='.*'):
    return live(f'(sum(waffles_jobs{{run="$run",state=~"{state}",worker=~"{worker}"}}) or vector(0)) and on() max(waffles_run_state{{run="$run"}})')


def rate(worker='.*'):
    return live(f'60 * sum(clamp_min(deriv(waffles_jobs{{run="$run",state="complete",worker=~"{worker}"}}[5m]),0)) or vector(0)')


def average(worker='.*'):
    return live(f'sum(waffles_processing_seconds{{run="$run",state="complete",worker=~"{worker}"}}) / sum(waffles_jobs{{run="$run",state="complete",worker=~"{worker}"}})')


def label(expr, **fields):
    for key, value in fields.items():
        expr = f'label_replace(({expr}), "{key}", "{value}", "", "")'
    return expr


def dashboard():
    panels = []

    def panel(title, queries, x, y, w=4, h=4, kind='stat', unit='locale', description=''):
        p = {'id': len(panels)+1, 'title': title, 'type': kind, 'datasource': DS,
             'gridPos': dict(x=x, y=y, w=w, h=h), 'description': description,
             'targets': [dict(refId=chr(65+i), expr=e, legendFormat=n, instant=kind!='timeseries', range=kind=='timeseries') for i,(e,n) in enumerate(queries)],
             'fieldConfig': {'defaults': {'unit': unit, 'decimals': 0, 'noValue': 'No data yet', 'color': {'mode': 'palette-classic'}}, 'overrides': []},
             'options': {'reduceOptions': {'calcs': ['lastNotNull']}, 'graphMode': 'none', 'textMode': 'value_and_name', 'colorMode': 'value',
                         'legend': {'displayMode': 'list', 'placement': 'bottom'}, 'tooltip': {'mode': 'multi'}}}
        panels.append(p)
        return p

    done, remaining, total = jobs('complete'), jobs('pending|running|classified'), jobs()
    panel('Photos processed', [(done,'Committed results')],0,0,description='Distinct assets with committed results in this run. Includes non-Waffles photos. Benchmark runs finish after classification and never write to Immich.')
    panel('Remaining',[(remaining,'Awaiting completion')],4,0)
    panel('Processed / total',[(f'100*({done})/({total})','Complete')],8,0,unit='percent')['fieldConfig']['defaults']['decimals']=2
    panel('Failed photos',[(jobs('failed'),'Exhausted retries')],12,0)
    panel('Estimated time remaining',[(f'({remaining}) / (({rate()})/60 > 0)','At recent pace')],16,0,unit='s',description='Pending, in-flight and awaiting-write jobs divided by five-minute committed throughput. Unavailable until progress is measurable; not a deadline.')
    panel('Queue report age', [('time()-max(waffles_queue_report_timestamp_seconds)','Telemetry age')],20,0,unit='s')
    for x,worker in enumerate(['mac','pve','still-fawn']):
        panel(worker+' · processed',[(jobs('complete',worker),'Photos'),(f'100*({jobs("complete",worker)})/clamp_min(({done}),1)','Share (%)')],x*6,4,w=6)
    panel('Run state',[(live('max(waffles_run_state{run="$run"})'),'Queue state')],18,4,w=6)['fieldConfig']['defaults']['mappings']=[{'type':'value','options':{'0':{'text':'Paused','color':'orange'},'1':{'text':'Running','color':'blue'},'2':{'text':'Finished','color':'green'}}}]

    workers = ['mac','pve','still-fawn']
    nodes = [('queue','PostgreSQL','Durable job queue',total,average()),
             *[(w,{'mac':'Mac · Metal','pve':'PVE · CPU','still-fawn':'still-fawn · CPU'}[w],'Processed photos',jobs('complete',w),average(w)) for w in workers],
             ('committed','Committed results','Processed photos',done,average())]
    queries = {
        'nodes': ' or '.join(label(f'({value}) or vector(0/0)',id=key,title=title,subtitle=subtitle) for key,title,subtitle,value,_ in nodes),
        'timing': ' or '.join(label(f'({seconds}) or vector(0/0)',id=key) for key,_,_,_,seconds in nodes),
        'inflight': ' or '.join(label(jobs('running',w),id=w) for w in workers),
        'pace': ' or '.join(label(rate(w),id=w) for w in workers),
        'edges': ' or '.join(label(rate(w),id=a+'_'+b,source=a,target=b) for w in workers for a,b in [('queue',w),(w,'committed')])}
    graph = panel('Job distribution · processed photos by backend',[],0,8,w=24,h=14,kind='nodeGraph',description='Node: committed photo count and mean processing seconds/photo. Edge: recent photos/minute. Hover a backend for in-flight jobs and throughput. Means cover completed jobs in this run; timings include thumbnail fetch, detection and classification. RTX is excluded.')
    graph['targets']=[dict(refId=ref,expr=expr,format='table',instant=True,range=False) for ref,expr in queries.items()]
    graph['options']={'nodes':{'mainStatUnit':'photos','secondaryStatUnit':'s/photo'},'edges':{'mainStatUnit':'photos/min'}}
    graph['fieldConfig']['overrides']=[{'matcher':{'id':'byName','options':'mainstat'},'properties':[{'id':'displayName','value':'Processed photos'}]}, {'matcher':{'id':'byName','options':'secondarystat'},'properties':[{'id':'displayName','value':'Mean seconds/photo'}]}]
    graph['fieldConfig']['defaults']['decimals']=1
    graph['fieldConfig']['defaults']['mappings']=[{'type':'special','options':{'match':'nan','result':{'text':'—','color':'gray'}}}]
    transforms=[]
    for ref,name in [('nodes','mainstat'),('timing','secondarystat'),('inflight','detail__in_flight'),('pace','detail__photos_per_minute'),('edges','mainstat')]:
        filt={'id':'byRefId','options':ref}
        transforms += [{'id':'calculateField','filter':filt,'options':{'mode':'reduceRow','reduce':{'reducer':'lastNotNull','include':['Value','Value #'+ref]},'alias':name}},
                       {'id':'organize','filter':filt,'options':{'excludeByName':{'Time':True,'Value':True,'Value #'+ref:True}}}]
    transforms.append({'id':'joinByField','filter':{'id':'byRefId','options':'/^(nodes|timing|inflight|pace)$/'},'options':{'byField':'id','mode':'outerTabular'}})
    graph['transformations']=transforms

    panel('Processed photos by backend',[(jobs('complete',w),w) for w in workers],0,22,w=12,h=7,kind='timeseries')
    p=panel('Throughput by backend · photos/min',[(rate(w),w) for w in workers],12,22,w=12,h=7,kind='timeseries');p['fieldConfig']['defaults']['decimals']=2
    panel('Mean processing time by backend',[(average(w),w) for w in workers],0,29,w=12,h=7,kind='timeseries',unit='s')['fieldConfig']['defaults']['decimals']=2
    panel('In-flight jobs by backend',[(jobs('running',w),w) for w in workers],12,29,w=12,h=7,kind='timeseries')
    panel('Worker ready',[(live(f'max(waffles_worker_ready{{worker="{w}"}})'),w) for w in workers],0,36,w=8)
    panel('Waffles face assignments added',[(live('sum(waffles_assignments{run="$run"}) or vector(0)'),'New assignments')],8,36,w=8)
    panel('Awaiting Immich writes',[(jobs('classified'),'Classified photos')],16,36,w=8)
    panel('Kubernetes worker CPU', [('sum by(pod)(rate(container_cpu_usage_seconds_total{namespace="immich-pilot",container="worker",pod=~"waffles-worker-.*"}[5m]))','{{pod}}')],0,40,w=12,h=7,kind='timeseries',unit='cores')['fieldConfig']['defaults']['decimals']=2
    panel('Worker memory · process high-water mark', [('waffles_worker_rss_bytes','{{worker}}')],12,40,w=12,h=7,kind='timeseries',unit='bytes',description='Process peak resident memory, not current working set. Mac accelerator allocations may not all be included.')
    for x,resource,unit in [(0,'cpu','cores'),(12,'memory','bytes')]:
        panel('VPA recommended '+resource,[('immich_vpa_recommendation{workload=~"waffles-worker-.*",bound="target",resource="'+resource+'"}','{{workload}}')],x,47,w=12,h=7,kind='timeseries',unit=unit,description='Recommendation mode (Off). VPA does not resize or evict backfill workers. Mac is a native worker and has no VPA.')
    for x,profile in [(0,'before'),(12,'after')]:
        expr=f'60 * sum by(run)(waffles_jobs{{run=~"{profile}-[12]",state="complete"}}) / on(run) (max by(run)(waffles_run_finished_timestamp_seconds{{run=~"{profile}-[12]"}})-max by(run)(waffles_run_started_timestamp_seconds{{run=~"{profile}-[12]"}}))'
        panel(profile.title()+' · matched sample photos/min',[(expr,'{{run}}')],x,54,w=12,description='Same 96 photos, ABBA order, reversed second pass. Before: still-fawn alone. After: Mac + PVE + still-fawn. Model warmup excluded. Benchmark mode never writes faces.')['fieldConfig']['defaults']['decimals']=2
    panel('Upload discovery enabled',[(live('max(waffles_discovery_enabled)'),'Hourly discovery')],0,58,w=8)
    panel('Upload discovery errors',[(live('max(waffles_discovery_error)'),'Last attempt failed')],8,58,w=8)
    panel('Last upload discovery',[(live('time()-max(waffles_discovery_last_success_timestamp_seconds)'),'Last success')],16,58,w=8,unit='s')
    panels.append({'id':len(panels)+1,'title':'How to read this dashboard','type':'text','gridPos':dict(x=0,y=62,w=24,h=4),'options':{'mode':'markdown','content':'**One job per asset per run.** Processed means a committed result, including photos without Waffles. Backend totals add up to processed photos. Failed jobs remain visible separately. Node counts show distribution; hover edges for photos/minute; node secondary values show mean seconds/photo. **RTX remains unused.** VPA collects Kubernetes resource recommendations without evictions. Select a benchmark run to inspect its distribution; benchmark jobs never change Immich. New uploads are discovered hourly into a separate durable run.'}})
    return {'uid':'immich-waffles','title':'Waffles · Immich Pet Tagger','schemaVersion':39,'version':2,'editable':False,'tags':['immich','waffles','pets','gitops'],
            'timezone':'utc','refresh':'15s','time':{'from':'now-1h','to':'now'},
            'templating':{'list':[{'name':'run','label':'Run','type':'query','datasource':DS,'query':'label_values(waffles_run_state, run)','refresh':1,'sort':1,'current':{'text':'historical-waffles','value':'historical-waffles'}}]},
            'links':[{'title':'Pet Tagger · references','url':'https://pets.app.home.panderosystems.com','type':'link','targetBlank':True},{'title':'Knowledge Index','url':'/d/knowledge-index/knowledge-index','type':'link'}], 'panels':panels}
