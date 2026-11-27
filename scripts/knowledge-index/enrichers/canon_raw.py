"""Read Canon RAW caption inputs on the index host. Never upload a derivative."""
import base64
from functools import lru_cache
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import subprocess
import time

from PIL import Image, ImageOps

EXTERNAL = '/external/gphotos/'


def guest(*command: str) -> str:
    """Use the index host's existing VM guest agent read path."""
    for attempt in range(3):
        result = subprocess.run(['qm', 'guest', 'exec', '105', '--timeout', '60', '--', *command],
                                capture_output=True, check=True, text=True, timeout=70)
        report = json.loads(result.stdout)
        if report.get('exited') and report.get('exitcode') == 0 and not report.get('out-truncated'):
            return report.get('out-data', '')
        transient = any(code in report.get('err-data', '') for code in ('502 Bad Gateway', '503 Service Unavailable'))
        if not transient or attempt == 2:
            raise RuntimeError('Immich guest read failed or was truncated')
        time.sleep(2 ** attempt)


def query(sql: str) -> list:
    rows = guest('/usr/local/bin/k3s', 'kubectl', '-n', 'immich-pilot', 'exec', 'deploy/immich-postgres',
                 '--', 'psql', '-XAt', '-v', 'ON_ERROR_STOP=1', '-U', 'immich', '-d', 'immich', '-c', sql)
    return [json.loads(line) for line in rows.splitlines()]


@lru_cache(maxsize=1)
def unavailable(recheck_period: int) -> list:
    """Refresh reversible Immich exclusions once per five-minute period."""
    return query("""SELECT json_build_object('path',substr(a."originalPath",length('/external/gphotos/')+1),
                                              'size_bytes',e."fileSizeInByte")
        FROM asset a JOIN library l ON l.id=a."libraryId" AND l."ownerId"=a."ownerId"
        JOIN asset_exif e ON e."assetId"=a.id
        LEFT JOIN asset_metadata h ON h."assetId"=a.id AND h.key='home.media-health.v1'
        WHERE l.name='Existing Google Photos' AND a."isExternal" AND a."originalPath" LIKE '/external/gphotos/%'
          AND lower(right(a."originalPath",4))='.cr2'
        GROUP BY a."originalPath",e."fileSizeInByte"
        HAVING bool_and(a."deletedAt" IS NOT NULL OR a."isOffline" OR
                        coalesce(h.value->>'excludeFromProcessing','false')='true')""")


def lookup(path: str, size: int) -> dict:
    """Match the exact external path and owner of the configured library."""
    relative = PurePosixPath(path)
    if relative.is_absolute() or '..' in relative.parts or relative.suffix.lower() != '.cr2':
        raise ValueError('Invalid external CR2 path')
    # Only hex enters the query. Takeout paths may contain quotes or newlines.
    encoded = (EXTERNAL + path).encode().hex()
    sql = f"""
      SELECT json_build_object('id',a.id,'size',e."fileSizeInByte",'native',e.description,
        'unavailable',a."deletedAt" IS NOT NULL OR a."isOffline" OR a.type<>'IMAGE',
        'excluded',h.value->>'excludeFromProcessing','packet',json_build_object(
          'summary',m.value->>'summary','summaryModel',m.value->>'summaryModel',
          'contentSha256',m.value->>'contentSha256','tags',m.value->'tags'),
        'preview',f.path)
      FROM asset a JOIN library l ON l.id=a."libraryId" AND l."ownerId"=a."ownerId"
      LEFT JOIN asset_exif e ON e."assetId"=a.id
      LEFT JOIN asset_metadata m ON m."assetId"=a.id AND m.key='home.knowledge-index.v1'
      LEFT JOIN asset_metadata h ON h."assetId"=a.id AND h.key='home.media-health.v1'
      LEFT JOIN asset_file f ON f."assetId"=a.id AND f.type='preview'
      WHERE l.name='Existing Google Photos' AND a."isExternal"
        AND a."originalPath"=convert_from(decode('{encoded}','hex'),'UTF8')"""
    rows = query(sql)
    if not rows:
        return {}
    active = [asset for asset in rows if not asset['unavailable'] and asset['excluded'] != 'true']
    if not active:
        return {'skip': 'Immich asset is trashed, offline or excluded'}
    if len(active) != 1 or active[0]['size'] != size:
        raise ValueError('Immich RAW mapping is ambiguous or its original size changed')
    asset = active[0]
    return asset


def original_path(library: str, path: str, size: int) -> Path:
    """Verify that the source still resolves inside the same library."""
    root = Path(library).resolve(strict=True)
    original = (root / path).resolve(strict=True)
    if not original.is_relative_to(root) or original.stat().st_size != size:
        raise ValueError('RAW original changed since import')
    return original


