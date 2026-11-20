# Echo-Mate 云端 LitePanel 设备服务

这是部署在 RV1106 上的独立应用，与原 DeskBot 分开。上位机仍部署在你的云服务器；不把上位机搬到开发板。设备通过 Wi-Fi 或电脑共享的 USB 网络，主动连接云端 MQTT Broker。

```text
浏览器（HTTPS + 麦克风权限）
           │
云服务器上的 LitePanel Python 上位机
           │ MQTT（控制/状态/音频）+ LPJ1 JPEG 分片
云端 MQTT Broker
           │ 设备主动发起 TLS 连接，可穿过普通家庭 NAT
家庭路由器 / 电脑 USB 网络共享
           │
RV1106：echo-litepanel 服务
           ├─ 原双电机 GPIO
           ├─ RV1106 ISP + VI + MJPEG
           └─ ALSA 喇叭 / 麦克风
```

## 硬件依据

不是重新猜接线：电机 GPIO 直接沿用原来已经工作过的 DeskBot 代码。

| 信号 | 引脚 | Linux GPIO 编号 |
|---|---|---:|
| MOTOR1_INA | GPIO1_A0 | 32 |
| MOTOR1_INB | GPIO1_A1 | 33 |
| MOTOR2_INA | GPIO1_A3 | 35 |
| MOTOR2_INB | GPIO1_A4 | 36 |

前进电平为 `0,1,1,0`；后退 `1,0,0,1`；左转 `1,0,1,0`；右转 `0,1,0,1`；停止为全 0。与原程序相同，此版是方向控制，没有硬件 PWM 调速，不声明 `vehicle_speed` 能力，速度指令返回失败。运动有效期 700ms，由独立线程检查；切换方向先全低再切换。断开控制连接、MQTT 断线、会话重置和正常退出都会停车。它不是硬件急停，进程被强杀、系统死机等情况仍需硬件失效保护。

屏幕、触摸、SDIO 无线和 UART 蓝牙定义保留在原内核设备树。此次不启动原桌面程序与 USB 副屏，也不启动另一套 IPC 应用抢占摄像头。蓝牙协议接入暂未实现；云端 MQTT 走 Wi-Fi 上网，BLE 不能直接替代云端互联网连接。

## 已实现的设备接口

- **主连接：主动连接云端 MQTT**。LP Binary v1，与本机 lite-panel 的编码器/字段表相同；设备声明能力，收到匹配序号 ACK 后才上报心跳。不伪造温湿度、电量等测量值。
- 上行 `devices/echo-mate001/up`；下行 `devices/echo-mate001/down`；图像 `devices/echo-mate001/up/camera`。`device_id` 可配置，主题随之变化。
- 所有发布均不 retain，设备拒绝 retained 下行消息。断网重新建立干净会话，重新握手。队列拥堵会关闭会话，不积压执行旧运动指令。公网实际延迟必须上板验证。
- 摄像头：硬件 MJPEG，640×480，采集目标 5fps；MQTT 默认目标 2fps，可配置 0～5。实际帧率、颜色、方向和传感器型号尚未实测。图像按现有 LPJ1 格式分片，单张最多 512KiB；不发送测试图。
- 音频：ALSA `plughw:0,0`，PCM S16LE、16kHz、单声道；上位机演示旋律、软件音量、半双工对讲、设备麦克风回传。音频硬件打开失败返回失败，不伪造声音。语音会话控制心跳超时约 2.5s 后关闭；实际音质、设备名和增益需要烧录验证。
- 调试连接：TCP 9000、UDP 9001 设备发现；HTTP 9002 `/api/camera`、`/snapshot.jpg`；9003 `/stream`。局域网 TCP 与 MQTT 共用一个控制会话，已有控制者时拒绝第二个。云端上位机无需访问家庭路由器后的这些端口。

## 镜像与运行

从 Echo-Mate 工程根目录构建：

```bash
bash applications/echo-litepanel/build-image.sh
# 系统/多媒体已经编译好，仅重新打包：
bash applications/echo-litepanel/build-image.sh --package-only
```

完整成功后输出到 `artifacts/echo-litepanel-cloud/`。当前是现有板级配置对应的 **SPI-NAND 镜像**，不是 SD 卡镜像。启动脚本为 `/etc/init.d/S99zzlitepanel`，应用目录 `/opt/echo-litepanel/`，日志 `/var/log/echo-litepanel.log`，原始摄像头程序 `/usr/bin/echo-camera`。

