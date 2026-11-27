#!/usr/bin/env python3
"""Exercise preflight against isolated scratch tables, never production jobs."""
import base64
from pathlib import Path
import subprocess
from distributed import KUBE
here=Path(__file__).resolve().parent
module='data:text/javascript;base64,'+base64.b64encode((here/'preview-preflight-core.mjs').read_bytes()).decode()
test=(here/'test-preview-preflight.mjs').read_text().replace("'./preview-preflight-core.mjs'",repr(module))
subprocess.run(KUBE+['-n','immich-pilot','exec','-i','deployment/waffles-queue','--','node','--input-type=module','-','--postgres'],input=test,text=True,check=True,timeout=60)
