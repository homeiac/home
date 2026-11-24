#!/usr/bin/env python3
"""Compare video JPEG extraction under live host load; store only private details."""
import argparse
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import time
from PIL import Image,ImageChops


def main():
    os.umask(0o077);os.nice(10)
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--state',type=Path,required=True);p.add_argument('--modes',default='default,bounded,bounded2')
    p.add_argument('--report',action='store_true')
    a=p.parse_args();db=sqlite3.connect(a.state/'trials.sqlite3')
    if a.report:
        rows=db.execute("SELECT mode,count(*),sum(frames),sum(pixel_changes),sum(error<>''),sum(seconds) FROM decode_trials GROUP BY mode").fetchall()
        print(json.dumps([dict(mode=m,cells=n,frames=f,pixel_changes=c,errors=e,seconds=s) for m,n,f,c,e,s in rows]));return
    db.execute('''CREATE TABLE IF NOT EXISTS decode_trials(block INTEGER,clip TEXT,mode TEXT,
        seconds REAL,frames INTEGER,pixel_changes INTEGER,error TEXT,PRIMARY KEY(block,clip,mode))''')
    clips=db.execute('SELECT id,row_json,duration FROM clips ORDER BY duration').fetchall()
    for block in (1,2):
        for key,row_json,duration in (clips if block==1 else list(reversed(clips))):
            modes=a.modes.split(',')
            if any(m not in ('default','bounded','bounded2') for m in modes):raise ValueError('Unknown decoder mode')
            for mode in (modes if block==1 else list(reversed(modes))):
                if db.execute('SELECT 1 FROM decode_trials WHERE block=? AND clip=? AND mode=?',[block,key,mode]).fetchone():continue
                path='/local-3TB-backup/gphotos/library/'+json.loads(row_json)['path']
                began=time.monotonic();done=changed=0;error=''
                try:
                    for i in range(8):
                        stamp=duration*(i+.5)/8
                        cmd=['ffmpeg','-v','error','-nostdin']
                        if mode!='default':cmd+=['-threads','2' if mode=='bounded2' else '1','-filter_threads','1','-filter_complex_threads','1']
                        cmd+=['-ss',str(round(stamp,2)),'-i',path,'-vf',"scale='if(gt(iw,ih),min(1024,iw),-2)':'if(gt(iw,ih),-2,min(1024,ih))'",'-frames:v','1']
                        if mode!='default':cmd+=['-threads','1']
                        cmd+=['-f','image2pipe','-vcodec','mjpeg','-']
                        result=subprocess.run(cmd,capture_output=True,timeout=120,check=True)
                        with Image.open(io.BytesIO(result.stdout)) as im,Image.open(a.state/key/f'{i}.jpg') as old:
                            changed+=ImageChops.difference(im.convert('RGB'),old.convert('RGB')).getbbox() is not None
                        done+=1
                except Exception as exc:error=type(exc).__name__
                seconds=time.monotonic()-began
                with db:db.execute('INSERT INTO decode_trials VALUES (?,?,?,?,?,?,?)',[block,key,mode,seconds,done,changed,error])
                print(json.dumps(dict(block=block,mode=mode,seconds=round(seconds,2),frames=done,pixel_changes=changed,error=error)),flush=True)
    print(json.dumps(dict(aggregate=db.execute('''SELECT mode,count(*),sum(frames),sum(pixel_changes),sum(error<>''),sum(seconds)
        FROM decode_trials GROUP BY mode''').fetchall())),flush=True)

if __name__=='__main__':main()