开发主机上的测试不访问真实 GPIO；真实硬件需烧录后验证。未配置云端前仍能通过本地调试入口检查服务。

## 设备连接自己的云端

目前没有你的云端域名、端口和 MQTT 账号，因此镜像不含任何可用的外部服务器或密码，也没有擅自连接公共 Broker。

先用 `echo-network` 连路由器，或通过 Windows USB 网络共享上网。然后在板子上执行：

```bash
mkdir -p /userdata/echo-litepanel
chmod 700 /userdata/echo-litepanel
cp /opt/echo-litepanel/cloud.example.json /userdata/echo-litepanel/cloud.json
chmod 600 /userdata/echo-litepanel/cloud.json
vi /userdata/echo-litepanel/cloud.json
/etc/init.d/S99zzlitepanel restart
tail -f /var/log/echo-litepanel.log
```

填写真实 `host`、端口、设备账号密码。默认使用 TLS 8883，校验证书和主机名；自签名服务器可额外设置 `"ca_file":"/userdata/echo-litepanel/ca.crt"`。TLS 需要正确的设备时间；先检查 `date` 和 NTP。这里保存的 MQTT 密码是本地配置，不能提交源码仓库。

云端 LitePanel 选择 **MQTT**，填写同一个 Broker、云端应用账号，以及上述 up/down 主题。设备账号需要订阅 down、发布 up 和 up/camera；云端账号需要相反权限。Broker 需要实际部署并配置对应 ACL、认证和 TLS。若目前只有 LitePanel 网页服务，没有 Broker，还缺这项部署。

## 云端语音的上位机补丁

现有 LitePanel 只允许 `wifi` 会话使用实时语音；运动控制和 MQTT 摄像头原本已支持。这里提供 `litepanel-cloud-audio.patch`，只将已有语音管线开放给 `mqtt`，保留 USB/BLE 限制。补丁包含父项目和独立子项目的 Python 与网页副本。

**本次没有修改 `/home/lubancat/lzd/lite-panel` 原目录，也没有部署云服务器。** 在云端上位机源码目录审核后执行：

```bash
git apply --check /path/to/litepanel-cloud-audio.patch
git apply /path/to/litepanel-cloud-audio.patch
# 重启上位机 Python 服务，并刷新网页缓存
```

若源码版本不同，可重新生成可审核补丁：

```bash
python3 applications/echo-litepanel/tools/make-cloud-audio-patch.py /path/to/lite-panel /tmp/cloud-audio.patch
```

浏览器录音需要 HTTPS（本机 localhost 除外）；云端网页使用 HTTPS，并正确代理现有 HTTP 音频接口。补丁不包含回声消除、压缩音频、视频同步或多人同时驾驶。

## 验证命令

```bash
LITEPANEL_SOURCE=/path/to/lite-panel python3 -m unittest discover -s applications/echo-litepanel/tests -v
```

兼容性测试读取真实上位机协议和 MQTT 图像解包器。电机测试使用临时 GPIO 文件，不能当作真实电机验证。第三方源码、固定版本 MQTT 客户端和公共 CA 来源见 `THIRD_PARTY.md`。


## 2026-11-20 实机修复与验证

RV1106 已通过 MQTT 连接现有云端 LitePanel，实测完成以下修复：

- 摄像头：RV1106 SDK 的 `RK_MPI_MB_Handle2VirAddr()` 返回的地址已指向当前编码包；不能再次叠加 `u32Offset`，也不能从 `u32Len` 中减去该环形缓冲区偏移。修复后本地连续 JPEG 可解码为 640×480，云端 MQTT 图片代理返回 HTTP 200。
- 云端语音：必须同时开放 `connections.py` 音频接收/发送、`server.py` 音频 GET/POST 和语音控制命令，以及 `web/voice.js` 的 MQTT 条件。原补丁漏掉了语音控制命令的限制；补丁生成器和补丁文件已补齐。
- HTTPS：公网 IP 已配置受信任 IP 证书，入口为 `https://81.70.31.79/`，HTTP 自动跳转。独立 Certbot 位于 `/opt/echo-certbot/`；`echo-certbot-renew.timer` 每日检查两次，续期后通过 `/usr/local/sbin/echo-certbot-reload` 校验并重载 Nginx。证书验证使用 `/var/www/echo-acme/`，须保持公网 80/443 端口可访问。

