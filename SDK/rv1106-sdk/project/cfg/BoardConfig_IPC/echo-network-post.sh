#!/bin/bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "$0")/../../../../.." && pwd)
python3 "$ROOT/network-image/prepare-rootfs.py" "$RK_PROJECT_PACKAGE_ROOTFS_DIR"
if [ "${ECHOMATE_NMTUI:-0}" = 1 ]; then
    python3 "$ROOT/network-image/networkmanager/install.py" "$RK_PROJECT_PACKAGE_ROOTFS_DIR"
fi
bash "$ROOT/applications/echo-litepanel/scripts/build-camera.sh" "$RK_PROJECT_PACKAGE_ROOTFS_DIR"
python3 "$ROOT/applications/echo-litepanel/tools/verify-rootfs.py" "$RK_PROJECT_PACKAGE_ROOTFS_DIR"
