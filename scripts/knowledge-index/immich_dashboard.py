"""Shared verified Immich PromQL for dashboards and alerts (#217)."""
QUEUE = 'immich_queue_jobs{queue="thumbnail_generation",state=~"waiting|delayed|prioritized|paused"}'
BACKLOG = f'sum({QUEUE})'
RATE = 'sum(rate(immich_jobs_asset_generate_thumbnails_success_total{namespace="immich-pilot",endpoint="metrics-ms"}[5m]))'
THROTTLE = '100 * sum by(pod)(rate(container_cpu_cfs_throttled_periods_total{namespace="immich-pilot",container!="",container!="POD"}[5m])) / sum by(pod)(rate(container_cpu_cfs_periods_total{namespace="immich-pilot",container!="",container!="POD"}[5m]))'
ETA = f'({BACKLOG} / ({RATE} > 0)) or ({BACKLOG} == 0)'
CPU = 'sum by(pod)(rate(container_cpu_usage_seconds_total{namespace="immich-pilot",container!="",container!="POD"}[5m]))'
MEMORY = 'sum by(pod)(container_memory_working_set_bytes{namespace="immich-pilot",container!="",container!="POD"})'
QUEUES = ['library', 'sidecar', 'metadata', 'thumbnail_generation', 'face_detection', 'facial_recognition', 'smart_search', 'ocr', 'video_conversion', 'duplicate_detection']


def add_panels(panel, panels):
    """Append an Immich overview to a fresh panel list; return its height."""
    def add(title, expr, x, y, w=8, h=6, kind='timeseries', unit='short', legend='', description=''):
        panel(title, expr, x, y, w, h, kind, unit, legend)
        panels[-1]['description'] = description
        if kind == 'stat':
            panels[-1]['targets'][0].update(instant=True, range=False)
        return panels[-1]
    add('Immich thumbnails waiting', BACKLOG, 0, 0, 6, 4, 'stat', description='Waiting + delayed + prioritized + paused BullMQ jobs. Missing telemetry is not zero. Active jobs are shown separately.')
    add('Immich thumbnails completed / minute', RATE+' * 60', 6, 0, 6, 4, 'stat', description='Successful asset thumbnail jobs over the last five minutes; not individual image variants.')
    add('Immich thumbnail drain estimate', ETA, 12, 0, 6, 4, 'stat', 's', description='Backlog divided by five-minute completion rate. Assumes no new arrivals; no estimate while stalled. Zero means empty queue.')
    add('Immich telemetry source health', 'immich_observer_source_up', 18, 0, 6, 4, 'stat', legend='{{source}}', description='1 = latest collection succeeded; 0 = failed. VPA starts reporting after policies are installed.')
    add('Immich queue backlog over time', 'sum by(queue)(immich_queue_jobs{state=~"waiting|delayed|prioritized|paused"})', 0, 4, 12, 7, legend='{{queue}}')
    add('Immich active and failed jobs', 'sum by(queue,state)(immich_queue_jobs{state=~"active|failed"})', 12, 4, 12, 7, legend='{{queue}} · {{state}}', description='Failed state is retained failed jobs, not an error rate. An empty failed queue does not prove progress.')
    p = add('Immich CPU usage and hard limits', CPU, 0, 11, 12, 7, legend='{{pod}} usage', unit='cores')
    p['targets'].append({'refId':'B','expr':'sum by(pod)(kube_pod_container_resource_limits{namespace="immich-pilot",resource="cpu"})','legendFormat':'{{pod}} limit'})
    add('Immich CPU throttled periods', THROTTLE, 12, 11, 12, 7, unit='percent', legend='{{pod}}', description='Share of CPU scheduling periods throttled by a hard limit; not percent CPU utilization. Correlate with backlog and throughput.')
    p = add('Immich memory usage and hard limits', MEMORY, 0, 18, 12, 7, unit='bytes', legend='{{pod}} usage')
    p['targets'].append({'refId':'B','expr':'sum by(pod)(kube_pod_container_resource_limits{namespace="immich-pilot",resource="memory"})','legendFormat':'{{pod}} limit'})
    add('Immich successful thumbnails / minute over time', RATE+' * 60', 12, 18, 12, 7, description='Zero throughput with positive backlog means waiting or stalled, even if no job has failed.')
    for x, resource, unit in [(0, 'cpu', 'cores'), (12, 'memory', 'bytes')]:
        add('VPA recommended '+resource+' requests', f'immich_vpa_recommendation{{resource="{resource}"}}', x, 25, 12, 7, unit=unit, legend='{{workload}} · {{bound}}', description='Recommendation only (Off). These are requests, not hard limits; no pod is resized or restarted. Early recommendations need a representative workload baseline.')
    add('VPA update mode', 'immich_vpa_policy_info', 0, 32, 8, 4, 'stat', legend='{{workload}} · {{mode}}')
    add('Immich API and worker scrape health', 'up{namespace="immich-pilot"}', 8, 32, 8, 4, 'stat', legend='{{service}} · {{endpoint}}')
    add('Immich queue telemetry age', 'time()-immich_observer_last_success_timestamp_seconds{source="queues"}', 16, 32, 8, 4, 'stat', 's')
    graph = {'id': len(panels)+1, 'title': 'Immich value stream map', 'type': 'nodeGraph',
        'datasource': {'type':'prometheus','uid':'prometheus'}, 'gridPos': {'x':0,'y':37,'w':24,'h':12},
        'description': 'The Immich processing branch, isolated from legacy enrichment so the backlog is easy to locate.',
        'targets': [{'refId': ref, 'expr': 'vector(0) > 1', 'format':'table','instant':True,'range':False} for ref in ['nodes','edges']],
        'options': {'nodes': {'mainStatUnit': ''}},
        'transformations': [
            {'id':'calculateField','filter':{'id':'byRefId','options':'nodes'},'options':{'mode':'reduceRow','reduce':{'reducer':'sum','include':['Value','Value #nodes']},'alias':'mainstat'}},
            {'id':'organize','filter':{'id':'byRefId','options':'nodes'},'options':{'excludeByName':{'Time':True,'Value':True,'Value #nodes':True}}},
            {'id':'organize','filter':{'id':'byRefId','options':'edges'},'options':{'excludeByName':{'Time':True,'Value':True,'Value #edges':True}}}]}
    def node(expr, node_id, title):
        return f'label_replace(label_replace(({expr}), "id", "{node_id}", "", ""), "title", "{title}", "", "")'
    add_graph(graph, node)
    panels.append(graph)
    return 50


