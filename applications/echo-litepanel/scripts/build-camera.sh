#!/bin/bash
set -euo pipefail
HERE=$(cd -- "$(dirname -- "$0")" && pwd)
SDK=$(cd "$HERE/../../../SDK/rv1106-sdk" && pwd)
MEDIA=$SDK/media/out
CC=$SDK/tools/linux/toolchain/arm-rockchip830-linux-uclibcgnueabihf/bin/arm-rockchip830-linux-uclibcgnueabihf-gcc
DEST=${1:?Usage: build-camera.sh ROOTFS_DIRECTORY}
mkdir -p "$DEST/usr/bin"
"$CC" -Os -Wall -Wextra -DISP_HW_V30 -DUAPI2 -DRKPLATFORM=ON \
    -I"$SDK/media/samples/common" -I"$SDK/media/samples/common/isp3.x" \
    -I"$MEDIA/include" -I"$MEDIA/include/rkaiq" -I"$MEDIA/include/rkaiq/uAPI2" \
    -I"$MEDIA/include/rkaiq/common" -I"$MEDIA/include/rkaiq/xcore" \
    -I"$MEDIA/include/rkaiq/algos" -I"$MEDIA/include/rkaiq/iq_parser" \
    -I"$MEDIA/include/rkaiq/iq_parser_v2" -I"$MEDIA/include/rkaiq/smartIr" \
    "$HERE/../src/drivers/camera_capture.c" -o "$DEST/usr/bin/echo-camera" \
    -L"$MEDIA/lib" -Wl,-rpath-link,"$MEDIA/lib" \
    -Wl,--disable-new-dtags,-rpath,/oem/usr/lib \
    -lsample_comm -lrockit -lrockchip_mpp -lrkaiq -lpthread -lm -ldl
