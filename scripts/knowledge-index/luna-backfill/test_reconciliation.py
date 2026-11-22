"""Synthetic tests for cross-runner fencing, accounting and separate summary columns."""
import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

import duckdb
import reconciliation as r
import worker


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'luna-backfill';self.root.mkdir()
        self.path=self.root/'test.sqlite3'
        self.db=sqlite3.connect(self.path);self.addCleanup(self.db.close)
        self.db.executescript('''CREATE TABLE jobs(cost INTEGER);INSERT INTO jobs VALUES (42000000);
            CREATE TABLE previous_captions(cost INTEGER);
            CREATE TABLE config(key TEXT PRIMARY KEY,value TEXT);INSERT INTO config VALUES ('pilot_cost','1000000');''')
        r.initialize(self.db);r.configure(self.db,2,{'still-fawn':2,'mac':2},2)
        self.records=[dict(path=f'{n}.jpg',size_bytes=n+10,inputs=dict(
            local_summary=dict(text='Two people at a table',model='local',prompt_version='v1'),
            luna_summary=dict(text='People eating outdoors',model='luna',prompt_version='v2'),
            saved_metadata=dict(confirmed_people=[],saved_groups=[]))) for n in range(5)]
        r.seed_records(self.db,self.records,'generation1')

    def answer(self):
        return dict(reconciled_summary='Two people eating at an outdoor table.',
                    conflicts=[],needs_visual_review=False,supported_by=['local_summary','luna_summary'],notes='')

    def settle(self,grant,item):
        r.handle(self.db,self.root,dict(op='reconcile_start',batch=grant['batch'],id=item['id']))
        request=dict(id=item['id'],batch=grant['batch'],result=dict(
            state='ok',answer=self.answer(),input=100,cached=10,output=30))
        r.finish(self.db,request)
        return request

    def test_two_hosts_cannot_claim_same_input_or_exceed_global_slots(self):
        barrier=threading.Barrier(2);claims=[]
        def claim(name):
            with sqlite3.connect(self.path,timeout=10) as db:
                barrier.wait();claims.append(r.reserve(db,name,2))
        threads=[threading.Thread(target=claim,args=(name,)) for name in ('still-fawn','mac')]
        for t in threads:t.start()
        for t in threads:t.join()
        ids=[item['id'] for grant in claims for item in grant['items']]
        self.assertEqual(len(ids),2);self.assertEqual(len(set(ids)),2)
        self.assertEqual(r.extra_cost(self.db),2000000)
        self.assertEqual(r.reserve(self.db,'unauthorized',20)['items'],[])

    def test_repeated_seed_and_result_replay_do_not_duplicate_or_charge_twice(self):
        self.assertEqual(r.seed_records(self.db,self.records,'generation2'),0)
        grant=r.reserve(self.db,'mac',1);item=grant['items'][0]
        request=self.settle(grant,item);cost=r.extra_cost(self.db)
        self.assertTrue(r.finish(self.db,request)['replayed'])
        self.assertEqual(r.extra_cost(self.db),cost)
        with self.assertRaises(ValueError):r.handle(self.db,self.root,dict(op='reconcile_start',batch=grant['batch'],id=item['id']))
        request['batch']='stale'
        with self.assertRaises(ValueError):r.finish(self.db,request)

    def test_unknown_result_keeps_hold_blocks_both_hosts_and_never_requeues(self):
        grant=r.reserve(self.db,'mac',1);item=grant['items'][0]
        r.handle(self.db,self.root,dict(op='reconcile_start',batch=grant['batch'],id=item['id']))
        r.finish(self.db,dict(id=item['id'],batch=grant['batch'],result=dict(state='unknown',failure='timeout')))
        self.assertEqual(r.extra_cost(self.db),r.RESERVE)
        self.assertTrue(r.reserve(self.db,'still-fawn',2)['blocked'])
        r.recover(self.db)
        self.assertEqual(self.db.execute('SELECT state FROM reconciliations WHERE id=?',[item['id']]).fetchone()[0],'unknown')

    def test_combined_campaign_cap_and_per_runner_limit(self):
        r.configure(self.db,250,{'mac':1,'still-fawn':20},40)
        self.db.execute('UPDATE jobs SET cost=248000000');self.db.commit()
        self.assertEqual(len(r.reserve(self.db,'still-fawn',20)['items']),1)
        self.assertEqual(r.reserve(self.db,'mac',1)['items'],[])

    def test_recovery_releases_only_unsent_and_marks_sent_unknown(self):
        grant=r.reserve(self.db,'mac',2)
        r.handle(self.db,self.root,dict(op='reconcile_start',batch=grant['batch'],id=grant['items'][0]['id']))
        self.db.execute('UPDATE reconciliations SET started=0 WHERE batch=?',[grant['batch']]);self.db.commit()
        self.assertEqual(r.recover(self.db)['unknown'],1)
        states=dict(self.db.execute('SELECT state,count(*) FROM reconciliations GROUP BY state'))
        self.assertEqual(states,{'pending':4,'unknown':1})

    def test_parquet_columns_are_separate_incremental_and_hide_old_revisions(self):
        r.publish_inputs(self.db,self.root)
        grant=r.reserve(self.db,'mac',1);item=grant['items'][0];self.settle(grant,item)
        self.assertEqual(r.publish(self.db,self.root)['rows'],1)
        self.assertEqual(r.publish(self.db,self.root)['rows'],0)
        target=self.root.parent/'summary-reconciliation/reconciliation.duckdb'
        with duckdb.connect(str(target),read_only=True) as con:
            row=con.execute("SELECT path,local_summary,luna_summary,reconciled_summary FROM reconciled_summaries WHERE state='ok'").fetchone()
            self.assertEqual(row[1:],('Two people at a table','People eating outdoors',self.answer()['reconciled_summary']))
            self.assertEqual(con.execute('SELECT count(*),count(DISTINCT path) FROM reconciled_summaries').fetchone(),(5,5))
        changed=copy.deepcopy(next(record for record in self.records if record['path']==row[0]))
        changed['inputs']['saved_metadata']['confirmed_people']=['Updated human label']
        self.assertEqual(r.seed_records(self.db,[changed],'generation3'),1)
        r.publish_inputs(self.db,self.root)
        with duckdb.connect(str(target),read_only=True) as con:
            self.assertEqual(con.execute('SELECT reconciled_summary,state FROM reconciled_summaries WHERE path=?',[row[0]]).fetchone(),(None,'pending'))
        batch_files=list((target.parent/'batches').glob('*.parquet'))
        self.assertEqual(len(batch_files),2)
        self.assertTrue(all(p.stat().st_mode & 0o777 == 0o600 for p in batch_files))

    def test_invalid_answers_and_usage_are_not_accepted(self):
        invalid=self.answer();invalid['conflicts']=['Different location']
        with self.assertRaises(ValueError):r.validate_answer(invalid)
        invalid['needs_visual_review']=True;r.validate_answer(invalid)
        for change in ({'supported_by':['imagined']},{'reconciled_summary':''},{'extra':'field'}):
            with self.assertRaises(ValueError):r.validate_answer(dict(self.answer(),**change))
        grant=r.reserve(self.db,'mac',1);item=grant['items'][0]
        r.handle(self.db,self.root,dict(op='reconcile_start',batch=grant['batch'],id=item['id']))
        with self.assertRaises(ValueError):r.finish(self.db,dict(id=item['id'],batch=grant['batch'],
            result=dict(state='ok',answer=self.answer(),input=1,cached=2,output=1)))

    def test_runner_sends_only_text_and_retries_only_persistence(self):
        calls=[];model_calls=[];finish_calls=[]
        def host(**request):
            calls.append(request['op'])
            if request['op']=='reconcile_finish':
                finish_calls.append(request)
                if len(finish_calls)==1:raise RuntimeError('synthetic lost acknowledgment')
            return {}
        def run(cmd,**kwargs):
            model_calls.append((cmd,kwargs))
            Path(cmd[cmd.index('--output-last-message')+1]).write_text(json.dumps(self.answer()))
            return type('Result',(),{'stdout':json.dumps({'type':'turn.completed','usage':{'input_tokens':10,'output_tokens':20}})})()
        with patch.object(worker,'host',host),patch.object(worker.subprocess,'run',run),patch.object(worker.time,'sleep'):
            result=worker.reconcile_process('batch',dict(id='id',inputs=self.records[0]['inputs']),None)
        self.assertEqual(result['state'],'ok');self.assertEqual(len(model_calls),1)
        self.assertEqual(len(finish_calls),2);self.assertEqual(finish_calls[0],finish_calls[1])
        self.assertNotIn('--image',model_calls[0][0]);self.assertIn('TEXT ONLY',model_calls[0][1]['input'])


if __name__=='__main__':unittest.main()
