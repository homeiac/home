#!/usr/bin/env python3
"""Render indexed training references for selecting a blinded visual-comparison atlas."""
import argparse
from pathlib import Path
from PIL import Image,ImageOps,ImageDraw
p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);a=p.parse_args()
files=sorted((a.directory/'references').glob('*.jpg'));w,h=260,230;sheet=Image.new('RGB',(w*6,h*((len(files)+5)//6)),(245,245,245));draw=ImageDraw.Draw(sheet)
for index,file in enumerate(files):
    image=ImageOps.contain(Image.open(file).convert('RGB'),(w-8,h-28));x=(index%6)*w;y=(index//6)*h;sheet.paste(image,(x+(w-image.width)//2,y+25));draw.text((x+8,y+5),file.stem,fill=(0,0,0))
sheet.save(a.directory/'reference-contact-sheet.jpg',quality=92)
