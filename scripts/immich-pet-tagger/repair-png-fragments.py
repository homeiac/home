#!/usr/bin/env python3
"""Recover a displaced PNG IDAT fragment only when CRCs and full zlib checksum verify.

Writes a separate candidate, never the source. This deliberately handles only one
shortened IDAT chunk plus small displaced byte blocks between otherwise valid chunks.
"""
import argparse
import json
from pathlib import Path
import struct
import zlib


def repair(source: bytes) -> tuple[bytes, dict]:
    """Reassemble a uniquely checksum-verified stream; reject uncertain reconstruction."""
    if source[:8]!=b'\x89PNG\r\n\x1a\n':raise ValueError('Not PNG')
    chunks=[];start=8
    while True:
        offset=source.find(b'IDAT',start)
        if offset<0:break
        start=offset+4
        if offset<4:continue
        size=struct.unpack_from('>I',source,offset-4)[0];end=offset+4+size
        if size>65536 or end+4>len(source):continue
        data=source[offset+4:end];crc=struct.unpack_from('>I',source,end)[0]
        chunks.append(dict(offset=offset-4,size=size,data=data,crc=crc,valid=zlib.crc32(b'IDAT'+data)==crc))
    bad=[i for i,c in enumerate(chunks) if not c['valid']]
    if len(bad)!=1 or bad[0]>=len(chunks)-1:raise ValueError('Expected one shortened IDAT chunk')
    i=bad[0];chunk=chunks[i];next_offset=chunks[i+1]['offset']
    actual=source[chunk['offset']+8:next_offset-4];expected_crc=struct.unpack_from('>I',source,next_offset-4)[0]
    missing=chunk['size']-len(actual)
    if not 0<missing<=8192:raise ValueError('Not a bounded displaced fragment')
    fragments=set()
    for j,c in enumerate(chunks[:-1]):
        end=c['offset']+12+c['size'];next_start=chunks[j+1]['offset']
        if next_start-end==missing:fragments.add(source[end:next_start])
    solutions=set()
    for fragment in fragments:
        for position in range(len(actual)+1):
            data=actual[:position]+fragment+actual[position:]
            if zlib.crc32(b'IDAT'+data)==expected_crc:solutions.add(data)
    if len(solutions)!=1:raise ValueError('No unique CRC-verified reconstruction')
    chunk['data']=solutions.pop();chunk['crc']=expected_crc
    stream=b''.join(c['data'] for c in chunks)
    decoder=zlib.decompressobj();pixels=decoder.decompress(stream)+decoder.flush()
    if not decoder.eof or decoder.unused_data:raise ValueError('Compressed pixel stream incomplete or ambiguous')
    width,height,depth,color,compression,filtering,interlace=struct.unpack('>IIBBBBB',source[16:29])
    if (depth,color,compression,filtering,interlace)!=(8,6,0,0,0):raise ValueError('Only non-interlaced RGBA8 verified here')
    if len(pixels)!=(width*4+1)*height:raise ValueError('Incomplete decoded pixels')
    out=source[:chunks[0]['offset']]
    for c in chunks:out+=struct.pack('>I',len(c['data']))+b'IDAT'+c['data']+struct.pack('>I',c['crc'])
    last=chunks[-1];out+=source[last['offset']+12+last['size']:]
    # Every reconstructed chunk, including ancillary metadata and IEND, must validate.
    position=8;last_kind=None
    while position+12<=len(out):
        n=struct.unpack_from('>I',out,position)[0];end=position+12+n
        if end>len(out):raise ValueError('Invalid reconstructed framing')
        if zlib.crc32(out[position+4:end-4])!=struct.unpack_from('>I',out,end-4)[0]:raise ValueError('Reconstructed CRC mismatch')
        last_kind=out[position+4:position+8];position=end
    if position!=len(out) or last_kind!=b'IEND':raise ValueError(f'Missing clean PNG terminator: {position}/{len(out)} {last_kind!r}')
    return out,{'repaired_idat_chunks':1,'fragment_bytes':missing,'width':width,'height':height,'decoded_pixel_bytes':len(pixels),'all_chunk_crcs_valid':True,'zlib_checksum_valid':True}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    fixed,report=repair(a.source.read_bytes())
    with a.output.open('xb') as target:target.write(fixed)
    a.output.with_suffix('.report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
