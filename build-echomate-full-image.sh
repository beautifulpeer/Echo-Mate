#!/bin/bash
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
SDK=$ROOT/SDK/rv1106-sdk
DESKBOT=$ROOT/Demo/DeskBot_demo
BUILD=$DESKBOT/build-rv1106-image
PACK=$SDK/sysdrv/tools/board/android-tools
TOOLCHAIN=$SDK/tools/linux/toolchain/arm-rockchip830-linux-uclibcgnueabihf/bin
CC=$TOOLCHAIN/arm-rockchip830-linux-uclibcgnueabihf-gcc
EXPECTED_BOARD=project/cfg/BoardConfig_IPC/BoardConfig-SPI_NAND-Buildroot-RV1106_Echo_Mate-DeskMate.mk

cd "$SDK"
ACTUAL_BOARD=$(readlink .BoardConfig.mk || true)
if [[ "$ACTUAL_BOARD" != "$EXPECTED_BOARD" ]]; then
    echo "错误：当前板级配置不是 Echo-Mate SPI-NAND：$ACTUAL_BOARD"
    echo "请先执行 ./build.sh lunch 并选择：$EXPECTED_BOARD"
    exit 1
fi

grep -q '^CONFIG_USB_CONFIGFS_ACM=y' \
    sysdrv/source/kernel/arch/arm/configs/echo_rv1106_linux_defconfig
grep -q '^ACM_EN=on' "$PACK/S50usbdevice"
grep -q '^RNDIS_EN=off' "$PACK/S50usbdevice"

echo '[1/5] 编译 DeskBot ARM 主程序'
cmake -S "$DESKBOT" -B "$BUILD" \
    -DTARGET_ARM=ON -DCMAKE_BUILD_TYPE=Release
cmake --build "$BUILD" --parallel "$(nproc)"
test -x "$DESKBOT/bin/main"

echo '[2/5] 编译 USB CDC-ACM 帧接收程序'
"$CC" -O2 -Wall -Wextra \
    "$PACK/usb_displayd_serial.c" \
    -o "$PACK/usb_displayd_serial"

echo '[3/5] 同步 DeskBot 运行文件到 rootfs 打包目录'
mkdir -p "$PACK/echomate-bin"
rm -rf "$PACK/echomate-bin/assets/usb-wait" \
       "$PACK/echomate-bin/assets/usb-wait-frames"
cp -a "$DESKBOT/bin/." "$PACK/echomate-bin/"
chmod 755 "$PACK/echomate-bin/main" "$PACK/usb_displayd_serial" \
    "$PACK/S50usbdevice" "$PACK/S99echomate"

if [[ "${1:-}" == '--clean' ]]; then
    echo '[4/5] 清理 SDK 历史输出'
    ./build.sh clean
else
    echo '[4/5] 增量构建（传入 --clean 可执行全清理）'
fi

echo '[5/5] 编译并打包完整 SPI-NAND 镜像'
./build.sh

echo '构建完成，镜像如下：'
find "$SDK/output/image" -maxdepth 1 -type f -printf '%f  %s bytes\n' | sort
echo 'SHA-256：'
sha256sum "$SDK"/output/image/*
