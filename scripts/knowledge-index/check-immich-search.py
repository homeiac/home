#!/usr/bin/env python3
"""Run read-only description/context search checks inside the existing sync pod."""
import os,subprocess
from pathlib import Path
os.environ.setdefault('KUBECONFIG',str(Path.home()/'kubeconfig'))
subprocess.run(['kubectl','-n','immich-pilot','exec','-i','deploy/immich-sync','--','node','--input-type=module'],input=Path(__file__).with_name('immich_sync').joinpath('check-search.mjs').read_bytes(),check=True)
