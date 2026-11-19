#!/usr/bin/env python3
"""Publish live Frigate processing metrics for the knowledge-index value stream map (#217)."""
import argparse
import json
import logging
import math
import os
from pathlib import Path
import time
import urllib.request

HELP = {
    "service_up": "Frigate stats endpoint reachable (not face-classifier readiness)",
    "last_poll_timestamp_seconds": "Last stats poll attempt Unix time",
    "processing_milliseconds": "Frigate-reported rolling mean processing milliseconds; not percentage of summary time",
    "frames_per_second": "Frigate-reported processing frames per second",
    "edge_info": "Frigate service topology, separate from photo caption processing",
}


def collect(url: str) -> str:
    """Read aggregate stats only and preserve missing values as missing."""
    rows = []
    def add(name: str, value: float, **labels) -> None:
        if not isinstance(value, (int,float)) or not math.isfinite(value) or value < 0:
            return
        label = "{" + ",".join(f"{k}={json.dumps(v)}" for k,v in sorted(labels.items())) + "}" if labels else ""
        rows.append(f"photo_frigate_{name}{label} {value}")
    add("last_poll_timestamp_seconds", time.time())
    headers = {}
    if os.environ.get("PHOTO_FRIGATE_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["PHOTO_FRIGATE_TOKEN"]
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    try:
        request = urllib.request.Request(url.rstrip('/')+'/api/stats', headers=headers)
        with urllib.request.build_opener(NoRedirect).open(request, timeout=5) as response:
            data = json.load(response)
        if not isinstance(data,dict) or not isinstance(data.get('detectors'),dict):
            raise ValueError('Unexpected Frigate stats schema')
    except Exception:
        data = None
    add("service_up", int(data is not None), id="frigate_service", title="Frigate API (1=up)")
    if data is not None:
        speeds = [d.get('inference_speed') for d in data.get('detectors',{}).values() if isinstance(d,dict)]
        speeds = [s for s in speeds if isinstance(s,(int,float)) and math.isfinite(s) and s >= 0]
        if speeds:
            add("processing_milliseconds", max(speeds), kind="detector", id="frigate_detector", title="Frigate object detector (ms)")
            add("edge_info", 1, id="frigate-service-detector", source="frigate_service", target="frigate_detector")
        embeddings = data.get('embeddings') or {}
        if not isinstance(embeddings, dict):
            embeddings = {}
        speed = embeddings.get('face_recognition_speed')
        if isinstance(speed,(int,float)) and math.isfinite(speed) and speed >= 0:
            add("processing_milliseconds", speed, kind="faces", id="frigate_faces", title="Frigate face recognition (ms)")
            add("edge_info", 1, id="frigate-service-faces", source="frigate_service", target="frigate_faces")
        for kind, value in (("objects",data.get('detection_fps')), ("faces",embeddings.get('face_recognition_fps'))):
            add("frames_per_second",value,kind=kind)
    return '\n'.join([line for name, help_text in HELP.items() for line in
        (f'# HELP photo_frigate_{name} {help_text}',f'# TYPE photo_frigate_{name} gauge')] + rows)+'\n'


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',default=os.environ.get('PHOTO_FRIGATE_URL','https://frigate.app.home.panderosystems.com'))
    parser.add_argument('--out',type=Path)
    parser.add_argument('--interval',type=float,default=5)
    parser.add_argument('--once',action='store_true')
    args=parser.parse_args()
    while True:
        output=collect(args.url)
        if args.out:
            temporary=args.out.with_suffix('.prom.tmp')
            temporary.write_text(output)
            temporary.chmod(0o644)
            temporary.replace(args.out)
        else:
            logging.info('\n%s',output)
        if args.once:
            return
        time.sleep(max(1,args.interval))


if __name__=='__main__':
    logging.basicConfig(level=logging.INFO,format='%(message)s')
    main()
