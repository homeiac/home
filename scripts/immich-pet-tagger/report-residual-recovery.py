#!/usr/bin/env python3
"""Report residual recovery results and unresolved assets without private identifiers."""
import subprocess
from distributed import KUBE
code='''import {createRequire} from 'node:module';const {Client}=createRequire('/usr/src/app/server/package.json')('pg');const db=new Client();await db.connect();
const results=(await db.query(`SELECT r.id,r.state,j.status,j.worker,count(*)::int jobs,sum(j.applied)::int assignments,sum(coalesce(jsonb_array_length(j.result->'matches'),0))::int matches FROM waffles.runs r JOIN waffles.jobs j ON r.id=j.run_id WHERE r.id='waffles-motion-recovery-20261127' GROUP BY r.id,j.status,j.worker`)).rows;
const unresolved=(await db.query(`SELECT j.last_error,count(*)::int assets FROM waffles.jobs j WHERE j.run_id='waffles-media-recovery-20261127' AND j.status='failed' AND NOT EXISTS(SELECT 1 FROM waffles.jobs fixed WHERE fixed.run_id='waffles-motion-recovery-20261127' AND fixed.asset_id=j.asset_id AND fixed.status='complete') GROUP BY j.last_error`)).rows;
console.log(JSON.stringify({results,unresolved}));await db.end();'''
subprocess.run(KUBE+['-n','immich-pilot','exec','-i','deployment/waffles-queue','--','node','--input-type=module','-'],input=code,text=True,check=True)
