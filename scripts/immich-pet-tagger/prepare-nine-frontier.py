#!/usr/bin/env python3
"""Freeze the original nine for prioritized, blinded qualified Sol review."""
import argparse
import json
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);a=p.parse_args()
nine={r['asset_id'] for r in json.loads((a.directory/'nine-misses.json').read_text())}
rows=[r for r in json.loads((a.directory/'rejects.json').read_text()) if r['asset_id'] in nine]
assert len(rows)==9
path=a.directory/'nine-cohort.json';encoded=json.dumps(rows,sort_keys=True,indent=2)+'\n'
if path.exists():assert path.read_text()==encoded
else:path.write_text(encoded)
print('Prepared nine-image priority cohort; no expected labels sent to model')
