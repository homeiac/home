#!/usr/bin/env python3
"""Export aggregate trial evidence only; private speech and clip IDs never enter Git."""
import argparse,json,sqlite3,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--host');a=p.parse_args()
if a.host:
 raw=subprocess.check_output(['ssh',a.host,'/opt/knowledge-index/venv/bin/python -'],input=Path(__file__).read_bytes())
 Path(__file__).with_name('results.json').write_bytes(raw);raise SystemExit
root=Path('/local-3TB-backup/photo-enrichment/audio-story/trials')
with sqlite3.connect('file:'+str(root/'trials.sqlite3')+'?mode=ro',uri=True) as db:
 trials=[dict(backend=b,beam=beam,clips=n,wall_seconds=round(seconds,2),source_seconds=round(source,2),realtime_multiple=round(source/seconds,2)) for b,beam,n,seconds,source in db.execute('SELECT backend,beam,count(*),sum(seconds),sum(duration) FROM trials GROUP BY backend,beam')]
 paired=[]
 for b, in db.execute('SELECT DISTINCT backend FROM trials'):
  row=db.execute('SELECT count(*),sum(a.seconds),sum(b.seconds) FROM trials a JOIN trials b ON a.clip=b.clip AND a.backend=b.backend WHERE a.backend=? AND a.beam=1 AND b.beam=3',[b]).fetchone()
  paired.append(dict(backend=b,clips=row[0],beam1_seconds=round(row[1] or 0,2),beam3_seconds=round(row[2] or 0,2)))
review=json.loads((root/'story-review.json').read_text()) if (root/'story-review.json').exists() else []
print(json.dumps(dict(
 story='Use saved visual captions plus timestamped speech to recall the event. Keep original captions and full transcripts separately; uncertain or repetitive ASR is withheld. The backfill never sends images to a model.',
 decision='Mac Metal does most transcription; spare still-fawn CPU adds independent capacity. The RTX was benchmarked with a reserved share, then returned to Immich so semantic search stays available. One audio request per backend and a separate text-only story merger. No-audio and unusable-speech videos retain their visual account.',
 method='Six fixed private clips capped at their first 30 seconds plus a 10-second silence control: 151.93 source seconds. Whisper small Q5_1 multilingual, Silero VAD, two CPU threads, warm model servers (first-request warmup may remain), beam 1. One cell per clip/backend under live host contention; extraction excluded, HTTP transfer included. Beam 3 uses a matched 70-second subset only; compare its overlapping cells separately. No reference word-error-rate or full-video accuracy score.',
 trials=trials,paired_decoding=paired,story_prompt_pairs=len(review)//2,
 quality='Reviewed paired text outputs against saved visual captions and automatic speech, not a human-labelled audio reference. Repetition, language confidence below 0.45 and low segment confidence are withheld. Source language is preserved; stories distinguish observations from spoken claims.'),indent=2,ensure_ascii=False))
