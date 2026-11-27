"""Durable photo completion and backend distribution, using real queue outcomes."""
DS = {'type': 'prometheus', 'uid': 'prometheus'}
FRESH = '(max(waffles_queue_up)==1) and on() (time()-max(waffles_queue_report_timestamp_seconds)<60)'
WORKERS = ['mac','pve','still-fawn','fun-bedbug','chief-horse']


def live(expr):
    return f'({expr}) and on() ({FRESH})'


def jobs(state='.*', worker='.*'):
    return live(f'(sum(max by(run,worker,state)(waffles_jobs{{run="$run",state=~"{state}",worker=~"{worker}"}})) or vector(0)) and on() max(waffles_run_state{{run="$run"}})')


def rate(worker='.*'):
    # Durable PG totals are exported again by every replacement queue pod.
    # Deduplicate each instant BEFORE the range derivative, otherwise retired
    # pod slopes remain counted until their samples leave the five-minute window.
    return live(f'60 * sum(clamp_min(deriv((max by(run,worker,state)(waffles_jobs{{run="$run",state="complete",worker=~"{worker}"}}))[5m:15s]),0)) or vector(0)')


def average(worker='.*'):
    return live(f'sum(max by(run,worker,state)(waffles_processing_seconds{{run="$run",state="complete",worker=~"{worker}"}})) / sum(max by(run,worker,state)(waffles_jobs{{run="$run",state="complete",worker=~"{worker}"}}))')


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
    panel('Estimated time remaining',[(f'(({remaining}) / (({rate()})/60 > 0)) and on() (max(waffles_run_state{{run="$run"}})==1)','At recent pace')],16,0,unit='s',description='Pending, in-flight and awaiting-write jobs divided by five-minute committed throughput. Unavailable while paused or until progress is measurable; not a deadline.')
    panel('Queue report age', [('time()-max(waffles_queue_report_timestamp_seconds)','Telemetry age')],20,0,unit='s')
    for x,worker in enumerate(WORKERS):
        panel(worker+' · processed',[(jobs('complete',worker),'Photos'),(f'100*({jobs("complete",worker)})/clamp_min(({done}),1)','Share (%)')],x*4,4,w=4)
    panel('Run state',[(live('max(waffles_run_state{run="$run"})'),'Queue state')],20,4,w=4)['fieldConfig']['defaults']['mappings']=[{'type':'value','options':{'0':{'text':'Paused','color':'orange'},'1':{'text':'Running','color':'blue'},'2':{'text':'Finished','color':'green'}}}]

    workers = WORKERS
    nodes = [('queue','PostgreSQL','Durable job queue',total,average()),
             *[(w,{'mac':'Mac · Apple Silicon','pve':'PVE · CPU','still-fawn':'still-fawn · CPU','fun-bedbug':'fun-bedbug · native','chief-horse':'chief-horse · native'}[w],'Processed photos',jobs('complete',w),average(w)) for w in workers],
             ('committed','Committed results','Processed photos',done,average())]
    queries = {
        'nodes': ' or '.join(label(f'({value}) or vector(0/0)',id=key,title=title,subtitle=subtitle) for key,title,subtitle,value,_ in nodes),
        'timing': ' or '.join(label(f'({seconds}) or vector(0/0)',id=key) for key,_,_,_,seconds in nodes),
        'inflight': ' or '.join(label(jobs('running',w),id=w) for w in workers),
        'pace': ' or '.join(label(rate(w),id=w) for w in workers),
        'edges': ' or '.join(label(rate(w),id=a+'_'+b,source=a,target=b) for w in workers for a,b in [('queue',w),(w,'committed')])}
    graph = panel('Job distribution · processed photos by backend',[],0,8,w=24,h=20,kind='nodeGraph',description='Node: committed photo count and mean processing seconds/photo. Edge: recent photos/minute. Hover a backend for in-flight jobs and throughput. Means cover completed jobs in this run; timings include thumbnail fetch, detection and classification. RTX is excluded.')
    graph['targets']=[dict(refId=ref,expr=expr,format='table',instant=True,range=False) for ref,expr in queries.items()]
    graph['options']={'nodes':{'mainStatUnit':'','secondaryStatUnit':'s/photo'},'edges':{'mainStatUnit':'photos/min'}}
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
    panel('Active / desired processes',[(live(f'max(waffles_worker_{kind}_instances{{worker="{w}"}})'),w+' '+kind) for w in workers for kind in ['active','desired']],0,36,w=8)
    panel('Waffles face assignments added',[(live('sum(max by(run,worker,state)(waffles_assignments{run="$run"})) or vector(0)'),'New assignments')],8,36,w=8)
    panel('Awaiting Immich writes',[(jobs('classified'),'Classified photos')],16,36,w=8)
    panel('Kubernetes worker CPU', [('sum by(pod)(rate(container_cpu_usage_seconds_total{namespace="immich-pilot",container="worker",pod=~"waffles-(worker|burst)-.*"}[5m]))','{{pod}}')],0,40,w=12,h=7,kind='timeseries',unit='cores')['fieldConfig']['defaults']['decimals']=2
    panel('Worker memory · process high-water mark', [('max by(worker)(waffles_worker_rss_bytes)','{{worker}}')],12,40,w=12,h=7,kind='timeseries',unit='bytes',description='Process peak resident memory, not current working set. Mac accelerator allocations may not all be included.')
    for x,resource,unit in [(0,'cpu','cores'),(12,'memory','bytes')]:
        panel('VPA recommended '+resource,[('immich_vpa_recommendation{workload=~"waffles-(worker|burst)-.*",bound="target",resource="'+resource+'"}','{{workload}}')],x,47,w=12,h=7,kind='timeseries',unit=unit,description='Recommendation mode (Off). VPA does not resize or evict backfill workers. Mac is a native worker and has no VPA.')
    for x,profile in [(0,'before'),(12,'after')]:
        expr=f'60 * sum by(run)(max by(run,worker,state)(waffles_jobs{{run=~"{profile}-[12]",state="complete"}})) / on(run) (max by(run)(waffles_run_finished_timestamp_seconds{{run=~"{profile}-[12]"}})-max by(run)(waffles_run_started_timestamp_seconds{{run=~"{profile}-[12]"}}))'
        panel(profile.title()+' · matched sample photos/min',[(expr,'{{run}}')],x,54,w=12,description='Same 96 photos, ABBA order, reversed second pass. Before: still-fawn alone. After: Mac + PVE + still-fawn. Model warmup excluded. Benchmark mode never writes faces.')['fieldConfig']['defaults']['decimals']=2
    panel('Upload discovery enabled',[(live('max(waffles_discovery_enabled)'),'Hourly discovery')],0,58,w=8)
    panel('Upload discovery errors',[(live('max(waffles_discovery_error)'),'Last attempt failed')],8,58,w=8)
    panel('Last upload discovery',[(live('time()-max(waffles_discovery_last_success_timestamp_seconds)'),'Last success')],16,58,w=8,unit='s')
    panels.append({'id':len(panels)+1,'title':'How to read this dashboard','type':'text','gridPos':dict(x=0,y=62,w=24,h=4),'options':{'mode':'markdown','content':'**One job per asset per run.** Processed means a committed result, including photos without Waffles. Backend totals add up to processed photos. Failed jobs remain visible separately. Node counts show distribution; hover edges for photos/minute; node secondary values show mean seconds/photo. **RTX remains unused.** VPA collects Kubernetes resource recommendations without evictions. Select a benchmark run to inspect its distribution; benchmark jobs never change Immich. New uploads are discovered hourly into a separate durable run.'}})
    for p in panels:
        if p['gridPos']['y']>=22:p['gridPos']['y']+=6
    for x,profile in [(0,'before'),(12,'after')]:
        pattern=f'burst-.*-pool-{profile}-[ab]'
        expr=f'60 * sum by(run)(max by(run,worker,state)(waffles_jobs{{run=~"{pattern}",state="complete"}})) / on(run) (max by(run)(waffles_run_finished_timestamp_seconds{{run=~"{pattern}"}})-max by(run)(waffles_run_started_timestamp_seconds{{run=~"{pattern}"}}))'
        panel('Extra capacity '+profile+' · photos/min',[(expr,'{{run}}')],x,72,w=12,h=5,description='Continuous-production experiment on the same frozen sample plus reviewed holdouts. Baseline workers keep processing real jobs. Before: one extra Mac and still-fawn worker. After: selected extra capacity. No result is shown until that comparison actually completes. See the journal for quality gates and failed trials.')['fieldConfig']['defaults']['decimals']=2
    panel('Baseline production processes',[(live(f'max(waffles_pool_active_instances{{worker="{w}",pool="base"}})'),w) for w in workers],0,77,w=12,h=5,description='Permanent production workers. Tuning affects the separate extra-worker pool. Chief-horse remains guarded standby until capacity and quality validation permit admission.')
    panel('Extra processes · active / desired',[(live(f'max(waffles_pool_{kind}_instances{{worker="{w}",pool="burst"}})'),w+' '+kind) for w in workers[:3] for kind in ['active','desired']],12,77,w=12,h=5)
    panel('Mac host CPU and Apple GPU utilization',[(live('max(waffles_mac_'+name+'_percent) and on() (time()-max(waffles_mac_report_timestamp_seconds)<60)'),name.upper()) for name in ['cpu','gpu']],0,82,w=12,h=7,kind='timeseries',unit='percent',description='Whole-Mac utilization, including other applications. Model inference uses Metal; CPU utilization alone does not measure accelerator load.')
    panel('Extra Mac workers · accelerator allocations',[('sum(max by(worker,instance)(waffles_instance_accelerator_bytes{worker="mac"}))','Metal driver allocations')],12,82,w=12,h=7,kind='timeseries',unit='bytes',description='Sum of reported MPS driver allocations for extra workers only. May overlap RSS; do not add it to RSS as total physical memory.')
    panel('Mac memory pressure',[(live('max(waffles_mac_pressure) and on() (time()-max(waffles_mac_report_timestamp_seconds)<60)'),'OS pressure level')],0,89,w=12,description='1 normal, 2 warning, 4 critical. Mac extras record warnings and continue under the approved policy; critical or unknown pressure stops extra capacity. Baseline Metal remains running.')
    panel('Mac system swap used',[(live('max(waffles_mac_swap_bytes) and on() (time()-max(waffles_mac_report_timestamp_seconds)<60)'),'All applications')],12,89,w=12,unit='bytes')
    panel('Mac processed photos · CPU versus Metal',[(live(f'sum(max by(run,worker,pool,device)(waffles_device_jobs{{run="$run",worker="mac",device="{device}"}})) or vector(0)'),name) for device,name in [('cpu','CPU'),('mps','Metal')]],0,93,w=12,h=5,description='Committed results for the selected run, attributed to the actual inference device. Baseline remains Metal; extra workers can use CPU or Metal.')
    panel('Processed photos · baseline versus extra',[(live('sum by(worker,pool)(max by(run,worker,pool,device)(waffles_device_jobs{run="$run"}))'),'{{worker}} · {{pool}}')],12,93,w=12,h=5)
    panel('Failed assets by reason',[(live('sum by(reason)(max by(run,reason)(waffles_failed_jobs{run="$run"}))'),'{{reason}}')],0,98,w=24,h=5,description='Per-asset errors never pause the run. Four attempts per stage: thumbnail/inference retries after 30 seconds; face/tag application after 60 seconds. Exhaustion retains failed status and workers move on. thumbnail_http_404 means an unavailable preview; apply_http_404 means a write-stage failure.')
    panel('Mac CPU threads · extra worker',[(live('max(waffles_burst_cpu_threads{worker="mac"})'),'Desired'),(live('max(waffles_instance_cpu_threads{worker="mac"})'),'Effective PyTorch threads')],0,103,w=8,h=5,description='CPU inference threads per extra Mac process. Baseline Metal stays unchanged. Thread changes drain and replace only extras; each configuration is warmed and quality-checked before selection.')
    expr='60 * sum by(run)(max by(run,worker,state)(waffles_jobs{run=~"burst-.*-threads-[0-9]+-[ab]",state="complete"})) / on(run) (max by(run)(waffles_run_finished_timestamp_seconds{run=~"burst-.*-threads-[0-9]+-[ab]"})-max by(run)(waffles_run_started_timestamp_seconds{run=~"burst-.*-threads-[0-9]+-[ab]"}))'
    panel('One CPU model · thread sweep photos/min',[(expr,'{{run}}')],8,103,w=16,h=5,description='Same 122 photos and reviewed holdouts, one extra CPU model. Counterbalanced 2/4/8/16-thread experiment; warm-up excluded, production baselines continue. Only completed runs appear; consult the journal for validity and failed trials.')['fieldConfig']['defaults']['decimals']=1
    return {'uid':'immich-waffles','title':'Waffles · Immich Pet Tagger','schemaVersion':39,'version':2,'editable':False,'tags':['immich','waffles','pets','gitops'],
            'timezone':'utc','refresh':'15s','time':{'from':'now-1h','to':'now'},
            'templating':{'list':[{'name':'run','label':'Run','type':'query','datasource':DS,'query':'label_values(waffles_run_state, run)','refresh':1,'sort':1,'current':{'text':'historical-waffles','value':'historical-waffles'}}]},
            'links':[{'title':'Pet Tagger · references','url':'https://pets.app.home.panderosystems.com','type':'link','targetBlank':True},{'title':'Knowledge Index','url':'/d/knowledge-index/knowledge-index','type':'link'}], 'panels':panels}
