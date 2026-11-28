"""Owner-bound cricket adapter for the existing private photo review server."""

import mimetypes
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode

from .ledger import Ledger, require_text


class RangeError(ValueError):
    """A request cannot be satisfied by the original file."""

    def __init__(self, size: int) -> None:
        super().__init__("Requested byte range is not satisfiable")
        self.size = size


@dataclass(frozen=True)
class FileBody:
    """A bounded streaming response; file bytes are never loaded into the DB lock."""

    path: Path
    start: int
    length: int
    size: int
    partial: bool
    content_type: str


def byte_range(value: str | None, size: int) -> tuple[int, int]:
    """Interpret a single HTTP bytes range, including suffix and open-ended forms."""
    if not value:
        return 0, size
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", value)
    if not match or not any(match.groups()) or size <= 0:
        raise RangeError(size)
    left, right = match.groups()
    if left:
        start = int(left)
        end = min(int(right), size - 1) if right else size - 1
    else:
        start, end = max(0, size - int(right)), size - 1
    if start < 0 or start >= size or end < start:
        raise RangeError(size)
    return start, end - start + 1


def public_event(event: dict) -> dict:
    """Do not expose private source locators or internal audit records to the UI."""
    return {
        key: event[key]
        for key in (
            "id",
            "album",
            "asset",
            "revision",
            "dismissed",
            "review_state",
            "manual",
            "data",
            "evidence",
            "proposal_version",
        )
    }


