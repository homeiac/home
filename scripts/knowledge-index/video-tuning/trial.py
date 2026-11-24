#!/usr/bin/env python3
"""Private, resumable matched video trials. Never writes production captions.

Run on Piglet using the existing knowledge-index Python environment. Media and
answers remain under --state (mode 0700); stdout contains aggregates only.
"""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import statistics
import sys
import time
import urllib.error
import urllib.request

import duckdb
from PIL import Image

ROOT = Path('/opt/knowledge-index')
sys.path.insert(0, str(ROOT/'enrichers'))
import media_summary as media

PROFILES = {
    'baseline8': dict(frames=8,edge=1024,prompt='baseline',tokens=384),
    'baseline4': dict(frames=4,edge=1024,prompt='baseline',tokens=384),
    'story4': dict(frames=4,edge=1024,prompt='story',tokens=256),
    'story4small': dict(frames=4,edge=768,prompt='story',tokens=256),
    'story8small': dict(frames=8,edge=768,prompt='story',tokens=256),
    'safe4': dict(frames=4,edge=1024,prompt='safe',tokens=256),
    'safe8': dict(frames=8,edge=1024,prompt='safe',tokens=256),
    'safe4small': dict(frames=4,edge=768,prompt='safe',tokens=256),
    'safe_adaptive': dict(frames=0,edge=1024,prompt='safe',tokens=256),
    'sequence4': dict(frames=4,edge=1024,prompt='sequence',tokens=256),
    'sequence8': dict(frames=8,edge=1024,prompt='sequence',tokens=256),
    'sequence8small': dict(frames=8,edge=768,prompt='sequence',tokens=256),
    'current': dict(frames=8,edge=1024,prompt='baseline',tokens=384,production=True),
    'story_final': dict(frames=8,edge=768,prompt='story',tokens=256,production=True),
}


def story_prompt(row, duration, positions):
    """Ask for an observable event and sequence; metadata is context, not proof."""
    hints={k:row.get(k) for k in ('album','people','description') if row.get(k)}
    if row.get('taken_ts'):
        hints['date']=datetime.datetime.fromtimestamp(row['taken_ts'],datetime.timezone.utc).strftime('%Y-%m-%d')
    return ('These chronological frames sample a '+str(round(duration,1))+' second video at seconds '
            +', '.join(str(round(t,1)) for t in positions)+'. '
            'Tell the small story of the clip: the main subject, setting, activity, and meaningful change '
            'from beginning to end when the frames support one. If there is no clear change, describe the scene. '
            'Keep distinctive visible details useful for remembering this moment. Do not invent actions between '
            'frames, dialogue, names, relationships, emotions or events. Metadata is a hint, not visual proof. '
            'Omit uncertain incidental details. Context: '+json.dumps(hints,ensure_ascii=False)+'. '
            'Return only JSON: {"summary":"2-3 concise sentences","tags":["up to 6 useful keywords"]}.')


def connect(state):
    db=sqlite3.connect(state/'trials.sqlite3')
    db.execute('PRAGMA journal_mode=WAL')
    db.executescript('''CREATE TABLE IF NOT EXISTS clips(id TEXT PRIMARY KEY, row_json TEXT, duration REAL);
        CREATE TABLE IF NOT EXISTS results(profile TEXT,backend TEXT,block INTEGER,clip TEXT,
        seconds REAL,decode_seconds REAL,ok INTEGER,prompt_tokens INTEGER,output_tokens INTEGER,
        answer TEXT,error TEXT,created REAL,PRIMARY KEY(profile,backend,block,clip));
        CREATE TABLE IF NOT EXISTS cells(profile TEXT,backend TEXT,block INTEGER,parallel INTEGER,
        seconds REAL,PRIMARY KEY(profile,backend,block));''')
    return db


