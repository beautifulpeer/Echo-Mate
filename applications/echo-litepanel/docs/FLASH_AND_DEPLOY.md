# RV1106 整体烧录和设备应用部署

> **nmtui 版本更新：** 现在需要真正 nmtui 时，烧录 `artifacts/echomate-nmtui/update.img`，以该目录 `SHA256SUMS` 为准。下文旧镜像的大小和哈希只适用于旧版，不能用于新版。新版登录后运行 `nmtui`，选择 `Activate a connection` 配网，使用 `nmcli device status`、`ifconfig wlan0` 查看结果。Wi-Fi 配置保存在 `/userdata/NetworkManager/system-connections/`。完整说明见仓库 `network-image/networkmanager/README.md`。


当前可烧录产物：`artifacts/echo-litepanel-cloud/update.img`，137216586 字节，SHA256：

```text
da5247d4db8b7361561e7327ff849a3efb7487183e290e37e3e431ca633ab7df
```

此产物是当前 SPI-NAND 配置的完整镜像，包含 Python 设备主服务和 C 摄像头程序，不是完整 C 版，也不是 SD 卡镜像。软件已编译/测试，尚未实机烧录验证。烧录会覆盖分区，先备份设备上的文件和配置。首次测试将车轮架空。

## 1. 电脑上准备镜像

Ubuntu 开发机：

```bash
cd /home/lubancat/lzd/Echo-Mate/artifacts/echo-litepanel-cloud
sha256sum -c SHA256SUMS
```

将 `update.img` 复制到 Windows，例如 `D:\EchoMate\update.img`。在 PowerShell 校验：

```powershell
Get-FileHash D:\EchoMate\update.img -Algorithm SHA256
```

使用当前已生成的镜像即可，不需要为了首次烧录重新编译。

## 2. Windows 烧录 SPI-NAND

1. 打开仓库 `SDK/rv1106-sdk/tools/windows/SocToolKit/SocToolKit.exe`，选择 RV1106。
2. 若电脑尚未安装 Rockchip USB 烧录驱动，按工具附带的驱动说明先安装。烧录驱动与开机后的 RNDIS 网络驱动是两件事。
3. 开发板断开电源，按住 BOOT，插入支持数据的 USB 线，连接后松开 BOOT。
4. 等工具识别为 Maskrom。若没有识别，检查 USB 线、驱动及是否把设备连接到了运行烧录工具的电脑；虚拟机用户还要确认 USB 设备归属。
5. 在固件下载界面选完整的 `update.img`，按工具的固件下载流程执行，等待成功。不要把 update.img 当作 rootfs 单分区文件，也不要写到 SD 卡。
6. 正常情况下不必先擦除 NAND；只有明确需要恢复/处理分区异常时，再按原 SDK 文档操作。
7. 成功后松开 BOOT，重新上电，等待 Linux 启动。此镜像关闭了原桌面主程序，屏幕无原菜单不等于没有启动。

配图见仓库 `SDK/README.md` 的 NAND 烧录章节。Ubuntu 用户也可以从工程根目录启动 `./SDK/rv1106-sdk/tools/linux/SocToolKit/SocToolKit`，使用同样的 GUI 流程；缺少 GUI 依赖时按工具错误补齐。

## 3. USB 登录

开机后的 USB 设备应为 RNDIS 网卡。先在 Windows 的 `ncpa.cpl` 中找到对应网卡，配置电脑这一侧 IPv4：

```text
IP：192.168.137.1
掩码：255.255.255.0
网关：留空
DNS：留空
```

PowerShell：

```powershell
ping 192.168.137.100
ssh root@192.168.137.100
```

初始密码 `root`。如果首次烧录后提示旧 SSH 主机密钥变化，确认地址确实是这块板子后，执行 `ssh-keygen -R 192.168.137.100` 再连接。

若没有 USB 网卡，先查 Windows 设备管理器的 RNDIS 驱动；USB 副屏串口已关闭，不能将它当作 Linux 调试串口。无法通过 USB 登录时，使用板子原有的调试 UART 入口，接线和串口参数按原硬件资料设置。

## 4. 在板子上连接 Wi-Fi

下列命令在 SSH 登录后的 RV1106 上执行：

```sh
echo-network
# 或命令行交互输入密码：
echo-network connect '你的WiFi名称'
echo-network status
ifconfig wlan0
route -n
ping -c 3 1.1.1.1
ping -c 3 example.com
```

密码不会作为命令行参数传入；配置保存后开机重连。Wi-Fi 芯片仅支持 2.4GHz，可以先连接双频同名 SSID。连接失败时先查扫描结果和认证状态；必要时测试 WPA2-PSK/AES 的 2.4GHz IoT 网络。真正 nmtui 没有启用，本镜像提供的是 echo-network 菜单。

