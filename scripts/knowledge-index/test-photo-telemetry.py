#!/usr/bin/env python3
"""Exercise real OTLP exporters against a local collector stub, using no photos."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
import threading
import unittest
from unittest.mock import patch
from photo_enrichment.telemetry import Telemetry,query_attributes


class TelemetryTests(unittest.TestCase):
    def test_triage_distinguishes_cause_from_waiting_request_symptom(self):
        from photo_enrichment.triage import classify
        probes={'health':True,'api':False}
        diag={'lock_waiters':15,'oldest_request':180}
        waits=[dict(state='active',wait_type='none',age_seconds=180,blockers=0)]
        self.assertEqual(classify(probes,diag,waits,{}),'slow_postgres_query')
        waits[0].update(wait_type='Lock',blockers=1)
        self.assertEqual(classify(probes,diag,waits,{}),'postgres_blocked')
        self.assertEqual(classify(probes,diag,[],{}),'application_lock')
        diag['requests']=[dict(stage='duckdb.query',age_seconds=180)]
        self.assertEqual(classify(probes,diag,[],{}),'slow_duckdb_query')
        self.assertEqual(classify({'health':False},{},[],{}),'service_unreachable')
        self.assertEqual(classify({'health':True,'api':True},{},[],{}),'healthy')

    def test_otlp_signals_correlate_and_exclude_photo_data(self):
        from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
        from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceRequest
        received=[]
        class Collector(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                received.append((self.path,self.rfile.read(int(self.headers['Content-Length']))))
                self.send_response(200);self.end_headers()
        server=ThreadingHTTPServer(('127.0.0.1',0),Collector)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        telemetry=Telemetry()
        try:
            with patch.dict(os.environ,OTEL_EXPORTER_OTLP_ENDPOINT=f'http://127.0.0.1:{server.server_port}'):
                telemetry.start()
            trace='0123456789abcdef0123456789abcdef'
            with telemetry.request('GET','/api/photo',{'traceparent':f'00-{trace}-0123456789abcdef-01'}) as record:
                self.assertEqual(record['trace_id'],trace)
                with telemetry.stage('db.query',**query_attributes('SELECT id FROM faces WHERE id=?')):
                    self.assertEqual(telemetry.summary()['inflight'],1)
                record['status']=200
            for provider in telemetry.providers:provider.force_flush()
            self.assertTrue({'/v1/traces','/v1/metrics','/v1/logs'}.issubset({p for p,_ in received}))
            spans=[]
            for path,body in received:
                if path=='/v1/traces':
                    req=ExportTraceServiceRequest.FromString(body)
                    spans.extend(s for resource in req.resource_spans for scope in resource.scope_spans for s in scope.spans)
            self.assertEqual({s.name for s in spans},{'GET /api/photo','db.query'})
            self.assertTrue(all(s.trace_id.hex()==trace for s in spans))
            logs=[ExportLogsServiceRequest.FromString(body) for path,body in received if path=='/v1/logs']
            records=[r for batch in logs for resource in batch.resource_logs for scope in resource.scope_logs for r in scope.log_records]
            self.assertTrue(any(json.loads(r.body.string_value)['trace_id']==trace for r in records))
        finally:
            telemetry.close();server.shutdown();server.server_close();thread.join()

    def test_watchdog_reports_unfinished_lock_wait_without_waiting_for_span_end(self):
        telemetry=Telemetry()
        with telemetry.request('GET','/api/faces',{}) as record:
            record['stage']='lock.wait';record['started']-=11
            telemetry.report_slow();telemetry.report_slow()
            slow=[event for event in telemetry.events if event['event']=='request.slow']
            self.assertEqual(len(slow),1)
            self.assertEqual(slow[0]['category'],'application_lock')
            self.assertEqual(slow[0]['trace_id'],record['trace_id'])
            self.assertEqual(telemetry.summary()['lock_waiters'],1)
            record['status']=503
        self.assertEqual(telemetry.summary()['inflight'],0)


if __name__=='__main__':unittest.main()
