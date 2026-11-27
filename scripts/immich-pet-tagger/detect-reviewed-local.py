#!/usr/bin/env python3
"""Use the installed Mac detector on exact reviewed bytes when pod exec is unavailable."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from PIL import Image
p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);a=p.parse_args();os.umask(0o077)
runtime=Path.home()/'Library/Application Support/immich-pet-tagger'
upstream=Path((runtime/'upstream-app.txt').read_text().strip());weights=runtime/'data/yolov8n.pt';assert weights.exists()
os.environ['YOLO_MODEL_NAME']=str(weights);os.environ['MODEL_WORKERS']='1';os.environ['YOLO_CONFIG_DIR']=str(a.directory/'yolo-config')
sys.path.insert(0,str(upstream))
import torch
torch.set_num_threads(2)
import device
device.pick_device=lambda:'cpu'  # This diagnostic process only; baseline workers untouched.
import detector
out=a.directory/'detections.json';saved=json.loads(out.read_text()) if out.exists() else {};decisions=json.loads((a.directory/'visual-decisions.json').read_text())
pending=[(i,r) for i,r in decisions.items() if r['decision']=='accept' and i not in saved]
print(json.dumps({'event':'local_box_detection_start','assets':len(pending),'device':'cpu','threads':2,'weights_sha256':hashlib.sha256(weights.read_bytes()).hexdigest()}),flush=True)
detector.start_workers();detector.wait_for_ready(timeout=60)
try:
 for index,row in pending:
  image_path=a.directory/'targets'/(row['asset_id']+'.jpg');assert hashlib.sha256(image_path.read_bytes()).hexdigest()==row['image_sha256']
  image=Image.open(image_path).convert('RGB')
  try:boxes=[[float(v) for v in d[1:]] for d in detector.detect_animals(image,conf=.25)]
  except Exception as e:print(json.dumps({'index':index,'error':type(e).__name__}),flush=True);continue
  saved[index]={'review_index':int(index),'sha256':row['image_sha256'],'size':list(image.size),'boxes':boxes,'backend':'mac_cpu','weights_sha256':hashlib.sha256(weights.read_bytes()).hexdigest()}
  temp=out.with_suffix('.tmp');temp.write_text(json.dumps(saved,indent=2)+'\n');temp.replace(out)
 print(json.dumps({'detected':len(saved),'missing_boxes':sum(not r['boxes'] for r in saved.values())}),flush=True)
finally:detector.stop_workers()
