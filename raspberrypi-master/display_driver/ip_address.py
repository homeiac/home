import netifaces as ni

import time
from datetime import datetime

def show_ip():
    for interface in ni.interfaces():
        if interface == ni.gateways()['default'][ni.AF_INET][1]:
            try:
                routingIPAddr = ni.ifaddresses(interface)[ni.AF_INET][0]['addr']
            except KeyError:
                pass
    print(routingIPAddr)
