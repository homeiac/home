"""Video tuning must preserve photos, cache identities and ordered evidence."""
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch
import io
import threading
import time
from PIL import Image

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'enrichers'))
import media_summary as m
from pipeline_metrics import PipelineMetrics


class VideoTests(unittest.TestCase):
    def args(self,**extra):
        return SimpleNamespace(enricher='e',model='bonsai-27b',endpoint='http://test',api='ollama',
            num_ctx=8192,extra={'options':{'temperature':.2,'num_ctx':8192}},frames=4,
            video_edge=768,video_prompt='story',video_tokens=256,**extra)

    def test_video_prompt_records_version_and_preserves_api_options(self):
        row=dict(path='clip.mov',size_bytes=1,ext='mov',taken_ts=None,album=None,has_geo=False,people=[])
        with patch.object(m,'video_duration',return_value=20),patch.object(m,'jpeg_frame',return_value=b'jpeg') as frame, \
                patch.object(m,'video_preview',side_effect=lambda raw,edge: raw),patch.object(m,'transcript',return_value='hello'),patch.object(m,'ask_model',return_value='{"summary":"A child rolls a ball."}') as ask:
            result=m.summarize(row,'/fixture',self.args())
        self.assertEqual(result['status'],'ok')
        self.assertEqual(result['prompt_version'],'video-story-v1')
        self.assertEqual([c.args[1] for c in frame.call_args_list],[1.25,6.25,13.75,18.75])
        self.assertTrue(all(not c.kwargs for c in frame.call_args_list))
        self.assertEqual(ask.call_args.kwargs['extra']['options'],dict(temperature=.2,num_ctx=8192,num_predict=256))
        self.assertIn('Do not invent actions between frames',ask.call_args.args[2])
        self.assertIn('hello',ask.call_args.args[2])

    def test_photo_prompt_and_settings_do_not_change(self):
        row=dict(path='photo.jpg',size_bytes=1,ext='jpg',taken_ts=None,album=None,has_geo=False,people=[])
        args=self.args()
        with patch.object(m,'jpeg_frame',return_value=b'jpeg') as frame, \
                patch.object(m,'ask_model',return_value='{"summary":"A ball."}') as ask:
            result=m.summarize(row,'/fixture',args)
        self.assertEqual(result['prompt_version'],'p1')
        self.assertEqual(ask.call_args.args[2],m.build_prompt(row,False,1,''))
        self.assertEqual(ask.call_args.kwargs['extra'],args.extra)
        frame.assert_called_once_with('/fixture/photo.jpg')

    def test_source_minutes_count_only_after_successful_publication(self):
        metrics=PipelineMetrics(None,'e');seen=set()
        rows=[({'path':'a','ext':'mov'},{'status':'ok','duration_s':120,'inference_backend':'metal'}),
              ({'path':'b','ext':'mov'},{'status':'error','duration_s':300}),
              ({'path':'c','ext':'jpg'},{'status':'ok'})]
        with patch.object(m,'write_batch'):
            m.persist(rows,SimpleNamespace(index='unused',enricher='e'),metrics,seen)
        self.assertEqual(metrics.video_seconds['metal'],120)
        self.assertEqual(metrics.video_counts['metal'],1)
        self.assertEqual(metrics.video_counts['primary'],0)
        with patch.object(m,'write_batch',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):m.persist(rows,SimpleNamespace(index='unused',enricher='e'),metrics,seen)
        self.assertEqual(metrics.video_seconds['metal'],120)

    def test_no_division_on_subsecond_clip_and_bounded_metadata(self):
        self.assertEqual(m.video_positions(.2,1),[.1])
        prompt=m.story_prompt(dict(description='x'*10000),1,[.1,.9],speech='a'*10000)
        self.assertLess(len(prompt),5200)

    def test_short_clip_cap_keeps_uniform_legacy_positions(self):
        self.assertEqual(m.video_positions(4.2,4),[.525,1.5750000000000002,2.625,3.6750000000000003])

    def test_resized_preview_matches_trial_and_unchanged_preview_keeps_bytes(self):
        buf=io.BytesIO();Image.new('RGB',(1024,576),'red').save(buf,'JPEG')
        raw=buf.getvalue()
        self.assertIs(m.video_preview(raw,1024),raw)
        with Image.open(io.BytesIO(m.video_preview(raw,768))) as resized:
            self.assertEqual(resized.size,(768,432))

    def test_mac_video_cap_preserves_photo_capacity_and_unique_dispatch(self):
        lock=threading.Lock();active=dict(video=0,all=0);peak=dict(video=0,all=0)
        def task(row):
            video=row['ext']=='mov'
            with lock:
                active['all']+=1;active['video']+=video
                for k in peak:peak[k]=max(peak[k],active[k])
            time.sleep(.02)
            with lock:active['all']-=1;active['video']-=video
            return dict(status='ok')
        rows=[dict(path=str(i),ext='mov' if i%2==0 else 'jpg') for i in range(16)]
        results=list(m.split_batch(rows,0,4,task,task,mac_video_slots=1))
        self.assertEqual(peak['video'],1)
        self.assertEqual(peak['all'],4)
        self.assertEqual(len({r['path'] for r,_ in results}),16)

if __name__=='__main__':unittest.main()
