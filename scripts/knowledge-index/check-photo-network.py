#!/usr/bin/env python3
"""Read-only network attribution: interface deltas, TCP peers and service timeline."""
import os
import argparse
import shlex
import subprocess

REMOTE = r'''
import json,pathlib,subprocess,time,datetime,zoneinfo,re,sys
def run(args):return subprocess.check_output(args,text=True,timeout=20)
def counters():
    return {p.name:{k:int((p/'statistics'/k).read_text()) for k in ('rx_bytes','tx_bytes','rx_errors','tx_errors','rx_dropped','tx_dropped')} for p in pathlib.Path('/sys/class/net').iterdir() if (p/'statistics').is_dir()}
a=counters();time.sleep(5);b=counters()
print('Interface deltas over 5s',json.dumps({dev:{key:round((value-a[dev][key])/5,1) for key,value in values.items()} for dev,values in b.items() if dev in a}))
sockets=run(['ss','-tinpH','state','established']).splitlines()
for i,line in enumerate(sockets):
    if ':5432' in line:
        print('PostgreSQL socket',line.strip(),re.findall(r'(?:bytes_sent|bytes_received):\d+',sockets[i+1]))
units=['photo-enrichment-gui','photo-enrichment-worker','photo-enrichment-export','photo-enrichment-catalog','photo-enrichment-triage','knowledge-index-enrich']
for unit in units:
    print(unit,run(['systemctl','show',unit,'-p','ActiveEnterTimestamp','-p','ExecMainStartTimestamp','-p','NRestarts']))
    records=run(['journalctl','-u',unit,'--since',sys.argv[1],'--no-pager','-o','json'])
    # Only systemd lifecycle events, never application records or photo paths.
    for line in records.splitlines():
        record=json.loads(line)
        if record.get('_COMM')=='systemd' and unit in ('photo-enrichment-gui','photo-enrichment-worker','knowledge-index-enrich','photo-enrichment-catalog'):print(datetime.datetime.fromtimestamp(int(record['__REALTIME_TIMESTAMP'])/1e6,zoneinfo.ZoneInfo('America/Los_Angeles')).isoformat(),record.get('MESSAGE',''))
errors=run(['journalctl','-u','photo-enrichment-catalog','--since',sys.argv[1],'-n','80','--no-pager','-o','cat'])
for line in errors.splitlines():
    if line.startswith(('psycopg.errors.','duckdb.','DETAIL:','HINT:')):print('Catalog error:',line[:300])
print('Link status',run(['ip','-s','link','show','dev','enx803f5df8d628']))
'''

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--since',default='-6 hours')
    args=parser.parse_args()
    subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10',os.environ['CB_HOST'],
        'python3 -c '+shlex.quote(REMOTE)+' '+shlex.quote(args.since)],check=True)