def add_graph(graph, node):
    """Independent Immich branch; edges express dependencies, not timing."""
    for queue in QUEUES:
        expr = f'sum(immich_queue_jobs{{queue="{queue}",state=~"waiting|delayed|prioritized|paused"}})'
        graph['targets'][0]['expr'] += ' or '+node(expr, 'immich_'+queue, 'Immich '+queue.replace('_', ' ')+' (queued jobs)')
    graph['targets'][0]['expr'] += ' or '+node(RATE+' * 60', 'immich_gallery', 'Immich thumbnail completions (jobs/min)')
    for source, target in [('library','metadata'),('sidecar','metadata'),('metadata','thumbnail_generation'),('thumbnail_generation','gallery'),('thumbnail_generation','face_detection'),('face_detection','facial_recognition'),('thumbnail_generation','smart_search'),('smart_search','duplicate_detection'),('thumbnail_generation','ocr'),('metadata','video_conversion')]:
        expr='vector(1)'
        for label, value in [('id', 'immich_'+source+'_'+target),('source','immich_'+source),('target','immich_'+target)]:
            expr = f'label_replace({expr}, "{label}", "{value}", "", "")'
        graph['targets'][1]['expr'] += ' or '+expr
    graph['description'] += ' Immich is a separate branch reading the same library. Its nodes show queued jobs, and thumbnail completions show jobs/min. Static edges show logical processing dependencies, not measured transfer rates or elapsed time. Immich uses its own ML service; Frigate is not its face engine. Custom enrichment is not yet wired into Immich. See Photo App for CPU throttling, queue states, throughput and VPA recommendations.'
