# Echo-Mate 联网镜像

**需要真正 nmtui 时，请使用新版 `artifacts/echomate-nmtui/update.img`，说明见 [nmtui 镜像](networkmanager/README.md)。下文描述的旧版 echo-network 菜单方案与新版不同，不要混用镜像。**

面向当前选中的 Echo-Mate RV1106 SPI-NAND 配置。关闭 USB 副屏和桌面主程序自启动，保留屏幕、音频、摄像头及蓝牙相关驱动。USB 改为单独的 RNDIS 虚拟网卡；Wi-Fi 增加持久化配置、开机重连和终端菜单。

## 硬件和当前联网方式

- 官方参数及本地 README：RV1106，单核 ARM Cortex-A7，256MB DDR3L；无线芯片 RTL8723BS；屏幕 P024C128-CTP，显示 SPI、触摸 I²C。
- 本地设备树：Wi-Fi 走 SDIO，蓝牙走 UART0，USB 为 peripheral；触摸为 FocalTech，I²C 地址 0x38；摄像头 IQ 配置同时包含 SC3336 和 SC4336。没有读到实物识别信息，不能据此断定实际摄像头型号、触摸芯片具体料号或存储容量。
- 当前系统为 Buildroot + uClibc，默认用 `wpa_supplicant` 关联 Wi-Fi，再用 `udhcpc` 获取 IP。旧启动脚本中的 `start_desk_bot` 未启用，因此不能认为旧镜像已经自动连接 Wi-Fi。
- BusyBox 已启用 `CONFIG_IFCONFIG=y`。`ifconfig` 能查看 IP 或配置接口，Wi-Fi 密码认证仍由 `wpa_supplicant` 完成。
- SDK 包含 NetworkManager 1.40.10 和 `BR2_PACKAGE_NETWORK_MANAGER_TUI`，但该包明确依赖 glibc 和 udev。当前 uClibc 工具链不能直接编入真正的 `nmtui`。这里提供的命令是 **`echo-network`，不是 nmtui**。若必须使用真正的 nmtui，需要另做 glibc 系统并验证厂商多媒体库兼容性，或采用 SD 卡上的其他发行版。

