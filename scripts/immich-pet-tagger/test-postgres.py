#!/usr/bin/env python3
"""Test current queue code against isolated scratch tables, never production jobs."""
import base64
from pathlib import Path
import subprocess
from distributed import KUBE

here=Path(__file__).resolve().parent
module='data:text/javascript;base64,'+base64.b64encode((here/'queue-core.mjs').read_bytes()).decode()
test=(here/'test-queue.mjs').read_text().replace("'./queue-core.mjs'",repr(module))
subprocess.run(KUBE+['-n','immich-pilot','exec','-i','deployment/waffles-queue','--','node','--input-type=module','-','--postgres'],input=test,text=True,check=True)
