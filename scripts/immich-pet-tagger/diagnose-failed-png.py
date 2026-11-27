#!/usr/bin/env python3
"""Check PNG chunk integrity and stage a tolerant preview privately for visual review."""
import argparse
import base64
import json
import os
from pathlib import Path
import struct
import subprocess
import zlib
from distributed import KUBE
p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);a=p.parse_args();os.umask(0o077)
items=[m for m in json.loads((a.directory/'original-metadata.json').read_text()) if m['type']=='IMAGE'];assert len(items)==1
code='''import fs from 'node:fs/promises';import {createRequire} from 'node:module';const sharp=createRequire('/usr/src/app/server/package.json')('sharp');const path=Buffer.from(process.argv[2],'base64').toString();const b=await fs.readFile(path);const out={original:b.toString('base64')};try{out.jpeg=(await sharp(b,{failOn:'none',limitInputPixels:40000000}).rotate().resize({width:1600,height:1600,fit:'inside',withoutEnlargement:true}).jpeg({quality:90}).toBuffer()).toString('base64');}catch(e){out.error=e.message;}console.log(JSON.stringify(out));'''
r=subprocess.run(KUBE+['-n','immich-pilot','exec','-i','deployment/immich-server','--','node','--input-type=module','-',base64.b64encode(items[0]['originalPath'].encode()).decode()],input=code,text=True,capture_output=True,check=True,timeout=60)
result=json.loads(r.stdout);source=base64.b64decode(result.pop('original'));(a.directory/'failed-original.png').write_bytes(source)
if 'jpeg' in result:(a.directory/'png-tolerant-preview.jpg').write_bytes(base64.b64decode(result.pop('jpeg')));result['tolerant_preview']=True
chunks=[];idat=[];position=8
while position+12<=len(source):
    length=struct.unpack_from('>I',source,position)[0];kind=source[position+4:position+8];end=position+12+length
    if end>len(source):chunks.append({'kind':kind.decode('ascii','replace'),'declared_length':length,'available':len(source)-position-12,'truncated':True});break
    data=source[position+8:position+8+length];expected=struct.unpack_from('>I',source,position+8+length)[0]
    chunks.append({'kind':kind.decode('ascii','replace'),'bytes':length,'crc_ok':zlib.crc32(kind+data)==expected})
    if kind==b'IDAT':idat.append(data)
    position=end
result.update(bytes=len(source),chunks=chunks,unparsed_bytes=len(source)-position)
try:result['inflated_bytes']=len(zlib.decompress(b''.join(idat)));result['deflate_ok']=True
except zlib.error as e:result['deflate_ok']=False;result['deflate_error']=str(e)
(a.directory/'png-diagnostics.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
