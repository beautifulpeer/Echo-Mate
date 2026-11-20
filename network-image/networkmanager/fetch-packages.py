#!/usr/bin/env python3
"""Fetch pinned ARM packages and validate every archive; never installs packages."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import sys
import urllib.request

manifest = json.loads(Path(__file__).with_name('packages.json').read_text())
output = Path(sys.argv[1])
output.mkdir(parents=True, exist_ok=True)

def fetch(package):
    target = output / package['file']
    if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == package['sha256']:
        return
    with urllib.request.urlopen(manifest['mirror'] + '/' + package['filename'], timeout=60) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != package['sha256']:
        raise ValueError('Checksum mismatch: ' + package['file'])
    partial = target.with_suffix('.downloading')
    partial.write_bytes(data)
    partial.replace(target)

with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    list(pool.map(fetch, manifest['packages']))
print('Verified all pinned packages:', output)
