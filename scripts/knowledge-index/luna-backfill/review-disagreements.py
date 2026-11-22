#!/usr/bin/env python3
"""Make a private, offline HTML review of two saved caption disagreements."""
import argparse
import html
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

REMOTE = r'''
import base64,io,json,sqlite3,sys
from pathlib import Path
sys.path.insert(0,'/opt/photo-enrichment/context')
from photo_enrichment.metadata import oriented_image
root=Path('/local-3TB-backup/photo-enrichment/luna-backfill')
library=Path('/local-3TB-backup/gphotos/library').resolve()
db=sqlite3.connect((root/'luna-ledger.sqlite3').as_uri()+'?mode=ro',uri=True)
db.row_factory=sqlite3.Row
rows=db.execute("""SELECT id,path,size_bytes,inputs,result FROM reconciliations
    WHERE state='ok' AND json_extract(result,'$.answer.needs_visual_review')=1
      AND (lower(path) LIKE '%.jpg' OR lower(path) LIKE '%.jpeg' OR lower(path) LIKE '%.heic')
    ORDER BY seeded,id LIMIT 30""")
examples=[]
for row in rows:
    source=(library/row['path']).resolve()
    if not source.is_relative_to(library) or not source.is_file() or source.stat().st_size!=row['size_bytes']:continue
    try:
        im=oriented_image(source)
        im.thumbnail((1000,800));buffer=io.BytesIO();im.convert('RGB').save(buffer,format='JPEG',quality=85)
        im.close()
    except (OSError,ValueError):continue
    examples.append(dict(id=row['id'],inputs=json.loads(row['inputs']),
        answer=json.loads(row['result'])['answer'],image=base64.b64encode(buffer.getvalue()).decode()))
    if len(examples)==2:break
if len(examples)!=2:raise RuntimeError('Could not prepare two readable photo examples')
print(json.dumps(examples))
'''


def render(examples: list[dict]) -> str:
    """Escape every model/source field; no external scripts, fonts or image requests."""
    escape=html.escape
    cards=[]
    for number, example in enumerate(examples,1):
        inputs,answer=example['inputs'],example['answer']
        conflicts=''.join('<li>'+escape(c)+'</li>' for c in answer['conflicts'])
        cards.append(f'''<article><h2>Example {number}</h2><div class="review">
          <figure><img src="data:image/jpeg;base64,{example['image']}" alt="Original photo for example {number}">
          <figcaption>Preview of the original photo · original file unchanged</figcaption></figure>
          <div class="text"><section class="conflict"><h3>Why it needs review</h3><ul>{conflicts}</ul></section>
          <div class="sources"><section><h3>Local GPU summary</h3><p>{escape(inputs['local_summary']['text'])}</p></section>
          <section><h3>Luna summary</h3><p>{escape(inputs['luna_summary']['text'])}</p></section></div>
          <section class="reconciled"><h3>Reconciled summary</h3><p>{escape(answer['reconciled_summary'])}</p></section>
          <p class="note"><strong>Luna’s explanation:</strong> {escape(answer['notes'])}</p>
          <details><summary>Saved metadata used for reconciliation</summary><pre>{escape(json.dumps(inputs['saved_metadata'],indent=2,ensure_ascii=False))}</pre></details>
          </div></div></article>''')
    return '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>Two summary disagreements</title><style>
    *{box-sizing:border-box}body{margin:0;background:#f3f5f4;color:#20332e;font:17px/1.55 system-ui,sans-serif}
    main{max-width:1500px;margin:auto;padding:32px}header{margin-bottom:30px}h1{font-size:36px;line-height:1.15;margin:10px 0}
    h2{margin:0 0 18px;font-size:24px}h3{font-size:15px;margin:0 0 8px}p{margin:0 0 12px}.badge{font-size:13px;font-weight:650;color:#50665e}
    article{background:white;border:1px solid #d8e0db;border-radius:18px;padding:24px;margin:26px 0;box-shadow:0 5px 20px #20332e08}
    .review{display:grid;grid-template-columns:minmax(280px,.9fr) minmax(360px,1.1fr);gap:28px;align-items:start}
    figure{margin:0;position:sticky;top:20px}img{display:block;width:100%;max-height:650px;object-fit:contain;background:#eef1ee;border-radius:10px}
    figcaption,.note{font-size:14px;color:#55675f;margin-top:12px}.sources{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:14px 0}
    section{padding:16px;border:1px solid #dde3e0;border-radius:10px}.conflict{background:#fff4e2;border-color:#ebcc94}.reconciled{background:#eaf5ee;border-color:#bad5c2}
    ul{padding-left:22px;margin:0}li+li{margin-top:6px}details{font-size:14px;margin-top:14px}summary{cursor:pointer;font-weight:650}
    pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f6f5;padding:14px;border-radius:8px;font-size:12px}
    @media(max-width:850px){main{padding:16px}.review,.sources{grid-template-columns:1fr}figure{position:static}h1{font-size:29px}article{padding:18px}}
    </style><main><header><div class="badge">PRIVATE · LOCAL REVIEW</div><h1>Two summary disagreements</h1>
    <p>Compare each photo with the captions. Reconciliation used text and saved metadata only; it did not re-examine the image.</p>
    <p class="note">This page is read-only. Nothing you view here changes the summaries or sends photos to a model.</p></header>'''+''.join(cards)+'</main></html>'


def main() -> None:
    """Keep private examples outside Git and report only the local HTML path."""
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host',required=True)
    args=parser.parse_args()
    raw=subprocess.check_output(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10',args.host,
        '/opt/photo-enrichment/context/venv/bin/python -c '+shlex.quote(REMOTE)])
    examples=json.loads(raw)
    directory=Path(tempfile.mkdtemp(prefix='summary-disagreements-'))
    directory.chmod(0o700)
    page=directory/'review.html';page.write_text(render(examples));page.chmod(0o600)
    print(page)


if __name__=='__main__':main()
