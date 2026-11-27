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
import signal
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
    cores=int(os.environ.get('BURST_CPU_CORES','0'))
    if cores and hasattr(os,'sched_setaffinity'):
        os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[:cores])
    os.chdir(directory)
    # This key authenticates only the restricted thumbnail proxy, not Immich.
    os.environ['IMMICH_URL'] = base + '/immich'
    os.environ['IMMICH_API_KEY'] = token
    os.environ.setdefault('HOME', str(directory))
    os.environ.setdefault('TORCH_HOME', str(directory / '.cache/torch'))
    os.environ.setdefault('HF_HOME', str(directory / '.cache/huggingface'))
    os.environ.setdefault('YOLO_CONFIG_DIR', str(directory / '.ultralytics'))
    sys.path.insert(0, os.environ.get('UPSTREAM_APP', '/app'))
    state = dict(worker=worker, instance=os.environ.get('WAFFLES_INSTANCE',worker), pool='burst', ready=False, device='loading', draining=False)
    draining = threading.Event()
    def drain(*_):
        state['draining'] = True
        draining.set()
    signal.signal(signal.SIGTERM, drain)
    signal.signal(signal.SIGINT, drain)

    def request(path: str, body=None):
        req = urllib.request.Request(base + path, headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'},
                                     data=None if body is None else json.dumps(body).encode())
        with urllib.request.urlopen(req, timeout=40) as response:
            return json.load(response)

    def heartbeat() -> None:
        while True:
            try:
                usage = resource.getrusage(resource.RUSAGE_SELF)
                rss = usage.ru_maxrss
                state['cpu_seconds'] = usage.ru_utime + usage.ru_stime
                state['cpu_affinity'] = len(os.sched_getaffinity(0)) if hasattr(os,'sched_getaffinity') else 0
                torch = sys.modules.get('torch')
                state['cpu_threads'] = torch.get_num_threads() if torch else int(os.environ.get('OMP_NUM_THREADS','2'))
                state['accelerator_bytes'] = torch.mps.driver_allocated_memory() if torch and state.get('device') == 'mps' and state['ready'] else 0
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
    from burst_guard import can_run
    if not can_run(starting=True):
        return
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    # Override the shared selector before any inference modules import it.
    # Model weights, preprocessing and classifier thresholds remain identical.
    import device as compute_device
    forced=os.environ.get('BURST_DEVICE','')
    if forced:
        if forced not in ('cpu','mps'):
            raise ValueError('Unsupported burst compute device')
        if forced=='mps' and compute_device.pick_device()!='mps':
            raise RuntimeError('Requested Metal is unavailable')
        compute_device.pick_device=lambda:forced
    # Pinned Ultralytics resets PyTorch threads in select_device(), ignoring
    # OMP_NUM_THREADS. Keep its selector and the CLIP/default pool consistent.
    if worker=='mac' and forced=='cpu':
        import torch
        import ultralytics.utils.torch_utils as yolo_torch
        requested_threads=int(os.environ.get('OMP_NUM_THREADS','2'))
        yolo_torch.NUM_THREADS=requested_threads
        torch.set_num_threads(requested_threads)
        assert torch.get_num_threads()==requested_threads
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
        ready_path = Path(os.environ['BURST_READY_DIR']) / state['instance']
        ready_path.parent.mkdir(parents=True, exist_ok=True)
        ready_path.touch()
        logging.info('Burst worker %s ready on %s', worker, state['device'])
        while not draining.is_set():
            job = None
            try:
                if not can_run():
                    state['ready'] = False
                    request('/api/heartbeat', state)
                    logging.info('Burst memory guard: draining extra capacity; baseline remains running')
                    return
                if os.environ.get('NATIVE_CAPACITY_GUARD') == 'true':
                    from native_guard import can_run
                    if not can_run():
                        state['ready'] = False
                        request('/api/heartbeat', state)
                        logging.info('Native capacity guard: unloading models and returning to standby')
                        return
                job = request('/api/claim', {'worker': worker, 'pool': 'burst', 'device': state['device']})
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
        state['ready'] = False
        request('/api/heartbeat', state)


if __name__ == '__main__':
    main()
