#!/usr/bin/env python3
"""Local telemetry tests: python3 scripts/knowledge-index/test-pipeline-metrics.py."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "enrichers"))
from pipeline_metrics import PipelineMetrics, MediaCacheProbe, EDGES, TITLES
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
        self.assertFalse(m.active)
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

    def test_parallel_stages_and_durable_backlog(self):
        barrier = threading.Barrier(3, timeout=5)
        with PipelineMetrics(None, "e1") as metrics:
            def measure_request():
                with metrics.measure("inference", "photo"):
                    barrier.wait()
                    barrier.wait()

            workers = [threading.Thread(target=measure_request) for _ in range(2)]
            for worker in workers:
                worker.start()
            try:
                barrier.wait()
                self.assertIn('media_pipeline_in_flight{enricher="e1",kind="photo",stage="inference"} 2',
                              metrics.render())
            finally:
                barrier.wait()
                for worker in workers:
                    worker.join()
            self.assertEqual(metrics.operations["inference", "photo"], 2)
            metrics.queue_size(5)
            metrics.item("photo", "ok")
            metrics.item("video", "error", persisted=True)
            self.assertIn('media_pipeline_queue{enricher="e1"} 5', metrics.render())
            metrics.item("photo", "ok", persisted=True)
            self.assertIn('media_pipeline_queue{enricher="e1"} 4', metrics.render())

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
                                   enricher="e1", dry_run=False, prom=path, parallel=1)
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

    def test_mac_cache_requires_delivery_and_evicts_by_bytes(self):
        cache = MediaCacheProbe(10)
        frames = [(b"a", 7), (b"b", 3)]
        cache.observe(frames)
        self.assertEqual(cache.reusable, 0)
        cache.delivered(frames)
        cache.observe([frames[0]])
        self.assertEqual(cache.reusable, 12)
        cache.delivered([(b"c", 2)])
        self.assertEqual(list(cache.entries), [b"a", b"c"])
        cache.delivered([(b"huge", 11)])
        self.assertEqual(cache.used, 9)
        m = PipelineMetrics(None, "e")
        request = m.mac_request([b"frame"])
        self.assertEqual(m.mac_bytes, 8)
        m.mac_response(request, "photo", 4, {"timings": {"prompt_ms": 300, "predicted_ms": 2000}})
        m.mac_request([b"frame"])
        self.assertTrue(all(c.reusable == 8 for c in m.mac_cache.values()))
        self.assertEqual(m.mac_seconds["prompt", "photo"], 0.3)

    def test_mac_failure_retries_only_unfinished_work_on_primary(self):
        # Arrange for the last Mac request to fail after the RTX pool drained.
        primary_drained = threading.Event()
        primary_calls = []
        def primary(row):
            primary_calls.append(row)
            if row == 9:
                primary_drained.set()
            return {"status": "ok"}
        def metal(row):
            self.assertTrue(primary_drained.wait(5))
            return {"status": "error", "_model_failure": True}
        results = list(media_summary.split_batch(range(10), 2, 1, primary, metal))
        self.assertEqual(sorted(row for row, _ in results), list(range(10)))
        self.assertEqual(sorted(primary_calls), list(range(10)))
        self.assertTrue(all(result["status"] == "ok" for _, result in results))

    def test_shared_queue_saves_each_item_once_and_keeps_decode_errors(self):
        for mac_slots in (0, 2):
            def metal(row):
                return {"status": "error", "inference_backend": "metal"}
            def primary(row):
                return {"status": "ok", "inference_backend": "primary"}
            results = list(media_summary.split_batch(range(19), 2, mac_slots, primary, metal))
            self.assertEqual(sorted(row for row, _ in results), list(range(19)))
            self.assertEqual(any(result["status"] == "error" for _, result in results), bool(mac_slots))

    def test_refill_keeps_rtx_busy_and_mac_prefers_photos(self):
        rtx_refilled = threading.Event()
        pages = iter([[{"path": "next", "ext": "jpg"}], []])

        def primary(row):
            if row["path"] == "next":
                rtx_refilled.set()
            return {"status": "ok", "backend": "RTX"}

        def metal(row):
            self.assertEqual(row["path"], "photo")
            self.assertTrue(rtx_refilled.wait(5))
            return {"status": "ok", "backend": "Mac"}

        rows = [{"path": "video1", "ext": "mp4"}, {"path": "video2", "ext": "mov"},
                {"path": "photo", "ext": "jpg"}]
        results = media_summary.split_batch(rows, 1, 1, primary, metal, refill=lambda: next(pages))
        self.assertEqual({row["path"]: result["backend"] for row, result in results},
                         {"video1": "RTX", "video2": "RTX", "photo": "Mac", "next": "RTX"})

    @patch.object(media_summary, "mac_headers", return_value={})
    def test_mac_sleep_and_mismatched_model_fall_back(self, headers):
        import io
        args = SimpleNamespace(mac_assist=True, model="bonsai-27b", dry_run=False)
        with patch("urllib.request.urlopen", side_effect=ConnectionRefusedError):
            self.assertEqual(media_summary.mac_route(args), (0, None))
        for model, slots, wanted in (("unrelated", 8, 0), ("bonsai-27b-metal", 27, 0), ("bonsai-27b-metal", 8, 8)):
            props = io.BytesIO(json.dumps({"data": [{"id": model, "tags": [f"backfill-parallel={slots}"]}]}).encode())
            with patch("urllib.request.urlopen", return_value=props):
                self.assertEqual(media_summary.mac_route(args)[0], wanted)

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
        value_start = next(p["gridPos"]["y"] for p in panels if p["title"] == "Value delivered")
        self.assertEqual(start - value_start, 16)
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
