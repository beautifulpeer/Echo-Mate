#!/bin/bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
export ECHOMATE_NETWORK_IMAGE=1
if [ "${1:-}" != --package-only ] && ! command -v gperf >/dev/null; then
    echo '缺少主机依赖 gperf，请安装 gperf 或将其加入 PATH。' >&2
    exit 1
fi
if [ "${1:-}" = --package-only ]; then
    cd "$ROOT/SDK/rv1106-sdk"
    EXPECTED=project/cfg/BoardConfig_IPC/BoardConfig-SPI_NAND-Buildroot-RV1106_Echo_Mate-DeskMate.mk
    [ "$(readlink .BoardConfig.mk)" = "$EXPECTED" ] || { echo '板级配置不匹配' >&2; exit 1; }
    # Refresh the packaged host tools so incremental firmware builds use source
    # fixes too (not an old cached mkfs_ubi.sh without --squash-uids).
    ./build.sh tool
    ./build.sh firmware
else
    bash "$ROOT/build-echomate-full-image.sh" "$@"
fi
IMAGE=$ROOT/SDK/rv1106-sdk/output/image
test -s "$IMAGE/rootfs.img"
test -s "$IMAGE/oem.img"
test -s "$IMAGE/userdata.img"
test -s "$IMAGE/update.img"
if [ "${ECHOMATE_NMTUI:-0}" = 1 ]; then
    python3 "$ROOT/network-image/networkmanager/verify-ubifs-owner.py" "$IMAGE/rootfs.img"
fi
DEST=${ECHOMATE_IMAGE_DEST:-$ROOT/artifacts/echomate-network}
mkdir -p "$DEST"
for file in "$IMAGE"/*; do
    [ -f "$file" ] && cp -pL "$file" "$DEST/"
done
(cd "$DEST" && sha256sum *.img *.bin > SHA256SUMS)
cp "$ROOT/network-image/README.md" "$DEST/README.md"
echo "联网镜像及校验和：$DEST"
