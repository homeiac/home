import psutil 
import platform 
from datetime import datetime

# number of cores
def get_CPU():
    cpu = " CPU  " + str(psutil.cpu_count(logical=True)) + " " + str(psutil.cpu_percent())
    return cpu