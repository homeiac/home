#!/usr/bin/env python3
"""Derive separate burst inference from the unchanged, running baseline adapter."""
from pathlib import Path

here=Path(__file__).resolve().parent
source=(here/'distributed-worker.py').read_text()
source=source.replace('    os.chdir(directory)', '''    cores=int(os.environ.get('BURST_CPU_CORES','0'))
    if cores and hasattr(os,'sched_setaffinity'):
        os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[:cores])
    os.chdir(directory)''')
source=source.replace('ready=False, device=',"pool='burst', ready=False, device=")
source=source.replace("{'worker': worker})","{'worker': worker, 'pool': 'burst', 'device': state['device']})")
source=source.replace('    import classifier', '''    # Override the shared selector before any inference modules import it.
    # Model weights, preprocessing and classifier thresholds remain identical.
    import device as compute_device
    forced=os.environ.get('BURST_DEVICE','')
    if forced:
        if forced not in ('cpu','mps'):
            raise ValueError('Unsupported burst compute device')
        if forced=='mps' and compute_device.pick_device()!='mps':
            raise RuntimeError('Requested Metal is unavailable')
        compute_device.pick_device=lambda:forced
    import classifier''')
source=source.replace('    import classifier', '''    # Pinned Ultralytics resets PyTorch threads in select_device(), ignoring
    # OMP_NUM_THREADS. Keep its selector and the CLIP/default pool consistent.
    if worker=='mac' and forced=='cpu':
        import torch
        import ultralytics.utils.torch_utils as yolo_torch
        requested_threads=int(os.environ.get('OMP_NUM_THREADS','2'))
        yolo_torch.NUM_THREADS=requested_threads
        torch.set_num_threads(requested_threads)
        assert torch.get_num_threads()==requested_threads
    import classifier''')
source=source.replace("rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss",'''usage = resource.getrusage(resource.RUSAGE_SELF)
                rss = usage.ru_maxrss
                state['cpu_seconds'] = usage.ru_utime + usage.ru_stime
                state['cpu_affinity'] = len(os.sched_getaffinity(0)) if hasattr(os,'sched_getaffinity') else 0
                torch = sys.modules.get('torch')
                state['cpu_threads'] = torch.get_num_threads() if torch else int(os.environ.get('OMP_NUM_THREADS','2'))
                state['accelerator_bytes'] = torch.mps.driver_allocated_memory() if torch and state.get('device') == 'mps' and state['ready'] else 0''')
source=source.replace("    import numpy as np",'''    from burst_guard import can_run
    if not can_run(starting=True):
        return
    import numpy as np''')
source=source.replace("        logging.info('Worker %s ready on %s', worker, state['device'])",'''        ready_path = Path(os.environ['BURST_READY_DIR']) / state['instance']
        ready_path.parent.mkdir(parents=True, exist_ok=True)
        ready_path.touch()
        logging.info('Burst worker %s ready on %s', worker, state['device'])''')
source=source.replace("                if os.environ.get('NATIVE_CAPACITY_GUARD') == 'true':",'''                if not can_run():
                    state['ready'] = False
                    request('/api/heartbeat', state)
                    logging.info('Burst memory guard: draining extra capacity; baseline remains running')
                    return
                if os.environ.get('NATIVE_CAPACITY_GUARD') == 'true':''')
assert "'pool': 'burst'" in source and 'BURST_READY_DIR' in source
(here/'burst-worker.py').write_text(source)
