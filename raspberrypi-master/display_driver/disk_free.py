import psutil 
import platform 
from datetime import datetime

def get_size(bytes, suffix="B"):
    """
    Scale bytes to its proper format
    e.g:
        1253656 => '1.20MB'
        1253656678 => '1.17GB'
    """
    factor = 1024
    for unit in ["", "K", "M", "G", "T", "P"]:
        if bytes < factor:
            return f"{bytes:.2f}{unit}{suffix}"
        bytes /= factor

def get_diskfree():
    partitions = psutil.disk_partitions()
    df = ""
    for partition in partitions:
        try:
            partition_usage = psutil.disk_usage(partition.mountpoint)
        except PermissionError:
            continue 
        if partition.mountpoint == "/":
            df = "disk Free| " + str(get_size(partition_usage.free)) + " | " + str(partition_usage.percent) + " o|o used"
    return df