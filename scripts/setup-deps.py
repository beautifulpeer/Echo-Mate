#!/usr/bin/env python3
"""Restore verified models from this project's own GitHub Release."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import urllib.request


def digest_file(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def restore(entry, target, url):
    if target.is_file() and target.stat().st_size == entry['size']:
        if digest_file(target) == entry['sha256']:
            print(f'Verified: {target}')
            return
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + '.downloading')
    digest = hashlib.sha256()
    size = 0
    try:
        request = urllib.request.Request(url, headers={'User-Agent': 'Echo-Mate-dependency-setup'})
        with urllib.request.urlopen(request, timeout=120) as response, temporary.open('wb') as output:
            while block := response.read(1024 * 1024):
                size += len(block)
                if size > entry['size']:
                    raise RuntimeError('Download exceeds expected model size')
                digest.update(block)
                output.write(block)
        if size != entry['size'] or digest.hexdigest() != entry['sha256']:
            raise RuntimeError('Model size or SHA-256 does not match the manifest')
        os.replace(temporary, target)
        print(f'Restored and verified: {target}')
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Verify local models without downloading')
    parser.add_argument('--prepare-release', type=Path, metavar='DIR', help='Prepare verified release assets from the original model source')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    manifest = json.loads((root / 'dependencies.json').read_text())
    checksums = []
    for entry in manifest['models']:
        target = root / entry['path']
        if args.check:
            if not target.is_file() or target.stat().st_size != entry['size'] or digest_file(target) != entry['sha256']:
                raise RuntimeError(f'Missing or invalid model: {entry["path"]}')
            print(f'Verified: {entry["path"]}')
            continue
        if args.prepare_release:
            target = args.prepare_release / entry['asset']
            url = entry['source_url']
        else:
            url = f'https://github.com/{manifest["repository"]}/releases/download/{manifest["release"]}/{entry["asset"]}'
        restore(entry, target, url)
        checksums.append(f'{entry["sha256"]}  {entry["asset"]}\n')
    if args.prepare_release:
        (args.prepare_release / 'SHA256SUMS.txt').write_text(''.join(checksums))


if __name__ == '__main__':
    main()
