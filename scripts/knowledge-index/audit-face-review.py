#!/usr/bin/env python3
"""Read-only face-review counts; no identities, photos or embeddings are printed."""
import json
import os
from pathlib import Path
import subprocess
import urllib.request
import urllib.parse

SQL = """SELECT json_build_object('detections',count(*),'unnamed',count(*) FILTER(WHERE person IS NULL),
 'human_confirmed',count(*) FILTER(WHERE label_source='user'),
 'automatic',count(*) FILTER(WHERE label_source='automatic'),
 'confirmed_people',count(DISTINCT person) FILTER(WHERE label_source='user'),
 'models',count(DISTINCT model)) FROM faces;"""
env=dict(os.environ,KUBECONFIG=os.environ.get('KUBECONFIG',str(Path.home()/'kubeconfig')))
subprocess.run(['kubectl','-n','database','exec','postgres-postgresql-0','--','psql','-X','-U','postgres',
                '-d','photo_enrichment','-At','-c',SQL],env=env,check=True,timeout=30)
def get(route, **parameters):
    """Fetch a read-only endpoint without printing personal records."""
    with urllib.request.urlopen('https://photos.app.home.panderosystems.com'+route+'?'+urllib.parse.urlencode(parameters),timeout=30) as response:
        return json.load(response)


for scope,status in [('repeated','unreviewed'),('ungrouped','unreviewed'),('all','named')]:
    data=get('/api/faces',status=status,scope=scope)
    print(json.dumps(dict(scope=scope,status=status,**{key:data.get(key) for key in
        ('counts','total','suggestions_refreshing','grouping_refreshing')},
        page_faces=len(data['faces']),page_with_match_details=sum(bool(f.get('match_details')) for f in data['faces']),
        page_with_score=sum(isinstance(f.get('match_details',{}).get('score'),(int,float)) for f in data['faces']))))
    if scope=='repeated' and data['faces'] and data['faces'][0].get('review_group'):
        first=data['faces'][0]
        group=first['review_group']
        members=get('/api/faces',status='unreviewed',group=group['id'],limit=1)
        selection=get('/api/faces/group-selection',group=group['id'],generation=data['generation'])
        photo=get('/api/photo',path=first['path'])
        print(json.dumps(dict(group_size=group['count'],group_page_total=members['total'],
            selected=selection['total'],unique_selected=len({face['id'] for face in selection['faces']}),
            photo_faces=len(photo['faces']),photo_faces_with_details=sum(bool(face.get('match_details')) for face in photo['faces']))))
