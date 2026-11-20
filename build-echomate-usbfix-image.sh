#!/bin/bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
export ECHOMATE_IMAGE_DEST="${ECHOMATE_IMAGE_DEST:-$ROOT/artifacts/echomate-nmtui-usbfix}"
bash "$ROOT/build-echomate-nmtui-image.sh" "$@"
cp "$ROOT/network-image/USB-RECOVERY.md" "$ECHOMATE_IMAGE_DEST/USB-RECOVERY.md"
cp "$ROOT/network-image/Connect-EchoMate.ps1" "$ECHOMATE_IMAGE_DEST/Connect-EchoMate.ps1"
cp -p "$ECHOMATE_IMAGE_DEST/update.img" "$ECHOMATE_IMAGE_DEST/EchoMate-nmtui-usbfix.img"
(cd "$ECHOMATE_IMAGE_DEST" && sha256sum *.img *.bin > SHA256SUMS)
