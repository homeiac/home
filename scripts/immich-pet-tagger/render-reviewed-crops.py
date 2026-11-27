#!/usr/bin/env python3
"""Render exact manual tag rectangles for a final placement check, privately."""
import argparse
import hashlib
import json
from pathlib import Path
from PIL import Image,ImageDraw,ImageOps
p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);a=p.parse_args()
boxes=json.loads((a.directory/'manual-boxes.json').read_text());decisions=json.loads((a.directory/'visual-decisions.json').read_text());folder=a.directory/'manual-crop-check';folder.mkdir(exist_ok=True)
indices=sorted(map(int,boxes))
for page,start in enumerate(range(0,len(indices),16)):
 subset=indices[start:start+16];w,h=300,320;canvas=Image.new('RGB',(4*w,((len(subset)+3)//4)*h),'white');draw=ImageDraw.Draw(canvas)
 for cell,index in enumerate(subset):
  row=decisions[str(index)];path=a.directory/'targets'/(row['asset_id']+'.jpg');content=path.read_bytes();assert hashlib.sha256(content).hexdigest()==boxes[str(index)]['sha256'];image=Image.open(path).convert('RGB');b=boxes[str(index)]['box'];crop=image.crop((int(b[0]*image.width),int(b[1]*image.height),int(b[2]*image.width),int(b[3]*image.height)));crop=ImageOps.contain(crop,(w-12,h-40));x=(cell%4)*w;y=(cell//4)*h;canvas.paste(crop,(x+(w-crop.width)//2,y+36));draw.text((x+8,y+8),f'Review {index}',fill='black')
 out=folder/f'{page:03}.jpg';canvas.save(out,quality=95);print(out)
(folder/'manifest.json').write_text(json.dumps({'indices':indices,'manual_boxes_sha256':hashlib.sha256((a.directory/'manual-boxes.json').read_bytes()).hexdigest()},indent=2)+'\n')
