#!/usr/bin/env python3
"""Read-only byte/container diagnostics; does not invent or overwrite source data."""
import collections
import json
from pathlib import Path
import struct
import subprocess
import zlib

ROOT=Path('/local-3TB-backup/gphotos')
items=json.loads(Path('/var/tmp/caption-gaps-20261122.json').read_text())
for item in items:
    if 'decode_error' not in item:continue
    p=ROOT/'library'/item['path']
    raw=p.read_bytes()
    blocks=[(i,len(b)) for i in range(0,len(raw),4096) if (b:=raw[i:i+4096]) and not any(b)]
    out={'job_id':item['job_id'],'zero_block_bytes':sum(n for _,n in blocks),'zero_first_offsets':[i for i,_ in blocks[:8]],
         'tail_zero_bytes':len(raw)-len(raw.rstrip(b'\0'))}
    if item['ext']=='png':
        pos=8;chunks=[];compressed=bytearray()
        while pos+12<=len(raw):
            n,kind=struct.unpack('>I4s',raw[pos:pos+8]);data=raw[pos+8:pos+8+n]
            info={'offset':pos,'kind':kind.decode('ascii',errors='replace'),'length':n}
            if pos+12+n>len(raw):chunks.append(info);break
            crc=struct.unpack('>I',raw[pos+8+n:pos+12+n])[0]
            info['crc_ok']=zlib.crc32(kind+data)==crc
            chunks.append(info)
            if kind==b'IDAT':compressed.extend(data)
            pos+=12+n
        out['chunks']=chunks[:15];out['iend_offsets']=[i for i in range(len(raw)-12,max(0,len(raw)-100),-1) if raw[i:i+4]==b'IEND']
        try:
            dec=zlib.decompressobj();pixels=dec.decompress(compressed)
            out['decompressed_bytes']=len(pixels);out['zlib_complete']=dec.eof
        except zlib.error as exc:out['zlib_error']=str(exc)
        from PIL import Image,ImageFile
        ImageFile.LOAD_TRUNCATED_IMAGES=True
        with Image.open(p) as im:
            im.load();out['decoded_bbox']=im.getbbox()
    if item['ext']=='mpg':
        out['mpeg_start_codes']={hex(code):raw.count(b'\0\0\1'+bytes([code])) for code in (0xb3,0xba,0xe0,0xb8)}
    if item['ext']=='mov' and len(raw)<10000:
        out['mov_video_markers']={x.decode():raw.count(x) for x in (b'vide',b'avc1',b'hvc1',b'meta',b'me ta',b'alis',b'url ')}
    print(json.dumps(out),flush=True)
for parent in [ROOT/'.versions',ROOT/'_staging',ROOT/'.zfs/snapshot',Path('/local-3TB-backup/exports')]:
    print('Recovery location',str(parent),'exists',parent.exists(),'direct entries',len(list(parent.iterdir())) if parent.exists() else 0)
print(subprocess.check_output(['findmnt','-rno','TARGET,SOURCE,FSTYPE'],text=True))
