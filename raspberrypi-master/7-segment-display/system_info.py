#!/usr/bin/python
import time
import asyncio
from datetime import timedelta
from aiohttp import web
from uptime import uptime
import netifaces as ni

async def show_ip(request):
    for interface in ni.interfaces():
        if interface == ni.gateways()['default'][ni.AF_INET][1]:
            try:
                routingIPAddr = ni.ifaddresses(interface)[ni.AF_INET][0]['addr']
            except KeyError:
                pass
    print(routingIPAddr)
    return web.Response(content_type='text/html', text=routingIPAddr)


async def bellon(request): # enable auto bell
    print('bell on')
    return web.Response(content_type='text/html', text='Auto bell is enabled')

async def show_uptime(request): # print the uptime
    uptime_seconds = uptime()
    uptime_string = str(timedelta(seconds = uptime_seconds))
    print('uptime= ' + uptime_string)
    return web.Response(content_type='text/html', text=uptime_string)


if __name__ == '__main__':
    app = web.Application()
    app.router.add_get('/autobellon', bellon)
    app.router.add_post('/uptime', show_uptime)
    app.router.add_post('/ip', show_ip)
    web.run_app(app, port=8000)
