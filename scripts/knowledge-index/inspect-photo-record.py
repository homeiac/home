#!/usr/bin/env python3
"""Inspect saved metadata/labels for a card by date and position; never alter data."""
import argparse
import json
import urllib.parse
import urllib.request


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--date',required=True)
    parser.add_argument('--position',type=int,required=True,help='One-based position in date order')
    parser.add_argument('--timezone',default='America/New_York')
    args=parser.parse_args()
    if args.position<1:parser.error('position must be positive')
    def get(route,**params):
        url='https://photos.app.home.panderosystems.com'+route+'?'+urllib.parse.urlencode(params)
        with urllib.request.urlopen(url,timeout=20) as response:return json.load(response)
    page=get('/api/photos',date=args.date,timezone=args.timezone,offset=args.position-1)
    if not page['photos']:raise SystemExit('No photo at that position')
    photo=get('/api/photo',path=page['photos'][0]['path'])
    print(json.dumps({key:photo.get(key) for key in ('name','summary','summary_model','extraction_version','extraction_error','faces')},default=str,indent=2))


if __name__=='__main__':main()
