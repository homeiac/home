"""Exercise restart, duplicate fencing, transcript uncertainty and text-only stories."""
import concurrent.futures,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import worker

class AudioTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);worker.initialize(self.root)
  self.config={'version':'v1','attempts':3}
  with worker.connect(self.root) as d:d.execute("INSERT INTO jobs(id,path,size_bytes,version,visual_summary,visual_hash,updated) VALUES('a','a.mp4',4,'v1','A group walks through a forest.','h',0)")
 def tearDown(self):self.temp.cleanup()
 def test_claim_is_atomic_across_backends(self):
  with concurrent.futures.ThreadPoolExecutor(3) as p:rows=list(p.map(lambda b:worker.claim('audio',b,self.config,self.root),['mac','cpu','rtx']))
  self.assertEqual(sum(r is not None for r in rows),1)
 def test_restart_recovers_claim_preserves_checkpoint(self):
  worker.claim('audio','mac',self.config,self.root)
  with worker.connect(self.root) as d:d.execute("INSERT INTO chunks VALUES('a',0,'{}')")
  worker.initialize(self.root)
  self.assertIsNotNone(worker.claim('audio','cpu',self.config,self.root))
  with worker.connect(self.root) as d:self.assertEqual(d.execute('SELECT count(*) FROM chunks').fetchone()[0],1)
 def test_bad_item_is_bounded(self):
  for i in range(3):
   row=worker.claim('audio','cpu',self.config,self.root)
   worker.fail(row,'audio','cpu',ValueError('private path'),0,self.config,self.root)
   with worker.connect(self.root) as d:d.execute('UPDATE jobs SET retry_at=0')
  self.assertIsNone(worker.claim('audio','cpu',self.config,self.root))
  with worker.connect(self.root) as d:self.assertEqual(d.execute('SELECT audio_state,error FROM jobs').fetchone()[:],('skipped','ValueError'))
 def test_no_audio_reuses_visual_without_model(self):
  with worker.connect(self.root) as d:d.execute("UPDATE jobs SET audio_state='no_audio'")
  row=worker.claim('story','mac',self.config,self.root)
  with patch.object(worker.urllib.request,'urlopen',side_effect=AssertionError('Unexpected model call')):worker.story_job(row,self.config,self.root)
  with worker.connect(self.root) as d:self.assertEqual(d.execute('SELECT story FROM jobs').fetchone()[0],row['visual_summary'])
 def test_segment_confidence_and_offsets(self):
  raw={'segments':[{'start':1,'end':2,'text':' hello '},{'start':2,'end':3,'text':'noise','no_speech_prob':.95},{'start':3,'end':4,'text':'unclear','avg_logprob':-2}]}
  self.assertEqual(worker.parse_transcript(raw,120),[{'start':121.0,'end':122.0,'text':'hello'}])
 def test_story_samples_whole_clip_and_marks_untrusted(self):
  segments=[dict(start=i,end=i+1,text=str(i)) for i in range(100)]
  prompt=worker.story_prompt('A walk',segments);self.assertIn('untrusted',prompt)
  evidence=json.loads(prompt.split('Evidence:\n')[1]);self.assertEqual(evidence['speech_samples'][-1]['text'],'99');self.assertEqual(len(evidence['speech_samples']),40)
 def test_source_path_is_fenced(self):
  with self.assertRaises(ValueError):worker.safe_source({'path':'../escape','size_bytes':4},self.root)
 def test_parquet_is_idempotent_and_separate(self):
  import duckdb
  worker.publish('a',self.root);worker.publish('a',self.root)
  self.assertEqual(len(list((self.root/'parquet').glob('*.parquet'))),1)
  with duckdb.connect() as d:self.assertEqual(d.execute('SELECT count(*) FROM read_parquet(?)',[str(self.root/'parquet/*.parquet')]).fetchone()[0],1)

 def test_repetitive_or_unknown_language_is_withheld(self):
  self.assertEqual(worker.parse_transcript({'detected_language_probability':.2,'segments':[{'text':'wrong','start':0,'end':1}]}),[])
  self.assertEqual(worker.parse_transcript({'segments':[{'text':'blah'*200,'start':0,'end':1}]}),[])
 def test_story_request_contains_text_only(self):
  from unittest.mock import MagicMock
  with worker.connect(self.root) as d:d.execute("UPDATE jobs SET audio_state='speech',language='english',transcript=?",[json.dumps([dict(start=0,end=1,text='Look at the monkey')])])
  row=worker.claim('story','mac',self.config,self.root)
  response=MagicMock();response.__enter__.return_value.read.return_value=json.dumps({'choices':[{'message':{'content':json.dumps({'spoken_context':'Someone mentions a monkey.'})}}]}).encode()
  with patch.object(worker.Path,'read_text',return_value='test-only'),patch.object(worker.urllib.request,'urlopen',return_value=response) as call:
   worker.story_job(row,dict(self.config,story_model='bonsai-27b-metal'),self.root)
  body=json.loads(call.call_args.args[0].data)
  self.assertIsInstance(body['messages'][0]['content'],str)
  self.assertNotIn('images',body)
 def test_discovery_maps_copies_and_preserves_completed_audio(self):
  import duckdb
  index=self.root/'index';index.mkdir()
  with duckdb.connect(str(index/'knowledge.duckdb')) as d:
   d.execute('CREATE TABLE gphotos_files(path VARCHAR,name VARCHAR,size_bytes BIGINT,kind VARCHAR,ext VARCHAR)')
   d.execute("INSERT INTO gphotos_files VALUES ('Google Photos/Photos from 2020/a.mp4','a.mp4',4,'media','mp4'),('Google Photos/Trip/a.mp4','a.mp4',4,'media','mp4')")
   d.execute('CREATE TABLE media_summaries(source VARCHAR,path VARCHAR,size_bytes BIGINT,summary VARCHAR,duration_s DOUBLE,created_at TIMESTAMP,status VARCHAR)')
   d.execute("INSERT INTO media_summaries VALUES ('gphotos','Google Photos/Trip/a.mp4',4,'A forest walk',10,now(),'ok')")
  worker.discover(self.config,self.root,index)
  with worker.connect(self.root) as d:
   row=d.execute('SELECT * FROM jobs WHERE active=1').fetchone();self.assertEqual(len(json.loads(row['aliases'])),2)
   d.execute("UPDATE jobs SET audio_state='speech',story_state='ok' WHERE active=1")
  worker.discover(self.config,self.root,index)
  with worker.connect(self.root) as d:self.assertEqual(d.execute("SELECT count(*) FROM jobs WHERE active=1 AND audio_state='speech'").fetchone()[0],1)

 def test_luna_caption_is_used_without_local_and_local_supersedes_it(self):
  import duckdb
  index=self.root/'knowledge-index';index.mkdir()
  luna=self.root/'photo-enrichment/luna-backfill/luna_codex_captions';luna.mkdir(parents=True)
  with duckdb.connect(str(index/'knowledge.duckdb')) as d:
   d.execute('CREATE TABLE gphotos_files(path VARCHAR,name VARCHAR,size_bytes BIGINT,kind VARCHAR,ext VARCHAR)')
   d.execute("INSERT INTO gphotos_files VALUES ('Google Photos/Photos from 2020/b.mp4','b.mp4',4,'media','mp4')")
   d.execute('CREATE TABLE media_summaries(source VARCHAR,path VARCHAR,size_bytes BIGINT,summary VARCHAR,duration_s DOUBLE,created_at TIMESTAMP,status VARCHAR)')
   d.execute("COPY (SELECT 'Google Photos/Photos from 2020/b.mp4' source_path,4 size_bytes,'A forest walk' summary,now() finished_at,'ok' state) TO ? (FORMAT PARQUET)",[str(luna/'a.parquet')])
  worker.discover(self.config,self.root,index)
  with worker.connect(self.root) as d:
   self.assertEqual(d.execute('SELECT visual_source FROM jobs WHERE active=1').fetchone()[0],'luna')
   d.execute("UPDATE jobs SET audio_state='speech',story_state='ok' WHERE active=1")
  with duckdb.connect(str(index/'knowledge.duckdb')) as d:
   d.execute("INSERT INTO media_summaries VALUES ('gphotos','Google Photos/Photos from 2020/b.mp4',4,'A clearer forest walk',10,now(),'ok')")
  worker.discover(self.config,self.root,index)
  with worker.connect(self.root) as d:
   r=d.execute('SELECT visual_source,audio_state,story_state FROM jobs WHERE active=1').fetchone()
   self.assertEqual(tuple(r),('local','speech','pending'))

 def test_metrics_are_readable_without_exposing_private_paths(self):
  import os,stat
  old=os.umask(0o077)
  try:worker.metrics(dict(self.config,backends={'mac':'http://127.0.0.1:19477'}),self.root,self.root/'metrics.prom')
  finally:os.umask(old)
  p=self.root/'metrics.prom';self.assertEqual(stat.S_IMODE(p.stat().st_mode),0o644)
  self.assertNotIn('a.mp4',p.read_text())
  self.assertIn('knowledge_index_audio_jobs{stage="audio",state="pending"} 1',p.read_text())

 def test_non_english_waits_for_authorized_translation_worker(self):
  with worker.connect(self.root) as d:d.execute("UPDATE jobs SET audio_state='speech',language='tamil'")
  self.assertIsNone(worker.claim('story','mac',self.config,self.root))
  self.assertIsNotNone(worker.claim('story','mac',dict(self.config,codex_ready=True),self.root))

 def test_mixed_script_uses_capable_translator(self):
  self.assertEqual(worker.needs_codex('english','hello café'),0)
  self.assertEqual(worker.needs_codex('english','hello வணக்கம்'),1)

 def test_visual_only_batch_bypasses_models_and_is_idempotent(self):
  with worker.connect(self.root) as d:
   d.execute("UPDATE jobs SET audio_state='no_speech'")
   for key,audio,story in [('b','speech','pending'),('c','no_audio','inflight'),('d','no_audio','pending'),('e','uncertain_speech','pending')]:
    d.execute('INSERT INTO jobs(id,path,size_bytes,version,visual_summary,audio_state,story_state,updated) VALUES(?,?,?,?,?,?,?,?)',[key,key+'.mp4',4,'v1','Visual '+key,audio,story,0])
  with patch.object(worker.urllib.request,'urlopen',side_effect=AssertionError('Unexpected model call')):
   with concurrent.futures.ThreadPoolExecutor(2) as pool:counts=list(pool.map(lambda _:worker.complete_visual_only(self.config,self.root,2),range(2)))
   self.assertEqual(sum(counts),3)
   self.assertEqual(worker.complete_visual_only(self.config,self.root),0)
  with worker.connect(self.root) as d:
   self.assertEqual(d.execute("SELECT count(*) FROM jobs WHERE story_state='ok' AND story=visual_summary").fetchone()[0],3)
   self.assertEqual(d.execute("SELECT count(*) FROM attempts WHERE backend='visual_only'").fetchone()[0],3)
   self.assertEqual(d.execute("SELECT story_state FROM jobs WHERE id='b'").fetchone()[0],'pending')
   self.assertEqual(d.execute("SELECT story_state FROM jobs WHERE id='c'").fetchone()[0],'inflight')
   self.assertEqual(d.execute('SELECT count(*) FROM codex_requests').fetchone()[0],0)

 def test_tied_raw_captions_do_not_requeue_completed_story(self):
  import datetime,duckdb
  index=self.root/'stable-index';index.mkdir();parquet=index/'summaries/local';parquet.mkdir(parents=True)
  canonical='Google Photos/Photos from 2020/tie.mp4';album='Google Photos/Trip/tie.mp4'
  with duckdb.connect(str(index/'knowledge.duckdb')) as d:
   d.execute('CREATE TABLE gphotos_files(path VARCHAR,name VARCHAR,size_bytes BIGINT,kind VARCHAR,ext VARCHAR)')
   d.executemany('INSERT INTO gphotos_files VALUES(?,?,?,?,?)',[(canonical,'tie.mp4',4,'media','mp4'),(album,'tie.mp4',4,'media','mp4')])
   # Deliberately incompatible view: discovery must use raw successes, whose ties
   # cannot be made deterministic after this view has discarded candidates.
   d.execute("CREATE VIEW media_summaries AS SELECT 'discarded by legacy view' AS summary")
  timestamp=datetime.datetime(2026,1,1)
  rows=[('gphotos',canonical,4,'Canonical A',10,timestamp,'ok'),('gphotos',canonical,4,'Canonical B',10,timestamp,'ok'),('gphotos',album,4,'ZZZ album',10,timestamp,'ok')]
  def write(records):
   with duckdb.connect() as d:
    d.execute('CREATE TABLE s(source VARCHAR,path VARCHAR,size_bytes BIGINT,summary VARCHAR,duration_s DOUBLE,created_at TIMESTAMP,status VARCHAR)')
    d.executemany('INSERT INTO s VALUES(?,?,?,?,?,?,?)',records)
    d.execute('COPY s TO ? (FORMAT PARQUET)',[str(parquet/'captions.parquet')])
  write(rows);worker.discover(self.config,self.root,index)
  with worker.connect(self.root) as d:
   r=d.execute('SELECT * FROM jobs WHERE active=1').fetchone();key=r['id'];self.assertEqual(r['visual_summary'],'Canonical B')
   d.execute("UPDATE jobs SET audio_state='speech',story_state='ok',story=visual_summary WHERE id=?",[key])
  for records in [list(reversed(rows)),rows]:
   write(records);worker.discover(self.config,self.root,index)
   with worker.connect(self.root) as d:
    r=d.execute('SELECT * FROM jobs WHERE id=?',[key]).fetchone();self.assertEqual((r['visual_summary'],r['audio_state'],r['story_state']),('Canonical B','speech','ok'))
  # Actual newer information still updates the story, preserving its audio.
  write(rows+[('gphotos',album,4,'Newer caption',10,timestamp+datetime.timedelta(seconds=1),'ok')]);worker.discover(self.config,self.root,index)
  with worker.connect(self.root) as d:
   r=d.execute('SELECT * FROM jobs WHERE id=?',[key]).fetchone();self.assertEqual((r['visual_summary'],r['audio_state'],r['story_state']),('Newer caption','speech','pending'))

if __name__=='__main__':unittest.main()
