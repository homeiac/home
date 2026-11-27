#!/usr/bin/env python3
"""Make private contact sheets of frozen audit images with predicted boxes.

For visual inspection only; never changes source photos or inference inputs.
"""
import argparse
import json
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont

p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);args=p.parse_args()
items=json.loads((args.directory/'sample.json').read_text())
font=ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc',16)
rendered=[row for row in items if (args.directory/f"{row['index']:03d}.media").exists()]
for start in range(0,len(rendered),12):
    sheet=Image.new('RGB',(1600,1320),'#202020');draw=ImageDraw.Draw(sheet)
    for offset,row in enumerate(rendered[start:start+12]):
        path=args.directory/f"{row['index']:03d}.media"
        if not path.exists():continue
        image=Image.open(path).convert('RGB');image.thumbnail((390,385))
        x=(offset%4)*400+(400-image.width)//2;y=(offset//4)*440+45
        sheet.paste(image,(x,y))
        matches=row['result']['matches']
        text=f"{row['index']:02d} {row['group'].replace('random_match_','')}"
        if matches:text+=' '+str(round(max(m['probability'] for m in matches),3))
        draw.text(((offset%4)*400+5,(offset//4)*440+5),text,font=font,fill='white')
        for m in matches:
            a,b,c,d=m['box'];draw.rectangle((x+a*image.width,y+b*image.height,x+c*image.width,y+d*image.height),outline='lime',width=3)
    target=args.directory/f'sheet-{start:02d}.jpg';sheet.save(target,quality=90);print(target)
