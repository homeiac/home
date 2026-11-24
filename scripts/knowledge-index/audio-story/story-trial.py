#!/usr/bin/env python3
"""Compare audio-aware story prompts privately, using saved vision and speech only."""
import argparse,importlib.util,json,sqlite3,subprocess,time,urllib.request
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--host');a=p.parse_args()
if a.host:
 for name,target in [('worker.py','worker-next.py'),('story-trial.py','story-trial.py')]:subprocess.run(['ssh',a.host,'cat > /opt/knowledge-index/audio-story/'+target],input=Path(__file__).with_name(name).read_bytes(),check=True)
 subprocess.run(['ssh',a.host,'/opt/knowledge-index/venv/bin/python /opt/knowledge-index/audio-story/story-trial.py'],check=True);raise SystemExit
spec=importlib.util.spec_from_file_location('audio',Path(__file__).with_name('worker-next.py'));w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)
root=w.ROOT/'trials';db=sqlite3.connect(root/'trials.sqlite3')
clips=sqlite3.connect('file:/local-3TB-backup/photo-enrichment/video-tuning-20261124/trials.sqlite3?mode=ro',uri=True)
import duckdb
out=[]
inputs=[]
for clip,raw in db.execute("SELECT clip,result FROM trials WHERE backend='mac' AND beam=1 AND clip<>'silence'").fetchall():
 segments=w.parse_transcript(json.loads(raw))
 if segments:
  row=json.loads(clips.execute('SELECT row_json FROM clips WHERE id=?',[clip]).fetchone()[0]);inputs.append((clip,row,segments))
with duckdb.connect(str(w.INDEX/'knowledge.duckdb'),read_only=True,config={'threads':2}) as d:
 visual_rows=d.execute("SELECT path,size_bytes,summary FROM media_summaries WHERE path=ANY(?) AND status='ok' QUALIFY row_number() OVER(PARTITION BY path,size_bytes ORDER BY created_at DESC)=1",[[r['path'] for _,r,_ in inputs]]).fetchall()
 visuals={(p,size):text for p,size,text in visual_rows}
 for clip,row,segments in inputs:
  text=visuals.get((row['path'],row['size_bytes']))
  if not text:continue
  visual=(text,)
  for profile,prompt in [('simple','Combine the saved visual caption and automatic transcript into a short story. Return JSON with a story string. '+json.dumps({'visual':visual[0],'speech':segments},ensure_ascii=False)),('evidence',w.story_prompt(visual[0],segments))]:
   body={'model':'bonsai-27b-metal','messages':[{'role':'user','content':prompt}],'temperature':.1,'max_tokens':384,'chat_template_kwargs':{'enable_thinking':False},'response_format':{'type':'json_object'}}
   req=urllib.request.Request('http://127.0.0.1:19476/v1/chat/completions',json.dumps(body).encode(),{'Content-Type':'application/json','Authorization':'Bearer '+Path('/opt/knowledge-index/mac-bonsai.key').read_text().strip()})
   started=time.monotonic()
   with urllib.request.urlopen(req,timeout=300) as r:answer=json.load(r)['choices'][0]['message']['content']
   out.append({'clip':clip,'profile':profile,'visual':visual[0],'speech':segments,'answer':answer,'seconds':time.monotonic()-started})
(root/'story-review.json').write_text(json.dumps(out,indent=2,ensure_ascii=False))
print(json.dumps({'pairs':len(out)//2,'requests':len(out),'seconds':round(sum(r['seconds'] for r in out),2)}))
