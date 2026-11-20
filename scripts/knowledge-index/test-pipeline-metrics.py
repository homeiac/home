#!/usr/bin/env python3
"""Local telemetry tests: python3 scripts/knowledge-index/test-pipeline-metrics.py."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "enrichers"))
from pipeline_metrics import PipelineMetrics, EDGES, TITLES
import media_summary


class PipelineTests(unittest.TestCase):
    def test_inflight_time_is_counted_once_and_errors_are_timed(self):
        m = PipelineMetrics(None, "e1")
        with patch("pipeline_metrics.time.monotonic", side_effect=[10, 12, 15]):
            with self.assertRaises(ValueError):
                with m.measure("decode", "photo"):
                    during = m.render()
                    self.assertIn('stage="decode",title="Read / decode"} 2.0', during)
                    self.assertEqual(m.operations["decode", "photo"], 0)
                    raise ValueError("bad media")
        self.assertEqual(m.seconds["decode", "photo"], 5)
        self.assertEqual(m.operations["decode", "photo"], 1)
        self.assertIsNone(m.active_since)
        self.assertIn('stage="decode",title="Read / decode"} 5.0', m.render())

    def test_ollama_units_missing_fields_and_bad_values(self):
        m = PipelineMetrics(None, "e1")
        m.ollama({"load_duration": 2_000_000_000, "eval_duration": 500_000_000,
                  "eval_count": 10, "prompt_eval_duration": float("nan"), "total_duration": -1}, "video")
        self.assertEqual(m.ollama_seconds["load", "video"], 2)
        self.assertEqual(m.ollama_seconds["generation", "video"], 0.5)
        self.assertEqual(m.tokens["generation", "video"], 10)
        self.assertNotIn(("prompt", "video"), m.ollama_seconds)
        self.assertNotIn(("total", "video"), m.ollama_observations)
        before = m.render()
        m.ollama({}, "photo")
        self.assertEqual(m.ollama_observations, {("load", "video"): 1, ("generation", "video"): 1})
        self.assertNotIn('phase="prompt"', before)

    def test_atomic_output_escaping_and_terminal_state(self):
        with tempfile.TemporaryDirectory() as td:
            path = str(Path(td) / "pipeline.prom")
            with self.assertRaises(RuntimeError):
                with PipelineMetrics(path, 'e"\\\n1') as m:
                    m.item("photo", "ok")
                    self.assertEqual(m.persisted["photo", "ok"], 0)
                    m.item("photo", "ok", persisted=True)
                    raise RuntimeError("write failed")
            text = Path(path).read_text()
            escaped = json.dumps('e"\\\n1')
            self.assertIn(f'media_pipeline_running{{enricher={escaped}}} 0', text)
            self.assertIn(f'media_pipeline_worker_stage{{enricher={escaped}}} 9', text)
            self.assertIn('kind="photo",status="ok"} 1', text)
            self.assertFalse(Path(path + ".tmp").exists())
            self.assertFalse(m.thread.is_alive())

    def test_background_heartbeat_during_blocking_operation(self):
        import threading
        with tempfile.TemporaryDirectory() as td:
            path = str(Path(td) / "pipeline.prom")
            published = threading.Event()
            with PipelineMetrics(path, "e1", every=0.01) as m:
                original = m.publish

                def observe():
                    original()
                    if threading.current_thread() is m.thread:
                        published.set()

                m.publish = observe
                with m.measure("inference", "video"):
                    self.assertTrue(published.wait(2), "heartbeat stopped while request was in flight")
                    self.assertIn('media_pipeline_worker_stage{enricher="e1"} 5', Path(path).read_text())
            self.assertIn('media_pipeline_running{enricher="e1"} 0', Path(path).read_text())

    def test_telemetry_failure_does_not_abort_work(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertLogs(level="ERROR"):
                with PipelineMetrics(str(Path(td) / "missing" / "pipeline.prom"), "e1") as m:
                    with m.measure("write"):
                        m.item("video", "ok", persisted=True)
            self.assertEqual(m.persisted["video", "ok"], 1)

    def test_disabled_telemetry_never_writes(self):
        with patch("builtins.open", side_effect=AssertionError("unexpected write")):
            with PipelineMetrics(None, "e1") as m:
                with m.measure("queue"):
                    pass
        self.assertIsNone(m.thread)

    def test_failed_batch_write_never_reports_persisted_items(self):
        with tempfile.TemporaryDirectory() as td:
            path = str(Path(td) / "pipeline.prom")
            args = SimpleNamespace(min_free_mib=0, limit=1, batch_size=1, index=td, library=td,
                                   enricher="e1", dry_run=False, prom=path)
            with patch.object(media_summary, "queue", return_value=[{"path": "private.jpg", "ext": "jpg"}]), \
                 patch.object(media_summary, "summarize", return_value={"status": "ok"}), \
                 patch.object(media_summary, "write_batch", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    media_summary.run(args)
            text = Path(path).read_text()
            self.assertIn('media_pipeline_worker_stage{enricher="e1"} 9', text)
            self.assertIn('media_pipeline_persisted_items_total{enricher="e1",kind="photo",status="ok"} 0', text)
            self.assertIn('media_pipeline_stage_operations_total{enricher="e1",kind="batch",stage="write"} 1', text)
            self.assertNotIn("private.jpg", text)

    def test_dashboard_graph_frames_and_layout(self):
        spec = importlib.util.spec_from_file_location("dashboard", HERE / "gen-dashboard.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        dashboard = module.dashboard()
        panels = dashboard["panels"]
        self.assertEqual(len({p["id"] for p in panels}), len(panels))
        graph = next(p for p in panels if p["type"] == "nodeGraph")
        self.assertEqual({t["refId"] for t in graph["targets"]}, {"nodes", "edges"})
        self.assertTrue(all(t["format"] == "table" and t["instant"] for t in graph["targets"]))
        self.assertEqual(graph["transformations"][0]["id"], "calculateField")
        self.assertEqual(graph["transformations"][0]["options"]["alias"], "mainstat")
        self.assertTrue(all(s in TITLES and t in TITLES for s, t in EDGES))
        # Both instrumented branches sit directly after Value delivered, before inventory.
        start = next(p["gridPos"]["y"] for p in panels if p["title"] == "Pipeline bottlenecks")
        end = next(p["gridPos"]["y"] for p in panels if p["title"] == "Backfill progress")
        self.assertEqual(end - start, 99)  # Includes the existing queue/snapshot and Frigate rows.
        self.assertEqual(start, 16)
        self.assertIn("immich_queue_jobs", graph["targets"][0]["expr"])
        self.assertIn("immich_thumbnail_generation", graph["targets"][1]["expr"])
        self.assertIn("photo_enrichment_stage_seconds_total", graph["targets"][0]["expr"])
        self.assertIn("photo_enrichment_edge_info", graph["targets"][1]["expr"])
        self.assertEqual(graph["options"]["nodes"]["mainStatUnit"], "")
        self.assertIn("photo_frigate_processing_milliseconds", graph["targets"][0]["expr"])
        self.assertIn("photo_frigate_last_poll_timestamp_seconds", graph["targets"][0]["expr"])
        new = [p for p in panels if start <= p["gridPos"]["y"] < end]
        for i, a in enumerate(new):
            ag = a["gridPos"]
            self.assertLessEqual(ag["y"] + ag["h"], end)
            for b in new[i + 1:]:
                bg = b["gridPos"]
                overlaps = (ag["x"] < bg["x"] + bg["w"] and bg["x"] < ag["x"] + ag["w"]
                            and ag["y"] < bg["y"] + bg["h"] and bg["y"] < ag["y"] + ag["h"])
                self.assertFalse(overlaps, (a["title"], b["title"]))


if __name__ == "__main__":
    unittest.main()
