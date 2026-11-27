#!/usr/bin/env python3
"""Render a private model batch with exact target order for alignment inspection."""
import argparse
import json
from pathlib import Path
from PIL import Image,ImageDraw,ImageOps
p=argparse.ArgumentParser(description=__doc__);p.add_argument('batch',type=Path);a=p.parse_args()
root=a.batch.parent.parent
rows=json.loads((a.batch/'submitted.json').read_text())['assets']
w,h=640,720
out=Image.new('RGB',(2*w,2*h),'white');draw=ImageDraw.Draw(out)
for i,asset in enumerate(rows):
 im=ImageOps.contain(Image.open(root/'targets'/(asset+'.jpg')).convert('RGB'),(w-12,h-44))
 x=(i%2)*w;y=(i//2)*h;out.paste(im,(x+(w-im.width)//2,y+40));draw.text((x+8,y+8),f'target_{i}',fill='black')
target=a.batch/'alignment.jpg';out.save(target,quality=94);print(target)
print((a.batch/'answer.json').read_text())
