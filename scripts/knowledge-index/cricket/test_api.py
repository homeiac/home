"""Real local HTTP tests for playback, correction, and owner boundaries."""

import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from cricket.api import CricketAPI, RangeError, byte_range
from cricket.ledger import Ledger
from cricket.test_ledger import delivery
from photo_enrichment.server import make_server


class APITests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.media = self.root / "clip.mp4"
        self.media.write_bytes(b"0123456789" * 100)
        self.ledger = Ledger(self.root / "ledger.sqlite3")
        for owner in ("one", "two"):
            self.ledger.add_album(owner, "album", "person-a")
            self.ledger.add_asset(
                owner, "album", "clip", "video", 120, "v1", "clip.mp4"
            )
        self.event = self.ledger.create_event("one", "album", "clip", delivery())
        self.other_event = self.ledger.create_event("two", "album", "clip", delivery())
        self.api = CricketAPI(
            self.ledger, "one", self.root, {"person-a": "Test batter"}
        )
        self.store = SimpleNamespace(lock=threading.RLock())
        self.server = make_server(
            self.store, self.root, "127.0.0.1", 0, cricket=self.api
        )
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            kwargs={"poll_interval": 0.01},
            daemon=True,
        )
        self.thread.start()
        self.addCleanup(self.close_server)
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.csrf = self.request("/api/config")[2]["csrf"]

    def test_dashboard_and_event_notes_routes(self) -> None:
        for route, marker in (("/", b"<title>Photo dashboard</title>"),
                              ("/context", b"<title>Event notes"),
                              ("/context.js", b"/api/groups/save"),
                              ("/context.css", b".annotations")):
            with self.subTest(route=route), urlopen(self.base + route) as response:
                self.assertEqual(response.status, 200)
                self.assertIn(marker, response.read())
        with urlopen(self.base + "/") as response:
            body=response.read()
            self.assertNotIn(b"face-workspace", body)
            self.assertIn(b"https://immich.app.home.panderosystems.com", body)

    def close_server(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(
        self, path: str, body: dict | None = None, headers: dict | None = None
    ) -> tuple:
        request_headers = {"Content-Type": "application/json"}
        if body is not None:
            request_headers["X-Photo-Token"] = self.csrf
        request_headers.update(headers or {})
        request = Request(
            self.base + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers=request_headers,
        )
        try:
            response = urlopen(request, timeout=3)
        except HTTPError as exc:
            response = exc
        with response:
            raw = response.read()
            value = (
                json.loads(raw)
                if response.headers.get_content_type() == "application/json"
                else raw
            )
            return response.status, response.headers, value

    def test_list_get_create_correct_and_restart_readback(self) -> None:
        self.assertTrue(self.request("/api/config")[2]["cricket"])
        results = self.request("/api/cricket/search?album=album&filter=four&q=test")[2][
            "results"
        ]
        self.assertEqual([r["event"] for r in results], [self.event])
        self.assertNotIn("owner", results[0])
        self.assertNotIn("path", results[0])
        self.assertEqual(
            self.request("/api/cricket/status?album=album")[2], {"jobs": []}
        )
        self.assertEqual(
            self.request("/api/cricket/people")[2]["people"],
            [{"id": "person-a", "name": "Test batter"}],
        )
        for route in ("/cricket", "/cricket.js", "/cricket.css"):
            self.assertEqual(self.request(route)[0], 200)
        self.assertEqual(
            self.request("/api/cricket/albums")[2]["albums"][0]["id"], "album"
        )
        assets = self.request("/api/cricket/assets?album=album")[2]["assets"]
        self.assertEqual(
            assets,
            [
                {
                    "id": "clip",
                    "kind": "video",
                    "duration": 120,
                    "name": "clip.mp4",
                    "preview": False,
                }
            ],
        )
        event = self.request("/api/cricket/events?album=album")[2]["events"][0]
        self.assertNotIn("owner", event)
        self.assertNotIn("locator", event)
        saved = self.request(
            "/api/cricket/revise",
            {
                "id": event["id"],
                "revision": event["revision"],
                "patch": {"outcome": "six"},
            },
        )
        self.assertEqual(saved[0], 200)
        self.assertEqual(
            Ledger(self.ledger.path).get("one", self.event)["data"]["outcome"], "six"
        )
        self.assertEqual(
            self.request("/api/cricket/event?id=" + self.event)[2]["data"]["outcome"],
            "six",
        )
        new = self.request(
            "/api/cricket/create",
            {"album": "album", "asset": "clip", "data": delivery(start=70, end=110)},
        )
        self.assertEqual(new[0], 200)
        self.assertTrue(new[2]["manual"])
        dismissed = self.request(
            "/api/cricket/revise",
            {"id": new[2]["id"], "revision": new[2]["revision"], "action": "dismiss"},
        )
        self.assertTrue(dismissed[2]["dismissed"])
        self.assertEqual(
            len(
                self.request("/api/cricket/events?album=album&dismissed=true")[2][
                    "events"
                ]
            ),
            2,
        )

    def test_owner_cannot_be_overridden_by_browser(self) -> None:
        events = self.request("/api/cricket/events?album=album&owner=two")[2]["events"]
        self.assertEqual([e["id"] for e in events], [self.event])
        self.assertEqual(
            self.request("/api/cricket/event?id=" + self.other_event)[0], 400
        )
        self.assertEqual(
            self.request(
                "/api/cricket/revise",
                {
                    "id": self.other_event,
                    "owner": "two",
                    "revision": 0,
                    "patch": {"outcome": "six"},
                },
            )[0],
            400,
        )

    def test_conflicts_and_invalid_payloads_are_explicit(self) -> None:
        body = {"id": self.event, "revision": 0, "patch": {"outcome": "six"}}
        self.assertEqual(self.request("/api/cricket/revise", body)[0], 200)
        self.assertEqual(self.request("/api/cricket/revise", body)[0], 409)
        body.update(revision=1, patch={"start": -1})
        self.assertEqual(self.request("/api/cricket/revise", body)[0], 400)
        self.assertEqual(self.request("/api/cricket/absent")[0], 400)
        self.assertEqual(self.request("/api/cricket/absent", {})[0], 400)
        for bad in (
            None,
            [],
            delivery(role=[]),
            delivery(outcome={}),
            delivery(wicket_credit=[]),
        ):
            self.assertEqual(
                self.request(
                    "/api/cricket/create",
                    {"album": "album", "asset": "clip", "data": bad},
                )[0],
                400,
            )

    def test_write_protection_is_shared_with_existing_server(self) -> None:
        body = {"id": self.event, "revision": 0, "patch": {"outcome": "six"}}
        self.assertEqual(
            self.request("/api/cricket/revise", body, {"X-Photo-Token": "invalid"})[0],
            403,
        )
        self.assertEqual(
            self.request(
                "/api/cricket/revise", body, {"Origin": "https://untrusted.example"}
            )[0],
            403,
        )
        self.assertEqual(
            self.request("/api/cricket/albums", headers={"Host": "untrusted.example"})[
                0
            ],
            403,
        )

    def test_video_ranges_stream_and_do_not_need_photo_database_lock(self) -> None:
        path = "/api/cricket/media?album=album&asset=clip"
        self.store.lock.acquire()
        try:
            status, headers, body = self.request(path, headers={"Range": "bytes=10-19"})
        finally:
            self.store.lock.release()
        self.assertEqual((status, body), (206, b"0123456789"))
        self.assertEqual(headers["Content-Range"], "bytes 10-19/1000")
        self.assertEqual(headers["Accept-Ranges"], "bytes")
        self.assertEqual(self.request(path)[2], self.media.read_bytes())
        self.assertEqual(self.request(path, headers={"Range": "bytes=-3"})[2], b"789")
        self.assertEqual(self.request(path, headers={"Range": "bytes=997-"})[2], b"789")
        failed = self.request(path, headers={"Range": "bytes=1000-"})
        self.assertEqual(failed[0], 416)
        self.assertEqual(failed[1]["Content-Range"], "bytes */1000")

    def test_media_paths_and_versions_are_checked(self) -> None:
        for asset, locator in (
            ("escape", "../outside.mp4"),
            ("absolute", str(self.media)),
            ("missing", "absent.mp4"),
            ("empty", ""),
        ):
            self.ledger.add_asset("one", "album", asset, "video", 120, "v1", locator)
            self.assertEqual(
                self.request("/api/cricket/media?album=album&asset=" + asset)[0], 400
            )
        self.ledger.add_asset(
            "one", "album", "changed", "video", 120, "stat:1:1", "clip.mp4"
        )
        self.assertEqual(
            self.request("/api/cricket/media?album=album&asset=changed")[0], 400
        )

    def test_disabled_by_default(self) -> None:
        server = make_server(self.store, self.root, "127.0.0.1", 0)
        thread = threading.Thread(
            target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
        )
        thread.start()
        old_base = self.base
        try:
            self.base = f"http://127.0.0.1:{server.server_port}"
            self.assertEqual(self.request("/api/cricket/albums")[0], 404)
            self.assertEqual(self.request("/cricket")[0], 404)
        finally:
            self.base = old_base
            server.shutdown()
            server.server_close()
            thread.join()

    def test_range_parser_rejects_malformed_empty_and_multiple_ranges(self) -> None:
        for value, size in [
            ("bytes=-0", 100),
            ("bytes=2-1", 100),
            ("bytes=-", 100),
            ("bytes=0-1,2-3", 100),
            ("items=1-2", 100),
            ("bytes=0-", 0),
        ]:
            with self.subTest(value=value), self.assertRaises(RangeError):
                byte_range(value, size)
        self.assertEqual(byte_range("bytes=0-999", 10), (0, 10))


if __name__ == "__main__":
    unittest.main()
