#!/usr/bin/env python3
"""Exercise migration, fencing, retries, live review and coherent snapshots."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from photo_enrichment.demo import build_demo
from photo_enrichment.faces import MODEL_ID
from photo_enrichment.store import Store
from photo_enrichment.worker import batch
from photo_enrichment.postgres import connect, migrate, PostgresStore
from photo_enrichment.snapshots import export_snapshot, analytical_connection


class EmptyFaces:
    def detect(self,path): return []


class FakeFaces:
    def detect(self,path):
        return [dict(id='stable-face',box=[.1,.1,.5,.5],confidence=.95,embedding=[1.,0.],model=MODEL_ID)]


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.index,self.library=build_demo(self.root)
        self.state=self.root/'state'
        with connect() as c:
            # This test runner supplies only an ephemeral loopback database.
            self.assertEqual(c.info.host,'127.0.0.1')
            c.execute('DROP SCHEMA public CASCADE; CREATE SCHEMA public; DROP SCHEMA IF EXISTS catalog CASCADE')
        legacy=Store(self.index,self.library,self.state)
        batch(legacy,FakeFaces(),1,'UTC')
        self.path=legacy.face('stable-face')['path']
        legacy.label_face('stable-face','Synthetic person')
        legacy.save_group(dict(paths=[self.path],event='Synthetic event'))
        batch(legacy,EmptyFaces(),2,'UTC')
        class Broken:
            def detect(self,path): raise ValueError('synthetic failure')
        batch(legacy,Broken(),1,'UTC')
        legacy.close()
        with connect() as c: self.counts=migrate(c,self.index,self.state)
        self.store=PostgresStore(self.index,self.library,self.state)

    def tearDown(self):
        self.store.close();self.temp.cleanup()

    def test_migration_preserves_results_and_rerun_is_idempotent(self):
        self.assertEqual(self.counts['face_scans'],3)
        self.assertEqual(self.counts['worker_attempts'],1)
        self.assertEqual(self.store.face('stable-face')['person'],'Synthetic person')
        self.assertEqual(self.store.groups()[0]['event'],'Synthetic event')
        with connect() as c:self.assertEqual(migrate(c,self.index,self.state),self.counts)
        self.assertEqual(self.store.seed_jobs(),5)
        self.assertEqual(self.store.queue_metrics()['ready'],5)
        selected=[]
        while job:=self.store.claim_job():
            selected.append(job['path'])
            self.assertTrue(self.store.process_job(job,EmptyFaces()))
        self.assertEqual(len(selected),4)  # imported retry remains backed off
        self.assertNotIn(self.path,selected)
        self.assertEqual(self.store.rows('SELECT count(*) n FROM face_scans')[0]['n'],7)

    def test_claim_fencing_and_atomic_completion(self):
        self.store.seed_jobs()
        job=self.store.claim_job()
        other=PostgresStore(self.index,self.library,self.state)
        try:
            second=other.claim_job()
            self.assertNotEqual(job['path'],second['path'])
            self.store.db.execute("UPDATE photo_jobs SET lease_until=now()-interval '1 second' WHERE path=?",[job['path']])
            self.assertFalse(self.store.process_job(job,EmptyFaces()))
            self.assertFalse(self.store.rows('SELECT * FROM face_scans WHERE path=?',[job['path']]))
            # Explicitly make this expired job next; reclaim creates a new fencing token.
            self.store.db.execute("UPDATE photo_jobs SET attempts=-1 WHERE path=?",[job['path']])
            new=other.claim_job()
            self.assertEqual(new['path'],job['path']);self.assertNotEqual(new['claim'],job['claim'])
            self.assertTrue(other.process_job(new,EmptyFaces()))
            self.assertFalse(self.store.process_job(job,FakeFaces()))
            self.assertEqual(self.store.rows('SELECT status FROM photo_jobs WHERE path=?',[job['path']])[0]['status'],'done')
        finally:other.close()

    def test_live_gui_reads_and_snapshot_retains_old_generation(self):
        first=export_snapshot(self.state)
        reader,manifest=analytical_connection(self.state)
        try:
            self.store.label_face('stable-face','Changed synthetic name')
            self.assertEqual(self.store.face_library(status='named')['people'][0]['person'],'Changed synthetic name')
            self.assertEqual(reader.execute("SELECT person FROM faces WHERE id='stable-face'").fetchone()[0],'Synthetic person')
            second=export_snapshot(self.state)
            self.assertNotEqual(first['generation'],second['generation'])
            self.assertEqual(reader.execute("SELECT person FROM faces WHERE id='stable-face'").fetchone()[0],'Synthetic person')
            fresh,_=analytical_connection(self.state)
            self.assertEqual(fresh.execute("SELECT person FROM faces WHERE id='stable-face'").fetchone()[0],'Changed synthetic name')
            fresh.close()
            before=(self.state/'analytics/current.json').read_bytes()
            with patch('photo_enrichment.snapshots.atomic_json',side_effect=OSError('synthetic disk failure')):
                with self.assertRaises(OSError):export_snapshot(self.state)
            self.assertEqual((self.state/'analytics/current.json').read_bytes(),before)
        finally:reader.close()

    def test_bulk_labels_reject_stale_revision_atomically(self):
        face=self.store.face_library(status='named')['faces'][0]
        self.store.label_face(face['id'],'Newer edit',str(face['revision']))
        with self.assertRaises(ValueError):
            self.store.label_faces([{'id':face['id'],'revision':str(face['revision'])}],'Stale edit')
        self.assertEqual(self.store.face(face['id'])['person'],'Newer edit')

    def add_review_faces(self):
        """Synthetic, already processed faces for mixed-name confirmation tests."""
        reference=self.store.face('stable-face')
        for face_id in ('review-a','review-b'):
            self.store.db.execute('INSERT INTO faces VALUES (?,?,?,?,?,?,?,?,NULL,NULL,current_timestamp)',
                [face_id,reference['path'],reference['size_bytes'],reference['mtime_ns'],reference['box'],.9,[1.,0.],MODEL_ID])
        return [dict(id=face_id,revision=str(self.store.face(face_id)['updated_at']),person=name)
            for face_id,name in [('review-a','Synthetic G'),('review-b','Synthetic Asha')]]

    def test_mixed_confirmation_preserves_each_name_and_audits(self):
        faces=self.add_review_faces()
        before=len(self.store.rows('SELECT * FROM annotation_history'))
        self.store.label_faces(faces)
        for face in faces:
            saved=self.store.face(face['id'])
            self.assertEqual(saved['person'],face['person'])
            self.assertEqual(saved['label_source'],'user')
        self.assertEqual(len(self.store.rows('SELECT * FROM annotation_history')),before+2)
        self.assertEqual(self.store.face('stable-face')['person'],'Synthetic person')
        export_snapshot(self.state)
        reader,_=analytical_connection(self.state)
        try:
            self.assertEqual(reader.execute("SELECT id,person FROM faces WHERE id LIKE 'review-%' ORDER BY id").fetchall(),
                [('review-a','Synthetic G'),('review-b','Synthetic Asha')])
        finally:reader.close()

    def test_mixed_confirmation_rolls_back_entire_batch_on_stale_face(self):
        faces=self.add_review_faces()
        self.store.label_face('review-b','Newer correction')
        before=len(self.store.rows('SELECT * FROM annotation_history'))
        with self.assertRaisesRegex(ValueError,'edited elsewhere'):
            self.store.label_faces(faces)
        self.assertIsNone(self.store.face('review-a')['person'])
        self.assertEqual(self.store.face('review-b')['person'],'Newer correction')
        self.assertEqual(len(self.store.rows('SELECT * FROM annotation_history')),before)

    def test_mixed_confirmation_requires_names_and_unique_faces(self):
        faces=self.add_review_faces()
        for bad in (None,'', ' ', 123, 'x'*201):
            with self.subTest(name=bad),self.assertRaises(ValueError):
                self.store.label_faces([faces[0],dict(faces[1],person=bad)])
        with self.assertRaises(ValueError):self.store.label_faces([faces[0],faces[0]])
        self.assertIsNone(self.store.face('review-a')['person'])
        self.assertIsNone(self.store.face('review-b')['person'])

    def test_threshold_selection_covers_all_pages_without_writing(self):
        reference=self.store.face('stable-face')
        matches={}
        for i in range(125):
            face_id=f'threshold-{i:03}'
            self.store.db.execute('INSERT INTO faces VALUES (?,?,?,?,?,?,?,?,NULL,NULL,current_timestamp)',
                [face_id,reference['path'],reference['size_bytes'],reference['mtime_ns'],reference['box'],.9,[1.,0.],MODEL_ID])
            matches[face_id]=dict(person='Synthetic G' if i<100 else 'Synthetic Asha',score=.9 if i<124 else .899)
        # A cached suggestion for a face already confirmed elsewhere is excluded.
        matches['stable-face']=dict(person='Stale suggestion',score=.99)
        before=self.store.rows('SELECT count(*) n FROM annotation_history')[0]['n']
        with patch.object(self.store,'matching_pass',return_value=matches):
            selected=self.store.suggested_selection(.9)
            self.assertEqual(selected['total'],124)
            self.assertEqual(len({f['id'] for f in selected['faces']}),124)
            self.assertTrue(all(f['revision'] for f in selected['faces']))
            self.assertEqual(self.store.suggested_selection(.9,'Synthetic Asha')['total'],24)
            self.assertEqual(self.store.suggested_selection(.91)['total'],0)
            for invalid in (-.1,1.1,float('nan'),float('inf')):
                with self.assertRaises(ValueError):self.store.suggested_selection(invalid)
        self.assertEqual(self.store.rows('SELECT count(*) n FROM annotation_history')[0]['n'],before)
        self.assertEqual(self.store.rows('SELECT count(*) n FROM faces WHERE person IS NULL')[0]['n'],125)

    def test_automatic_acceptance_is_opt_in_and_preserves_review_work(self):
        self.add_review_faces()
        self.assertFalse(self.store.auto_accept_settings()['enabled'])
        self.assertEqual(self.store.auto_accept_pass()['saved'],0)
        self.store.label_face('review-b','Explicit correction')
        self.store.db.execute("UPDATE faces SET embedding=ARRAY[0.,1.]::double precision[] WHERE id='review-b'")
        self.store.configure_auto_accept(True,.9)
        self.assertEqual(self.store.auto_accept_pass()['saved'],1)
        self.assertEqual(self.store.face('review-a')['person'],'Synthetic person')
        self.assertEqual(self.store.face('review-a')['label_source'],'automatic')
        self.assertEqual(self.store.face('review-b')['person'],'Explicit correction')
        self.assertEqual(self.store.face('stable-face')['label_source'],'user')
        # Opt-in configuration and machine provenance survive another process.
        other=PostgresStore(self.index,self.library,self.state)
        try:
            self.assertTrue(other.auto_accept_settings()['enabled'])
            self.assertEqual(other.auto_accept_settings()['accepted'],1)
        finally:other.close()
        self.assertEqual(self.store.auto_accept_pass()['saved'],0)
        self.assertEqual(self.store.rows("SELECT count(*) n FROM annotation_history WHERE action='auto_accept_face'")[0]['n'],1)
        export_snapshot(self.state)
        reader,_=analytical_connection(self.state)
        try:
            self.assertEqual(reader.execute("SELECT person,label_source FROM faces WHERE id='review-a'").fetchone(),('Synthetic person','automatic'))
        finally:reader.close()
        # Clearing an automatic label is a durable instruction to leave it for review.
        self.store.label_face('review-a','')
        self.assertEqual(self.store.face('review-a')['label_source'],'user_cleared')
        self.assertEqual(self.store.auto_accept_pass()['saved'],0)
        self.assertIsNone(self.store.face('review-a')['person'])
        self.store.configure_auto_accept(False,.9)
        self.assertEqual(self.store.auto_accept_pass()['saved'],0)

    def test_automatic_names_never_train_matching_without_human_confirmation(self):
        self.add_review_faces()
        self.store.configure_auto_accept(True,.9)
        self.assertEqual(self.store.auto_accept_pass()['saved'],2)
        self.store.label_face('stable-face','')  # no human reference remains
        self.assertEqual(self.store.suggestions('stable-face'),[])
        self.assertEqual(self.store.matching_pass(),{})
        self.store.label_face('review-a','Human-confirmed example')
        self.assertEqual(self.store.matching_pass()['stable-face']['person'],'Human-confirmed example')

    def test_auto_accept_respects_threshold_rejections_and_pause(self):
        self.add_review_faces()
        self.store.db.execute("UPDATE faces SET embedding=ARRAY[.8,.6]::double precision[] WHERE id='review-a'")
        self.store.reject('review-b','stable-face')
        self.store.configure_auto_accept(True,.9)
        self.assertEqual(self.store.auto_accept_pass()['saved'],0)
        self.store.configure_auto_accept(True,.75)
        self.assertEqual(self.store.auto_accept_pass()['saved'],1)
        self.assertIsNone(self.store.face('review-b')['person'])
        self.store.configure_auto_accept(False,.75)
        self.assertEqual(self.store.auto_accept_pass()['saved'],0)
        for enabled,threshold in [('yes',.9),(True,.54),(True,float('nan')),(True,True)]:
            with self.assertRaises(ValueError):self.store.configure_auto_accept(enabled,threshold)

    def test_clipped_face_coordinates_commit(self):
        """OpenCV boxes at image edges can mix integer clamps with float values."""
        class ClippedFaces:
            def detect(self,path):
                return [dict(id='clipped-face',box=[0,.1,1,.9],confidence=.9,embedding=[1.,0.],model=MODEL_ID)]
        self.store.seed_jobs()
        job=self.store.claim_job()
        self.assertTrue(self.store.process_job(job,ClippedFaces()))
        self.assertEqual(self.store.face('clipped-face')['box'],[0.,.1,1.,.9])

    def test_gui_api_saves_labels_and_group_context(self):
        import json
        import threading
        import urllib.request
        from photo_enrichment.server import make_server
        server=make_server(self.store,self.state/'models','127.0.0.1',0)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base=f'http://127.0.0.1:{server.server_port}'
        try:
            server.lock_timeout=.05
            self.store.query_lock_timeout=.05
            with self.store.lock:
                for route in ('/','/app.js','/healthz','/api/config'):
                    with urllib.request.urlopen(base+route,timeout=1) as response:
                        self.assertEqual(response.status,200)
                with self.assertRaises(urllib.error.HTTPError) as busy:
                    urllib.request.urlopen(base+'/api/status',timeout=1)
                self.assertEqual(busy.exception.code,503)
            with urllib.request.urlopen(base+'/api/config') as response:csrf=json.load(response)['csrf']
            def post(path,body):
                request=urllib.request.Request(base+path,data=json.dumps(body).encode(),headers={
                    'Content-Type':'application/json','Origin':base,'X-Photo-Token':csrf})
                with urllib.request.urlopen(request) as response:return json.load(response)
            with urllib.request.urlopen(base+'/api/auto-accept') as response:
                self.assertFalse(json.load(response)['enabled'])
            self.assertFalse(post('/api/auto-accept',{'enabled':False,'threshold':.9})['enabled'])
            with urllib.request.urlopen(base+'/api/faces?status=named') as response:face=json.load(response)['faces'][0]
            post('/api/faces/labels',{'faces':[{'id':face['id'],'revision':face['revision']}],'person':'Synthetic API label'})
            self.assertEqual(self.store.face(face['id'])['person'],'Synthetic API label')
            mixed=self.add_review_faces()
            with urllib.request.urlopen(base+'/api/faces/selection?threshold=.9') as response:
                selected=json.load(response)
            self.assertEqual({f['id'] for f in selected['faces']},{'review-a','review-b'})
            post('/api/faces/labels',{'faces':mixed})
            for selected in mixed:
                self.assertEqual(self.store.face(selected['id'])['person'],selected['person'])
            group=post('/api/groups/save',{'paths':[self.path],'event':'Synthetic API event','location':'Synthetic location'})
            self.assertEqual(self.store.group(group['id'])['location'],'Synthetic location')
            post('/api/groups/save',{'id':group['id'],'paths':[self.path],'notes':'Synthetic correction'})
            self.assertEqual(self.store.group(group['id'])['notes'],'Synthetic correction')
            post('/api/groups/delete',{'id':group['id']})
            self.assertEqual(len(self.store.groups()),1)
        finally:
            server.shutdown();server.server_close();thread.join()

    def test_matching_backfills_without_reextracting_or_relabeling(self):
        reference=self.store.face('stable-face')
        for face_id,vector in [('candidate-a',[.99,.05]),('candidate-b',[.97,.1]),('unrelated',[0.,1.])]:
            self.store.db.execute('INSERT INTO faces VALUES (?,?,?,?,?,?,?,?,NULL,NULL,current_timestamp)',
                [face_id,reference['path'],reference['size_bytes'],reference['mtime_ns'],reference['box'],.9,vector,MODEL_ID])
        history=self.store.rows('SELECT count(*) n FROM annotation_history')[0]['n']
        with patch('photo_enrichment.postgres.read_metadata',side_effect=AssertionError('Must reuse embeddings')):
            suggested=self.store.face_library(status='suggested',person='Synthetic person')
        self.assertEqual({r['id'] for r in suggested['faces']},{'candidate-a','candidate-b'})
        self.assertTrue(all(r['person'] is None for r in suggested['faces']))
        self.assertEqual(self.store.rows('SELECT count(*) n FROM annotation_history')[0]['n'],history)
        self.store.reject('candidate-a','stable-face')
        self.assertEqual([r['id'] for r in self.store.face_library(status='suggested')['faces']],['candidate-b'])
        candidate=self.store.face_library(status='suggested')['faces'][0]
        self.store.label_faces([{'id':candidate['id'],'revision':str(candidate['revision'])}],'Synthetic person')
        self.assertEqual(self.store.face('candidate-b')['person'],'Synthetic person')
        self.assertEqual(self.store.face_library(status='suggested')['total'],0)
        self.assertEqual(self.store.face('stable-face')['person'],'Synthetic person')
        self.assertEqual(self.store.rows('SELECT count(*) n FROM face_scans')[0]['n'],3)

    def test_matching_excludes_ambiguous_and_incompatible_vectors(self):
        from photo_enrichment.matching import match_batch
        references=[dict(id='a1',person='A',model='v1',embedding=[1.,0.]),
                    dict(id='a2',person='A',model='v1',embedding=[.99,.01]),
                    dict(id='b',person='B',model='v1',embedding=[0.,1.])]
        candidates=[dict(id='clear',model='v1',embedding=[.98,.02]),
                    dict(id='tie',model='v1',embedding=[1.,1.]),
                    dict(id='wrong-model',model='v2',embedding=[1.,0.]),
                    dict(id='zero',model='v1',embedding=[0.,0.]),
                    dict(id='invalid',model='v1',embedding=[float('nan'),0.]),
                    dict(id='wrong-size',model='v1',embedding=[1.,0.,0.])]
        self.assertEqual(set(match_batch(candidates,references,set())),{'clear'})
        self.assertEqual(match_batch(candidates,references,{('clear','a1')}),{})

    def test_snapshot_remains_consistent_during_concurrent_edit(self):
        import duckdb
        real_connect=duckdb.connect
        writer=PostgresStore(self.index,self.library,self.state)
        class ConcurrentConnection:
            def __init__(self):self.inner=real_connect();self.changed=False
            def __enter__(self):return self
            def __exit__(self,*args):self.inner.close()
            def execute(self,statement,*args):
                result=self.inner.execute(statement,*args)
                if statement.startswith('COPY ') and 'source.public.extracted' in statement and not self.changed:
                    writer.label_face('stable-face','Concurrent edit')
                    self.changed=True
                return result
        try:
            with patch('photo_enrichment.snapshots.duckdb.connect',side_effect=ConcurrentConnection):
                export_snapshot(self.state)
            reader,_=analytical_connection(self.state)
            try:self.assertEqual(reader.execute("SELECT person FROM faces WHERE id='stable-face'").fetchone()[0],'Synthetic person')
            finally:reader.close()
            self.assertEqual(writer.face('stable-face')['person'],'Concurrent edit')
        finally:writer.close()

    def test_gallery_and_status_do_not_wait_for_background_matching_or_thumbnail_decode(self):
        import threading
        import urllib.parse
        import urllib.request
        from concurrent.futures import ThreadPoolExecutor
        from photo_enrichment.server import make_server
        from photo_enrichment.store import oriented_image
        self.add_review_faces()
        export_snapshot(self.state)
        background=PostgresStore(self.index,self.library,self.state)
        self.store.suggestion_source=background
        server=make_server(self.store,self.state/'models','127.0.0.1',0)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base=f'http://127.0.0.1:{server.server_port}'
        entered=threading.Event();release=threading.Event()
        def slow_decode(path):
            entered.set()
            if not release.wait(5):raise RuntimeError('Test decode release timed out')
            return oriented_image(path)
        try:
            with background.lock,patch.object(background,'matching_pass',side_effect=AssertionError('HTTP must not run matching')):
                with urllib.request.urlopen(base+'/api/faces',timeout=2) as response:
                    import json
                    self.assertTrue(json.load(response)['suggestions_refreshing'])
                background._matching_cache={'matches':{'review-a':{'person':'Synthetic person','reference_id':'stable-face','score':.95}}}
                self.assertIn('review-a',self.store.matching_pass())
            with patch('photo_enrichment.store.oriented_image',side_effect=slow_decode),ThreadPoolExecutor(1) as pool:
                thumbnail=pool.submit(urllib.request.urlopen,base+'/api/thumbnail?'+urllib.parse.urlencode({'path':self.path,'face':'stable-face'}))
                try:
                    self.assertTrue(entered.wait(2))
                    with urllib.request.urlopen(base+'/api/status',timeout=1) as response:self.assertEqual(response.status,200)
                    with urllib.request.urlopen(base+'/api/faces',timeout=2) as response:self.assertEqual(response.status,200)
                finally:release.set()
                thumbnail.result(timeout=2).close()
        finally:
            release.set();server.shutdown();server.server_close();thread.join();background.close()

    def test_gallery_uses_duckdb_and_overlays_live_confirmations(self):
        self.add_review_faces()
        snapshot=export_snapshot(self.state)
        self.store.label_face('review-a','Immediate correction')
        execute=self.store.db.execute
        def bounded_postgres(statement,params=()):
            self.assertNotIn('enriched_media',statement,'Gallery browsing must not query the PostgreSQL enrichment view')
            return execute(statement,params)
        with patch.object(self.store.db,'execute',side_effect=bounded_postgres):
            page=self.store.face_library(status='unreviewed')
            self.assertEqual(page['query_backend'],'duckdb')
            self.assertEqual(page['captured_at'],snapshot['captured_at'])
            self.assertEqual([f['id'] for f in page['faces']],['review-b'])
            named=self.store.face_library(person='Immediate correction',status='named')
            self.assertEqual(named['faces'][0]['id'],'review-a')
            self.assertEqual(named['faces'][0]['label_source'],'user')
            dates=self.store.dates('UTC')
            self.assertTrue(dates)
            self.assertEqual(self.store.photos(dates[0]['date'],'UTC')['query_backend'],'duckdb')
        # A stale snapshot must not make the updated revision unusable for review.
        face=named['faces'][0]
        self.store.label_faces([dict(id=face['id'],revision=str(face['revision']))],'Second correction')
        self.assertEqual(self.store.face('review-a')['person'],'Second correction')


if __name__=='__main__': unittest.main()
