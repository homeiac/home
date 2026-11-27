"""Keep native inference off memory-constrained or hot Proxmox hosts."""
import os
from pathlib import Path
import sys


def permitted(available_mib: float, temperature: float, starting: bool) -> bool:
    """Use separate startup/running thresholds to avoid immediate restart loops."""
    return available_mib >= (1800 if starting else 512) and temperature < (65 if starting else 68)


def can_run(starting: bool = False) -> bool:
    """Read only available host memory and CPU package sensors, not AUX sensors."""
    memory = dict(line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())
    available = int(memory['MemAvailable'].split()[0])/1024
    temperatures = []
    for name in Path('/sys/class/hwmon').glob('hwmon*/name'):
        if name.read_text().strip() in ('coretemp','k10temp'):
            temperatures.extend(float(p.read_text())/1000 for p in name.parent.glob('temp*_input'))
    if not temperatures:
        return False  # Fail closed when thermal telemetry cannot be read.
    return permitted(available,max(temperatures),starting)


if __name__ == '__main__':
    if not can_run(starting=True):
        print('Native worker standby: memory or CPU-temperature startup guard')
        sys.exit(1)
