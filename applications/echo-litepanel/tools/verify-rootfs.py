#!/usr/bin/env python3
"""Check files and dynamic-library closure without executing ARM hardware code."""
from pathlib import Path
import re
import ssl
import subprocess
import sys

root = Path(sys.argv[1]).resolve()
sdk = Path(__file__).resolve().parents[3] / 'SDK/rv1106-sdk'
oem = root.parent / 'oem'
readelf = sdk / 'tools/linux/toolchain/arm-rockchip830-linux-uclibcgnueabihf/bin/arm-rockchip830-linux-uclibcgnueabihf-readelf'
search = [oem / 'usr/lib', root / 'usr/lib', root / 'lib']
todo = [root / 'usr/bin/echo-camera']
seen, missing = set(), set()
while todo:
    binary = todo.pop()
    if binary in seen:
        continue
    seen.add(binary)
    dynamic = subprocess.check_output([str(readelf), '-d', str(binary)], text=True)
    if binary.name == 'echo-camera' and '/oem/usr/lib' not in dynamic:
        raise SystemExit('Missing camera runtime path to OEM libraries')
    for dependency in re.findall(r'\(NEEDED\).*\[(.*?)\]', dynamic):
        found = next((folder / dependency for folder in search if (folder / dependency).is_file()), None)
        if found:
            todo.append(found)
        else:
            missing.add(dependency)
if missing:
    raise SystemExit('Missing shared libraries: ' + ', '.join(sorted(missing)))
for relative in ('usr/bin/python3', 'usr/bin/arecord', 'usr/bin/aplay', 'usr/bin/amixer',
                 'usr/sbin/echo-network', 'usr/sbin/wpa_supplicant',
                 'opt/echo-litepanel/server.py', 'opt/echo-litepanel/vendor/paho/mqtt/client.py',
                 'etc/init.d/S99zzlitepanel'):
    if not (root / relative).is_file():
        raise SystemExit('Missing runtime file: ' + relative)
ssl.create_default_context(cafile=str(root / 'opt/echo-litepanel/vendor/ca-bundle.crt'))
print(f'PASS: app runtime, public CA bundle, and {len(seen)} ARM ELF dependency files')
