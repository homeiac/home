#!/usr/bin/env python3
"""Regression checks for singleton workers, policy reload and safe reconciliation."""
import importlib.util
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'enrichers'))
sys.path.insert(0, str(HERE))
import install
import media_summary
import audit
import duckdb


def bundle() -> dict:
    """Return the same canonical files used by the manifest generator."""
    result = {name: (HERE.parent / 'enrichers' / name).read_text()
              for name in ('media_summary.py', 'pipeline_metrics.py', 'summary_cache.py')}
    result.update({name: (HERE / name).read_text()
                   for name in ('run.py', 'config.json', 'knowledge-index-enrich.service')})
    result['dispatch-policy.json'] = (HERE.parent / 'bonsai-dispatch-policy.json').read_text()
    for name in install.EXPORTER_FILES:
        result[name] = (HERE.parent / name).read_text()
    return result


class GitOpsTests(unittest.TestCase):
    def test_repair_manifest_prioritizes_old_video_without_retrying_inflight(self):
        with tempfile.TemporaryDirectory() as td:
            with duckdb.connect(str(Path(td)/'knowledge.duckdb')) as db:
                db.execute("""CREATE MACRO gphotos_to_summarize(e) AS TABLE
                    SELECT * FROM (VALUES ('new.jpg','jpg',2),('old.mov','mov',1)) t(path,ext,taken_ts)""")
            manifest=Path(td)/'repair.json'
            manifest.write_text(json.dumps([{'path':'old.mov'}]))
            with patch.dict(os.environ, {'KI_SUMMARY_PRIORITY_MANIFEST':str(manifest)}):
                rows=media_summary.queue(td,'e',1,photos_first=True)
                self.assertEqual([r['path'] for r in rows],['old.mov'])
                rows=media_summary.queue(td,'e',1,seen={'old.mov'},photos_first=True)
                self.assertEqual([r['path'] for r in rows],['new.jpg'])

    def test_idle_clean_exit_is_healthy_but_crash_is_not(self):
        for status, expected in [('0', True), ('1', False), ('75', False)]:
            with patch.object(install, 'command', side_effect=[
                    SimpleNamespace(returncode=3),
                    SimpleNamespace(stdout='ActiveState=activating\nSubState=auto-restart\nExecMainStatus=' + status)]):
                self.assertEqual(install.healthy_service(), expected)

    def test_audit_detects_repeated_success_but_allows_retry_of_error(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            output = root / 'summaries/e1'
            output.mkdir(parents=True)
            baseline = root / 'baseline.json'
            con = duckdb.connect()
            con.execute('CREATE TABLE rows(source VARCHAR, path VARCHAR, size_bytes BIGINT, enricher VARCHAR, status VARCHAR)')
            con.execute("INSERT INTO rows VALUES ('gphotos','done',1,'e1','ok'), ('gphotos','retry',1,'e1','error')")
            con.execute('COPY rows TO ? (FORMAT parquet)', [str(output / 'old.parquet')])
            with patch.object(audit, 'INDEX', root), contextlib.redirect_stdout(io.StringIO()):
                with patch.object(sys, 'argv', ['audit', 'snapshot', str(baseline)]):
                    audit.main()
                con.execute("DELETE FROM rows WHERE path = 'done'")
                con.execute("UPDATE rows SET status = 'ok'")
                con.execute('COPY rows TO ? (FORMAT parquet)', [str(output / 'retry.parquet')])
                with patch.object(sys, 'argv', ['audit', 'verify', str(baseline)]):
                    audit.main()
                    con.execute("INSERT INTO rows VALUES ('gphotos','done',1,'e1','ok')")
                    con.execute('COPY rows TO ? (FORMAT parquet)', [str(output / 'duplicate.parquet')])
                    with self.assertRaises(SystemExit):
                        audit.main()

    def test_identity_and_destinations_cannot_change_accidentally(self):
        payload = bundle()
        self.assertEqual(install.validate(payload)['enricher'], 'gemma4-e2b-p1')
        payload['../../elsewhere'] = ''
        with self.assertRaises(ValueError):
            install.validate(payload)
        del payload['../../elsewhere']
        config = json.loads(payload['config.json'])
        config['enricher'] = 'new-identity'
        payload['config.json'] = json.dumps(config)
        with self.assertRaises(ValueError):
            install.validate(payload)

    def test_local_policy_is_hot_reloaded_and_bad_policy_keeps_last_good(self):
        with tempfile.TemporaryDirectory() as td:
            policy = Path(td) / 'policy.json'
            policy.write_text(bundle()['dispatch-policy.json'])
            with patch.dict(os.environ, {'KI_GPU_DISPATCH_POLICY_FILE': str(policy)}):
                p = media_summary.DispatchPolicy(SimpleNamespace(dry_run=False))
                self.assertEqual(p.poll(), ('continuous', 48, 'photo-first'))
                self.assertEqual(p.queue_order, 'photos-first')
                policy.write_text('{broken')
                p.next_poll = 0
                self.assertEqual(p.poll(), ('continuous', 48, 'photo-first'))

    def test_second_worker_cannot_enter_but_lock_releases(self):
        with tempfile.TemporaryDirectory() as td:
            args = ['run', '--index', td, '--library', td, '--endpoint', 'http://unused', '--model', 'stub', '--enricher', 'e1']
            import fcntl
            with open(Path(td) / '.media-summary.lock', 'a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with patch.object(media_summary, 'run') as run:
                    self.assertEqual(media_summary.main(args), 75)
                    run.assert_not_called()
            with patch.object(media_summary, 'run', return_value=0) as run:
                self.assertEqual(media_summary.main(args), 0)
                run.assert_called_once()

    def exercise(self, *, failure=False, policy_only=False, exporter_only=False, disabled=False):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            paths = {name: root / name for name in install.FILES}
            payload = bundle()
            for name, target in paths.items():
                target.write_text(payload[name])
            if exporter_only:
                paths['export-metrics.py'].write_text('# previous exporter\n')
            elif not policy_only:
                paths['run.py'].write_text('# previous version\n')
            else:
                paths['dispatch-policy.json'].write_text('{}')
            if disabled:
                config = json.loads(payload['config.json']); config['enabled'] = False
                payload['config.json'] = json.dumps(config)
            calls = []
            def fake(*args, check=True):
                calls.append(args)
                if failure and args == ('systemctl', 'enable', install.UNIT):
                    raise subprocess.CalledProcessError(1, args)
                return SimpleNamespace(returncode=0)
            with patch.multiple(install, ROOT=root, FILES=paths, METRICS=paths['config.json']), \
                    patch.object(install, 'preflight'), patch.object(install, 'command', side_effect=fake), \
                    patch.object(install.time, 'time', return_value=0):
                if failure:
                    with self.assertRaises(subprocess.CalledProcessError):
                        install.reconcile(payload)
                    self.assertEqual(paths['run.py'].read_text(), '# previous version\n')
                else:
                    install.reconcile(payload)
                    if policy_only or exporter_only:
                        self.assertNotIn(('systemctl', 'stop', install.UNIT), calls)
                    calls.clear()
                    result = install.reconcile(payload)
                    self.assertEqual(result['changed_files'], [])
                    self.assertFalse(result['restarted'])
                    self.assertNotIn(('systemctl', 'stop', install.UNIT), calls if not disabled else [])
                return calls

    def test_repeat_reconcile_does_not_restart_healthy_worker(self):
        self.exercise()

    def test_policy_only_change_does_not_restart(self):
        calls = self.exercise(policy_only=True)
        self.assertNotIn(('systemctl', 'stop', install.UNIT), calls)

    def test_exporter_only_change_does_not_restart_caption_worker(self):
        self.exercise(exporter_only=True)

    def test_previous_bundle_is_accepted_during_bootstrap(self):
        payload = bundle()
        for name in install.EXPORTER_FILES:
            del payload[name]
        install.validate(payload)

    def test_failed_rollout_restores_previous_code(self):
        self.exercise(failure=True)

    def test_disabled_policy_stops_and_disables_worker(self):
        calls = self.exercise(disabled=True)
        self.assertIn(('systemctl', 'disable', '--now', install.UNIT), calls)


if __name__ == '__main__':
    unittest.main()
