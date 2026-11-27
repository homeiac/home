#!/usr/bin/env python3
"""Ensure incomplete or mismatched comparisons cannot be published as valid trials."""
import json,subprocess,sys,tempfile,unittest
from pathlib import Path

class ReportTests(unittest.TestCase):
 def trial(self,root,name,hash_value='same'):
  trial=root/name;trial.mkdir()
  meta={k:hash_value for k in ['manifest_sha256','classifier_sha256','weights_sha256','clip_sha256']}
  meta.update(before={'cpu':0,'wall':0},after={'cpu':1,'wall':2,'rss':10})
  (trial/'metadata.json').write_text(json.dumps(meta))
  rows=[{'pass':rep,'index':i,'expected':'positive' if i<13 else 'negative','matched':i<9,'total':.1,'decode':.01,'detect':.03,'embed':.059,'classify':.001} for rep in [0,1] for i in range(26)]
  (trial/'rows.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
  return trial,rows
 def call(self,root):
  return subprocess.run([sys.executable,str(Path(__file__).with_name('report.py')),str(root),'--output',str(root/'output.json')],capture_output=True)
 def test_complete_then_missing_or_duplicate(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);trial,rows=self.trial(root,'a')
   self.assertEqual(self.call(root).returncode,0)
   for invalid in [rows[:-1],rows[:-1]+[rows[0]]]:
    (trial/'rows.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in invalid))
    self.assertNotEqual(self.call(root).returncode,0)
 def test_mismatched_hashes(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);self.trial(root,'a');self.trial(root,'b','different')
   self.assertNotEqual(self.call(root).returncode,0)

if __name__=='__main__':unittest.main()
