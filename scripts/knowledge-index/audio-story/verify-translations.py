#!/usr/bin/env python3
"""Run three authorized, private text-only Codex checks with shared cost holds."""
import argparse,hashlib,importlib.util,json,os,shlex,subprocess,sys,time
from pathlib import Path


def remote(mode):
    root=Path('/local-3TB-backup/photo-enrichment/audio-story')
    if mode=='samples':
        import sqlite3
        trial=root/'trials';review=json.loads((trial/'story-review.json').read_text())
        with sqlite3.connect('file:'+str(trial/'trials.sqlite3')+'?mode=ro',uri=True) as db:
            languages={k:json.loads(raw).get('language') for k,raw in db.execute("SELECT clip,result FROM trials WHERE backend='mac' AND beam=1")}
        rows=[{'case':row['clip'],'evidence':{'visual':row['visual'],'speech':row['speech'],'language':languages[row['clip']]}} for row in review if row['profile']=='evidence']
        print(json.dumps(rows));return
    spec=importlib.util.spec_from_file_location('worker','/opt/knowledge-index/audio-story/worker.py');w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)
    request=json.load(sys.stdin)
    with w.connect(root) as db:
        if mode=='reserve':
            db.execute('BEGIN IMMEDIATE')
            previous=db.execute('SELECT state,result FROM codex_requests WHERE id=?',[request['id']]).fetchone()
            if previous:print(json.dumps(dict(previous)));return
            total=db.execute('SELECT coalesce(sum(cost),0) FROM codex_requests').fetchone()[0]
            if total+25000>10_000_000:raise RuntimeError('Translation cap reached')
            db.execute("INSERT INTO codex_requests VALUES(?,?,'sent',25000,NULL)",[request['id'],'pilot:'+request['case']]);print(json.dumps({'state':'reserved'}))
        elif mode=='settle':
            answer=request.get('answer')
            if answer:
                u=answer['usage'];i,c,o=u['input_tokens'],u.get('cached_input_tokens',0),u['output_tokens']
                if any(type(n) is not int for n in (i,c,o)) or not 0<=c<=i or o<0:raise ValueError('Invalid usage')
                cost=((i-c)*10+c+o*50+99)//100
                db.execute("UPDATE codex_requests SET state='ok',cost=?,result=? WHERE id=? AND state='sent'",[cost,json.dumps(answer),request['id']])
            else:db.execute("UPDATE codex_requests SET state='unknown' WHERE id=? AND state='sent'",[request['id']])
            print(json.dumps({'settled':True}))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--host');p.add_argument('--remote',choices=('samples','reserve','settle'));a=p.parse_args()
    if a.remote:return remote(a.remote)
    if not a.host:p.error('--host is required')
    import codex_translate as broker
    os.umask(0o077);broker.ROOT.mkdir(parents=True,exist_ok=True)
    os.environ['CODEX_BIN']=subprocess.check_output(['which','codex'],text=True).strip()
    destination='/opt/knowledge-index/audio-story/verify-translations.py'
    subprocess.run(['ssh','-o','BatchMode=yes',a.host,'cat > '+destination],input=Path(__file__).read_bytes(),check=True)
    def call(mode,body=None):
        command=shlex.join(['/opt/knowledge-index/venv/bin/python',destination,'--remote',mode])
        raw=subprocess.check_output(['ssh','-o','BatchMode=yes',a.host,command],input=json.dumps(body).encode() if body else None)
        return json.loads(raw)
    cases=call('samples');cases.append({'case':'synthetic-tamil-control','evidence':{'visual':'A mountain landscape with a walking trail.','speech':[{'start':0,'end':4,'text':'நாம் இன்று மலை ஏற வந்திருக்கிறோம்.'}],'language':'tamil'}});results=[]
    for case in cases:
        identity=json.dumps(['translation-pilot-v1',case,broker.PROMPT],sort_keys=True,ensure_ascii=False)
        key=hashlib.sha256(identity.encode()).hexdigest();reservation=call('reserve',{'id':key,'case':case['case']})
        began=time.monotonic()
        if reservation['state']=='ok':answer=json.loads(reservation['result'])
        elif reservation['state']=='reserved':
            try:answer=broker.translate({'id':key,'evidence':case['evidence']})
            except Exception:
                call('settle',{'id':key});raise
            call('settle',{'id':key,'answer':answer})
        else:raise RuntimeError('Previous pilot request needs inspection; not repeating it')
        results.append(dict(case=case,answer=answer,seconds=round(time.monotonic()-began,2)))
        print(json.dumps({'language':case['evidence']['language'],'assessment':answer['assessment'],'seconds':results[-1]['seconds']}),flush=True)
    (broker.ROOT/'translation-review.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'reviewed':len(results),'useful':sum(r['answer']['assessment']=='useful' for r in results),'withheld':sum(r['answer']['assessment']!='useful' for r in results)}))

if __name__=='__main__':main()