class CricketAPI:
    """One configured owner's view; identity never comes from request parameters."""

    def __init__(
        self, ledger: Ledger, owner: str, library: Path, people: dict | None = None
    ) -> None:
        self.ledger = ledger
        self.owner = require_text(owner)
        self.library = library.resolve()
        self.people = people or {}
        for identifier, name in self.people.items():
            require_text(identifier)
            require_text(name)

    def event_view(self, event: dict) -> dict:
        """Refresh native face metadata without rewriting reviewed event identities."""
        from .face_context import load, subject

        result = public_event(event)
        registry = load(
            self.ledger.path.parent / "evidence",
            {
                "id": event["asset"],
                "owner": self.owner,
                "fingerprint": event["fingerprint"],
            },
        )
        if registry:
            evidence = dict(result["evidence"])
            start, end = result["data"]["start"], result["data"]["end"]
            frames = [
                f
                for f in registry["frames"]
                if start is None
                or f["timestamp"] is not None
                and start <= f["timestamp"] <= end
            ]
            evidence["immich_faces"] = frames
            evidence["face_scan"] = {
                "complete": registry.get("detection_complete", False),
                "frames": len(registry["frames"]),
                "expected": registry.get("expected_frames"),
                "pending": sum(f["state"] != "detected" for f in registry["frames"]),
            }
            evidence["subject_face"] = subject(evidence.get("subject_location"), frames)
            if registry.get("identity_context"):
                evidence["identity_context"] = registry["identity_context"]
            result["evidence"] = evidence
        return result

    def get(
        self, route: str, query: dict, range_header: str | None = None
    ) -> dict | FileBody:
        """Serve authorized metadata or a range-capable original file."""
        if route == "/api/cricket/people":
            return {
                "people": [
                    {"id": identifier, "name": name}
                    for identifier, name in self.people.items()
                ]
            }
        if route == "/api/cricket/albums":
            with self.ledger.connect() as db:
                return {
                    "albums": [
                        dict(row)
                        for row in db.execute(
                            "SELECT id,default_batter,rule_revision FROM albums WHERE owner=? ORDER BY id",
                            (self.owner,),
                        )
                    ]
                }
        if route == "/api/cricket/events":
            return {
                "events": [
                    self.event_view(row)
                    for row in self.ledger.list_events(
                        self.owner, query["album"], query.get("dismissed") == "true"
                    )
                ]
            }
        if route == "/api/cricket/search":
            from .search import search

            results = search(
                self.ledger,
                self.people,
                self.owner,
                query["album"],
                query.get("q", ""),
                query.get("filter", "all"),
            )
            return {
                "results": [
                    {k: v for k, v in r.items() if k not in {"owner", "path"}}
                    for r in results
                ]
            }
        if route == "/api/cricket/status":
            with self.ledger.connect() as db:
                latest = db.execute(
                    "SELECT j.version FROM jobs j JOIN members m ON m.owner=j.owner AND m.asset=j.asset WHERE m.owner=? AND m.album=? ORDER BY j.rowid DESC LIMIT 1",
                    (self.owner, query["album"]),
                ).fetchone()
                jobs = [
                    dict(r)
                    for r in db.execute(
                        "SELECT a.kind,j.state,count(*) AS assets FROM jobs j JOIN assets a ON a.owner=j.owner AND a.id=j.asset JOIN members m ON m.owner=a.owner AND m.asset=a.id WHERE m.owner=? AND m.album=? AND j.version=? GROUP BY a.kind,j.state",
                        (
                            self.owner,
                            query["album"],
                            query.get("version")
                            or (latest[0] if latest else "cricket-v1"),
                        ),
                    )
                ]
            return {"jobs": jobs}
        if route == "/api/cricket/event":
            return self.event_view(self.ledger.get(self.owner, query["id"]))
        if route == "/api/cricket/export":
            from .exports import target

            event = self.ledger.get(self.owner, query["id"])
            if event["revision"] != int(query["revision"]):
                raise ValueError("Highlight changed; export the current revision")
            self.get(
                "/api/cricket/media", {"album": event["album"], "asset": event["asset"]}
            )
            path = target(event, self.ledger.path.parent / "exports")
            if not path.is_file():
                raise FileNotFoundError("Export is not ready")
            size = path.stat().st_size
            start, length = byte_range(range_header, size)
            return FileBody(path, start, length, size, bool(range_header), "video/mp4")
        if route == "/api/cricket/assets":
            with self.ledger.connect() as db:
                rows = db.execute(
                    "SELECT a.id,a.kind,a.duration,a.locator FROM assets a JOIN members m "
                    "ON a.owner=m.owner AND a.id=m.asset WHERE m.owner=? AND m.album=? ORDER BY a.id",
                    (self.owner, query["album"]),
                )
                return {
                    "assets": [
                        {
                            "id": row["id"],
                            "kind": row["kind"],
                            "duration": row["duration"],
                            "name": Path(row["locator"]).name,
                            "preview": (
                                self.ledger.path.parent
                                / "evidence"
                                / (row["id"] + ".jpg")
                            ).is_file(),
                        }
                        for row in rows
                    ]
                }
        if route == "/api/cricket/media":
            with self.ledger.connect() as db:
                asset = self.ledger._asset(
                    db, self.owner, query["album"], query["asset"]
                )
            locator = Path(asset["locator"])
            path = (self.library / locator).resolve()
            if (
                not asset["locator"]
                or locator.is_absolute()
                or not path.is_relative_to(self.library)
            ):
                raise ValueError("Original is outside the configured library")
            if not path.is_file():
                raise FileNotFoundError("Original is not available")
            stat = path.stat()
            # Inventory uses this format; older synthetic fingerprints remain usable in tests.
            if (
                asset["fingerprint"].startswith("stat:")
                and asset["fingerprint"] != f"stat:{stat.st_size}:{stat.st_mtime_ns}"
            ):
                raise ValueError("Original changed; refresh inventory before playback")
            if query.get("preview") == "true":
                previews = (self.ledger.path.parent / "evidence").resolve()
                preview = (previews / (asset["id"] + ".jpg")).resolve()
                if not preview.is_relative_to(previews):
                    raise ValueError("Invalid preview path")
                if preview.is_file():
                    size = preview.stat().st_size
                    return FileBody(preview, 0, size, size, False, "image/jpeg")
            start, length = byte_range(range_header, stat.st_size)
            content_type = (
                mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            )
            return FileBody(
                path, start, length, stat.st_size, bool(range_header), content_type
            )
        raise KeyError("Cricket route not found")

    def post(self, route: str, body: dict) -> dict:
        """Persist a correction using the owner fixed at server startup."""
        if route == "/api/cricket/export":
            from .exports import create
            from .ledger import Conflict

            event = self.ledger.get(self.owner, body["id"])
            if event["revision"] != body["revision"]:
                raise Conflict("Highlight changed; refresh before exporting")
            original = self.get(
                "/api/cricket/media", {"album": event["album"], "asset": event["asset"]}
            )
            create(event, original.path, self.ledger.path.parent / "exports")
            return {
                "url": "/api/cricket/export?"
                + urlencode({"id": event["id"], "revision": event["revision"]})
            }
        if route == "/api/cricket/create":
            event = self.ledger.create_event(
                self.owner,
                body["album"],
                body["asset"],
                body["data"],
                manual=True,
                editor=self.owner,
            )
            return self.event_view(self.ledger.get(self.owner, event))
        if route == "/api/cricket/revise":
            return self.event_view(
                self.ledger.revise(
                    self.owner,
                    body["id"],
                    body["revision"],
                    patch=body.get("patch"),
                    action=body.get("action", "edit"),
                    editor=self.owner,
                )
            )
        raise KeyError("Cricket route not found")
