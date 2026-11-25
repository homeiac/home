"""Verify the restricted audio installer cannot restart the vision worker."""
import importlib.util,json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('install',HERE.parent/'caption-gitops/install.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class InstallerTest(unittest.TestCase):
 def bundle(self):
  c=json.loads((HERE/'config.json').read_text());c['enabled']=False
  return {'audio-worker.py':(HERE/'worker.py').read_text(),'audio-config.json':json.dumps(c),'knowledge-index-audio-story.service':(HERE/'knowledge-index-audio-story.service').read_text()}
 def test_rejects_unknown_endpoint_before_commands(self):
  b=self.bundle();c=json.loads(b['audio-config.json']);c['backends']['cpu']='https://outside.invalid';b['audio-config.json']=json.dumps(c)
  with patch.object(m,'command') as command:
   with self.assertRaises(ValueError):m.reconcile_audio(b)
  command.assert_not_called()
 def test_only_audio_unit_is_touched(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);files={name:root/name for name in m.AUDIO_FILES}
   with patch.object(m,'ROOT',root),patch.object(m,'AUDIO_STATE',root/'state'),patch.object(m,'AUDIO_FILES',files),patch.object(m,'command',return_value=SimpleNamespace(returncode=1)) as command,patch.object(m.Path,'mkdir'):
    # Real file writes need mkdir; the production state root exists from bootstrap.
    with patch.object(m.Path,'mkdir',side_effect=lambda *args,**kwargs:None):
     m.reconcile_audio(self.bundle())
   args=[call.args for call in command.call_args_list]
   self.assertTrue(any('knowledge-index-audio-story.service' in call for call in args))
   self.assertFalse(any('knowledge-index-enrich.service' in call for call in args))
 def test_policy_only_change_keeps_running_worker(self):
  import os,time
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);files={name:root/name for name in m.AUDIO_FILES};bundle=self.bundle()
   config=json.loads(bundle['audio-config.json']);config['enabled']=True;config['codex_translation']['enabled']=True
   bundle['audio-config.json']=json.dumps(config)
   for name,path in files.items():path.write_text(bundle[name])
   config['codex_translation']['enabled']=False;files['audio-config.json'].write_text(json.dumps(config))
   heartbeat=root/'metrics.prom';heartbeat.write_text('test');os.utime(heartbeat,(time.time()+100,time.time()+100))
   with patch.object(m,'ROOT',root),patch.object(m,'AUDIO_FILES',files),patch.object(m,'AUDIO_STATE',root/'state'),patch.object(m,'AUDIO_METRICS',heartbeat),patch.object(m,'command',return_value=SimpleNamespace(returncode=0)) as command:
    result=m.reconcile_audio(bundle)
   self.assertEqual(result['changed_files'],['audio-config.json'])
   self.assertFalse(any(call.args[:2]==('systemctl','stop') for call in command.call_args_list))

if __name__=='__main__':unittest.main()
