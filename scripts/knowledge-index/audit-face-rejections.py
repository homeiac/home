#!/usr/bin/env python3
"""Read saved rejections and API explanations; print aggregate results only."""
import json
import os
from pathlib import Path
import subprocess
import urllib.parse
import urllib.request


def main():
    """Check existing decisions without writing labels, rejections or media."""
    query="""SELECT coalesce(json_agg(row_to_json(sample)),'[]'::json) FROM (
        SELECT DISTINCT r.face_id,f.path,ref.person FROM rejected_matches r
        JOIN faces f ON f.id=r.face_id JOIN faces ref ON ref.id=r.reference_id
        WHERE ref.person IS NOT NULL ORDER BY r.face_id LIMIT 20) sample"""
    env=dict(os.environ,KUBECONFIG=os.environ.get('KUBECONFIG',str(Path.home()/'kubeconfig')))
    result=subprocess.run(['kubectl','-n','database','exec','postgres-postgresql-0','--','psql','-X','-U','postgres',
        '-d','photo_enrichment','-At','-c',query],env=env,capture_output=True,text=True,timeout=30,check=True)
    rows=json.loads(result.stdout)
    totals=dict(sampled_rejections=len(rows),rejected_explanations=0,other_candidate=0,pending=0,missing=0,violations=0)
    photos={}
    for row in rows:
        if row['path'] not in photos:
            url='https://photos.app.home.panderosystems.com/api/photo?'+urllib.parse.urlencode(dict(path=row['path']))
            with urllib.request.urlopen(url,timeout=30) as response:photos[row['path']]=json.load(response)
        face=next((face for face in photos[row['path']]['faces'] if face['id']==row['face_id']),None)
        if face is None:totals['missing']+=1;continue
        match=face.get('match_details') or {}
        if match.get('reason')=='pending':totals['pending']+=1
        elif match.get('person')!=row['person']:totals['other_candidate']+=1
        elif match.get('reason')=='rejected' and not match.get('qualified'):totals['rejected_explanations']+=1
        else:totals['violations']+=1
    print(json.dumps(totals))
    if totals['violations']:raise SystemExit(1)


if __name__=='__main__':main()
