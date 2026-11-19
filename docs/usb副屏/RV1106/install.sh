#!/bin/sh
set -e
BASE="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
[ "$(id -u)" = 0 ] || { echo "请使用 root 执行"; exit 1; }
grep -q 'CONFIG_USB_CONFIGFS_ACM=y' /proc/config.gz 2>/dev/null || \
  zcat /proc/config.gz 2>/dev/null | grep -q 'CONFIG_USB_CONFIGFS_ACM=y' || \
  echo "警告：无法确认内核 CONFIG_USB_CONFIGFS_ACM=y，请按文档检查。"
mkdir -p /root/bin /root/usb-display-backup
[ -e /etc/init.d/S50usbdevice ] && cp -a /etc/init.d/S50usbdevice /root/usb-display-backup/
[ -e /root/bin/usb_displayd_serial ] && cp -a /root/bin/usb_displayd_serial /root/usb-display-backup/
cp "$BASE/usb_displayd_serial" /root/bin/usb_displayd_serial
cp "$BASE/S50usbdevice" /etc/init.d/S50usbdevice
chmod 755 /root/bin/usb_displayd_serial /etc/init.d/S50usbdevice
if [ "$1" = "--install-main" ]; then
  [ -e /root/bin/main ] && cp -a /root/bin/main /root/usb-display-backup/main
  cp "$BASE/main-usb-display" /root/bin/main
  chmod 755 /root/bin/main
fi
/etc/init.d/S50usbdevice restart
echo "SUCCESS：RV1106 USB CDC-ACM 和接收端已安装。"
echo "检查：ls -l /dev/ttyGS0; ps | grep '[u]sb_displayd_serial'"
