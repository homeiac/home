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

def get_memory():
    svmem = psutil.virtual_memory()
    memory_string = "mem Free " + str(get_size(svmem.used)) +  " used " + str(svmem.percent) + "o|o"
    return memory_string