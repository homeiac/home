#!/usr/bin/env python3
"""Behavior tests using synthetic images, a real DuckDB fixture and a mock recognizer."""
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch, MagicMock
import urllib.error
import urllib.request

from PIL import Image, TiffImagePlugin

from photo_enrichment.demo import build_demo
from photo_enrichment.faces import MODEL_ID, similarity, frigate_candidate
from photo_enrichment.metrics import Metrics
from photo_enrichment.metadata import capture_time, contained, coordinates, exif_coordinates, read_metadata
from photo_enrichment.server import make_server
from photo_enrichment.store import Store


class MetadataTests(unittest.TestCase):
    def test_coordinate_validation(self):
        self.assertIsNone(coordinates(0, 0))
        self.assertIsNone(coordinates(float('nan'), 12))
        self.assertIsNone(coordinates(91, 12))
        self.assertEqual(coordinates(0, 12), (0, 12, None))

    def test_direction_is_not_location(self):
        self.assertIsNone(exif_coordinates({16: 'M', 17: 34.0}))
        self.assertEqual(exif_coordinates({1:'S',2:(33,30,0),3:'W',4:(18,15,0)}), (-33.5,-18.25,None))
        self.assertIsNone(exif_coordinates({1:'N',2:(33,99,0),3:'E',4:(18,15,0)}))

    def test_timezone_and_precedence(self):
        timestamp, source = capture_time({}, {36867:'2023:04:23 23:30:00',36881:'-04:00'}, 'UTC')
        self.assertEqual(timestamp, 1682307000)
        self.assertEqual(source, 'exif.offset')
        self.assertEqual(capture_time({'photoTakenTime':{'timestamp':'100'}},{36867:'2023:04:23 23:30:00'},'UTC'), (100,'takeout.photoTakenTime'))
        self.assertEqual(capture_time({}, {36867:'2023:04:23 23:30:00'}, 'America/New_York')[0], timestamp)

    def test_sidecar_and_embedded_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'photo.jpg';sidecar=Path(directory)/'photo.json'
            exif=Image.Exif();ratio=TiffImagePlugin.IFDRational
            exif[34853]={1:'N',2:(ratio(37),ratio(30),ratio(0)),3:'W',4:(ratio(122),ratio(15),ratio(0))}
            Image.new('RGB',(50,30)).save(path,exif=exif)
            sidecar.write_text(json.dumps({'geoData':{'latitude':0,'longitude':0}}))
            result=read_metadata(path,sidecar,'UTC')
            self.assertEqual((result['latitude'],result['longitude'],result['gps_source']),(37.5,-122.25,'embedded.exif'))
            sidecar.write_text(json.dumps({'geoData':{'latitude':0,'longitude':0},'geoDataExif':{'latitude':12,'longitude':13}}))
            result=read_metadata(path,sidecar,'UTC')
            self.assertEqual((result['latitude'],result['gps_source']),(12,'takeout.geoDataExif'))
            sidecar.write_text(json.dumps({'geoData':{'latitude':10,'longitude':11},'geoDataExif':{'latitude':12,'longitude':13}}))
            self.assertEqual(read_metadata(path,sidecar,'UTC')['gps_source'],'takeout.geoData')

    def test_containment(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'library';root.mkdir()
            (root/'escape').symlink_to(Path(directory))
            for path in ('../other','/etc/passwd','escape/other'):
                with self.assertRaises(ValueError):contained(root,path)


class IntegrationTests(unittest.TestCase):
    def test_frigate_negative_and_unknown_results_are_not_person_names(self):
        for payload, status in [({'success': False, 'message': 'No face was detected.'}, 400),
                                ({'success': False, 'message': 'No face was recognized.'}, 400),
                                ({'success': True, 'face_name': 'unknown', 'score': .2}, 200),
                                ({'success': True, 'face_name': 'Test Person', 'score': .9}, 200)]:
            with self.subTest(payload=payload), patch.dict('os.environ', {'PHOTO_FRIGATE_URL': 'https://frigate.example'}), \
                    patch('photo_enrichment.faces.urllib.request.build_opener') as factory:
                response = io.BytesIO(json.dumps(payload).encode())
                if status == 400:
                    factory.return_value.open.side_effect = urllib.error.HTTPError('https://frigate.example',400,'bad',{},response)
                else:
                    factory.return_value.open.return_value = response
                result = frigate_candidate(b'jpeg')
                self.assertEqual(result['name'], 'Test Person' if payload.get('face_name') == 'Test Person' else None)
                self.assertFalse(result['confirmed'])
                request = factory.return_value.open.call_args.args[0]
                self.assertIn(b'name="file"', request.data)
                self.assertEqual(request.full_url, 'https://frigate.example/api/faces/recognize')

    def test_frigate_operational_errors_and_redirects_remain_errors(self):
        for status in (302, 400, 401, 503):
            with self.subTest(status=status), patch.dict('os.environ', {'PHOTO_FRIGATE_URL': 'https://frigate.example'}), \
                    patch('photo_enrichment.faces.urllib.request.build_opener') as factory:
                payload = io.BytesIO(b'{"success":false,"message":"Face recognition is not enabled."}')
                factory.return_value.open.side_effect = urllib.error.HTTPError('https://frigate.example',status,'failed',{},payload)
                with self.assertRaises(urllib.error.HTTPError):
                    frigate_candidate(b'jpeg')
                handler = factory.call_args.args[0]
                self.assertIsNone(handler.redirect_request(None,None,None,None,None,None))

    def test_live_timing_and_failure_counted_once(self):
        metrics = Metrics()
        with patch('photo_enrichment.metrics.time.monotonic', side_effect=[10,12,15]):
            with self.assertRaises(ValueError):
                with metrics.measure('faces'):
                    self.assertIn('stage="faces",title="Photo: CPU faces"} 2.0', metrics.render())
                    raise ValueError('private path must not enter telemetry')
        self.assertEqual(metrics.seconds['faces'], 5)
        self.assertEqual(metrics.operations['faces','error'], 1)
        self.assertNotIn('private path', metrics.render())

    def test_metrics_atomic_terminal_state_and_output_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'test.prom'
            with Metrics(path) as metrics:
                with metrics.measure('export'):
                    pass
            self.assertIn('photo_enrichment_running 0', path.read_text())
            self.assertIn('photo_enrichment_worker_stage 8', path.read_text())
            self.assertFalse(path.with_suffix('.prom.tmp').exists())
            with self.assertLogs(level='WARNING'):
                with Metrics(Path(directory)/'missing'/'test.prom') as broken:
                    with broken.measure('persist'):
                        pass
            self.assertEqual(broken.operations['persist','ok'], 1)


class StoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary=tempfile.TemporaryDirectory();cls.root=Path(cls.temporary.name)
        cls.index,cls.library=build_demo(cls.root)
        cls.original=hashlib.sha256((cls.index/'knowledge.duckdb').read_bytes()).hexdigest()

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def setUp(self):
        self.state=Path(tempfile.mkdtemp(dir=self.root))
        self.store=Store(self.index,self.library,self.state)
        self.paths=[p['path'] for p in self.store.photos('2023-04-23','America/New_York')['photos']]

    def tearDown(self):
        self.store.close()
        self.assertEqual(hashlib.sha256((self.index/'knowledge.duckdb').read_bytes()).hexdigest(),self.original)

    def test_dates_and_pagination(self):
        self.assertEqual(len(self.paths),6)
        first=self.store.photos('2023-04-23','America/New_York',0,2)
        second=self.store.photos('2023-04-23','America/New_York',2,2)
        self.assertEqual(first['total'],6)
        self.assertFalse(set(p['path'] for p in first['photos']) & set(p['path'] for p in second['photos']))
        with self.assertRaises(ValueError):self.store.photos('bad-date','UTC')

    def test_annotation_save_update_delete(self):
        saved=self.store.save_group({'paths':self.paths[:2],'event':'Wedding','location':'Atlanta','timezone':'America/New_York'})
        self.assertEqual(saved['photos'],2)
        self.assertEqual(self.store.detail(self.paths[0])['groups'][0]['event'],'Wedding')
        self.assertFalse(self.store.detail(self.paths[2])['groups'])
        self.store.save_group({'id':saved['id'],'paths':self.paths[1:3],'event':'Reception','tags':['family']})
        self.assertFalse(self.store.detail(self.paths[0])['groups'])
        self.assertEqual(self.store.detail(self.paths[2])['groups'][0]['event'],'Reception')
        self.store.delete_group(saved['id']);self.assertFalse(self.store.groups())
        self.assertEqual(len(self.store.rows('SELECT * FROM annotation_history')),3)

    def test_bad_annotation_is_atomic(self):
        with self.assertRaises(ValueError):self.store.save_group({'paths':[self.paths[0],'missing.jpg'],'event':'test'})
        self.assertFalse(self.store.groups())
        with self.assertRaises(ValueError):self.store.save_group({'paths':[],'event':'test'})

    def test_extraction_resumes_and_exports(self):
        first=self.store.extract(self.paths[:2],'UTC')
        self.assertEqual(first['processed'],2);self.assertEqual(first['errors'],[])
        self.assertEqual(self.store.extract(self.paths[:2],'UTC')['skipped'],2)
        self.assertEqual(self.store.photo(self.paths[0])['camera_make'],'Demo camera')
        exported=self.store.export();self.assertEqual(len(exported['tables']),6)
        self.assertEqual(self.store.rows("SELECT count(*) AS n FROM read_parquet(?)",[str(self.state/'parquet/extracted.parquet')])[0]['n'],2)

    def test_metrics_backlogs_follow_durable_facts(self):
        self.store.metrics = Metrics(self.state/'photo.prom')
        self.store.refresh_metrics()
        self.assertEqual(self.store.metrics.queues, {'exif':8,'faces':8,'review':0})
        class NoFaces:
            def detect(self, path):
                return []
        self.store.extract(self.paths[:2], 'UTC', NoFaces())
        self.assertEqual(self.store.metrics.queues, {'exif':6,'faces':6,'review':0})
        self.assertEqual(self.store.metrics.inventory['exif'],2)
        self.store.save_group({'paths':self.paths[:1],'event':'Private event'})
        self.assertEqual(self.store.metrics.inventory['groups'],1)
        self.assertEqual(self.store.metrics.operations['review','ok'],1)
        self.store.export()
        self.assertEqual(self.store.metrics.operations['export','ok'],1)
        exposition=(self.state/'photo.prom').read_text()
        self.assertNotIn('Private event',exposition)
        self.assertNotIn(self.paths[0],exposition)

    def test_face_labels_require_confirmation_and_survive_rerun(self):
        class FakeEngine:
            def detect(self,path):
                return [dict(id=path.stem,box=[0.1,0.1,0.8,0.9],confidence=.95,embedding=[1.,0.],model=MODEL_ID)]
        self.store.extract(self.paths[:2],'UTC',FakeEngine())
        one=self.store.detail(self.paths[0])['faces'][0]['id'];two=self.store.detail(self.paths[1])['faces'][0]['id']
        self.assertIsNone(self.store.face(two)['person'])
        self.store.label_face(one,'Example Person')
        suggestions=self.store.suggestions(two)
        self.assertEqual(suggestions[0]['person'],'Example Person')
        self.assertFalse(suggestions[0]['confirmed']);self.assertIsNone(self.store.face(two)['person'])
        self.store.reject(two,one);self.assertFalse(self.store.suggestions(two))
        self.store.extract(self.paths[:2],'UTC',FakeEngine(),force=True)
        self.assertEqual(self.store.face(one)['person'],'Example Person')
        self.store.label_face(one,'');self.assertIsNone(self.store.face(one)['person'])

    def test_thumbnail_and_no_unknown_file(self):
        self.assertTrue(self.store.thumbnail(self.paths[0]).startswith(b'\xff\xd8'))
        with self.assertRaises(ValueError):self.store.thumbnail('../outside.jpg')

    def test_similarity_not_probability(self):
        self.assertEqual(similarity([1,0],[1,0]),1)
        self.assertEqual(similarity([1,0],[0,1]),0)
        self.assertEqual(similarity([1,0],[-1,0]),-1)

    def test_http_csrf_and_annotation(self):
        server=make_server(self.store,self.state/'models','127.0.0.1',0)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        url=f'http://127.0.0.1:{server.server_port}'
        try:
            with urllib.request.urlopen(url+'/api/config') as response:config=json.load(response)
            body=json.dumps({'paths':self.paths[:1],'event':'test'}).encode()
            request=urllib.request.Request(url+'/api/groups/save',body,{'Content-Type':'application/json'})
            with self.assertRaises(urllib.error.HTTPError) as caught:urllib.request.urlopen(request)
            self.assertEqual(caught.exception.code,403)
            request.add_header('X-Photo-Token',config['csrf'])
            request.add_header('Origin','https://untrusted.example')
            with self.assertRaises(urllib.error.HTTPError) as caught:urllib.request.urlopen(request)
            self.assertEqual(caught.exception.code,403)
            request.remove_header('Origin')
            with urllib.request.urlopen(request) as response:self.assertEqual(json.load(response)['photos'],1)
            with urllib.request.urlopen(url) as response:self.assertIn(b'Group dates',response.read())
        finally:
            server.shutdown();server.server_close();thread.join()


if __name__=='__main__':
    unittest.main(verbosity=2)
