#!/bin/bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
export ECHOMATE_IMAGE_DEST="${ECHOMATE_IMAGE_DEST:-$ROOT/artifacts/echomate-nmtui-wifi-fix}"
bash "$ROOT/build-echomate-usbfix-image.sh" "$@"
python3 "$ROOT/network-image/networkmanager/verify-ubifs-owner.py" \
    "$ECHOMATE_IMAGE_DEST/rootfs.img" --report "$ECHOMATE_IMAGE_DEST/IMAGE-OWNERSHIP.json"
cp -p "$ECHOMATE_IMAGE_DEST/update.img" "$ECHOMATE_IMAGE_DEST/EchoMate-nmtui-wifi-fix.img"
cp "$ROOT/network-image/WIFI-FIX.md" "$ECHOMATE_IMAGE_DEST/WIFI-FIX.md"
(cd "$ECHOMATE_IMAGE_DEST" && sha256sum *.img *.bin > SHA256SUMS)
