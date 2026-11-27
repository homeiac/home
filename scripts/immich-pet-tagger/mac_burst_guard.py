"""Mac extras observe warning pressure; critical pressure still drains safely."""
import logging
import subprocess

last_level=None

def can_run(starting=False):
    global last_level
    try:
        level=int(subprocess.check_output(['sysctl','-n','kern.memorystatus_vm_pressure_level'],text=True))
    except Exception:
        logging.warning('Mac pressure probe unavailable; refusing extra capacity')
        return False
    if level!=last_level:
        if level==2:logging.warning('Mac memory pressure warning recorded; extra work continues by operator policy')
        elif level>=4:logging.error('Mac critical memory pressure; draining extra capacity')
        last_level=level
    return level in (1,2)