官方资料：[参数](https://no-chicken.com/content/Echo-Mate/0.%E5%8F%82%E6%95%B0%E4%BB%8B%E7%BB%8D.html)、[联网操作](https://no-chicken.com/content/Echo-Mate/5.%E5%BC%80%E5%8F%91%E6%9D%BF%E6%93%8D%E4%BD%9C.html)。

## 构建

按 `SDK/README.md` 安装构建依赖；额外确保主机有 `python3` 和 `gperf`。

```bash
bash build-echomate-network-image.sh
```

脚本使用现有完整镜像构建入口，打包时应用联网配置。完整构建成功后，才把镜像复制到 `artifacts/echomate-network/` 并生成 `SHA256SUMS`。`SDK/rv1106-sdk/output/image` 中仅有 boot/uboot 等文件不代表完整镜像已经成功。

系统已编译成功、只需重新打包时，可以执行 `bash build-echomate-network-image.sh --package-only`。受限沙箱中的 fakeroot 可能无法模拟文件所有权；此时应在正常主机终端重新打包，不要忽略所有权错误继续烧录。

此入口沿用当前板级分区表，**只适用于已确认匹配的 SPI-NAND 板型**。烧录前备份板上的配置和数据，按官方 SocToolKit NAND 步骤操作；不能当作 SD 卡镜像直接写入。未授权自动烧录，本脚本只生成文件。

## USB 优先联网（Windows）

1. 用支持数据传输的 USB 线连接板子。设备应枚举为 RNDIS 网卡，不再枚举 USB 副屏串口。Windows 是否自动匹配驱动须在实机验证。
2. 在 Windows 网络适配器中，将当前能上网的 Wi-Fi/以太网连接的“Internet 连接共享”开启，共享给板子的 RNDIS 网卡。确认电脑这一侧为 `192.168.137.1/24`。
3. 板子固定为 `192.168.137.100/24`。电脑可通过 `ssh root@192.168.137.100` 登录；当前 SDK 默认密码为 `root`。
4. 在板子运行 `echo-network usb-share`，添加低优先级的 USB 默认路由，并在没有 Wi-Fi 默认路由时使用电脑的 DNS。
5. 检查 `ping -c 3 192.168.137.1`、`ping -c 3 1.1.1.1`、`ping -c 3 example.com`，依次区分本地 USB、互联网转发和 DNS。

仅出现 USB 网卡并不等于可上互联网，必须启用电脑共享。Linux/macOS 主机的共享地址及驱动方式不同，此预设不宣称已经支持。USB 默认不抢 Wi-Fi 路由；重新开机后如需走共享上网，再运行 `echo-network usb-share`。该命令目前要求电脑响应 ping。

## Wi-Fi

通过调试串口或 USB SSH 登录，执行：

```bash
echo-network                 # dialog 菜单，支持 SSH 终端
echo-network scan            # 显示频点、SSID 和认证能力
echo-network connect '你的SSID' # 交互输入密码，不写入命令行历史
echo-network status
ifconfig wlan0
ifconfig usb0
```

支持 WPA2 Personal。配置保存到 `/userdata/network/wpa_supplicant.conf`，权限 0600；保存的是派生 PSK，仍属于敏感凭据。切换网络会替换当前配置；重新启动保留配置并重连。首次连接没有立即拿到地址时，稍后用 `echo-network status` 查看 `wpa_state=COMPLETED` 和 IP。

RTL8723BS 的 Wi-Fi 为 2.4GHz 802.11b/g/n，不能连接 5GHz。2.4/5GHz 同名路由可以先保持现状，设备只会扫描到自身支持的频段。连接失败时请依次检查：

- 路由器确实启用 2.4GHz，使用 WPA2-PSK/AES；先避免 WPA3-only、强制 PMF 或企业认证。
- 如果双频引导反复拒绝连接，尝试临时关闭频段引导，或单独创建 2.4GHz IoT/访客网络；是否需要此步骤以实测为准。
- `iw dev wlan0 scan` 能否看到目标 SSID；`wpa_cli -i wlan0 status` 是否完成认证；完成认证后 DHCP 是否得到 IP。
- 配置已保存但没接口时，检查 `dmesg` 的 RTL8723BS/SDIO 信息和 `/oem/usr/ko/insmod_wifi.sh`。不要同时手动启动另一套 wpa_supplicant 或桌面程序管理 Wi-Fi。

## lite-panel 与小车扩展

指定项目：https://gitee.com/laingzd/lite-panel 。已根据用户提供的 `/home/lubancat/lzd/lite-panel` 检查真实源码。上位机部署在云端，设备端是独立的 `applications/echo-litepanel/`，通过 Wi-Fi 上网主动连接云端 MQTT Broker；不是在板子上运行整套上位机。

镜像会安装这个独立设备服务，并关闭原 IPC 启动入口与 DeskBot 自启动。服务复用原电机 GPIO/方向电平，提供 700ms 运动超时停车、LP Binary v1、MQTT JPEG 图像以及 ALSA 音频。云端域名和账号尚待填写，不包含真实云端凭据。云端语音需要应用目录提供的上位机补丁；没有直接修改用户的 lite-panel 原目录。完整说明见 [独立应用说明](../applications/echo-litepanel/README.md)。

构建独立应用镜像用 `bash applications/echo-litepanel/build-image.sh`，产物在 `artifacts/echo-litepanel-cloud/`。Buildroot 镜像不是 Debian/Ubuntu，不包含 apt 软件源；原生扩展仍需交叉编译。屏幕和手势识别可在独立应用中后续增加；BLE 控制尚未实现，不能把蓝牙音频功能当作已有 BLE 小车控制服务。
