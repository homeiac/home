"""Read-only canary on the index host. Read a private JSON sample of {path,size} on stdin."""
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image
import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'enrichers'))
import canon_raw
import media_summary


def main() -> None:
    """Exercise both decoders, existing-caption reuse and persistence in an isolated index."""
    library = Path('/local-3TB-backup/gphotos/library')
    for item in json.load(sys.stdin):
        original = library / item['path']
        lookup = lambda: canon_raw.lookup(item['path'], item['size'])
        first = lookup()
        assert first['id'] and first['preview'] and canon_raw.saved_caption(first, original)
        width_height = []
        with original.open('rb') as source:
            expected_original = 'original-jpeg' if source.read(3) == bytes.fromhex('ff d8 ff') else 'libraw'
        for preview, expected in [(first['preview'], 'immich-preview'), (None, expected_original)]:
            data, route = canon_raw.frame(original, preview)
            with Image.open(io.BytesIO(data)) as img:
                img.load()
                assert route == expected and img.format == 'JPEG' and 0 < max(img.size) <= 1024
                width_height.append(img.size)
        row = dict(path=item['path'], size_bytes=item['size'], ext='cr2')
        args = SimpleNamespace(model='unused',enricher='cr2-canary')
        with tempfile.TemporaryDirectory() as index, patch.object(media_summary,'ask_model',
                side_effect=AssertionError('existing caption triggered inference')) as model:
            stored = media_summary.summarize(row, str(library), args)
            assert stored['status']=='ok' and stored['inference_backend']=='reuse', stored['error']
            table = media_summary.write_batch([stored],index,args.enricher)
            with duckdb.connect() as con:
                count, summary = con.execute('SELECT count(*),min(summary) FROM read_parquet(?)',[table]).fetchone()
            assert count == 1 and stored['summary'] == summary and model.call_count == 0
        assert lookup() == first
        print('one existing asset, reused caption, zero model calls; preview and', expected_original, width_height, flush=True)


if __name__ == '__main__':
    main()
