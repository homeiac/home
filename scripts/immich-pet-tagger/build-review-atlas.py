#!/usr/bin/env python3
"""Build a fixed training-only multi-view Waffles reference atlas for blinded evaluation."""
import argparse
import hashlib
import json
from pathlib import Path
from PIL import Image,ImageDraw,ImageOps
p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);a=p.parse_args()
indices=[4,0,16,18,6,19];references=json.loads((a.directory/'reference-candidates.json').read_text());holdout=json.loads((a.directory.parent/'owner-confirmed-holdout.json').read_text())
assert not {references[i] for i in indices}&set(holdout['positive']+holdout['negative'])
w,h=400,440;sheet=Image.new('RGB',(w*3,h*2),'white');draw=ImageDraw.Draw(sheet)
for n,index in enumerate(indices):
    image=ImageOps.contain(Image.open(a.directory/'references'/f'{index:02}.jpg').convert('RGB'),(w-12,h-36));x=(n%3)*w;y=(n//3)*h
    sheet.paste(image,(x+(w-image.width)//2,y+32));draw.text((x+10,y+10),f'WAFFLES reference {n+1}',fill='black')
path=a.directory/'reference-atlas.jpg';sheet.save(path,quality=95)
(a.directory/'reference-atlas.json').write_text(json.dumps({'reference_indices':indices,'asset_ids':[references[i] for i in indices],'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'holdout_overlap':0},indent=2)+'\n')
print(json.dumps({'reference_count':len(indices),'holdout_overlap':0,'atlas_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}))
