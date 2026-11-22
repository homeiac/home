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

    def test_timeout_is_skipped_with_hold_and_other_host_can_continue(self):
        grant=r.reserve(self.db,'mac',1);item=grant['items'][0]
        r.handle(self.db,self.root,dict(op='reconcile_start',batch=grant['batch'],id=item['id']))
        r.finish(self.db,dict(id=item['id'],batch=grant['batch'],result=dict(state='unknown',failure='timeout')))
        self.assertEqual(r.extra_cost(self.db),r.RESERVE)
        next_grant=r.reserve(self.db,'still-fawn',2)
        self.assertFalse(next_grant['blocked'])
        self.assertEqual(len(next_grant['items']),1)
        self.assertNotIn(item['id'],[i['id'] for i in next_grant['items']])
        r.recover(self.db)
        self.assertEqual(self.db.execute('SELECT state FROM reconciliations WHERE id=?',[item['id']]).fetchone()[0],'skipped')

    def test_rate_limit_authentication_and_cost_overrun_still_block(self):
        for failure in ('rate_limit','authentication'):
            grant=r.reserve(self.db,'mac',1);item=grant['items'][0]
            r.handle(self.db,self.root,dict(op='reconcile_start',batch=grant['batch'],id=item['id']))
            r.finish(self.db,dict(id=item['id'],batch=grant['batch'],result=dict(state='unknown',failure=failure)))
            self.assertTrue(r.reserve(self.db,'still-fawn',1)['blocked'])
            self.assertEqual(r.skip_unresolved(self.db)['skipped'],0)
            self.assertTrue(r.status(self.db)['blocked'])
            # Test fixture only: make room to exercise the other failure category.
            self.db.execute('DELETE FROM reconciliation_config WHERE key=\'blocked\'')
            self.db.execute('UPDATE reconciliations SET cost=0');self.db.commit()
        grant=r.reserve(self.db,'mac',1);item=grant['items'][0]
        r.handle(self.db,self.root,dict(op='reconcile_start',batch=grant['batch'],id=item['id']))
        r.finish(self.db,dict(id=item['id'],batch=grant['batch'],result=dict(
            state='ok',answer=self.answer(),input=100,cached=0,output=3000000)))
        self.assertTrue(r.status(self.db)['blocked'])
        self.assertFalse(r.skip_unresolved(self.db)['cleared_block'])

    def test_combined_campaign_cap_and_per_runner_limit(self):
        r.configure(self.db,250,{'mac':1,'still-fawn':20},40)
        self.db.execute('UPDATE jobs SET cost=248000000');self.db.commit()
        self.assertEqual(len(r.reserve(self.db,'still-fawn',20)['items']),1)
        self.assertEqual(r.reserve(self.db,'mac',1)['items'],[])

    def test_recovery_releases_only_unsent_and_skips_interrupted_sent(self):
        grant=r.reserve(self.db,'mac',2)
        r.handle(self.db,self.root,dict(op='reconcile_start',batch=grant['batch'],id=grant['items'][0]['id']))
        self.db.execute('UPDATE reconciliations SET started=0 WHERE batch=?',[grant['batch']]);self.db.commit()
        self.assertEqual(r.recover(self.db)['skipped'],1)
        states=dict(self.db.execute('SELECT state,count(*) FROM reconciliations GROUP BY state'))
        self.assertEqual(states,{'pending':4,'skipped':1})
        self.assertFalse(r.status(self.db)['blocked'])

    def test_skip_legacy_unknown_backs_up_audits_and_republishes_without_resubmission(self):
        r.publish_inputs(self.db,self.root)
        grant=r.reserve(self.db,'mac',1);item=grant['items'][0]
        original=r.canonical(dict(state='unknown',failure='response_unavailable'))
        self.db.execute("UPDATE reconciliations SET state='unknown',result=? WHERE id=?",[original,item['id']])
        self.db.execute("INSERT INTO reconciliation_config VALUES ('blocked','response_unavailable')");self.db.commit()
        r.publish(self.db,self.root)
        before=r.extra_cost(self.db)
        result=r.handle(self.db,self.root,dict(op='reconcile_skip_unresolved',expected=1))
        self.assertEqual(result['skipped'],1);self.assertTrue(result['cleared_block'])
        self.assertEqual(r.extra_cost(self.db),before)
        self.assertEqual(self.db.execute('SELECT result FROM reconciliations WHERE id=?',[item['id']]).fetchone()[0],original)
        self.assertEqual(self.db.execute('SELECT count(*) FROM reconciliation_actions').fetchone()[0],1)
        backup=next((self.root/'reconciliation-backups').glob('*.sqlite3'))
        with sqlite3.connect(backup) as old:
            self.assertEqual(old.execute('SELECT state FROM reconciliations WHERE id=?',[item['id']]).fetchone()[0],'unknown')
        with duckdb.connect(str(self.root.parent/'summary-reconciliation/reconciliation.duckdb'),read_only=True) as con:
            self.assertEqual(con.execute('SELECT state,reconciled_summary FROM reconciled_summaries WHERE id=?',[item['id']]).fetchone(),('skipped',None))
            self.assertEqual(con.execute('SELECT count(*),count(DISTINCT id) FROM reconciled_summaries').fetchone(),(5,5))
        self.assertEqual(r.skip_unresolved(self.db)['skipped'],0)
        self.assertNotIn(item['id'],[i['id'] for i in r.reserve(self.db,'still-fawn',1)['items']])

    def test_skipped_invalid_answer_uses_reported_cost_and_finish_replay_is_idempotent(self):
        grant=r.reserve(self.db,'mac',1);item=grant['items'][0]
        r.handle(self.db,self.root,dict(op='reconcile_start',batch=grant['batch'],id=item['id']))
        request=dict(id=item['id'],batch=grant['batch'],result=dict(state='skipped',failure='invalid_answer',
                     input=100,cached=10,output=30,response_text='private malformed output'))
        r.finish(self.db,request);before=r.extra_cost(self.db)
        self.assertLess(before,r.RESERVE)
        self.assertTrue(r.finish(self.db,request)['replayed'])
        self.assertEqual(before,r.extra_cost(self.db));self.assertFalse(r.status(self.db)['blocked'])

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

    def test_metrics_contain_no_private_source_text(self):
        target=self.root/'metrics.prom'
        r.export_metrics(self.db,target)
        text=target.read_text()
        self.assertIn('knowledge_index_reconciliation_jobs{state="pending"} 5',text)
        self.assertNotIn('outdoors',text);self.assertNotIn('.jpg',text)

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

    def test_one_invalid_model_answer_does_not_stop_dispatch_or_retry_that_item(self):
        from concurrent.futures import ThreadPoolExecutor
        calls=[];saved=[]
        def host(**request):
            if request['op']=='reconcile_finish':saved.append(request['result'])
            return {}
        def run(cmd,**kwargs):
            calls.append(cmd)
            answer=self.answer()
            if len(calls)==1:answer['conflicts']=['Unresolved detail']  # inconsistent review flag
            Path(cmd[cmd.index('--output-last-message')+1]).write_text(json.dumps(answer))
            return type('Result',(),{'stdout':'{bad diagnostic line\n'+json.dumps(
                {'type':'turn.completed','usage':{'input_tokens':10,'output_tokens':20}})})()
        items=[dict(id=str(n),inputs=self.records[0]['inputs']) for n in range(3)]
        results=[]
        with patch.object(worker,'host',host),patch.object(worker.subprocess,'run',run),ThreadPoolExecutor(1) as pool:
            self.assertFalse(worker.dispatch(pool,items,'batch',results,1,process_fn=worker.reconcile_process))
        self.assertEqual([v['state'] for v in saved],['skipped','ok','ok'])
        self.assertEqual(saved[0]['failure'],'invalid_answer')
        self.assertEqual(saved[0]['failure_detail'],'Conflicts must be marked for review')
        self.assertIn('response_text',saved[0]);self.assertEqual(saved[0]['input'],10)
        self.assertEqual(len(calls),3)


if __name__=='__main__':unittest.main()
