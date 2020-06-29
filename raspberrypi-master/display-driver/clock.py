import time
from datetime import datetime

from luma.led_matrix.device import max7219
from luma.core.interface.serial import spi, noop
from luma.core.virtual import viewport, sevensegment

def clock(seg, seconds):
    """
    Display current time on device.
    """

    interval = 0.5
    for i in range(int(seconds / interval)):
        now = datetime.now()
        seg.text = now.strftime("%H-%M-%S") + "\n"

        # calculate blinking dot
        if i % 2 == 0:
            seg.text = now.strftime("%H-%M-%S") + "\n"
        else:
            seg.text = now.strftime("%H %M %S") + "\n"

        time.sleep(interval)

    return datetime.now()

