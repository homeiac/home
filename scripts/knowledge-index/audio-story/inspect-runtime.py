#!/usr/bin/env python3
"""Inspect pinned Whisper build availability and shared GPU workload health."""
import json,subprocess,urllib.request
for url in ['https://api.github.com/repos/ggml-org/whisper.cpp/releases/latest','https://ghcr.io/token?service=ghcr.io&scope=repository:ggml-org/whisper.cpp:pull']:
 with urllib.request.urlopen(url,timeout=30) as response: doc=json.load(response)
 if 'tag_name' in doc: print(json.dumps({'release':doc['tag_name'],'assets':[a['name'] for a in doc['assets']]}))
 else:
  request=urllib.request.Request('https://ghcr.io/v2/ggml-org/whisper.cpp/manifests/main-cuda',headers={'Authorization':'Bearer '+doc['token'],'Accept':'application/vnd.oci.image.index.v1+json,application/vnd.docker.distribution.manifest.v2+json'})
  with urllib.request.urlopen(request,timeout=30) as response: print(json.dumps({'cuda_image_digest':response.headers.get('Docker-Content-Digest'),'manifest':json.load(response)}))