def prepare(db,state,count):
    if db.execute('SELECT count(*) FROM clips').fetchone()[0]>=count:return
    with duckdb.connect(str(Path('/local-3TB-backup/knowledge-index/knowledge.duckdb')),read_only=True) as d:
        d.execute('SET threads=2')
        # Use already-captioned clips for matched comparisons with saved text.
        d.execute('''CREATE TEMP TABLE candidates AS SELECT path,size_bytes,max(duration_s) duration
            FROM media_summaries WHERE status='ok' AND duration_s BETWEEN 3 AND 600
            GROUP BY path,size_bytes''')
        rows=d.execute('''WITH joined AS (SELECT c.*,m.name,m.ext,m.taken_ts,m.album,m.has_geo,m.people,m.description
            FROM candidates c JOIN gphotos_media m USING(path,size_bytes) WHERE m.album IS NULL),
            ranked AS (SELECT *,row_number() OVER(PARTITION BY
            CASE WHEN duration<20 THEN 0 WHEN duration<90 THEN 1 ELSE 2 END ORDER BY sha256(path)) n
            FROM joined) SELECT * FROM ranked WHERE n<=?
            ORDER BY duration LIMIT ?''',[max(count//3,1),count]).fetchall()
        names=[c[0] for c in d.description]
    for values in rows:
        row=dict(zip(names,values));duration=row.pop('duration');row.pop('n',None)
        key=hashlib.sha256((row['path']+str(row['size_bytes'])).encode()).hexdigest()[:12]
        if db.execute('SELECT 1 FROM clips WHERE id=?',[key]).fetchone():continue
        target=state/key;target.mkdir(exist_ok=True)
        began=time.monotonic()
        for i in range(8):
            f=target/f'{i}.jpg'
            if not f.exists():f.write_bytes(media.jpeg_frame('/local-3TB-backup/gphotos/library/'+row['path'],duration*(i+.5)/8))
        with db:db.execute('INSERT INTO clips VALUES (?,?,?)',[key,json.dumps(row),duration])
        print(json.dumps(dict(prepared=key,duration=round(duration,1),decode_seconds=round(time.monotonic()-began,2))),flush=True)


def infer(job):
    state,profile,backend,block,clip,row_json,duration=job
    row=json.loads(row_json);p=PROFILES[profile]
    frames=p['frames'] or (4 if duration<=20 else 8)
    indices=list(range(8)) if frames==8 else [0,2,5,7]
    began=time.monotonic();images=[]
    for i in indices:
        raw=(state/clip/f'{i}.jpg').read_bytes()
        if p['edge']!=1024:
            image=Image.open(io.BytesIO(raw));image.thumbnail((p['edge'],p['edge']))
            out=io.BytesIO();image.save(out,format='JPEG',quality=88);raw=out.getvalue()
        images.append(base64.b64encode(raw).decode())
    prep=time.monotonic()-began
    positions=[duration*(i+.5)/8 for i in indices]
    if p.get('production'):
        count=max(1,min(p['frames'],int(duration) or 1))
        positions=[duration*(i+.5)/count for i in range(count)]
        if count!=8:
            images=[]
            for number,t in enumerate(positions):
                cache=state/clip/f'cap-{count}-{number}.jpg'
                if not cache.exists():cache.write_bytes(media.jpeg_frame('/local-3TB-backup/gphotos/library/'+row['path'],t))
                raw=cache.read_bytes()
                if p['edge']!=1024:
                    image=Image.open(io.BytesIO(raw));image.thumbnail((p['edge'],p['edge']))
                    out=io.BytesIO();image.save(out,format='JPEG',quality=88);raw=out.getvalue()
                images.append(base64.b64encode(raw).decode())
            prep=time.monotonic()-began
    prompt=(media.build_prompt(row,True,len(images),'') if p['prompt']=='baseline'
            else story_prompt(row,duration,positions))
    if p['prompt']=='sequence':
        prompt=('These are chronological video frames at seconds '+', '.join(str(round(t,1)) for t in positions)+'. '
                'Write two factual sentences connecting the state already visible in the first frame to observed later actions or changes. '
                'If no change is clear, describe the scene and camera movement. Never reconstruct earlier steps or fill gaps between frames. '
                'Distinguish holding or positioning an object from actually using it. Describe visible actions without assuming their purpose, '
                'relationships, emotions or speech. Omit uncertain details. Return only JSON with summary and up to six short tags.')
    if p['prompt']=='safe':
        prompt += (' Describe only actions actually visible in the sampled frames. The first frame may already be midway through an activity. '
                   'Never invent an earlier step to make a story complete. When the purpose is unclear, describe visible movements rather than naming an event. '
                   'Text overlays alone do not prove an action occurred. Do not call a scene static when people or the camera visibly change position.')
    if backend=='rtx':
        settings={}
        for line in Path('/etc/default/knowledge-index').read_text().splitlines():
            if line.startswith('KI_OLLAMA_URL='):settings['url']=line.split('=',1)[1].strip('"\'')
        endpoint=settings['url'].rstrip('/')+'/api/chat'
        body=dict(model='bonsai-27b',stream=False,think=False,keep_alive='30m',
                  options=dict(num_ctx=8192,num_predict=p['tokens'],temperature=.2,seed=217),
                  messages=[dict(role='user',content=prompt,images=images)])
        headers={}
    else:
        endpoint='http://127.0.0.1:19476/v1/chat/completions'
        headers={'Authorization':'Bearer '+(ROOT/'mac-bonsai.key').read_text().strip()}
        body=dict(model='bonsai-27b-metal',temperature=.2,seed=217,max_tokens=p['tokens'],cache_prompt=False,
                  chat_template_kwargs=dict(enable_thinking=False),messages=[dict(role='user',content=
                  [dict(type='text',text=prompt)]+[dict(type='image_url',image_url=dict(url='data:image/jpeg;base64,'+im)) for im in images])])
    started=time.monotonic();answer='';error='';ok=0;pt=ot=0
    try:
        req=urllib.request.Request(endpoint,json.dumps(body).encode(),{'Content-Type':'application/json',**headers})
        with urllib.request.urlopen(req,timeout=180) as response:result=json.load(response)
        answer=result['message']['content'] if backend=='rtx' else result['choices'][0]['message']['content']
        media.parse_answer(answer);ok=1
        pt=result.get('prompt_eval_count',result.get('usage',{}).get('prompt_tokens',0))
        ot=result.get('eval_count',result.get('usage',{}).get('completion_tokens',0))
    except urllib.error.HTTPError as exc:
        error=f'HTTP {exc.code}: '+exc.read(2000).decode(errors='replace')
    except Exception as exc:error=type(exc).__name__+': '+str(exc)[:500]
    return (profile,backend,block,clip,time.monotonic()-started,prep,ok,pt,ot,answer,error,time.time())


def reset_rtx(profile):
    """Clear model-runtime caches, then warm weights/kernels with synthetic frames."""
    settings={}
    for line in Path('/etc/default/knowledge-index').read_text().splitlines():
        if line.startswith('KI_OLLAMA_URL='):settings['url']=line.split('=',1)[1].strip('"\'')
    def post(route,body):
        req=urllib.request.Request(settings['url'].rstrip('/')+route,json.dumps(body).encode(),{'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=180) as response:return json.load(response)
    post('/api/generate',dict(model='bonsai-27b',keep_alive=0,stream=False))
    image=Image.new('RGB',(1024,576),'#777777');buf=io.BytesIO();image.save(buf,'JPEG')
    raw=base64.b64encode(buf.getvalue()).decode()
    post('/api/chat',dict(model='bonsai-27b',stream=False,think=False,keep_alive='30m',
        options=dict(num_ctx=8192,num_predict=1,temperature=.2),
        messages=[dict(role='user',content='Warmup: describe the blank frames.',images=[raw]*8)]))


def report(db):
    rows=[]
    for profile,backend,block,parallel,wall in db.execute('SELECT * FROM cells ORDER BY block,profile,backend'):
        values=db.execute('SELECT r.seconds,r.ok,r.prompt_tokens,r.output_tokens,c.duration FROM results r JOIN clips c ON c.id=r.clip WHERE profile=? AND backend=? AND block=?',[profile,backend,block]).fetchall()
        times=sorted(v[0] for v in values);ok=sum(v[1] for v in values)
        rows.append(dict(profile=profile,backend=backend,block=block,parallel=parallel,requests=len(values),ok=ok,
            mean_seconds=round(statistics.mean(times),2),p95_seconds=round(times[max(0,__import__('math').ceil(.95*len(times))-1)],2),
            prompt_tokens=round(statistics.mean(v[2] for v in values)),output_tokens=round(statistics.mean(v[3] for v in values)),
            successful_per_minute=round(ok*60/wall,2),source_minutes_per_minute=round(sum(v[4] for v in values if v[1])/wall,2)))
    return rows


def main():
    os.umask(0o077)
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--state',type=Path,required=True)
    ap.add_argument('--prepare',action='store_true')
    ap.add_argument('--count',type=int,default=6)
    ap.add_argument('--profiles',default='baseline8,baseline4,story4,story4small,story8small')
    ap.add_argument('--backends',default='rtx,mac')
    ap.add_argument('--block',type=int,default=1)
    ap.add_argument('--parallel',type=int,default=1)
    ap.add_argument('--report',action='store_true')
    ap.add_argument('--reset-rtx',action='store_true',help='Clear model runtime caches before each RTX cell; excludes synthetic warmup')
    args=ap.parse_args();args.state.mkdir(parents=True,exist_ok=True,mode=0o700)
    db=connect(args.state)
    if args.prepare:prepare(db,args.state,args.count);return
    if args.report:print(json.dumps(report(db)));return
    if __import__('subprocess').run(['systemctl','is-active','--quiet','knowledge-index-enrich.service']).returncode==0:
        raise RuntimeError('Pause production through GitOps before matched trials')
    clips=db.execute('SELECT * FROM clips ORDER BY duration').fetchall()
    for profile in args.profiles.split(','):
        if profile not in PROFILES:raise ValueError('Unknown profile')
        for backend in args.backends.split(','):
            if backend not in ('rtx','mac'):raise ValueError('Unknown backend')
            existing=db.execute('SELECT parallel FROM cells WHERE profile=? AND backend=? AND block=?',
                                [profile,backend,args.block]).fetchone()
            if existing:
                if existing[0]!=args.parallel:raise ValueError('Use a new block for a different concurrency')
                continue
            # Replay an interrupted cell in full so wall time and result count cover the same work.
            jobs=[(args.state,profile,backend,args.block,*clip) for clip in clips]
            if args.reset_rtx:
                if backend!='rtx':raise ValueError('Runtime reset is RTX-only')
                reset_rtx(profile)
            began=time.monotonic()
            with ThreadPoolExecutor(args.parallel) as pool:
                for result in pool.map(infer,jobs):
                    with db:db.execute('INSERT OR REPLACE INTO results VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',result)
                    print(json.dumps(dict(profile=profile,backend=backend,clip=result[3],seconds=round(result[4],2),ok=result[6])),flush=True)
            with db:db.execute('INSERT INTO cells VALUES (?,?,?,?,?)',[profile,backend,args.block,args.parallel,time.monotonic()-began])
            print(json.dumps(dict(cell=[r for r in report(db) if r['profile']==profile and r['backend']==backend and r['block']==args.block])),flush=True)

if __name__=='__main__':main()
