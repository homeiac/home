#!/usr/bin/env python3
"""Review missing/ambiguous local boxes and record explicit manual dog-face boxes."""
import argparse
from datetime import datetime,timezone
import importlib.util
import json
import os
from pathlib import Path
from PIL import Image,ImageDraw,ImageOps
spec=importlib.util.spec_from_file_location('recovery',Path(__file__).with_name('prepare-reviewed-recovery.py'));recovery=importlib.util.module_from_spec(spec);spec.loader.exec_module(recovery)

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);p.add_argument('--render');p.add_argument('--set',nargs='+',help='index,x0,y0,x1,y1 in normalized image coordinates');a=p.parse_args();os.umask(0o077)
 detections=json.loads((a.directory/'detections.json').read_text());decisions=json.loads((a.directory/'visual-decisions.json').read_text());file=a.directory/'manual-boxes.json';manual=json.loads(file.read_text()) if file.exists() else {}
 if a.set:
  for value in a.set:
   parts=value.split(',');index=str(int(parts[0]));box=list(map(float,parts[1:]));assert decisions[index]['decision']=='accept';assert index not in manual;recovery.choose_box([box])
   manual[index]={'box':box,'sha256':decisions[index]['image_sha256'],'source':'assistant visually placed dog-face box','at':datetime.now(timezone.utc).isoformat()}
  file.write_text(json.dumps(manual,indent=2)+'\n')
 pending=sorted(int(i) for i,d in detections.items() if decisions[i]['decision']=='accept' and recovery.choose_box(d['boxes']) is None and i not in manual)
 if a.render:
  folder=a.directory/'box-review'/a.render;folder.mkdir(parents=True,exist_ok=False);(folder/'indices.json').write_text(json.dumps(pending)+'\n')
  for page,start in enumerate(range(0,len(pending),9)):
   indices=pending[start:start+9];w,h=480,540;canvas=Image.new('RGB',(3*w,((len(indices)+2)//3)*h),'white');draw=ImageDraw.Draw(canvas)
   for cell,index in enumerate(indices):
    row=decisions[str(index)];im=ImageOps.contain(Image.open(a.directory/'targets'/(row['asset_id']+'.jpg')).convert('RGB'),(w-12,h-40));x=(cell%3)*w;y=(cell//3)*h;canvas.paste(im,(x+(w-im.width)//2,y+36));draw.text((x+8,y+8),f'Review {index} | full image bounds below',fill='black')
   path=folder/f'{page:03}.jpg';canvas.save(path,quality=95);print(path)
 print(json.dumps({'manual_boxes':len(manual),'pending_boxes':len(pending),'pending_indices':pending}))

if __name__=='__main__':main()