云端接口实测监听收到麦克风 PCM 帧；下行发送 8 帧静音 PCM，设备接收计数增加 8，语音命令收到确认。实际浏览器录音权限、声音播放和音质仍需用户在 HTTPS 页面测试。电机已由用户确认接好驱动板后正常，本次未修改电机逻辑或发送行驶指令。

云端修复前文件备份在 `/opt/litepanel/backups/audio-fix-20261120/`；开发板摄像头旧程序备份在 `/opt/echo-camera.before-jpeg-fix`。云端账户与 MQTT 密码继续保存在原有受限配置中，不写入本仓库。


## 2026-11-20 连续语音、流畅预览与访问加固

本次实机部署进一步更新为 480×272、20fps 采集目标、MJPEG Q45。云端网页通过单个持续的 MJPEG 请求观看，避免每张 JPEG 重建 HTTP 请求。设备的 `camera_fps` 支持 0～20；实际同时对讲测试中，公网预览约 18.9fps，最大帧间隔约 100ms，结果取决于网络和场景。

设备原有逐位 Python CRC 处理 30 个 PCM 包耗时约 2.68 秒；改为协议兼容的 `binascii.crc_hqx` 后约 0.07 秒。WebSocket 输出掩码同样改用原生 XOR。语音使用最多 8 帧的 HTTP 批次、独立有界播放队列、短暂抖动缓冲和 ALSA 低延迟缓冲；不会因扬声器背压堵住控制读取。旧语音可丢弃，运动指令超过时限仍会关闭会话。8 秒浏览器测试上传 193 帧静音 PCM，设备收到 191 帧，连接和心跳持续正常；实际声音仍需现场试听。

云端需先应用 `patches/litepanel-cloud-audio.patch`，再应用配套的 `patches/litepanel-streaming.patch`；已有修改的服务器应先检查补丁，避免覆盖部署差异。已部署源文件的备份在服务器 `/opt/litepanel/backups/talk-stream-fix-20261120/`。

设备通过 `wss://81.70.31.79/mqtt`、443 端口连接，启用 TLS 并验证证书。公网明文 1883 已关闭；服务器内部 1883 和 WebSocket 9004 都只绑定 127.0.0.1。设备和网页后端使用不同随机密码与既有最小主题 ACL。启动脚本在存在云配置时，将本地 9000/9002/9003 接口限制到回环地址。排障需通过 SSH 读取本地接口；没有云配置时仍提供原有局域网首次调试入口。

网页登录已替换初始弱密码，服务器只保存加盐哈希；新登录信息应由用户本地保管，不提交仓库。HTTPS Cookie 带 Secure；登录入口按 IP 限速；未登录访问摄像头接口返回 401。示例 Nginx、Mosquitto 和证书续期配置位于 `config/deployment/`，不包含实际凭据。

上述方案是用户选择的“继续使用云端网页并加强登录、传输加密”，不是端到端加密。若云服务器被完全控制，攻击者仍可能读取服务器解密后的媒体或篡改网页；抵御该威胁需要独立可信观看端和端到端密钥管理。

最终回归：15 项测试中 13 项通过、2 项需要专用 MQTT 测试 Broker 而跳过，真实 Chrome 已验证 480×272 连续预览、保存配置断开重连、持续对讲与登录 Cookie。测试凭据临时副本已清理。


## Wi-Fi 信号与本地源码备份

设备在后台每 5 秒通过 `iw dev wlan0 link` 读取真实 dBm，并上报 `wifi_rssi` 与 `wifi_signal_age_ms`；不会把 `/proc/net/wireless` 中驱动返回的正数百分比当作 dBm。网页将 Wi-Fi 信号与 MQTT 在线/超时状态分开显示，并显示四格、等级和数值。没有有效读数或超过 15 秒时，不把缓存值当作当前信号。实机验证约 -45dBm、4/4 格、很好。

最新界面顺序为视频预览在上、小车控制在其下方、活动日志最后；电脑与手机宽度均已验证。电脑端源码备份保存在 `artifacts/cloud-backup-20261120-094349/`，同名 `.tar.gz` 带 SHA256 校验文件。备份包括实际云端源码、Nginx/MQTT/systemd 配置和配套设备 runtime；账户密码、私钥、录像及运行数据应单独保管。信号显示变更补丁为 `patches/litepanel-wifi-signal.patch`。
