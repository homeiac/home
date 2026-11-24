"""Offline tests only: no credentials, network requests or real Codex invocation."""
import json,os,subprocess,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock,patch
import codex_translate as broker
import worker

class TranslationTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);worker.initialize(self.root)
  self.request={'id':'a'*64,'evidence':{'visual':'A forest','speech':[{'text':'hello'}],'language':'test'}}
 def tearDown(self):self.temp.cleanup()
 def test_broker_replay_uses_saved_result_and_disables_tools(self):
  def invoke(args,**kwargs):
   Path(args[args.index('--output-last-message')+1]).write_text(json.dumps({'spoken_context':'Someone says hello.','assessment':'useful'}))
   return SimpleNamespace(stdout=json.dumps({'type':'turn.completed','usage':{'input_tokens':100,'output_tokens':20}}))
  with patch.object(broker,'ROOT',self.root),patch.dict(os.environ,{'CODEX_BIN':'not-executed'}),patch.object(broker.subprocess,'run',side_effect=invoke) as run:
   first=broker.translate(self.request);second=broker.translate(self.request)
  self.assertEqual(first,second);self.assertEqual(run.call_count,1)
  command=run.call_args.args[0];self.assertNotIn('--image',command)
  self.assertIn('shell_tool',command);self.assertIn('plugins',command)
 def test_ambiguous_broker_submission_is_not_repeated(self):
  with patch.object(broker,'ROOT',self.root),patch.dict(os.environ,{'CODEX_BIN':'not-executed'}),patch.object(broker.subprocess,'run',side_effect=subprocess.TimeoutExpired('test',180)) as run:
   with self.assertRaises(subprocess.TimeoutExpired):broker.translate(self.request)
   with self.assertRaises(RuntimeError):broker.translate(self.request)
  self.assertEqual(run.call_count,1)
 def test_parent_retains_unknown_hold_and_does_not_repeat(self):
  row={'id':'one','story_version':'v3','visual_summary':'A forest','transcript':'[]','language':'test'}
  config={'codex_translation':{'enabled':True,'endpoint':'http://127.0.0.1:19479','estimated_limit_usd':10}}
  with patch.object(worker.urllib.request,'urlopen',side_effect=TimeoutError) as call:
   for _ in range(2):
    with self.assertRaises(worker.CodexUnknown):worker.codex_context(row,config,self.root)
  self.assertEqual(call.call_count,1)
  with worker.connect(self.root) as d:self.assertEqual(tuple(d.execute('SELECT state,cost FROM codex_requests').fetchone()),('unknown',25000))
 def test_disabled_parent_never_sends(self):
  with patch.object(worker.urllib.request,'urlopen') as call:
   with self.assertRaises(worker.CodexUnknown):worker.codex_context({}, {'codex_translation':{'enabled':False}},self.root)
  call.assert_not_called()
 def test_parent_budget_is_bounded(self):
  with worker.connect(self.root) as d:d.execute("INSERT INTO codex_requests VALUES('a','job','unknown',10000000,NULL)")
  self.assertFalse(worker.codex_budget_open({'codex_translation':{'estimated_limit_usd':10}},self.root))

if __name__=='__main__':unittest.main()
