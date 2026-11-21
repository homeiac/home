"""Shared verified Immich PromQL for dashboards and alerts (#217)."""
QUEUE = 'immich_queue_jobs{queue="thumbnail_generation",state=~"waiting|delayed|prioritized|paused"}'
BACKLOG = f'sum({QUEUE})'
RATE = f'((sum(rate(immich_jobs_asset_generate_thumbnails_success_total{{namespace="immich-pilot",endpoint="metrics-ms"}}[5m]))) or ({BACKLOG} == 0))'
THROTTLE = '100 * sum by(pod)(rate(container_cpu_cfs_throttled_periods_total{namespace="immich-pilot",container!="",container!="POD"}[5m])) / sum by(pod)(rate(container_cpu_cfs_periods_total{namespace="immich-pilot",container!="",container!="POD"}[5m]))'
ETA = f'({BACKLOG} / ({RATE} > 0)) or ({BACKLOG} == 0)'
CPU = 'sum by(pod)(rate(container_cpu_usage_seconds_total{namespace="immich-pilot",container!="",container!="POD"}[5m]))'
MEMORY = 'sum by(pod)(container_memory_working_set_bytes{namespace="immich-pilot",container!="",container!="POD"})'
QUEUES = ['library', 'sidecar', 'metadata', 'thumbnail_generation', 'face_detection', 'facial_recognition', 'smart_search', 'ocr', 'video_conversion', 'duplicate_detection']

OCR_BACKLOG = 'sum(immich_queue_jobs{queue="ocr",state=~"waiting|delayed|prioritized|paused"})'
OCR_IDLE = 'sum(immich_queue_jobs{queue="ocr",state!="failed"}) == 0'
OCR_RATE = f'(sum(rate(immich_jobs_ocr_success_total{{namespace="immich-pilot",endpoint="metrics-ms"}}[5m])) or ({OCR_IDLE}))'
GPU = '{Hostname="k3s-vm-pumped-piglet-gpu"}'
OCR_FAILURE_RATE = f'(sum(rate(immich_jobs_ocr_failed_total{{namespace="immich-pilot",endpoint="metrics-ms"}}[5m])) or ({OCR_IDLE}))'
VIDEO_QUEUE = 'immich_queue_jobs{queue="video_conversion"}'
VIDEO_BACKLOG = 'sum(immich_queue_jobs{queue="video_conversion",state=~"waiting|delayed|prioritized|paused"})'
VIDEO_IDLE = 'sum(immich_queue_jobs{queue="video_conversion",state!="failed"}) == 0'
VIDEO_METRICS = '{namespace="immich-pilot",endpoint="metrics-ms"}'
VIDEO_RATE = f'(sum(rate(immich_jobs_asset_encode_video_success_total{VIDEO_METRICS}[5m])) or ({VIDEO_IDLE})) * 60'
VIDEO_ERRORS = f'(sum(rate(immich_jobs_asset_encode_video_failed_total{VIDEO_METRICS}[5m])) or ({VIDEO_IDLE})) * 60'
OVERVIEW_HEIGHT = 119


