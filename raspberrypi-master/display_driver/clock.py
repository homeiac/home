import time
from datetime import datetime

def clock():
    """
    Display current time on device.
    """

    interval = 0.5
    seconds = 5
    cl = ""
    for i in range(int(seconds / interval)):
        now = datetime.now()
        cl = cl + now.strftime("%H-%M-%S") + "\n"

        # calculate blinking dot
        if i % 2 == 0:
            cl = cl + now.strftime("%H-%M-%S") + "\n"
        else:
            cl = cl + now.strftime("%H %M %S") + "\n"
        time.sleep(interval)
    return cl

