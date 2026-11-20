import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('image_owner', HERE / 'verify-ubifs-owner.py')
owner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(owner)
REPO = HERE.parents[1]
TOOL = REPO / 'SDK/rv1106-sdk/sysdrv/tools/pc/mtd-utils/mkfs.ubifs'


class ImageOwnership(unittest.TestCase):
    def test_static_mkfs_squashes_actual_image_owners(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / 'root'
            plugin = root / owner.WIFI
            plugin.parent.mkdir(parents=True)
            plugin.write_bytes(b'Test plugin metadata; no executable code')
            for squash in (False, True):
                image = Path(folder) / ('fixed.ubifs' if squash else 'old.ubifs')
                command = [str(TOOL), '-m', '2048', '-e', '126976', '-c', '128', '-r', str(root), '-o', str(image)]
                if squash:
                    command.append('-U')
                subprocess.run(command, check=True, capture_output=True)
                inodes, entries = owner.read_metadata(image)
                info = owner.lookup(inodes, entries, owner.WIFI)
                self.assertEqual(info['uid'], 0 if squash else os.getuid())
                self.assertEqual(info['gid'], 0 if squash else os.getgid())
                if squash:
                    self.assertTrue(all(item['uid'] == item['gid'] == 0 for inode, item in inodes.items() if inode != 1))


if __name__ == '__main__':
    unittest.main(verbosity=2)