如果 Wi-Fi 暂时不可用，在 Windows 当前能上网的网卡属性中启用 Internet 连接共享，目标选 RNDIS 网卡，确认电脑端 IP 是 192.168.137.1。板子执行：

```sh
echo-network usb-share
ping -c 3 1.1.1.1
ping -c 3 example.com
```

单独的 USB 静态 IP 只负责本地登录，不能自动提供互联网。usb-share 当前要求电脑响应 ping；重新开机后需要使用共享时再执行。

## 5. 检查设备应用

应用已包含在整体镜像里，并通过 `/etc/init.d/S99zzlitepanel` 自启动：

```sh
ls -l /opt/echo-litepanel/server.py /usr/bin/echo-camera
cat /var/run/echo-litepanel.pid
ps | grep -E 'server.py|echo-camera'
tail -n 100 /var/log/echo-litepanel.log
netstat -lnt | grep -E ':9000|:9002|:9003'
```

手动管理：

```sh
/etc/init.d/S99zzlitepanel stop
/etc/init.d/S99zzlitepanel start
/etc/init.d/S99zzlitepanel restart
```

摄像头出现故障时主服务仍可启动，单独检查日志；没有完整能力握手时不发送控制心跳，不是网络断开。

## 6. 云端尚未部署时，先做局域网验证

电脑与板子连接同一可互通网络，或电脑通过 USB 直连板子。在 Ubuntu 开发机执行：

```bash
cd /home/lubancat/lzd/lite-panel
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python server.py
```

打开 `http://127.0.0.1:8765`，选择真实设备和 Wi-Fi/TCP，填板子的 wlan0 IP、9000 端口；USB 直连调试时可填 `192.168.137.100`、9000。这里选择 Wi-Fi/TCP 是因为通信使用 IP 网络，不是 USB CDC 串口。

等待设备属性握手，再依次验证方向/停止、摄像头和低音量音频。网页只显示设备声明的能力；GPIO 初始化失败时不会声明小车模块。当前不提供 PWM 调速。

摄像头可直接访问 `http://板子IP:9002/api/camera`、`http://板子IP:9002/snapshot.jpg`、`http://板子IP:9003/stream`。语音测试使用电脑 localhost 页面并授予麦克风权限。

## 7. 以后接云端

目前不用创建 cloud.json，也不用填写占位服务器；保持云端预留即可。只有云端 Broker 准备好后，再在设备上执行：

```sh
mkdir -p /userdata/echo-litepanel
chmod 700 /userdata/echo-litepanel
cp /opt/echo-litepanel/cloud.example.json /userdata/echo-litepanel/cloud.json
chmod 600 /userdata/echo-litepanel/cloud.json
vi /userdata/echo-litepanel/cloud.json
/etc/init.d/S99zzlitepanel restart
```

填写真实 Broker 域名、端口、TLS 和账号密码。云端上位机选择 MQTT，上行 `devices/echo-mate001/up`、下行 `devices/echo-mate001/down`；设备主动连接 Broker，不要求云服务器直接访问板子的局域网 IP。详细 ACL、TLS 和上位机语音补丁见同目录 `USAGE.md`。

## 8. 后续只更新设备软件

一般不需要重新烧整机。现阶段上传的是 `runtime/` Python 服务；C 版还未完成，不要手动将迁移中的 C 源码当可执行程序上传。开发机可先暂存：

```bash
cd /home/lubancat/lzd/Echo-Mate
ssh root@192.168.137.100 'mkdir -p /userdata/echo-litepanel/update'
scp -O -r applications/echo-litepanel/runtime/. root@192.168.137.100:/userdata/echo-litepanel/update/
```

在板子上停止服务、保留旧目录并替换：

```sh
/etc/init.d/S99zzlitepanel stop
sleep 3
# 确认上述 server.py 进程确实退出后继续
ps | grep '[s]erver.py'
# 备份目录若已存在，请先换成不同名字
mv /opt/echo-litepanel /opt/echo-litepanel.before-update
mkdir -p /opt/echo-litepanel
cp -a /userdata/echo-litepanel/update/. /opt/echo-litepanel/
cp /opt/echo-litepanel.before-update/cloud.example.json /opt/echo-litepanel/
/etc/init.d/S99zzlitepanel start
tail -n 100 /var/log/echo-litepanel.log
```

保留 `/userdata/echo-litepanel/cloud.json` 中的真实配置。上述更新不更新 C 摄像头二进制或启动脚本；改动这些内容时需使用配套交叉编译产物，或重新构建整体镜像。
