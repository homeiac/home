"""Bound concurrent original decoding and retain a byte-limited preview cache."""
from collections import OrderedDict
import threading

from .telemetry import get_telemetry


class PreviewCache:
    def __init__(self,max_bytes=32*1024*1024,max_entries=256):
        self.max_bytes=max_bytes;self.max_entries=max_entries
        self.items=OrderedDict();self.bytes=0
        self.lock=threading.Lock();self.decoders=threading.BoundedSemaphore(2)

    def get(self,key):
        with self.lock:
            result=self.items.get(key)
            if result is not None:self.items.move_to_end(key)
            return result

    def render(self,key,build):
        result=self.get(key)
        if result is not None:return result
        with get_telemetry().stage('thumbnail.queue'):
            self.decoders.acquire()
        try:
            result=self.get(key)
            if result is not None:return result
            result=build()
            if len(result)<=self.max_bytes:
                with self.lock:
                    previous=self.items.pop(key,None)
                    if previous is not None:self.bytes-=len(previous)
                    self.items[key]=result;self.bytes+=len(result)
                    while self.bytes>self.max_bytes or len(self.items)>self.max_entries:
                        _,old=self.items.popitem(last=False);self.bytes-=len(old)
            return result
        finally:self.decoders.release()


PREVIEWS=PreviewCache()
