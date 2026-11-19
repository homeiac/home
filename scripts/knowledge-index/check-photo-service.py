#!/usr/bin/env python3
"""Verify private HTTPS photo review without changing any real labels or groups."""
import json
import urllib.error
import urllib.parse
import urllib.request


def main() -> None:
    base='https://photos.app.home.panderosystems.com'
    def get(path):
        with urllib.request.urlopen(base+path,timeout=30) as response:
            return json.load(response)
    status=get('/api/status')
    faces=get('/api/faces?status=all')
    dates=get('/api/dates?timezone=UTC')
    print('Backend:',status['backend'],'snapshot captured:',status.get('captured_at'))
    print('Faces:',faces['total'],'first page:',len(faces['faces']),'capture dates:',len(dates))
    if faces['faces']:
        face=faces['faces'][0]
        path='/api/thumbnail?'+urllib.parse.urlencode({'path':face['path'],'face':face['id']})
        with urllib.request.urlopen(base+path,timeout=30) as response:
            body=response.read()
            if response.headers.get_content_type()!='image/jpeg' or not body.startswith(b'\xff\xd8'):
                raise RuntimeError('Face thumbnail validation failed')
            print('Face crop HTTPS: OK')
    request=urllib.request.Request(base+'/api/faces/label',data=b'{}',headers={'Content-Type':'application/json'},method='POST')
    try:urllib.request.urlopen(request,timeout=10)
    except urllib.error.HTTPError as error:
        if error.code!=403:raise
        print('Writes without a request token: rejected')
    else:raise RuntimeError('Expected CSRF rejection')


if __name__=='__main__':main()
