#!/usr/bin/env python3
"""Wait for Flux to apply this checkout before checking its worker rollout."""
import json
from pathlib import Path
import subprocess
import time
from distributed import KUBE

root=Path(__file__).resolve().parents[2]
revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
deadline=time.monotonic()+300
while True:
    value=json.loads(subprocess.check_output(KUBE+['-n','flux-system','get','kustomization','photo-enrichment-preview','-o','json'],text=True))['status']
    if value.get('lastAppliedRevision','').endswith(revision) and any(c['type']=='Ready' and c['status']=='True' for c in value.get('conditions',[])):break
    if time.monotonic()>deadline:raise RuntimeError('Flux has not applied the current revision')
    time.sleep(5)
print('Flux applied',revision)
subprocess.run(['bash',str(root/'scripts/immich-pet-tagger/check-distributed.sh')],check=True)
