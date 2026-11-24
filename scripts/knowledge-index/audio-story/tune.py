#!/usr/bin/env python3
"""Private matched audio trials; print aggregate timings, retain speech only locally."""
import argparse,importlib.util,json,sqlite3,subprocess,sys,time,wave
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--host');p.add_argument('--backends',default='mac,cpu,rtx');p.add_argument('--beams',default='1,3');a=p.parse_args()
    if a.host:
        dest='/opt/knowledge-index/audio-story'
        for local,remote in [('worker.py','worker-next.py'),('tune.py','tune.py')]:
            subprocess.run(['ssh',a.host,'mkdir -p '+dest+'; cat > '+dest+'/'+remote],input=Path(__file__).with_name(local).read_bytes(),check=True)
        subprocess.run(['ssh',a.host,'/opt/knowledge-index/venv/bin/python '+dest+'/tune.py --backends '+a.backends+' --beams '+a.beams],check=True);return
    s=importlib.util.spec_from_file_location('audio',Path(__file__).with_name('worker-next.py'));w=importlib.util.module_from_spec(s);s.loader.exec_module(w)
    root=Path('/local-3TB-backup/photo-enrichment/audio-story/trials');root.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(root/'trials.sqlite3',timeout=90);db.execute('PRAGMA journal_mode=WAL');db.execute('CREATE TABLE IF NOT EXISTS trials(clip TEXT,backend TEXT,beam INTEGER,seconds REAL,duration REAL,result TEXT,PRIMARY KEY(clip,backend,beam))')
    source=sqlite3.connect('file:/local-3TB-backup/photo-enrichment/video-tuning-20261124/trials.sqlite3?mode=ro',uri=True)
    clips=[]
    for key,row,duration in source.execute('SELECT id,row_json,duration FROM clips ORDER BY duration'):
        row=json.loads(row);wav=root/(key+'.wav')
        if not wav.exists():
            r=subprocess.run(['ffmpeg','-v','error','-threads','2','-i',str(w.LIBRARY/row['path']),'-t','30','-vn','-ac','1','-ar','16000','-c:a','pcm_s16le','-y',str(wav)],capture_output=True)
            if r.returncode:continue
        clips.append((key,wav,min(duration,30)))
    silence=root/'silence.wav'
    if not silence.exists():
        with wave.open(str(silence),'wb') as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(16000);f.writeframes(bytes(16000*2*10))
    clips.append(('silence',silence,10))
    urls={'mac':'http://127.0.0.1:19477','cpu':'https://whisper-cpu.app.home.panderosystems.com','rtx':'https://whisper.app.home.panderosystems.com'}
    for beam in map(int,a.beams.split(',')):
        for backend in a.backends.split(','):
            # Full matched sample for beam 1; beam 3 probes longer speech candidates.
            sample=clips if beam==1 else [c for c in clips if c[2]>=30][:2]+[clips[-1]]
            for key,wav,duration in sample:
                if db.execute('SELECT 1 FROM trials WHERE clip=? AND backend=? AND beam=?',[key,backend,beam]).fetchone():continue
                started=time.monotonic()
                try:raw=w.transcribe(urls[backend],wav.read_bytes(),beam)
                except Exception as exc:
                    print(json.dumps({'backend':backend,'beam':beam,'error':type(exc).__name__}),flush=True);break
                elapsed=time.monotonic()-started
                if 'segments' not in raw:raise ValueError('No timestamped segments')
                db.execute('INSERT INTO trials VALUES(?,?,?,?,?,?)',[key,backend,beam,elapsed,duration,json.dumps(raw,ensure_ascii=False)]);db.commit()
                print(json.dumps({'backend':backend,'beam':beam,'seconds':round(elapsed,2),'audio_seconds':round(duration,2),'segments':len(w.parse_transcript(raw)),'silence_control':key=='silence'}),flush=True)
    result=[]
    for backend,beam,n,seconds,audio in db.execute('SELECT backend,beam,count(*),sum(seconds),sum(duration) FROM trials GROUP BY backend,beam'):
        result.append(dict(backend=backend,beam=beam,clips=n,wall_seconds=round(seconds,2),source_seconds=round(audio,2),realtime_multiple=round(audio/seconds,2)))
    (root/'aggregates.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'aggregates':result}),flush=True)

if __name__=='__main__':main()
