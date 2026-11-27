#!/usr/bin/env python3
"""Check whether PNG corruption is only chunk framing or damaged compressed pixels."""
import argparse
import json
from pathlib import Path
import struct
import zlib
p=argparse.ArgumentParser(description=__doc__);p.add_argument('path',type=Path);a=p.parse_args();b=a.path.read_bytes()
chunks=[];start=0
while True:
    offset=b.find(b'IDAT',start)
    if offset<0:break
    start=offset+4
    if offset<4:continue
    size=struct.unpack_from('>I',b,offset-4)[0];end=offset+4+size
    if size>len(b) or end+4>len(b):continue
    chunks.append({'offset':offset-4,'size':size,'crc_ok':zlib.crc32(b[offset:end])==struct.unpack_from('>I',b,end)[0],'data':b[offset+4:end]})
stream=b''.join(c['data'] for c in chunks)
report={'idat_chunks_found':len(chunks),'valid_crc_chunks':sum(c['crc_ok'] for c in chunks),'iend_present':b[-12:]==b'\x00\x00\x00\x00IEND\xaeB`\x82'}
try:report['inflated_bytes']=len(zlib.decompress(stream));report['reframed_stream_valid']=True
except zlib.error as e:report['reframed_stream_valid']=False;report['error']=str(e)
report['gaps']=[chunks[i+1]['offset']-(c['offset']+c['size']+12) for i,c in enumerate(chunks[:-1]) if chunks[i+1]['offset']!=c['offset']+c['size']+12]
report['bad_chunks']=[{k:v for k,v in c.items() if k!='data'} for c in chunks if not c['crc_ok']]
report['gap_details']=[{'previous':{k:v for k,v in c.items() if k!='data'},'next':{k:v for k,v in chunks[i+1].items() if k!='data'}} for i,c in enumerate(chunks[:-1]) if chunks[i+1]['offset']!=c['offset']+c['size']+12]
(a.path.parent/'png-chunk-audit.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
