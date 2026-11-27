#!/usr/bin/env python3
"""Download a private contact sheet for visual reference selection, never auto-label.

The manifest stays alongside the thumbnails, outside Git. Review the numbered
images against the owner's reference before enrolling any matching asset IDs.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import json
from pathlib import Path
import urllib.request

from PIL import Image, ImageDraw
from immich_client import BASE, api, key

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--query', default='tan dog pointed ears')
parser.add_argument('--size', type=int, default=80)
parser.add_argument('--random', action='store_true', help='Sample potential negatives for visual review')
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
args.output.mkdir(mode=0o700, parents=True, exist_ok=True)
if args.random:
    assets = api('/search/random', 'POST', {'size': args.size, 'type': 'IMAGE'})
else:
    result = api('/search/smart', 'POST', {'query': args.query, 'size': args.size, 'type': 'IMAGE'})
    assets = result['assets']['items']
manifest = [{'index': i, 'id': a['id'], 'date': a.get('localDateTime'), 'owner': a.get('ownerId')} for i, a in enumerate(assets)]
(args.output/'manifest.json').write_text(json.dumps(manifest, indent=2))


def thumbnail(item: dict):
    """Fetch only a thumbnail for this review batch."""
    path = args.output/f'{item["index"]:03d}.jpg'
    request = urllib.request.Request(BASE+'/api/assets/'+item['id']+'/thumbnail?size=thumbnail',
                                     headers={'x-api-key': key()})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read()
        image = Image.open(BytesIO(raw)).convert('RGB')
        image.thumbnail((180, 170))
        image.save(path)
        return item['index'], image
    except Exception:
        return item['index'], None


for start in range(0, len(manifest), 40):
    batch = manifest[start:start+40]
    sheet = Image.new('RGB', (1000, ((len(batch)+4)//5)*200), 'white')
    draw = ImageDraw.Draw(sheet)
    with ThreadPoolExecutor(max_workers=4) as pool:
        for index, image in pool.map(thumbnail, batch):
            x, y = ((index-start)%5)*200, ((index-start)//5)*200
            if image:
                sheet.paste(image, (x+(200-image.width)//2, y))
            draw.text((x+5, y+175), f'{index}: {manifest[index]["date"] or ""}'[:28], fill='black')
    sheet.save(args.output/f'contact-{start:03d}.jpg')
print(f'Saved {len(manifest)} private candidates to {args.output}')
