#!/usr/bin/env python3
"""Refuse to publish a contention result unless resume and health are verified."""
import json,subprocess,sys,tempfile,unittest
from pathlib import Path
class VerificationTests(unittest.TestCase):
 def test_incomplete_restore_or_watchdog_invalidates_result(self):
  for resumed,watchdog in [(0,False),(1,True)]:
   with tempfile.TemporaryDirectory() as directory:
    root=Path(directory);study=root/'contention-aba';study.mkdir()
    (study/'verified.json').write_text(json.dumps({'state':'complete','stopped':1,'resumed':resumed,'watchdog_fired':watchdog}))
    result=subprocess.run([sys.executable,str(Path(__file__).with_name('report-contention.py')),directory,'--output',str(root/'report.json')],capture_output=True)
    self.assertNotEqual(result.returncode,0);self.assertFalse((root/'report.json').exists())
 def test_unhealthy_resumed_server_invalidates_result(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);study=root/'contention-aba';study.mkdir()
   (study/'verified.json').write_text(json.dumps({'state':'complete','stopped':1,'resumed':1,'watchdog_fired':False}))
   (study/'resume-health.json').write_text(json.dumps([{'identity_preserved':True,'state':'running','health_http':503}]))
   result=subprocess.run([sys.executable,str(Path(__file__).with_name('report-contention.py')),directory,'--output',str(root/'report.json')],capture_output=True)
   self.assertNotEqual(result.returncode,0);self.assertFalse((root/'report.json').exists())
if __name__=='__main__':unittest.main()
