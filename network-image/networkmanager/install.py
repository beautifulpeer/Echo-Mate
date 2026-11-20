#!/usr/bin/env python3
"""Install real glibc NetworkManager without replacing vendor uClibc libraries."""
from pathlib import Path
import os
import shutil
import sys

root = Path(sys.argv[1]).resolve()
here = Path(__file__).resolve().parent
repo = here.parents[1]
bundle = Path(os.environ.get('ECHOMATE_NM_BUNDLE', str(repo / 'artifacts/networkmanager-armhf/runtime')))
if not (bundle / 'usr/bin/nmtui').is_file():
    raise SystemExit('Missing NetworkManager bundle; see network-image/networkmanager/README.md')
target = root / 'opt/networkmanager'
if target.exists():
    shutil.rmtree(target)
shutil.copytree(bundle, target, symlinks=True)

def write(relative, text, mode=0o755):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        path.unlink()
    path.write_text(text)
    path.chmod(mode)

def link(relative, destination):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        path.unlink()
    elif path.exists():
        raise SystemExit('Refusing to replace existing directory/file: ' + str(path))
    path.symlink_to(destination)

programs = {
    'usr/bin/nmtui': 'usr/bin/nmtui',
    'usr/bin/nmtui-connect': 'usr/bin/nmtui-connect',
    'usr/bin/nmtui-edit': 'usr/bin/nmtui-edit',
    'usr/bin/nmtui-hostname': 'usr/bin/nmtui-hostname',
    'usr/bin/nmcli': 'usr/bin/nmcli',
    'usr/bin/nm-online': 'usr/bin/nm-online',
    'usr/sbin/NetworkManager': 'usr/sbin/NetworkManager',
    'usr/sbin/wpa_supplicant-nm': 'sbin/wpa_supplicant',
}
for public, private in programs.items():
    write(public, f'''#!/bin/sh
# This executes the genuine ARM executable with its private glibc loader.
export TERMINFO=/opt/networkmanager/lib/terminfo
export LOCPATH=/opt/networkmanager/usr/lib/locale
export LC_ALL=C.UTF-8
export GIO_MODULE_DIR=/opt/networkmanager/usr/lib/arm-linux-gnueabihf/gio/modules
exec /opt/networkmanager/lib/ld-linux-armhf.so.3 \\
    --library-path /opt/networkmanager/lib/arm-linux-gnueabihf:/opt/networkmanager/usr/lib/arm-linux-gnueabihf \\
    /opt/networkmanager/{private} "$@"
''')
# NetworkManager discovers its Wi-Fi module using this compile-time path.
link('usr/lib/arm-linux-gnueabihf/NetworkManager', '/opt/networkmanager/usr/lib/arm-linux-gnueabihf/NetworkManager')
# Dispatcher/helper paths are also compiled into the Debian binary.
helpers = target / 'usr/lib/NetworkManager'
for helper in helpers.iterdir():
    if helper.is_file():
        write('usr/lib/NetworkManager/' + helper.name, f'''#!/bin/sh
exec /opt/networkmanager/lib/ld-linux-armhf.so.3 \\
    --library-path /opt/networkmanager/lib/arm-linux-gnueabihf:/opt/networkmanager/usr/lib/arm-linux-gnueabihf \\
    /opt/networkmanager/usr/lib/NetworkManager/{helper.name} "$@"
''')
for original, name in [
    ('usr/share/dbus-1/system.d/org.freedesktop.NetworkManager.conf', 'org.freedesktop.NetworkManager.conf'),
    ('etc/dbus-1/system.d/wpa_supplicant.conf', 'wpa_supplicant.conf')]:
    write('etc/dbus-1/system.d/' + name, (bundle / original).read_text(), 0o644)
for policy in (bundle / 'usr/share/dbus-1/system.d').glob('nm-*.conf'):
    write('etc/dbus-1/system.d/' + policy.name, policy.read_text(), 0o644)
for service in (bundle / 'usr/share/dbus-1/system-services').glob('org.freedesktop.nm*.service'):
    text = '\n'.join(line for line in service.read_text().splitlines() if not line.startswith('SystemdService=')) + '\n'
    write('usr/share/dbus-1/system-services/' + service.name, text, 0o644)
write('usr/share/dbus-1/system-services/fi.w1.wpa_supplicant1.service', '''[D-BUS Service]
Name=fi.w1.wpa_supplicant1
Exec=/usr/sbin/wpa_supplicant-nm -u -s
User=root
''', 0o644)
write('etc/NetworkManager/NetworkManager.conf', (here / 'NetworkManager.conf').read_text(), 0o644)
if not (root / 'etc/machine-id').exists() and not (root / 'etc/machine-id').is_symlink():
    link('etc/machine-id', '/var/lib/dbus/machine-id')
link('etc/NetworkManager/system-connections', '/userdata/NetworkManager/system-connections')
link('var/lib/NetworkManager', '/userdata/NetworkManager/state')
write('etc/init.d/S99znetwork', (here / 'S99znetwork').read_text())
# The vendor module-loader invokes this name after probing SDIO. Keep driver
# loading intact, but prevent it from launching a competing Wi-Fi manager.
write('usr/bin/rkwifi_server', '''#!/bin/sh
# Disabled in the NetworkManager image; hardware probing may still invoke it.
exit 0
''')
# Keep the old command usable, but never start a competing Wi-Fi manager.
legacy = root / 'usr/sbin/echo-network'
legacy.rename(legacy.with_name('echo-usb-network'))
write('usr/sbin/echo-network', '''#!/bin/sh
case "${1:-menu}" in
menu) exec nmtui ;;
status) nmcli device status; ifconfig -a; route -n ;;
scan) exec nmcli device wifi list ifname wlan0 ;;
connect) echo 'Use nmtui or: nmcli --ask device wifi connect SSID ifname wlan0' >&2; exit 1 ;;
usb-share) exec /usr/sbin/echo-usb-network usb-share ;;
*) echo 'Usage: echo-network [menu|status|scan|usb-share]'; exit 1 ;;
esac
''')
# Delete legacy Wi-Fi controls from the retained USB-only helper.
text = (root / 'usr/sbin/echo-usb-network').read_text()
text = text.replace("action = sys.argv[1] if len(sys.argv) > 1 else 'menu'",
                    "action = sys.argv[1] if len(sys.argv) > 1 else 'usb-share'\n    if action != 'usb-share':\n        raise ValueError('Wi-Fi is managed by NetworkManager; use nmtui')")
(root / 'usr/sbin/echo-usb-network').write_text(text)
print('Installed genuine NetworkManager 1.42.4, nmtui, nmcli; vendor libc untouched')
