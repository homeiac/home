#!/usr/bin/env python3
"""Inspect aggregate post-rollout progress and lease ages without photo identifiers."""
import subprocess
from distributed import KUBE
code='''import {createRequire} from 'node:module';const {Client}=createRequire('/usr/src/app/server/package.json')('pg');const db=new Client();await db.connect();
for(const [name,sql] of Object.entries({
recent:`SELECT worker,pool,status,count(*)::int jobs,max(completed_at) last_completed FROM waffles.jobs WHERE run_id='historical-waffles' AND (completed_at>now()-interval '4 minutes' OR status IN ('running','classified')) GROUP BY worker,pool,status`,
leases:`SELECT worker,pool,attempts,count(*)::int jobs,min(extract(epoch FROM lease_until-now())) ttl FROM waffles.jobs WHERE status='running' GROUP BY worker,pool,attempts`,
instances:`SELECT worker,pool,ready,draining,device,count(*)::int instances,max(extract(epoch FROM now()-reported_at)) age FROM waffles.instances WHERE reported_at>now()-interval '2 minutes' GROUP BY worker,pool,ready,draining,device`
})){console.log(name,JSON.stringify((await db.query(sql)).rows));}await db.end();'''
subprocess.run(KUBE+['-n','immich-pilot','exec','-i','deployment/waffles-queue','--','node','--input-type=module','-'],input=code,text=True,check=True)
