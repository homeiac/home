"""Owner-bound cricket adapter for the existing private photo review server."""

import mimetypes
import re
from dataclasses import dataclass
from pathlib import Path

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

    def __init__(self, ledger: Ledger, owner: str, library: Path) -> None:
        self.ledger = ledger
        self.owner = require_text(owner)
        self.library = library.resolve()

    def get(
        self, route: str, query: dict, range_header: str | None = None
    ) -> dict | FileBody:
        """Serve authorized metadata or a range-capable original file."""
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
                    public_event(row)
                    for row in self.ledger.list_events(
                        self.owner, query["album"], query.get("dismissed") == "true"
                    )
                ]
            }
        if route == "/api/cricket/event":
            return public_event(self.ledger.get(self.owner, query["id"]))
        if route == "/api/cricket/assets":
            with self.ledger.connect() as db:
                rows = db.execute(
                    "SELECT a.id,a.kind,a.duration FROM assets a JOIN members m "
                    "ON a.owner=m.owner AND a.id=m.asset WHERE m.owner=? AND m.album=? ORDER BY a.id",
                    (self.owner, query["album"]),
                )
                return {"assets": [dict(row) for row in rows]}
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
        if route == "/api/cricket/create":
            event = self.ledger.create_event(
                self.owner,
                body["album"],
                body["asset"],
                body["data"],
                manual=True,
                editor=self.owner,
            )
            return public_event(self.ledger.get(self.owner, event))
        if route == "/api/cricket/revise":
            return public_event(
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
