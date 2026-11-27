#!/usr/bin/env python3
"""Run unchanged upstream detection/embedding/classification with fenced PG jobs.

The coordinator proxies thumbnails and owns all Immich writes. This worker gets
no Immich API credential, does not enroll pets, and never writes face metadata.
"""
import json
import logging
import os
from pathlib import Path
import resource
import sys
import threading
import time
import urllib.request


def main() -> None:
    """Maintain a heartbeat while processing one independently claimed photo."""
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    base = os.environ['QUEUE_URL'].rstrip('/')
    token = Path(os.environ['WORKER_TOKEN_FILE']).read_text().strip()
    worker = os.environ['WORKER_NAME']
    directory = Path(os.environ.get('DATA_DIR', '/data'))
    directory.mkdir(parents=True, exist_ok=True)
    os.chdir(directory)
    # This key authenticates only the restricted thumbnail proxy, not Immich.
    os.environ['IMMICH_URL'] = base + '/immich'
    os.environ['IMMICH_API_KEY'] = token
    os.environ.setdefault('HOME', str(directory))
    os.environ.setdefault('TORCH_HOME', str(directory / '.cache/torch'))
    os.environ.setdefault('HF_HOME', str(directory / '.cache/huggingface'))
    os.environ.setdefault('YOLO_CONFIG_DIR', str(directory / '.ultralytics'))
    sys.path.insert(0, os.environ.get('UPSTREAM_APP', '/app'))
    state = dict(worker=worker, ready=False, device='loading')

    def request(path: str, body=None):
        req = urllib.request.Request(base + path, headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'},
                                     data=None if body is None else json.dumps(body).encode())
        with urllib.request.urlopen(req, timeout=40) as response:
            return json.load(response)

    def heartbeat() -> None:
        while True:
            try:
                rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                request('/api/heartbeat', {**state, 'rss_bytes': rss if sys.platform == 'darwin' else rss * 1024})
            except Exception:
                logging.warning('Queue heartbeat unavailable')
            time.sleep(15)

    threading.Thread(target=heartbeat, daemon=True).start()
    while True:
        try:
            config = request('/api/config')
            break
        except Exception:
            time.sleep(10)
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    import classifier
    import embedder
    import inference
    from device import pick_device
    scaler = StandardScaler()
    for name, value in config['scaler'].items():
        setattr(scaler, name, np.asarray(value) if isinstance(value, list) else value)
    model = LogisticRegression()
    for name, value in config['model'].items():
        setattr(model, name, np.asarray(value) if isinstance(value, list) else value)
    # Prevent per-asset debug logs from exposing IDs in normal pod logs.
    for name in ('embedder', 'detector', 'immich'):
        logging.getLogger(name).setLevel(logging.ERROR)
    with inference.inference_session():
        state.update(ready=True, device=pick_device())
        logging.info('Worker %s ready on %s', worker, state['device'])
        while True:
            job = None
            try:
                job = request('/api/claim', {'worker': worker})
                if not job:
                    time.sleep(2)
                    continue
                # Runs retain their classifier snapshot across future enrollment
                # changes; never classify an old run with a newer global model.
                if job.get('config') and job['config'] != config:
                    config = job['config']
                    for obj, values in [(scaler, config['scaler']), (model, config['model'])]:
                        for name, value in values.items():
                            setattr(obj, name, np.asarray(value) if isinstance(value, list) else value)
                state.update({key: job[key] for key in ('run_id', 'asset_id', 'claim')})
                started = time.monotonic()
                errors = inference.model_error_count()
                image = embedder.fetch_thumbnail(job['asset_id'])
                if image is None:
                    raise RuntimeError('Thumbnail unavailable')
                crops = embedder.crop_animals(image, conf=0.25) or [(None, image)]
                result = dict(size=list(image.size), matches=[], unknown=0, low_confidence=0, out_of_range=0)
                for box, crop in crops:
                    vector = embedder.embed_image(crop)
                    if vector is None or inference.model_error_count() != errors:
                        raise RuntimeError('Model inference failed')
                    name, probability = classifier.classify(vector, config['names'], model, scaler)
                    if name != 'Waffles':
                        result['unknown'] += 1
                    elif box is None or probability < 0.90:
                        result['low_confidence'] += 1
                    else:
                        result['matches'].append({'box': [float(x) for x in box], 'probability': float(probability)})
                result['seconds'] = time.monotonic() - started
                accepted = request('/api/finish', {**{k: job[k] for k in ('run_id', 'asset_id', 'claim')}, 'result': result})
                if not accepted['accepted']:
                    logging.warning('Discarded expired claim result')
            except Exception as exc:
                logging.warning('Job or queue request failed: %s', type(exc).__name__)
                if job:
                    try:
                        request('/api/fail', {k: job[k] for k in ('run_id', 'asset_id', 'claim')})
                    except Exception:
                        pass  # The lease will expire; stale results cannot commit.
                time.sleep(5)
            finally:
                for key in ('run_id', 'asset_id', 'claim'):
                    state.pop(key, None)


if __name__ == '__main__':
    main()
