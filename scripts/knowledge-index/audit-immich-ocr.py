#!/usr/bin/env python3
"""Read-only database audit of completed and missing OCR after queue recovery."""
import os
from pathlib import Path
import subprocess

SQL = '''
BEGIN READ ONLY;
SELECT count(*) AS eligible, count(s."ocrAt") AS completed,
       count(*) FILTER (WHERE s."ocrAt" IS NULL) AS missing,
       count(*) FILTER (WHERE s."ocrAt" >= now() - interval '15 minutes') AS completed_last_15_minutes
FROM asset a JOIN asset_job_status s ON s."assetId"=a.id
WHERE a."deletedAt" IS NULL AND a.visibility != 'hidden';
SELECT a.id, a.type, a."originalFileName", a."isOffline",
       array_agg(f.type) AS available_files
FROM asset a JOIN asset_job_status s ON s."assetId"=a.id
LEFT JOIN asset_file f ON f."assetId"=a.id
WHERE a."deletedAt" IS NULL AND a.visibility != 'hidden' AND s."ocrAt" IS NULL
GROUP BY a.id ORDER BY a.id LIMIT 20;
ROLLBACK;
'''
subprocess.run(['kubectl','--kubeconfig',os.environ.get('KUBECONFIG',str(Path.home()/'kubeconfig')),
    '-n','immich-pilot','exec','-i','deployment/immich-postgres','--','psql','-X',
    '-v','ON_ERROR_STOP=1','-U','immich','-d','immich'],input=SQL,text=True,check=True)
