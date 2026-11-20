# nmtui Wi-Fi 插件归属修正版

完整镜像：`artifacts/echomate-nmtui-wifi-fix/EchoMate-nmtui-wifi-fix.img`，与该目录的 `update.img` 相同。适用于本项目 Echo-Mate RV1106 SPI-NAND 配置，包含 USB 网卡、USB 维护串口、nmtui、ifconfig 和设备应用。

## 修复内容

实机曾报告 `GENERAL.NM-PLUGIN-MISSING: yes`，Wi-Fi 插件归属为 `1000:1000`。修正 `/opt/networkmanager` 的归属为 `0:0` 并重启服务后，用户已确认连接成功。

SDK 内置的静态 `mkfs.ubifs` 不受 fakeroot 的文件归属模拟影响。本次在源打包脚本中加入 `-U`，使文件及子目录以 root 归属写入 UBIFS。该工具对根目录 inode 有独立处理，校验报告单独记录它；NetworkManager 运行文件与插件及其子目录必须为 `0:0`。打包入口刷新缓存工具，并在发布前直接校验 UBIFS 的 inode 和 CRC，避免只检查暂存目录。

## 烧录与连接

1. 备份板上需要保留的数据。你当前已修复并联网的设备无需为了这次修复立即重刷。
2. 在 SocToolKit 底部“固件…”选择本目录完整镜像，使用“升级”。不要将完整镜像当作地址 0 的单个分区下载。
3. 烧录成功后关闭工具，松开 BOOT，重新正常上电。
4. 按 `USB-RECOVERY.md` 用 USB COM 口登录，执行 `nmtui` 选择 Wi-Fi 并输入密码。新烧录系统可能需要重新配置网络。
5. 执行以下命令检查：

```sh
export PAGER=cat
nmcli device status
nmcli -f GENERAL.NM-PLUGIN-MISSING device show wlan0
nmcli device wifi list ifname wlan0
ifconfig wlan0
```

插件缺失应显示 `no`；连接成功后 wlan0 显示 `connected` 且取得 IP。芯片只支持 2.4GHz。

## 重建与验证

已有编译结果时：

```sh
bash build-echomate-wifi-fix-image.sh --package-only
```

完整重建去掉 `--package-only`。构建需要 SDK 的原有主机依赖和可工作的 fakeroot 环境。

`IMAGE-OWNERSHIP.json` 来自生成后的 rootfs 镜像。`SHA256SUMS` 用于校验发布文件。此修复有实际 UBIFS 生成回归测试；新完整镜像尚未代替用户烧录验证。
