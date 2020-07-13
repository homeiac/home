import time
import asyncio
from datetime import datetime
from aiohttp import web
import netifaces as ni
from get_time import get_time
from memory_free import get_memory
from disk_free import get_diskfree
import cpu_load
from clock import clock

from up_time import get_uptime

from luma.led_matrix.device import max7219
from luma.core.interface.serial import spi, noop
from luma.core.virtual import viewport, sevensegment

def show_message_vp(request, msg):
    device = request.app['device']
    delay = request.app['delay']
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
    delay = request.app['delay']
    # Does same as above but does
    # string slicing itself
    width = seg.device.width
    padding = " " * width
    msg = padding + msg + padding

    for i in range(len(msg)):
        seg.text = msg[i:i + width]
        time.sleep(delay)

async def show_cpu(request): # print the cpu
    """Send the CPU response and then display on 7 segment display."""
    cpu_string = cpu_load.get_CPU()
    print('cpu= ' + cpu_string)

    # explicitly send the response
    resp = web.Response(content_type='text/html', text=cpu_string)
    await resp.prepare(request)
    await resp.write_eof()

    show_message_vp(request, cpu_string)
    return resp



async def show_clock(request): # print the clock
    """Send the current time and then display blinking clock on the 7 segment display."""
    clock_string = datetime.now().strftime("%H-%M-%S")
    print('time now = ' + clock_string)

    # explicitly send the response
    resp = web.Response(content_type='text/html', text=clock_string)
    await resp.prepare(request)
    await resp.write_eof()
    clock.clock(app['seg'], 10)
    return resp

async def show_disk(request): # print the disk
    """Send the disk  usage and then display disk usage data on the 7 segment display."""
    disk_string = get_diskfree()
    print('disk= ' + disk_string)

    # explicitly send the response
    resp = web.Response(content_type='text/html', text=disk_string)
    await resp.prepare(request)
    await resp.write_eof()

    show_message_vp(request, disk_string)
    return resp


async def show_memory(request): # print the memory
    """Send the memory  usage and then display memory usage data on the 7 segment display."""
    memory_string = get_memory()
    print('memory= ' + memory_string)

    # explicitly send the response
    resp = web.Response(content_type='text/html', text=memory_string)
    await resp.prepare(request)
    await resp.write_eof()

    show_message_vp(request, memory_string)
    return resp

async def show_time(request): # print the time
    """Send the current time and then display current time on the 7 segment display."""
    time_string = get_time.get_time()
    print('time= ' + time_string)

    # explicitly send the response
    resp = web.Response(content_type='text/html', text=time_string)
    await resp.prepare(request)
    await resp.write_eof()

    show_message_vp(request, time_string)
    return resp

async def show_ip(request):
    """Send the ip address and then display ip address on the 7 segment display."""
    for interface in ni.interfaces():
        if interface == ni.gateways()['default'][ni.AF_INET][1]:
            try:
                routingIPAddr = ni.ifaddresses(interface)[ni.AF_INET][0]['addr']
            except KeyError:
                pass
    print(routingIPAddr)


    # explicitly send the response
    resp = web.Response(content_type='text/html', text=routingIPAddr)
    await resp.prepare(request)
    await resp.write_eof()

    show_message_vp(request, routingIPAddr)
    return resp


async def all_off(request): # turn off everything
    print('turn off everything')
    show_message_vp(request, "")
    return web.Response(content_type='text/html', text='everything is off')

async def show_uptime(request): # print the uptime
    """Send the uptime and then display it on the 7 segment display."""
    uptime_string = get_uptime()
    print('uptime= ' + uptime_string)

    # explicitly send the response
    resp = web.Response(content_type='text/html', text=uptime_string)
    await resp.prepare(request)
    await resp.write_eof()

    show_message_vp(request, uptime_string)
    return resp

def setup(app): # create the display device and store it
    app['serial'] = spi(port=0, device=0, gpio=noop())
    app['device'] = max7219(app['serial'], cascaded=1)
    app['seg'] = sevensegment(app['device'])
    app['delay'] = 0.15


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

