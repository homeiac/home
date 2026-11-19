#!/usr/bin/env python3
"""Guard the migration against silently replacing or inventing human labels."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('pilot',Path(__file__).with_name('immich-pilot.py'))
pilot=importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)


class MigrationTests(unittest.TestCase):
    def test_box_coordinates_use_detection_dimensions(self):
        face=dict(boundingBoxX1=160,boundingBoxY1=80,boundingBoxX2=320,
                  boundingBoxY2=160,imageWidth=640,imageHeight=320)
        self.assertEqual(pilot.normalized_face(face),[.25,.25,.5,.5])
        self.assertEqual(pilot.overlap([.25,.25,.5,.5],pilot.normalized_face(face)),1)
        self.assertEqual(pilot.overlap([0,0,.1,.1],pilot.normalized_face(face)),0)

    def run_annotation(self, source, ledger=None):
        record=dict(key='sample',filename='sample.jpg',sha256='digest',faces=source,
                    metadata={},groups=[],oriented_size=[1600,1200])
        ledger=ledger or dict(assets={'sample':'asset'},people={},faces={},albums={'pilot':'album'})
        calls=[]
        def request(path,method='GET',body=None,token=None):
            calls.append((path,method,body))
            if path=='/faces?id=asset':
                return [dict(id='detected',imageWidth=640,imageHeight=480,
                             boundingBoxX1=64,boundingBoxY1=48,boundingBoxX2=128,boundingBoxY2=96)]
            if path=='/people':
                return dict(id='person')
        with tempfile.TemporaryDirectory() as directory, patch.object(pilot,'ROOT',Path(directory)), \
             patch.object(pilot,'sample_and_ledger',return_value=([record],ledger)), \
             patch.object(pilot,'login',return_value='test'),patch.object(pilot,'request',side_effect=request):
            pilot.annotate()
        return ledger,calls

    def test_only_explicit_confirmations_transfer(self):
        source=[dict(id='old-user',label_source='user',person='Person',box=[.1,.1,.2,.2]),
                dict(id='old-auto',label_source='automatic',person='Other',box=[.1,.1,.2,.2])]
        ledger,calls=self.run_annotation(source)
        self.assertEqual(list(ledger['faces']),['old-user'])
        self.assertEqual([c for c in calls if c[0]=='/people'],[('/people','POST',{'name':'Person'})])

    def test_used_detection_cannot_be_reassigned_on_resume(self):
        ledger=dict(assets={'sample':'asset'},people={'Person':'person'},
                    faces={'previous':dict(face='detected',asset='asset',person='person')},albums={'pilot':'album'})
        source=[dict(id='another',label_source='user',person='Someone else',box=[.1,.1,.2,.2])]
        result,calls=self.run_annotation(source,ledger)
        self.assertNotIn('another',result['faces'])
        self.assertFalse(any(path=='/people' or path.startswith('/faces/') for path,_,_ in calls))

    def test_no_spatial_match_does_not_invent_assignment(self):
        result,calls=self.run_annotation([dict(id='old',label_source='user',person='Person',box=[.7,.7,.8,.8])])
        self.assertEqual(result['faces'],{})
        self.assertFalse(any(path=='/people' for path,_,_ in calls))

    def test_upload_preserves_binary_content(self):
        content=b'\xff\xd8\x00\x80\xfe\xff'
        body,kind=pilot.multipart({'fileCreatedAt':'2026-01-01T00:00:00Z'},'sample.jpg',content)
        self.assertIn(content,body)
        self.assertIn('multipart/form-data; boundary=',kind)


if __name__=='__main__':
    unittest.main()
