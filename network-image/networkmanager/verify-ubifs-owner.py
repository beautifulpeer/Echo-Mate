#!/usr/bin/env python3
"""Read CRC-valid UBIFS inode/directory metadata directly from UBIFS/UBI images.

Does not mount or extract the image. Layouts are defined by this SDK's
kernel/fs/ubifs/ubifs-media.h (24-byte common header, 16-byte key).
"""
import argparse
import binascii
import json
from pathlib import Path
import struct

MAGIC = b'\x31\x18\x10\x06'
WIFI = 'opt/networkmanager/usr/lib/arm-linux-gnueabihf/NetworkManager/1.42.4/libnm-device-plugin-wifi.so'


def read_metadata(image):
    data = Path(image).read_bytes()
    inodes, entries = {}, {}
    offset = 0
    while True:
        offset = data.find(MAGIC, offset)
        if offset < 0:
            break
        start, offset = offset, offset + 4
        if start % 8 or start + 24 > len(data):
            continue
        size = struct.unpack_from('<I', data, start + 16)[0]
        kind = data[start + 20]
        if kind not in (0, 2) or size < 56 or size > 65536 or start + size > len(data):
            continue
        expected = struct.unpack_from('<I', data, start + 4)[0]
        actual = binascii.crc32(data[start + 8:start + size]) ^ 0xffffffff
        if expected != actual:
            continue
        key = struct.unpack_from('<I', data, start + 24)[0]
        sequence = struct.unpack_from('<Q', data, start + 8)[0]
        if kind == 0 and size >= 160:
            uid, gid, mode = struct.unpack_from('<III', data, start + 96)
            if key not in inodes or sequence > inodes[key]['sequence']:
                inodes[key] = dict(uid=uid, gid=gid, mode=mode, sequence=sequence)
        elif kind == 2:
            inode = struct.unpack_from('<Q', data, start + 40)[0]
            length = struct.unpack_from('<H', data, start + 50)[0]
            if length > 255 or 56 + length + 1 > size:
                continue
            try:
                name = data[start + 56:start + 56 + length].decode('utf-8')
            except UnicodeError:
                continue
            if (key, name) not in entries or sequence > entries[key, name][1]:
                entries[key, name] = (inode, sequence)
    if not inodes:
        raise ValueError('No CRC-valid UBIFS inodes found')
    return inodes, entries


def lookup(inodes, entries, path):
    inode = 1  # UBIFS_ROOT_INO
    for name in path.strip('/').split('/'):
        inode = entries[inode, name][0]
    return inodes[inode]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    inodes, entries = read_metadata(args.image)
    bad = {inode: values for inode, values in inodes.items() if inode != 1 and (values['uid'] or values['gid'])}
    if bad:
        raise SystemExit(f'Image ownership check failed: {len(bad)} non-root inodes; example {next(iter(bad.items()))}')
    targets = [WIFI, 'opt/networkmanager/usr/sbin/NetworkManager',
               'opt/networkmanager/usr/bin/nmtui', 'usr/bin/nmtui',
               'etc/init.d/S99znetwork', 'etc/inittab']
    checked = {}
    for path in targets:
        info = lookup(inodes, entries, path)
        if info['mode'] & 0o022:
            raise SystemExit(f'Unsafe group/other-writable runtime file: {path}')
        checked[path] = {key: info[key] for key in ('uid', 'gid', 'mode')}
    report = dict(image=str(args.image), crc_verified=True, root_owned_inodes=len(inodes) - 1, root_directory=inodes.get(1), files=checked)
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(f'PASS: actual UBIFS image has {len(inodes) - 1} root-owned content inodes; Wi-Fi plugin UID/GID 0:0')


if __name__ == '__main__':
    main()