def add_panels(panel, panels):
    """Append an Immich overview to a fresh panel list; return its height."""
    def add(title, expr, x, y, w=8, h=6, kind='timeseries', unit='short', legend='', description=''):
        panel(title, expr, x, y, w, h, kind, unit, legend)
        panels[-1]['description'] = description
        if kind == 'stat':
            panels[-1]['targets'][0].update(instant=True, range=False)
        return panels[-1]
    add('Immich thumbnails waiting', BACKLOG, 0, 0, 6, 4, 'stat', description='Waiting + delayed + prioritized + paused BullMQ jobs. Missing telemetry is not zero. Active jobs are shown separately.')
    add('Immich thumbnails completed / minute', '('+RATE+') * 60', 6, 0, 6, 4, 'stat', description='Successful asset thumbnail jobs over the last five minutes; not individual image variants.')
    add('Immich thumbnail drain estimate', ETA, 12, 0, 6, 4, 'stat', 's', description='Backlog divided by five-minute completion rate. Assumes no new arrivals; no estimate while stalled. Zero means empty queue.')
    add('Immich telemetry source health', 'immich_observer_source_up', 18, 0, 6, 4, 'stat', legend='{{source}}', description='1 = latest collection succeeded; 0 = failed. VPA starts reporting after policies are installed.')
    add('Immich queue backlog over time', 'sum by(queue)(immich_queue_jobs{state=~"waiting|delayed|prioritized|paused"})', 0, 4, 12, 7, legend='{{queue}}')
    add('Immich active and failed jobs', 'sum by(queue,state)(immich_queue_jobs{state=~"active|failed"})', 12, 4, 12, 7, legend='{{queue}} · {{state}}', description='Failed state is retained failed jobs, not an error rate. An empty failed queue does not prove progress.')
    p = add('Immich CPU usage and hard limits', CPU, 0, 11, 12, 7, legend='{{pod}} usage', unit='cores')
    p['targets'].append({'refId':'B','expr':'sum by(pod)(kube_pod_container_resource_limits{namespace="immich-pilot",resource="cpu"})','legendFormat':'{{pod}} limit'})
    add('Immich CPU throttled periods', THROTTLE, 12, 11, 12, 7, unit='percent', legend='{{pod}}', description='Share of CPU scheduling periods throttled by a hard limit; not percent CPU utilization. Correlate with backlog and throughput.')
    p = add('Immich memory usage and hard limits', MEMORY, 0, 18, 12, 7, unit='bytes', legend='{{pod}} usage')
    p['targets'].append({'refId':'B','expr':'sum by(pod)(kube_pod_container_resource_limits{namespace="immich-pilot",resource="memory"})','legendFormat':'{{pod}} limit'})
    add('Immich successful thumbnails / minute over time', '('+RATE+') * 60', 12, 18, 12, 7, description='Zero throughput with positive backlog means waiting or stalled, even if no job has failed.')
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
    add('Summaries available in source snapshot', 'immich_sync_available_summaries', 0, 50, 6, 4, 'stat', description='Successful summaries in the PostgreSQL catalog snapshot. The original Parquet worker can be ahead until the next catalog refresh.')
    add('Enrichment waiting for Immich', 'immich_sync_assets{state="pending"}', 6, 50, 6, 4, 'stat')
    add('Enrichment preserved in Immich', 'immich_sync_assets{state="applied"}', 12, 50, 6, 4, 'stat', description='Custom metadata verified through the Immich API. Includes captions, tags, groups and old face labels; this does not mean native descriptions or people have been changed.')
    p = add('Normal captions: gated', 'immich_sync_visible_captions_enabled', 18, 50, 6, 4, 'stat', description='Normal caption/GPS/date writes remain disabled for read-only external libraries. Custom metadata survives metadata extraction.')
    p.setdefault('fieldConfig', {}).setdefault('defaults', {})['mappings'] = [{'type':'value','options':{'0':{'text':'Preserve only','color':'blue'}}}]
    add('Enrichment reconciliation over time', 'immich_sync_assets', 0, 54, 12, 7, legend='{{state}}', description='Pending and errors retry incrementally. Conflicts preserve edits. Excluded paths are outside the imported year folders; missing assets are not automatically imported.')
    add('Summary preservation over time', 'immich_sync_summaries', 12, 54, 12, 7, legend='{{state}}', description='Counts only reconciliation records containing a summary. Separate from the larger source generation backlog.')
    add('Source-confirmed face labels preserved', 'immich_sync_confirmed_labels_preserved', 0, 61, 6, 4, 'stat', description='Labels saved as provenance in custom metadata, not native Immich face assignments. Native face transfer remains disabled.')
    add('Reconciliation worker ready', 'immich_sync_api_ready', 6, 61, 6, 4, 'stat')
    add('Source discovery age', 'time()-immich_sync_last_discovery', 12, 61, 6, 4, 'stat', 's', description='Discovery runs every ten minutes. Zero timestamp means no discovery has succeeded yet.')
    add('Reconciliation mode', 'immich_sync_mode', 18, 61, 6, 4, 'stat', legend='{{mode}}')
    add('Reconciliation cycle duration', 'immich_sync_cycle_seconds', 0, 65, 12, 6, unit='s')
    add('Oldest eligible transfer waiting', 'immich_sync_oldest_pending_seconds', 12, 65, 12, 6, unit='s')
    add('Reconciliation measured stage duration', 'immich_sync_stage_seconds', 0, 71, 24, 6, unit='s', legend='{{stage}}', description='Last completed inventory scan, source query, or individual asset preservation duration. Counts in the value stream map are separate from these measured timings.')
    add('OCR jobs waiting', OCR_BACKLOG, 0, 78, 6, 4, 'stat')
    add('OCR completed / minute', OCR_RATE+' * 60', 6, 78, 6, 4, 'stat', description='Successful OCR jobs, including photos with no text. Five-minute rate; compare before and after CUDA warm-up.')
    add('OCR drain estimate', f'({OCR_BACKLOG} / ({OCR_RATE} > 0)) or ({OCR_BACKLOG} == 0)', 12, 78, 6, 4, 'stat', 's', description='Assumes no new arrivals. Initial TensorRT engine compilation can inflate this estimate. Blank while stalled; zero only when queue is empty.')
    add('Shared GPU driver', 'max by(DCGM_FI_DRIVER_VERSION)(DCGM_FI_DEV_GPU_UTIL'+GPU+' * 0 + 1)', 18, 78, 6, 4, 'stat', legend='{{DCGM_FI_DRIVER_VERSION}}', description='Loaded driver reported by DCGM; value 1 means present.')['options']['textMode'] = 'name'
    add('OCR throughput over time', OCR_RATE+' * 60', 0, 82, 12, 7, legend='OCR jobs/min', description='Jobs per minute. The driver and CUDA rollout briefly interrupt processing; use sustained rates after model warm-up.')
    add('OCR queue states over time', 'sum by(state)(immich_queue_jobs{queue="ocr"})', 12, 82, 12, 7, legend='{{state}}')
    add('Shared RTX 3070 utilization', 'max(DCGM_FI_DEV_GPU_UTIL'+GPU+')', 0, 89, 8, 7, unit='percent', legend='GPU busy', description='Whole GPU shared by Immich, Frigate and Ollama. This is not attribution to OCR.')
    p = add('Shared RTX 3070 memory', 'max(DCGM_FI_DEV_FB_USED'+GPU+') * 1024 * 1024', 8, 89, 8, 7, unit='bytes', legend='Used')
    p['targets'].append({'refId':'B','expr':'max(DCGM_FI_DEV_FB_FREE'+GPU+') * 1024 * 1024','legendFormat':'Free'})
    add('GPU service replicas ready', 'kube_deployment_status_replicas_available{namespace=~"immich-pilot|frigate|ollama",deployment=~"immich-server|immich-machine-learning|photo-bonsai|frigate|ollama-gpu"}', 16, 89, 8, 7, legend='{{deployment}}', description='Availability only. Verify processing through application logs and job metrics.')
    add('OCR failed attempts / minute', OCR_FAILURE_RATE+' * 60', 0, 96, 12, 6, legend='Failed attempts/min', description='Actual worker errors. Immich may discard failed jobs, so a zero retained failed queue does not mean zero errors. Requeue missing OCR after recovery.')
    add('Immich ML restarts', 'sum by(pod)(kube_pod_container_status_restarts_total{namespace="immich-pilot",container="main",pod=~"immich-machine-learning-.*"})', 12, 96, 12, 6, legend='{{pod}}', description='Correlate restarts with failed attempts, memory and throughput.')
    add('Video transcodes waiting', VIDEO_BACKLOG, 0, 103, 6, 4, 'stat')
    add('Video jobs completed / minute', VIDEO_RATE, 6, 103, 6, 4, 'stat', description='Successful video conversion jobs, including remuxes and software fallback. Check server logs to confirm NVENC.')
    add('Video jobs failed / minute', VIDEO_ERRORS, 12, 103, 6, 4, 'stat', description='Failed worker attempts. A successful software fallback is counted as success.')
    add('Shared RTX 3070 encoder utilization', 'max(DCGM_FI_DEV_ENC_UTIL'+GPU+')', 18, 103, 6, 4, 'stat', 'percent', description='Whole-device NVENC utilization, sampled by DCGM.')
    add('Video conversion queue over time', f'sum by(state)({VIDEO_QUEUE})', 0, 107, 8, 7, legend='{{state}}')
    p = add('Video conversion outcomes over time', VIDEO_RATE, 8, 107, 8, 7, legend='Completed / minute')
    p['targets'].append({'refId':'B','expr':VIDEO_ERRORS,'legendFormat':'Failed / minute'})
    add('Shared RTX 3070 video engine activity', 'max(DCGM_FI_DEV_ENC_UTIL'+GPU+')', 16, 107, 8, 7, unit='percent', legend='Encoder', description='Whole-device NVENC activity. Short encodes can complete between scrapes.')
    return OVERVIEW_HEIGHT


