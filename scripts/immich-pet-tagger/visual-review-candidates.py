#!/usr/bin/env python3
"""Render frozen private candidate pages, or record explicit visual decisions."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
from PIL import Image,ImageDraw,ImageOps
from importlib.util import spec_from_file_location,module_from_spec
spec=spec_from_file_location('report',Path(__file__).with_name('report-reject-review.py'));report=module_from_spec(spec);spec.loader.exec_module(report)

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);p.add_argument('--snapshot');p.add_argument('--pages',type=int,default=3);p.add_argument('--accept',nargs='*',type=int,default=[]);p.add_argument('--defer',nargs='*',type=int,default=[]);p.add_argument('--reject',nargs='*',type=int,default=[]);p.add_argument('--note');a=p.parse_args();os.umask(0o077)
 manifest=json.loads((a.directory/'rejects.json').read_text());by_index={r['review_index']:r for r in manifest}
 batches,records=report.read_records(a.directory/'review-sol-v3-single')
 eligible={r['review_index']:r for r in records if r['answer']['verdict']=='same_dog' and r['answer']['confidence']=='high'}
 path=a.directory/'visual-decisions.json';decisions=json.loads(path.read_text()) if path.exists() else {}
 if a.accept or a.defer or a.reject:
  assert a.note
  assert len(a.accept+a.defer+a.reject)==len(set(a.accept+a.defer+a.reject))
  for verdict,indices in [('accept',a.accept),('defer',a.defer),('reject',a.reject)]:
   for index in indices:
    assert index in eligible,'Only qualified Sol high-confidence nominations can be accepted'
    asset=by_index[index]['asset_id'];sha=hashlib.sha256((a.directory/'targets'/(asset+'.jpg')).read_bytes()).hexdigest()
    row={'review_index':index,'asset_id':asset,'image_sha256':sha,'decision':verdict,'reviewer':'assistant independent visual inspection; not owner confirmation','note':a.note,'at':datetime.now(timezone.utc).isoformat()}
    assert str(index) not in decisions,'Decisions are immutable; record correction separately'
    decisions[str(index)]=row
    with (a.directory/'visual-journal.jsonl').open('a') as stream:stream.write(json.dumps(row)+'\n')
  temp=path.with_suffix('.tmp');temp.write_text(json.dumps(decisions,indent=2)+'\n');temp.replace(path)
 if a.snapshot:
  pending=sorted(i for i in eligible if str(i) not in decisions)[:9*a.pages]
  folder=a.directory/'visual'/a.snapshot;folder.mkdir(parents=True,exist_ok=False)
  (folder/'manifest.json').write_text(json.dumps([by_index[i] for i in pending],indent=2)+'\n')
  for page,start in enumerate(range(0,len(pending),9)):
   w,h=480,540;canvas=Image.new('RGB',(3*w,((len(pending[start:start+9])+2)//3)*h),'white');draw=ImageDraw.Draw(canvas)
   for cell,index in enumerate(pending[start:start+9]):
    asset=by_index[index]['asset_id'];im=ImageOps.contain(Image.open(a.directory/'targets'/(asset+'.jpg')).convert('RGB'),(w-12,h-40));x=(cell%3)*w;y=(cell//3)*h
    canvas.paste(im,(x+(w-im.width)//2,y+36));draw.text((x+8,y+8),f'Review {index}',fill='black')
   output=folder/f'{page:03}.jpg';canvas.save(output,quality=95);print(output)
 print(json.dumps({'evaluated':len(records),'nominated':len(eligible),'visually_reviewed':len(decisions),'accepted':sum(r['decision']=='accept' for r in decisions.values()),'deferred':sum(r['decision']=='defer' for r in decisions.values())}))

if __name__=='__main__':main()
