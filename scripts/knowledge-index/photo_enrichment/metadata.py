"""Read Takeout and embedded photo metadata without modifying originals."""
import datetime as dt
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageOps

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass  # HEIC produces an explicit per-file error if the optional reader is absent.

VERSION = "exif-v1"
PHOTO_EXTENSIONS = ("jpg", "jpeg", "heic", "png", "gif", "webp")


def contained(root: Path, relative: str) -> Path:
    """Resolve a library path, rejecting traversal and escaping symlinks."""
    root = root.resolve()
    path = (root / relative).resolve()
    if not relative or Path(relative).is_absolute() or not path.is_relative_to(root):
        raise ValueError("Photo path is outside the library")
    return path


def coordinates(lat, lon, altitude=None):
    """Validate a coordinate pair; Takeout's zero/zero sentinel means unknown."""
    try:
        lat, lon = float(lat), float(lon)
        if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180 or (lat == 0 and lon == 0):
            return None
        altitude = float(altitude) if altitude is not None else None
        if altitude is not None and not math.isfinite(altitude):
            altitude = None
        return lat, lon, altitude
    except (ValueError, TypeError, OverflowError):
        return None


def exif_coordinates(gps):
    """GPS direction alone is not a location. Convert signed DMS coordinates."""
    def text(value):
        return value.decode() if isinstance(value, bytes) else value
    def dms(values):
        degrees, minutes, seconds = map(float, values)
        if degrees < 0 or not 0 <= minutes < 60 or not 0 <= seconds < 60:
            raise ValueError("Invalid DMS")
        return degrees + minutes / 60 + seconds / 3600
    try:
        ns, ew = text(gps[1]), text(gps[3])
        if ns not in ("N", "S") or ew not in ("E", "W"):
            return None
        lat = dms(gps[2]) * (-1 if ns == "S" else 1)
        lon = dms(gps[4]) * (-1 if ew == "W" else 1)
        alt = float(gps[6]) if 6 in gps else None
        if alt is not None and gps.get(5) in (1, b"\x01"):
            alt = -alt
        return coordinates(lat, lon, alt)
    except (KeyError, TypeError, ValueError, ZeroDivisionError, OverflowError):
        return None


def capture_time(sidecar, exif, timezone):
    """Keep explicit timestamps; interpret offset-free EXIF in the chosen timezone."""
    try:
        timestamp = float(sidecar["photoTakenTime"]["timestamp"])
        dt.datetime.fromtimestamp(timestamp, dt.timezone.utc)
        if math.isfinite(timestamp):
            return timestamp, "takeout.photoTakenTime"
    except (KeyError, TypeError, ValueError, OverflowError, OSError):
        pass
    value = exif.get(36867) or exif.get(306)
    if value:
        try:
            value = value.decode() if isinstance(value, bytes) else value
            captured = dt.datetime.strptime(value.strip("\x00"), "%Y:%m:%d %H:%M:%S")
            offset = exif.get(36881) or exif.get(36880)
            if offset:
                offset = offset.decode() if isinstance(offset, bytes) else offset
                captured = dt.datetime.fromisoformat(captured.isoformat() + offset.strip("\x00"))
                if captured.tzinfo is None:
                    raise ValueError("Missing offset")
                return captured.timestamp(), "exif.offset"
            return captured.replace(tzinfo=ZoneInfo(timezone)).timestamp(), "exif.assumed:" + timezone
        except (TypeError, ValueError, OverflowError):
            pass
    return None, None


def read_metadata(path: Path, sidecar_path: Path | None, timezone: str) -> dict:
    """Extract provenance-aware metadata; retain errors without guessing values."""
    ZoneInfo(timezone)
    sidecar, exif, gps, errors = {}, {}, {}, []
    if sidecar_path:
        try:
            sidecar = json.loads(sidecar_path.read_text())
            if not isinstance(sidecar, dict):
                raise ValueError("not an object")
        except (OSError, ValueError) as exc:
            sidecar = {}
            errors.append("sidecar: " + type(exc).__name__)
    width = height = None
    try:
        with Image.open(path) as image:
            width, height = image.size
            data = image.getexif()
            exif = dict(data)
            exif.update(data.get_ifd(34665))
            gps = data.get_ifd(34853)
    except (OSError, ValueError, TypeError, SyntaxError) as exc:
        errors.append("embedded: " + type(exc).__name__)
    found, source = None, None
    for key in ("geoData", "geoDataExif"):
        value = sidecar.get(key)
        if isinstance(value, dict):
            found = coordinates(value.get("latitude"), value.get("longitude"), value.get("altitude"))
            if found:
                source = "takeout." + key
                break
    if found is None:
        found = exif_coordinates(gps)
        if found:
            source = "embedded.exif"
    captured, capture_source = capture_time(sidecar, exif, timezone)
    return dict(capture_ts=captured, capture_source=capture_source,
                latitude=found[0] if found else None, longitude=found[1] if found else None,
                altitude=found[2] if found else None, gps_source=source,
                camera_make=str(exif.get(271, "")), camera_model=str(exif.get(272, "")),
                width=width, height=height, error="; ".join(errors) or None, version=VERSION)


def oriented_image(path: Path):
    """Return independent RGB pixels in the same orientation used for face boxes."""
    with Image.open(path) as image:
        return ImageOps.exif_transpose(image).convert("RGB")
