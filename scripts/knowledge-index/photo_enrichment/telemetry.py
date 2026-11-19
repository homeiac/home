"""Bounded OTel traces/metrics and structured logs; never record photo data."""
from collections import Counter, defaultdict, deque
from contextlib import contextmanager, nullcontext
import contextvars
import hashlib
import json
import logging
import os
import threading
import time
import uuid

CURRENT = contextvars.ContextVar('photo_request',default=None)
ROUTES = {'/','/app.js','/style.css','/healthz','/metrics','/api/config','/api/status',
          '/api/faces','/api/faces/selection','/api/faces/label','/api/faces/labels',
          '/api/faces/reject','/api/faces/frigate','/api/auto-accept','/api/dates',
          '/api/photos','/api/search','/api/group-suggestions','/api/photo','/api/thumbnail','/api/groups','/api/group',
          '/api/groups/save','/api/groups/delete','/api/extract','/api/export',
          '/api/suggestions','/api/diagnostics'}
_instance = None


class Telemetry:
    def __init__(self):
        self.lock=threading.RLock()
        self.active={}
        self.events=deque(maxlen=200)
        self.stop=threading.Event()
        self.thread=None
        self.providers=[]
        self.tracer=None
        self.instruments={}
        self.pools={}
        self.logger=logging.getLogger('photo.app')
        self.logger.setLevel(logging.INFO)
        self.logger.propagate=False
        if not self.logger.handlers:self.logger.addHandler(logging.StreamHandler())

    def start(self):
        endpoint=os.environ.get('OTEL_EXPORTER_OTLP_ENDPOINT','').rstrip('/')
        if endpoint:
            from opentelemetry import trace,metrics
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            from opentelemetry.sdk.metrics import MeterProvider,Histogram
            from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
            from opentelemetry.sdk.metrics.view import View,ExplicitBucketHistogramAggregation
            from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
            from opentelemetry.sdk._logs import LoggerProvider
            from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
            from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
            from opentelemetry.instrumentation.logging.handler import LoggingHandler
            resource=Resource.create({'service.name':os.environ.get('OTEL_SERVICE_NAME','photo-review'),
                'service.version':os.environ.get('PHOTO_SERVICE_VERSION','development')})
            tp=TracerProvider(resource=resource)
            tp.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint+'/v1/traces',timeout=3),
                max_queue_size=2048,max_export_batch_size=128,schedule_delay_millis=1000))
            self.tracer=tp.get_tracer('photo.app');self.providers.append(tp)
            reader=PeriodicExportingMetricReader(OTLPMetricExporter(endpoint=endpoint+'/v1/metrics',timeout=3),export_interval_millis=5000)
            mp=MeterProvider(resource=resource,metric_readers=[reader],views=[View(instrument_type=Histogram,
                aggregation=ExplicitBucketHistogramAggregation([.01,.05,.1,.25,.5,1,3,5,10,30]))])
            self.providers.append(mp)
            meter=mp.get_meter('photo.app')
            self.instruments['requests']=meter.create_counter('photo_app_http_requests')
            for name in ('http_duration','lock_wait','db_duration','pool_wait'):
                self.instruments[name]=meter.create_histogram('photo_app_'+name,unit='s')
            for name in ('inflight','lock_waiters','oldest_request'):
                meter.create_observable_gauge('photo_app_'+name,unit='s' if name=='oldest_request' else '',
                    callbacks=[lambda options,key=name:[metrics.Observation(self.summary()[key])]])
            for metric,stat in [('connections','pool_size'),('idle','pool_available'),('limit','pool_max'),('waiting','requests_waiting'),('errors','requests_errors')]:
                meter.create_observable_gauge('photo_app_pg_pool_'+metric,
                    callbacks=[lambda options,key=stat:[metrics.Observation(pool.get_stats().get(key,0),{'pool':role}) for role,pool in self.pools.items()]])
            lp=LoggerProvider(resource=resource)
            lp.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter(endpoint=endpoint+'/v1/logs',timeout=3),
                max_queue_size=1024,max_export_batch_size=128,schedule_delay_millis=1000))
            self.logger.addHandler(LoggingHandler(level=logging.INFO,logger_provider=lp));self.providers.append(lp)
        self.thread=threading.Thread(target=self._watch,daemon=True,name='photo-request-watchdog')
        self.thread.start()

    def close(self):
        self.stop.set()
        if self.thread:self.thread.join(timeout=2)
        for provider in reversed(self.providers):provider.shutdown()

    def emit(self,event,**fields):
        record=dict(timestamp=time.time(),event=event,**fields)
        with self.lock:self.events.append(record)
        self.logger.info(json.dumps(record,default=str))

    def summary(self):
        with self.lock:
            now=time.monotonic()
            return dict(inflight=len(self.active),lock_waiters=sum(r['stage']=='lock.wait' for r in self.active.values()),
                oldest_request=max((now-r['started'] for r in self.active.values()),default=0))

    def diagnostics(self):
        with self.lock:
            return dict(**self.summary(),requests=[dict(route=r['route'],stage=r['stage'],trace_id=r['trace_id'],
                age_seconds=round(time.monotonic()-r['started'],3)) for r in self.active.values()],events=list(self.events)[-30:],
                pools={role:pool.get_stats() for role,pool in self.pools.items()})

    def _watch(self):
        while not self.stop.wait(5):
            self.report_slow()

    def report_slow(self):
        with self.lock:
            slow=[dict(r) for r in self.active.values() if time.monotonic()-r['started']>=10
                and time.monotonic()-r.get('reported',0)>=30]
            for r in slow:self.active[r['key']]['reported']=time.monotonic()
        for r in slow:
            self.emit('request.slow',route=r['route'],stage=r['stage'],trace_id=r['trace_id'],
                span_id=r['span_id'],duration_seconds=round(time.monotonic()-r['started'],3),
                category='application_lock' if r['stage']=='lock.wait' else 'slow_operation')

    @contextmanager
    def request(self,method,route,headers):
        route=route if route in ROUTES else '/unknown'
        attributes={'http.request.method':method,'http.route':route}
        context=nullcontext(None)
        if self.tracer:
            from opentelemetry import propagate,trace
            context=self.tracer.start_as_current_span(method+' '+route,context=propagate.extract({k.lower():v for k,v in headers.items()}),
                kind=trace.SpanKind.SERVER,attributes=attributes,record_exception=False,set_status_on_exception=False)
        with context as span:
            sc=span.get_span_context() if span else None
            key=uuid.uuid4().hex
            record=dict(key=key,route=route,stage='dispatch',started=time.monotonic(),status=500,
                stage_durations={},query_hash=None,
                trace_id=format(sc.trace_id,'032x') if sc else key,span_id=format(sc.span_id,'016x') if sc else key[:16])
            token=CURRENT.set(key)
            with self.lock:self.active[key]=record
            try:yield record
            finally:
                elapsed=time.monotonic()-record['started']
                with self.lock:self.active.pop(key,None)
                attrs=dict(route=route,method=method,status=str(record['status']))
                if self.instruments:
                    self.instruments['requests'].add(1,attrs);self.instruments['http_duration'].record(elapsed,attrs)
                if span:
                    span.set_attribute('http.response.status_code',record['status'])
                    if record['status']>=500:
                        from opentelemetry.trace import Status,StatusCode
                        span.set_status(Status(StatusCode.ERROR))
                timings=record['stage_durations']
                bottleneck=max(timings,key=timings.get) if timings else 'dispatch'
                evidence=dict(trace_id=record['trace_id'],span_id=record['span_id'],duration_seconds=round(elapsed,4),
                    bottleneck_stage=bottleneck,bottleneck_seconds=round(timings.get(bottleneck,elapsed),4),
                    query_hash=record['query_hash'],stage_seconds={k:round(v,4) for k,v in timings.items()})
                self.emit('request.finished',**attrs,**evidence)
                if elapsed>=1:self.emit('request.slow',**attrs,**evidence,category=bottleneck,completed=True)
                CURRENT.reset(token)

    @contextmanager
    def stage(self,name,**attributes):
        key=CURRENT.get();previous=None
        with self.lock:
            if key in self.active:previous=self.active[key]['stage'];self.active[key]['stage']=name
        span=self.tracer.start_as_current_span(name,attributes=attributes,record_exception=False,set_status_on_exception=False) if self.tracer else nullcontext(None)
        start=time.monotonic()
        try:
            with span as current_span:yield current_span
        finally:
            duration=time.monotonic()-start
            metric={'lock.wait':'lock_wait','db.query':'db_duration','duckdb.query':'db_duration','pg.pool.wait':'pool_wait'}.get(name)
            labels={'stage':name}
            if 'pool' in attributes:labels['pool']=attributes['pool']
            if metric in self.instruments:self.instruments[metric].record(duration,labels)
            with self.lock:
                if key in self.active:
                    record=self.active[key]
                    record['stage']=previous
                    record['stage_durations'][name]=record['stage_durations'].get(name,0)+duration
                    if attributes.get('photo.query_hash') and duration>=record.get('slowest_query_seconds',0):
                        record['query_hash']=attributes['photo.query_hash'];record['slowest_query_seconds']=duration


def get_telemetry():
    global _instance
    if _instance is None:_instance=Telemetry()
    return _instance


def query_attributes(statement):
    """Hash the static statement template; never capture SQL parameters or paths."""
    operation=statement.lstrip().split(None,1)[0].upper() if statement.strip() else 'UNKNOWN'
    return {'db.system.name':'postgresql','db.operation.name':operation,
            'photo.query_hash':hashlib.sha256(statement.encode()).hexdigest()[:16]}
