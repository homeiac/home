#!/usr/bin/env python3
"""No network: provider failures, minimized input and uncertain landmark context."""
import io
import json
import unittest
import urllib.error
from photo_enrichment import places


class PlacesTests(unittest.TestCase):
    def test_invalid_gps_never_calls_provider(self):
        for lat,lon in [(None,None),(0,0),(91,0),(0,181),(float('nan'),2)]:
            with self.subTest(lat=lat),self.assertRaises((ValueError,TypeError)):
                places.nearby(lat,lon,lambda *a,**k:self.fail('Unexpected network'))

    def test_only_rounded_coordinates_sent_with_cc0_descriptions(self):
        def response(request,timeout):
            self.assertIn('12.346%7C23.457',request.full_url)
            self.assertNotIn('12.345678',request.full_url)
            self.assertIn('pageterms',request.full_url)
            self.assertIn('HomePhotoContext',request.get_header('User-agent'))
            return io.BytesIO(json.dumps({'query':{'pages':[{'title':'Synthetic site','pageid':1,
                'coordinates':[{'lat':12.346,'lon':23.457}], 'terms':{'description':['a test site']}}]}}).encode())
        result=places.nearby(12.345678,23.456789,response)
        self.assertEqual(result['candidates'][0]['description'],'a test site')
        prompt=places.prompt_context(result,12.345678,23.456789)
        self.assertIn('not verified subjects',prompt)
        self.assertIn('untrusted reference data',prompt)
        self.assertIn('distance_m',prompt)

    def test_empty_result_is_valid_and_maxlag_defers(self):
        self.assertEqual(places.nearby(12,23,lambda *a,**k:io.BytesIO(b'{}'))['candidates'],[])
        with self.assertRaises(places.LookupDeferred):
            places.nearby(12,23,lambda *a,**k:io.BytesIO(b'{"error":{"code":"maxlag"}}'))

    def test_retry_after_and_no_error_body_leak(self):
        def fail(*a,**k):raise urllib.error.HTTPError('private-coordinates',429,'private body',{'Retry-After':'120'},None)
        with self.assertRaises(places.LookupDeferred) as error:places.nearby(12,23,fail)
        self.assertEqual(error.exception.seconds,120)
        self.assertNotIn('private',str(error.exception))
        self.assertEqual(places.LookupDeferred('bad-header').seconds,60)

    def test_spatial_cache_key_and_distance(self):
        self.assertEqual(places.cache_key(12.34561,23.45671),places.cache_key(12.34562,23.45672))
        self.assertNotEqual(places.cache_key(12.34561,23.45671),places.cache_key(13,24))
        self.assertEqual(places.distance(12,23,12,23),0)


if __name__=='__main__':unittest.main()
