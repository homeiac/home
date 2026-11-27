#!/usr/bin/env python3
"""Verify a public GHCR version and report immutable digest without Docker auth."""
import json
import urllib.request

repo = 'tedornitier/immich-pet-tagger'
tag = 'v1.10.0-cpu'
with urllib.request.urlopen(f'https://ghcr.io/token?scope=repository:{repo}:pull') as response:
    token = json.load(response)['token']
request = urllib.request.Request(f'https://ghcr.io/v2/{repo}/manifests/{tag}', headers={
    'Authorization': 'Bearer ' + token,
    'Accept': 'application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json'})
with urllib.request.urlopen(request) as response:
    manifest = json.load(response)
    print(f'ghcr.io/{repo}:{tag}@{response.headers["Docker-Content-Digest"]}')
    print(json.dumps([m.get('platform') for m in manifest.get('manifests', [])]))