def add_graph(graph, node):
    """Independent Immich branch; edges express dependencies, not timing."""
    for queue in QUEUES:
        expr = f'sum(immich_queue_jobs{{queue="{queue}",state=~"waiting|delayed|prioritized|paused"}})'
        graph['targets'][0]['expr'] += ' or '+node(expr, 'immich_'+queue, 'Immich '+queue.replace('_', ' ')+' (queued jobs)')
    graph['targets'][0]['expr'] += ' or '+node('('+RATE+') * 60', 'immich_gallery', 'Immich thumbnail completions (jobs/min)')
    graph['targets'][0]['expr'] += ' or '+node(OCR_RATE+' * 60', 'immich_ocr_completed', 'Immich OCR completions (jobs/min)')
    graph['targets'][0]['expr'] += ' or '+node(OCR_FAILURE_RATE+' * 60', 'immich_ocr_errors', 'Immich OCR failed attempts (/min)')
    graph['targets'][0]['expr'] += ' or '+node(VIDEO_RATE, 'immich_video_completed', 'Immich video conversion completions (jobs/min)')
    graph['targets'][0]['expr'] += ' or '+node(VIDEO_ERRORS, 'immich_video_errors', 'Immich video conversion failures (/min)')
    for source, target in [('ocr','ocr_errors'),('ocr','ocr_completed'),('library','metadata'),('sidecar','metadata'),('metadata','thumbnail_generation'),('thumbnail_generation','gallery'),('thumbnail_generation','face_detection'),('face_detection','facial_recognition'),('thumbnail_generation','smart_search'),('smart_search','duplicate_detection'),('thumbnail_generation','ocr'),('metadata','video_conversion'),('video_conversion','video_completed'),('video_conversion','video_errors')]:
        expr='vector(1)'
        for label, value in [('id', 'immich_'+source+'_'+target),('source','immich_'+source),('target','immich_'+target)]:
            expr = f'label_replace({expr}, "{label}", "{value}", "", "")'
        graph['targets'][1]['expr'] += ' or '+expr
    for suffix, title, expr in [
        ('source', 'Knowledge Index completed summaries', 'immich_sync_available_summaries'),
        ('pending', 'Enrichment queue (assets)', 'immich_sync_assets{state="pending"}'),
        ('preserved', 'Immich custom metadata (assets)', 'immich_sync_assets{state="applied"}'),
        ('review', 'Sync errors or conflicts (assets)', 'sum(immich_sync_assets{state=~"error|conflict"})'),
        ('unmapped', 'Missing or excluded (assets)', 'sum(immich_sync_assets{state=~"missing|excluded"})')]:
        graph['targets'][0]['expr'] += ' or '+node(expr, 'sync_'+suffix, title)
    for source, target in [('sync_source','sync_pending'), ('immich_metadata','sync_pending'), ('sync_pending','sync_preserved'), ('sync_pending','sync_review'), ('sync_source','sync_unmapped')]:
        expr='vector(1)'
        for label, value in [('id', source+'_'+target),('source',source),('target',target)]:
            expr = f'label_replace({expr}, "{label}", "{value}", "", "")'
        graph['targets'][1]['expr'] += ' or '+expr
    graph['description'] += ' Immich is a separate branch reading the same library. Its nodes show queued jobs, and thumbnail/OCR completions show jobs/min. Static edges show logical processing dependencies, not measured transfer rates or elapsed time. Immich uses its own ML service; Frigate is not its face engine. Knowledge Index enrichment flows through a durable reconciliation queue into verified Immich custom metadata. These are counts, not timing percentages. The enrichment queue also includes face and group context without a summary. Native descriptions and face assignments remain gated; preserved provenance is not native UI promotion. See Photo App for CPU throttling, queue states, throughput and VPA recommendations.'