def sha256(original: Path) -> str:
    with original.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def album_copies(index: str, library: str, cache) -> list:
    """Only omit album paths when a current year-folder original has identical bytes."""
    import duckdb
    with duckdb.connect(str(Path(index) / 'knowledge.duckdb'), read_only=True) as con:
        rows = con.execute("""SELECT a.path, y.path, a.size_bytes
            FROM gphotos_album_dup a JOIN gphotos_media y
            ON y.album IS NULL AND y.name=a.name AND y.size_bytes=a.size_bytes
            WHERE lower(a.ext)='cr2'""").fetchall()
    duplicates = {}
    fingerprint = cache.file_digest if cache is not None else sha256
    for album, annual, size in rows:
        if album in duplicates:
            continue
        try:
            first = original_path(library, album, size)
            second = original_path(library, annual, size)
            if fingerprint(first) == fingerprint(second):
                duplicates[album] = {'path': album, 'size_bytes': size}
        except (FileNotFoundError, PermissionError, ValueError):
            continue
    return list(duplicates.values())


def match_catalog(index: str, library: str, row: dict, enricher: str, fingerprint: str) -> tuple | None:
    """Reuse a machine caption only after the candidate original matches byte-for-byte."""
    import duckdb
    with duckdb.connect(str(Path(index) / 'knowledge.duckdb'), read_only=True) as con:
        candidates = con.execute("""SELECT path, summary, tags, model FROM media_summaries
            WHERE source='gphotos' AND size_bytes=? AND enricher=? AND path<>?
              AND status='ok' AND length(trim(summary))>0 AND model<>'immich-description'
            ORDER BY path""", [row['size_bytes'], enricher, row['path']]).fetchall()
    for path, summary, tags, model in candidates:
        try:
            candidate = original_path(library, path, row['size_bytes'])
            if sha256(candidate) == fingerprint:
                return summary, tags or [], model
        except (OSError, ValueError):
            continue
    return None


def saved_caption(asset: dict, original: Path, fingerprint: str | None = None) -> tuple | None:
    """Prefer user text and validate any saved model caption against original bytes."""
    native = (asset.get('native') or '').strip()
    packet = asset.get('packet') or {}
    summary = (packet.get('summary') or '').strip()
    if native and native != summary:
        return native, [], 'immich-description'
    if not summary:
        return None
    digest = packet.get('contentSha256')
    if digest:
        if (fingerprint or sha256(original)) != digest:
            raise ValueError('Saved caption belongs to different RAW bytes')
    return summary, packet.get('tags') or [], packet.get('summaryModel') or 'immich-description'


def jpeg(image: Image.Image, edge: int) -> bytes:
    """Return an oriented, bounded RGB JPEG in memory."""
    frame = ImageOps.exif_transpose(image)
    frame.thumbnail((edge, edge), Image.Resampling.LANCZOS)
    result = io.BytesIO()
    frame.convert('RGB').save(result, format='JPEG', quality=88)
    return result.getvalue()


def preview_bytes(path: str) -> bytes:
    """Read the actual Immich preview, bounded before the guest-agent transfer."""
    location = PurePosixPath(path)
    if not location.is_relative_to('/data/thumbs') or '..' in location.parts:
        raise ValueError('Unexpected Immich preview location')
    # The deployment mounts this VM directory at /data. Resolve again inside the VM
    # and stream bounded chunks so large previews survive guest-agent output limits.
    program = """import base64,json,os,sys
from pathlib import Path
root=Path('/var/lib/immich-pilot/library/thumbs').resolve(strict=True)
path=(root / sys.argv[1]).resolve(strict=True)
if not path.is_relative_to(root): raise ValueError('outside preview directory')
with path.open('rb') as f:
    stat=os.fstat(f.fileno())
    if not 0 < stat.st_size <= 32*1024*1024: raise ValueError('invalid preview size')
    f.seek(int(sys.argv[2]))
    print(json.dumps([stat.st_size,stat.st_mtime_ns,base64.b64encode(f.read(196608)).decode()]))
"""
    data = bytearray()
    revision = None
    while True:
        size, mtime, chunk = json.loads(guest('python3', '-c', program,
            str(location.relative_to('/data/thumbs')), str(len(data))))
        if revision is not None and revision != (size, mtime):
            raise ValueError('Immich preview changed during read')
        revision = size, mtime
        block = base64.b64decode(chunk, validate=True)
        if not block or len(data) + len(block) > size:
            raise ValueError('Incomplete Immich preview')
        data.extend(block)
        if len(data) == size:
            return bytes(data)


def frame(original: Path, preview: str | None, edge: int = 1024) -> tuple[bytes, str]:
    """Use Immich's rendered image first, then develop the sensor data with LibRaw."""
    if preview:
        try:
            data = preview_bytes(preview)
            with Image.open(io.BytesIO(data)) as image:
                image.load()
                if image.format == 'JPEG' and max(image.size) <= edge:
                    return data, 'immich-preview'
                return jpeg(image, edge), 'immich-preview'
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
            pass
    # Google Takeout can preserve the camera filename on a converted JPEG.
    with original.open('rb') as stream:
        if stream.read(3) == bytes.fromhex('ff d8 ff'):
            stream.seek(0)
            with Image.open(stream) as image:
                return jpeg(image, edge), 'original-jpeg'
    import rawpy
    with rawpy.imread(str(original)) as raw:
        pixels = raw.postprocess(use_camera_wb=True, half_size=True, output_bps=8)
    return jpeg(Image.fromarray(pixels), edge), 'libraw'
