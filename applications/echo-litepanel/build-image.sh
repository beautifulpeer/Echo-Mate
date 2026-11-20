#!/bin/bash
set -euo pipefail
HERE=$(cd -- "$(dirname -- "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
export ECHOMATE_IMAGE_DEST=$ROOT/artifacts/echo-litepanel-cloud
bash "$ROOT/build-echomate-network-image.sh" "$@"
cp "$HERE/README.md" "$ECHOMATE_IMAGE_DEST/LITEPANEL.md"
cp "$HERE/patches/litepanel-cloud-audio.patch" "$ECHOMATE_IMAGE_DEST/"
