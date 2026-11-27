#!/usr/bin/env python3
"""Summarize actual-thread stack samples without conflating caller waits with idle compute."""
import json,argparse
from pathlib import Path
from collections import Counter
p=argparse.ArgumentParser();p.add_argument('directory',type=Path);a=p.parse_args()
for trial in a.directory.iterdir():
 file=trial/'python-stacks.json'
 if not file.exists():continue
 threads={}
 for row in json.loads(file.read_text()):
  name=row['thread'];leaf=row['stack'][0];threads.setdefault(name,Counter())[leaf]+=row['samples']
 print(trial.name,json.dumps({name:{'samples':sum(c.values()),'top_leaf':c.most_common(5)} for name,c in threads.items()},indent=2))
