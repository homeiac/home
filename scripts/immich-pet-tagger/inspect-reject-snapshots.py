#!/usr/bin/env python3
"""Verify diagnostic classifier and image dimensions against the actual historical run snapshot."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
from distributed import KUBE
p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);a=p.parse_args();os.umask(0o077)
code='''import {createRequire} from 'node:module';const {Client}=createRequire('/usr/src/app/server/package.json')('pg');const db=new Client();await db.connect();console.log(JSON.stringify((await db.query("SELECT config FROM waffles.runs WHERE id='historical-waffles'")).rows[0].config));await db.end();'''
r=subprocess.run(KUBE+['-n','immich-pilot','exec','-i','deployment/waffles-queue','--','node','--input-type=module','-'],input=code,text=True,capture_output=True,check=True)
config=json.loads(r.stdout);(a.directory/'historical-classifier.json').write_text(json.dumps(config)+'\n')
local=json.loads((a.directory.parent/'distributed/classifier.json').read_text())
rows=json.loads((a.directory/'nine-replay.json').read_text())
report={'classifier_matches_run_snapshot':config==local,'run_config_sha256':hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest(),
'images':[{'audit_index':r['audit_index'],'historical_size':r['stored']['size'],'replay_size':r['size'],'size_changed':r['stored']['size']!=r['size'],'historical_unknown':r['stored']['unknown'],'historical_low_confidence':r['stored']['low_confidence']} for r in rows]}
(a.directory/'snapshot-comparison.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
