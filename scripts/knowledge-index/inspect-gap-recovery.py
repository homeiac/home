#!/usr/bin/env python3
"""Read source/copy structure for the frozen twelve-item recovery manifest."""
import json
from pathlib import Path
import sqlite3
import struct
import duckdb

ROOT=Path('/local-3TB-backup')
items=json.loads(Path('/var/tmp/caption-gaps-20261122.json').read_text())
ledger=sqlite3.connect(f'file:{ROOT}/photo-enrichment/luna-backfill/luna-ledger.sqlite3?mode=ro',uri=True)
with duckdb.connect(str(ROOT/'knowledge-index/knowledge.duckdb'),read_only=True) as db:
    db.execute('SET threads=2')
    db.execute('CREATE TEMP TABLE inventory AS SELECT path,name,size_bytes,unit FROM gphotos_files')
    for item in items:
        path=item['path']; p=ROOT/'gphotos/library'/path
        job=ledger.execute('SELECT state,cost,origin_batch,finished FROM jobs WHERE id=?',[item['job_id']]).fetchone()
        history=ledger.execute('SELECT original_state,cost FROM previous_captions WHERE job_id=?',[item['job_id']]).fetchone()
        out={'job_id':item['job_id'],'state_cost_origin_finished':job,'previous_caption':history}
        copies=db.execute('SELECT path,size_bytes,unit FROM inventory WHERE name=?',[p.name]).fetchall()
        out['copies']=[{'same_path':q==path,'bytes':n,'unit':u} for q,n,u in copies]
        out['unit']=db.execute('SELECT unit FROM inventory WHERE path=?',[path]).fetchone()
        if 'decode_error' in item and item['ext']=='mov':
            atoms=[]
            with p.open('rb') as f:
                while f.tell()+8<=p.stat().st_size:
                    start=f.tell(); size,typ=struct.unpack('>I4s',f.read(8))
                    if size==1:size=struct.unpack('>Q',f.read(8))[0]
                    if size==0:size=p.stat().st_size-start
                    atoms.append({'offset':start,'type':typ.decode('ascii',errors='replace'),'bytes':size})
                    if size<8 or start+size>p.stat().st_size:break
                    f.seek(start+size)
            out['atoms']=atoms[:20]
        if item['ext']=='png':
            from PIL import Image,ImageFile
            for truncated in (False,True):
                ImageFile.LOAD_TRUNCATED_IMAGES=truncated
                try:
                    with Image.open(p) as im:im.load(); out['pillow_truncated_'+str(truncated)]={'size':im.size,'mode':im.mode}
                except Exception as exc:out['pillow_truncated_'+str(truncated)]=type(exc).__name__+': '+str(exc)[:100]
        print(json.dumps(out),flush=True)
print('Storage directories:',[str(p) for p in ROOT.glob('*') if p.is_dir()])
print('Photos directories:',[str(p) for p in (ROOT/'gphotos').glob('*') if p.is_dir()])
