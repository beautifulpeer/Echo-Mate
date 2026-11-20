#!/usr/bin/env python3
"""Validate private ARM ELF dependencies and execute real CLI programs with QEMU."""
import argparse
import os
from pathlib import Path
import re
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('rootfs', type=Path)
args = parser.parse_args()
root = args.rootfs.resolve()
bundle = root / 'opt/networkmanager'
libraries = [bundle / 'lib/arm-linux-gnueabihf', bundle / 'usr/lib/arm-linux-gnueabihf']
checked = 0
for binary in bundle.rglob('*'):
    if not binary.is_file() or binary.is_symlink():
        continue
    with binary.open('rb') as stream:
        if stream.read(4) != b'\x7fELF':
            continue
    output = subprocess.check_output(['readelf', '-d', str(binary)], text=True)
    for dependency in re.findall(r'\(NEEDED\).*\[(.*?)\]', output):
        if not any((directory / dependency).is_file() for directory in libraries):
            raise SystemExit(f'Missing private dependency: {binary.name}: {dependency}')
    checked += 1
commands = [
    ('usr/bin/nmcli', '--version', '1.42.4'),
    ('usr/sbin/NetworkManager', '--version', '1.42.4'),
    ('usr/bin/nmtui', '--help', 'nmtui'),
    ('sbin/wpa_supplicant', '-v', 'v2.10'),
]
for program, argument, expected in commands:
    result = subprocess.run(['qemu-arm-static', '-cpu', 'cortex-a7',
                             str(bundle / 'lib/ld-linux-armhf.so.3'),
                             '--library-path', ':'.join(map(str, libraries)),
                             str(bundle / program), argument],
                            check=True, capture_output=True, text=True,
                            env=dict(os.environ, LD_BIND_NOW='1'))
    if expected not in result.stdout + result.stderr:
        raise SystemExit('Unexpected executable output: ' + program)
for name in ('nmtui', 'nmtui-connect', 'nmtui-edit', 'nmcli', 'nm-online'):
    subprocess.run(['sh', '-n', str(root / 'usr/bin' / name)], check=True)
subprocess.run(['sh', '-n', str(root / 'etc/init.d/S99znetwork')], check=True)
config = (root / 'etc/NetworkManager/NetworkManager.conf').read_text()
assert 'dhcp=internal' in config and 'unmanaged-devices=interface-name:usb0' in config
assert os.readlink(root / 'etc/NetworkManager/system-connections') == '/userdata/NetworkManager/system-connections'
assert (root / 'opt/echo-litepanel/server.py').is_file()
assert (root / 'lib/ld-uClibc.so.0').is_file()
assert (root / 'sbin/ifconfig').exists()
assert 'Disabled in the NetworkManager image' in (root / 'usr/bin/rkwifi_server').read_text()
usb = (root / 'etc/init.d/S50usbdevice').read_text()
assert 'echo 0x4e4d > "$G/idProduct"' in usb
assert 'echo 0xEF > "$G/bDeviceClass"' in usb
assert 'echo 0x02 > "$G/bDeviceSubClass"' in usb
assert 'echo 0x01 > "$G/bDeviceProtocol"' in usb
assert 'mkdir -p "$F/rndis.usb0" "$F/acm.console"' in usb
assert 'ttyGS0::respawn:/sbin/getty -L 115200 ttyGS0 vt100' in (root / 'etc/inittab').read_text()
assert (root / 'sbin/getty').exists() and (root / 'bin/login').exists()
print(f'PASS: {checked} isolated ARM ELF files, 4 real executables on Cortex-A7, init/USB/persistence and vendor runtime')
