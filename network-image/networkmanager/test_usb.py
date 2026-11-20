#!/usr/bin/env python3
"""Exercise the USB init script against fake configfs/UDC objects, not hardware."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'overlay/etc/init.d/S50usbdevice'


class USBTests(unittest.TestCase):
    def test_identity_descriptors_order_and_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / 'config'
            gadget = config / 'usb_gadget/echo_net'
            functions = gadget / 'functions'
            (functions / 'rndis.usb0/os_desc/interface.rndis').mkdir(parents=True)
            (functions / 'acm.console').mkdir()
            (gadget / 'os_desc').mkdir()
            (root / 'udc/fake-controller').mkdir(parents=True)
            (root / 'net/usb0').mkdir(parents=True)
            (root / 'bin').mkdir()
            for command in ('mount', 'ifconfig'):
                path = root / 'bin' / command
                path.write_text('#!/bin/sh\nexit 0\n')
                path.chmod(0o755)
            env = dict(os.environ, ECHO_USB_CONFIGFS=str(config), ECHO_USB_UDC_DIR=str(root/'udc'),
                       ECHO_USB_NET_DIR=str(root/'net'), ECHO_USB_LOG=str(root/'usb.log'),
                       PATH=str(root/'bin') + ':' + os.environ['PATH'])
            def run(action):
                subprocess.run(['sh', str(SCRIPT), action], env=env, check=True)
            run('start')
            self.assertEqual((gadget/'idProduct').read_text().strip(), '0x4e4d')
            self.assertEqual((gadget/'bDeviceClass').read_text().strip(), '0xEF')
            self.assertEqual((gadget/'bDeviceSubClass').read_text().strip(), '0x02')
            self.assertEqual((gadget/'bDeviceProtocol').read_text().strip(), '0x01')
            self.assertEqual((functions/'rndis.usb0/class').read_text().strip(), '0xE0')
            self.assertEqual((functions/'rndis.usb0/os_desc/interface.rndis/compatible_id').read_text().strip(), 'RNDIS')
            self.assertEqual((functions/'rndis.usb0/os_desc/interface.rndis/sub_compatible_id').read_text().strip(), '5162001')
            self.assertEqual(Path(os.readlink(gadget/'configs/c.1/f1')).name, 'rndis.usb0')
            self.assertEqual(Path(os.readlink(gadget/'configs/c.1/f2')).name, 'acm.console')
            self.assertEqual((gadget/'UDC').read_text().strip(), 'fake-controller')
            addresses = [(functions/f'rndis.usb0/{name}').read_text() for name in ('dev_addr','host_addr')]
            self.assertNotEqual(*addresses)
            run('start')  # does not reconfigure a bound gadget
            run('stop')
            self.assertEqual((gadget/'UDC').read_text().strip(), '')
            run('start')
            self.assertEqual(addresses, [(functions/f'rndis.usb0/{name}').read_text() for name in ('dev_addr','host_addr')])

    def test_no_adb_or_old_cached_product_id(self):
        script = SCRIPT.read_text()
        self.assertNotIn('ffs.adb', script)
        self.assertNotIn('wceis', script.replace('# The old script attempted "wceis", which this kernel doesn\'t expose.', ''))
        self.assertNotIn('echo 0x0006', script)
        self.assertNotIn('echo 0x1005', script)
        self.assertLess(script.index('ln -s "$F/rndis.usb0"'), script.index('echo "$controller" > "$G/UDC"'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
