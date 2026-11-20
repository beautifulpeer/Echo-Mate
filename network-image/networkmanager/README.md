# 真正的 nmtui 联网镜像

**最新 Wi-Fi 修正版：`artifacts/echomate-nmtui-wifi-fix/EchoMate-nmtui-wifi-fix.img`。修正 Wi-Fi 插件的镜像内归属，说明见 [Wi-Fi 修复](../WIFI-FIX.md)。**

**USB 驱动冲突修正版：优先烧录 `artifacts/echomate-nmtui-usbfix/update.img`，连接步骤见 [USB v2 网卡与维护串口](../USB-RECOVERY.md)。新版启用独立 PID 和 USB COM 登录口；下文旧版仅网卡的说明不再覆盖全部 USB 功能。**

此版本包含 **NetworkManager 1.42.4、nmtui、nmcli**，使用 Debian bookworm ARMhf 的原始程序。入口脚本仅指定独立 glibc 加载器并执行真正的二进制，未用自制菜单冒充 nmtui。

原厂多媒体和设备程序仍使用 uClibc；NetworkManager 的 glibc 与依赖放在 `/opt/networkmanager`，不替换 `/lib/ld-uClibc.so.0` 或原系统共享库。Wi-Fi 由 NetworkManager 和专用 D-Bus wpa_supplicant 管理，旧 Wi-Fi 管理入口关闭；USB RNDIS 保留静态地址，不受 NetworkManager 管理。

## 镜像

输出目录：`artifacts/echomate-nmtui/`，烧录其中 `update.img`。这是现有 Echo-Mate **SPI-NAND** 配置的完整镜像，不是 SD 卡镜像。按此前 SocToolKit 的整机固件步骤烧录，烧录前备份设备数据。

旧目录 `artifacts/echo-litepanel-cloud/` 的镜像不包含本次新增的 nmtui，不要混用。设备应用仍是已验证的 Python 主服务与 C 摄像头，完整 C 版迁移另行进行。

## 使用

先通过 USB 登录：电脑 USB 网卡 `192.168.137.1/24`，板子 `192.168.137.100/24`。

```sh
ssh root@192.168.137.100
# 默认密码 root
nmtui
```

选择 `Activate a connection`（激活连接），选你的 Wi-Fi，输入密码，激活后退出。

```sh
nmcli device status
nmcli device wifi list ifname wlan0
ifconfig wlan0
ip route
ping -c 3 1.1.1.1
ping -c 3 example.com
```

也可以通过 nmcli 安全地交互输入密码：

```sh
nmcli --ask device wifi connect '你的SSID' ifname wlan0
```

连接配置保存到 `/userdata/NetworkManager/system-connections/`，重新启动自动重连。此版本不会自动导入旧 `echo-network` 保存的 Wi-Fi，请首次用 nmtui 配置。RTL8723BS 仍然只支持 2.4GHz，软件不能增加 5GHz 能力；双频同名可以先直接连接，认证不兼容时再检查路由器 WPA2/WPA3/PMF 设置。

USB 共享上网仍可运行 `echo-network usb-share`；电脑必须开启 Internet 连接共享。`echo-network` 不带参数会打开真正的 nmtui。

## 排查

```sh
nmcli --version
NetworkManager --version
tail -n 100 /var/log/NetworkManager.log
ps | grep -E 'NetworkManager|wpa_supplicant'
/etc/init.d/S99znetwork restart
```

不要额外手动运行另一套 wpa_supplicant/udhcpc。如 nmtui 提示服务未运行，先检查日志和 D-Bus，不要把这个问题归因于密码。

## 重建

已准备运行目录的本机直接执行：

```bash
PATH=/tmp/echomate-build-tools/usr/bin:$PATH bash build-echomate-nmtui-image.sh --package-only
```

首次恢复依赖：

```bash
python3 network-image/networkmanager/fetch-packages.py /tmp/echo-nm-packages
python3 network-image/networkmanager/build-bundle.py \
  --packages /tmp/echo-nm-packages \
  --output artifacts/networkmanager-armhf/runtime
bash build-echomate-nmtui-image.sh
```

`packages.json` 固定包版本、发行版路径和 SHA256。构建工具只提取用户态二进制和所需库，不执行 Debian 安装脚本，不把 systemd 或 Debian 的启动体系移植进原系统。构建目录内保留主要组件版权文件及包清单。

NetworkManager 配置依据：[官方 NetworkManager.conf 文档](https://www.networkmanager.dev/docs/api/1.40.12/NetworkManager.conf.html)。

## 验证边界

已完成 73 个独立 ARM ELF 文件依赖检查，并在 Cortex-A7 用户态模拟中运行真实 NetworkManager/nmcli 的版本命令、nmtui 帮助命令和 wpa_supplicant 版本命令。启动脚本、持久化路径、USB 排除配置与原 uClibc 程序保留情况也已检查。

尝试在独立网络命名空间中进一步启动 ARM 服务时，当前 QEMU 6.2 对 `socket(AF_NETLINK, SOCK_RAW, NETLINK_GENERIC)` 返回 EPROTONOSUPPORT，而同一命名空间的主机原生程序可创建此套接字。因此没有把这项模拟测试记为通过，该模拟结果不作为联网通过依据。随后用户在 RV1106 实机修正插件归属后已确认 Wi-Fi 连接成功；本次重新打包的完整镜像及重启重连仍需烧录后验证。
