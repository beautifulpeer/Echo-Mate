#!/bin/bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
export ECHOMATE_NMTUI=1
export ECHOMATE_IMAGE_DEST="${ECHOMATE_IMAGE_DEST:-$ROOT/artifacts/echomate-nmtui}"
bash "$ROOT/build-echomate-network-image.sh" "$@"
cp "$ROOT/network-image/networkmanager/README.md" "$ECHOMATE_IMAGE_DEST/NMTUI.md"
