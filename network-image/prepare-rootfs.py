#!/usr/bin/env python3
"""Apply the networking profile to the SDK's assembled filesystem."""
import pathlib
import shutil
import sys

root = pathlib.Path(sys.argv[1]).resolve()
source = pathlib.Path(__file__).resolve().parent
shutil.copytree(source / 'overlay', root, dirs_exist_ok=True)
for name in ['usr/sbin/echo-network', 'etc/init.d/S50usbdevice', 'etc/init.d/S90usb0config', 'etc/init.d/S99znetwork']:
    (root / name).chmod(0o755)
# USB CDC ACM gives a login prompt even if Windows RNDIS binding fails.
inittab = root / 'etc/inittab'
text = inittab.read_text()
console = 'ttyGS0::respawn:/sbin/getty -L 115200 ttyGS0 vt100'
text = '\n'.join(line for line in text.splitlines() if not line.startswith('ttyGS0:'))
inittab.write_text(text.rstrip() + '\n' + console + '\n')
securetty = root / 'etc/securetty'
if securetty.exists() and 'ttyGS0' not in securetty.read_text().splitlines():
    securetty.write_text(securetty.read_text().rstrip() + '\nttyGS0\n')
# Disable the display/main application: it can spawn USB receivers and own Wi-Fi.
(root / 'etc/init.d/S99echomate').write_text('#!/bin/sh\n# Disabled in network image.\nexit 0\n')
for name in ['root/bin/usb_displayd_serial', 'root/bin/usb_displayd']:
    (root / name).unlink(missing_ok=True)
app = source.parent / 'applications/echo-litepanel'
runtime = root / 'opt/echo-litepanel'
if runtime.exists():
    shutil.rmtree(runtime)
shutil.copytree(app / 'runtime', runtime,
                ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
shutil.copy2(app / 'config/cloud.example.json', runtime / 'cloud.example.json')
shutil.copy2(app / 'scripts/S99zzlitepanel', root / 'etc/init.d/S99zzlitepanel')
(root / 'etc/init.d/S99zzlitepanel').chmod(0o755)
# The new device service owns camera, motors, audio and protocol transport.
(root / 'etc/init.d/S21appinit').write_text('#!/bin/sh\n# Replaced by S99zzlitepanel in this image.\nexit 0\n')
(root / 'etc/init.d/S21appinit').chmod(0o755)
print('Applied Echo-Mate network profile (RNDIS, Wi-Fi menu, no USB display).')
