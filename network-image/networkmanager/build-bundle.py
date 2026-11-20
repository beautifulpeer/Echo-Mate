#!/usr/bin/env python3
"""Build an isolated ARMhf NetworkManager runtime from pinned Debian packages."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--packages', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
manifest = json.loads(Path(__file__).with_name('packages.json').read_text())
output = args.output.resolve()
if output.exists():
    raise SystemExit('Output already exists; choose a fresh bundle directory')
with tempfile.TemporaryDirectory(prefix='echo-nm-extract-') as temporary:
    source = Path(temporary)
    for package in manifest['packages']:
        archive = args.packages / package['file']
        if hashlib.sha256(archive.read_bytes()).hexdigest() != package['sha256']:
            raise SystemExit('Package checksum mismatch: ' + str(archive))
        subprocess.run(['dpkg-deb', '-x', str(archive), str(source)], check=True)
    output.mkdir(parents=True)
    seen = set()

    def copy(relative):
        if relative in seen:
            return
        seen.add(relative)
        original, target = source / relative, output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if original.is_symlink():
            link = os.readlink(original)
            dependency = Path(os.path.normpath(str(relative.parent / link))) if not link.startswith('/') else Path(link[1:])
            copy(dependency)
            target.symlink_to(os.path.relpath(output / dependency, target.parent))
            return
        shutil.copy2(original, target)
        if original.read_bytes()[:4] != b'\x7fELF':
            return
        dynamic = subprocess.check_output(['readelf', '-d', str(original)], text=True)
        for name in re.findall(r'\(NEEDED\).*\[(.*?)\]', dynamic):
            for directory in ('lib/arm-linux-gnueabihf', 'usr/lib/arm-linux-gnueabihf'):
                dependency = Path(directory) / name
                if (source / dependency).exists() or (source / dependency).is_symlink():
                    copy(dependency)
                    break
            else:
                raise SystemExit('Missing library: ' + name)

    for name in ('usr/sbin/NetworkManager', 'usr/bin/nmcli', 'usr/bin/nmtui',
                 'usr/bin/nmtui-connect', 'usr/bin/nmtui-edit', 'usr/bin/nmtui-hostname',
                 'usr/bin/nm-online', 'sbin/wpa_supplicant', 'lib/ld-linux-armhf.so.3'):
        copy(Path(name))
    for plugin in source.glob('usr/lib/arm-linux-gnueabihf/NetworkManager/*/libnm-device-plugin-wifi.so'):
        copy(plugin.relative_to(source))
    for helper in source.glob('usr/lib/NetworkManager/nm-*'):
        if helper.is_file():
            copy(helper.relative_to(source))
    for relative in ('lib/terminfo', 'usr/share/terminfo', 'usr/lib/locale'):
        if (source / relative).exists():
            shutil.copytree(source / relative, output / relative, symlinks=True, dirs_exist_ok=True)
    for relative in ('usr/share/dbus-1/system.d/org.freedesktop.NetworkManager.conf',
                     'etc/dbus-1/system.d/wpa_supplicant.conf'):
        copy(Path(relative))
    for pattern in ('usr/share/dbus-1/system.d/nm-*.conf', 'usr/share/dbus-1/system-services/org.freedesktop.nm*.service'):
        for path in source.glob(pattern):
            copy(path.relative_to(source))
    for package in (item['Package'] for item in manifest['packages']):
        folder = source / 'usr/share/doc' / package
        if (folder / 'copyright').is_file():
            destination = output / 'usr/share/doc' / package
            destination.mkdir(parents=True, exist_ok=True)
            shutil.copy2(folder / 'copyright', destination / 'copyright')
    if (source / 'usr/share/common-licenses').exists():
        shutil.copytree(source / 'usr/share/common-licenses', output / 'usr/share/common-licenses', symlinks=True)
    (output / 'PACKAGES.json').write_text(json.dumps(manifest, indent=2) + '\n')
print('Built real NetworkManager/nmtui runtime:', output)
