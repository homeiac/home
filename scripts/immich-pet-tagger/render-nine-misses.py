#!/usr/bin/env python3
"""Render the frozen nine misses next to their historical rejection paths for local review."""
import argparse
import json
from pathlib import Path
from PIL import Image,ImageDraw,ImageOps
p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);a=p.parse_args();rows=json.loads((a.directory/'nine-misses.json').read_text());root=a.directory.parent/'query-quality-20261127';w,h=480,540
sheet=Image.new('RGB',(3*w,3*h),'white');draw=ImageDraw.Draw(sheet)
for index,row in enumerate(rows):
    path=root/f"{row['index']:03}.media"
    if not path.exists():path=root/f"{row['index']:03}.jpg"
    image=ImageOps.contain(Image.open(path).convert('RGB'),(w-12,h-44));x=(index%3)*w;y=(index//3)*h
    sheet.paste(image,(x+(w-image.width)//2,y+40));draw.text((x+8,y+8),f"Audit {row['index']}: unknown={row['result']['unknown']}, low={row['result']['low_confidence']}",fill='black')
sheet.save(a.directory/'nine-misses-sheet.jpg',quality=93)
