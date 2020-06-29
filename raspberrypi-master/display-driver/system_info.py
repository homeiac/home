import time
import asyncio
from datetime import timedelta
from aiohttp import web
import netifaces as ni
import get_time
import memory_free
import disk_free
import cpu_load
import clock

import up_time

from luma.led_matrix.device import max7219
from luma.core.interface.serial import spi, noop
from luma.core.virtual import viewport, sevensegment

def show_message_vp(request, msg):
    device = request.app['device']
    delay = 0.5
    # Implemented with virtual viewport
    width = device.width
    padding = " " * width
    msg = padding + msg + padding
    n = len(msg)

    virtual = viewport(device, width=n, height=8)
    sevensegment(virtual).text = msg
    for i in reversed(list(range(n - width))):
        virtual.set_position((i, 0))
        time.sleep(delay)


def show_message_alt(request, msg):
    seg = request.ap['seg']
    delay = 0.1
    # Does same as above but does string slicing itself
    width = seg.device.width
    padding = " " * width
    msg = padding + msg + padding

    for i in range(len(msg)):
        seg.text = msg[i:i + width]
        time.sleep(delay)

async def show_cpu(request): # print the cpu
    cpu_string = cpu_load.get_CPU()
    print('cpu= ' + cpu_string)
    show_message_vp(request, cpu_string)
    return web.Response(content_type='text/html', text=cpu_string)

async def show_clock(request): # print the clock
    clock_string = clock.clock()
    print('clock= ' + clock_string)
    show_message_vp(request, clock_string)
    return web.Response(content_type='text/html', text=clock_string)

async def show_disk(request): # print the disk
    disk_string = disk_free.get_diskfree()
    print('disk= ' + disk_string)
    show_message_vp(request, disk_string)
    return web.Response(content_type='text/html', text=disk_string)


async def show_memory(request): # print the memory
    memory_string = memory_free.get_memory()
    print('memory= ' + memory_string)
    show_message_vp(request, memory_string)
    return web.Response(content_type='text/html', text=memory_string)

async def show_time(request): # print the time
    time_string = get_time.get_time()
    print('time= ' + time_string)
    show_message_vp(request, time_string)
    return web.Response(content_type='text/html', text=time_string)

async def show_ip(request):
    for interface in ni.interfaces():
        if interface == ni.gateways()['default'][ni.AF_INET][1]:
            try:
                routingIPAddr = ni.ifaddresses(interface)[ni.AF_INET][0]['addr']
            except KeyError:
                pass
    print(routingIPAddr)
    show_message_vp(request, routingIPAddr)
    return web.Response(content_type='text/html', text=routingIPAddr)


async def all_off(request): # turn off everything
    print('turn off everything')
    show_message_vp(request, "")
    return web.Response(content_type='text/html', text='everything is off')

async def show_uptime(request): # print the uptime
    uptime_string = up_time.get_uptime()
    print('uptime= ' + uptime_string)
    show_message_vp(request, uptime_string)
    return web.Response(content_type='text/html', text=uptime_string)

def setup(app): # create the display device and store it
    app['serial'] = spi(port=0, device=0, gpio=noop())
    app['device'] = max7219(app['serial'], cascaded=1)
    app['seg'] = sevensegment(app['device'])


if __name__ == '__main__':
    app = web.Application()
    setup(app)
    app.router.add_get('/time', show_time)
    app.router.add_get('/uptime', show_uptime)
    app.router.add_get('/ip', show_ip)
    app.router.add_get('/memory', show_memory)
    app.router.add_get('/disk', show_disk)
    app.router.add_get('/cpu', show_cpu)
    app.router.add_get('/clock', show_clock)
    app.router.add_get('/alloff', all_off)
    web.run_app(app, port=8000)

