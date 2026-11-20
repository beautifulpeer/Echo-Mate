# Echo-Mate 设备应用

这是运行在 RV1106 上、对接云端 LitePanel 上位机的独立应用。云端 MQTT 地址和账号暂时预留。

**当前状态：已验证的运行服务仍是 Python 版；C 版分层迁移尚未完成。现有镜像不是完整 C 版，不能把 `src/` 中的迁移代码当成已经编译通过的主服务。**

## 目录

```text
echo-litepanel/
├── README.md          本目录入口与迁移状态
├── build-image.sh     镜像构建入口
├── include/echo/      C 模块公开接口
├── src/               C 版源码（迁移中）
│   ├── app/           应用层：业务、设备状态、控制逻辑（待完成）
│   ├── protocol/      协议层：LP Binary 编解码与类型化字段
│   ├── transport/     传输层：TCP、MQTT、HTTP（待完成）
│   ├── drivers/       驱动层：电机 GPIO、ALSA 音频、摄像头
│   └── platform/      平台层：POSIX、时间、配置与文件操作
├── runtime/           当前可运行的 Python 服务，供迁移验证使用
├── config/            配置模板，不存放真实密码
├── scripts/           启动与摄像头交叉编译脚本
├── tools/             Python 打包检查、上位机补丁生成工具
├── tests/             自动化测试
├── patches/           云端上位机语音补丁
├── third_party/       预留的 C 依赖目录
└── docs/              使用说明和第三方来源
```

## Python 文件分别做什么

| 位置 | 用途 |
|---|---|
| `runtime/server.py` | 当前主服务：设备握手、指令、状态和各模块调度 |
| `runtime/motors.py` | 原电机 GPIO 方向控制与 700ms 超时停车 |
| `runtime/audio.py` | ALSA 音频播放、麦克风采集与半双工对讲 |
| `runtime/camera.py` | 摄像头 JPEG 抓拍与 HTTP 预览 |
| `runtime/cloud.py` | 设备主动连接 MQTT、图像分片及重连 |
| `runtime/wire_protocol.py` | LP Binary v1 编解码，字段表在同目录 JSON 文件 |
| `tools/verify-rootfs.py` | 构建后检查运行文件、共享库与 CA 证书 |
| `tools/make-cloud-audio-patch.py` | 生成可审核的上位机语音补丁，不修改上位机原目录 |

`runtime/` 是待被 C 版替换的运行实现；`tools/`、`tests/` 中的 Python 是开发工具。后续 C 版通过测试后，再切换启动入口并移除旧运行实现，避免出现两套业务代码长期并行维护。

## 分层原则

- 应用层负责业务状态与指令，不直接操作 GPIO、声卡或套接字。
- 协议层负责二进制帧，不绑定 TCP、MQTT 或具体硬件。
- 传输层负责连接和字节收发，通过统一接口对接应用层。
- 驱动层负责真实硬件，通过头文件暴露接口，不包含网络业务。
- 平台层封装 Linux 基础能力；配置与真实凭据分开保存。

## 构建与说明

从 Echo-Mate 仓库根目录执行：

```bash
bash applications/echo-litepanel/build-image.sh
# 已完成 SDK 编译时，仅重新打包：
bash applications/echo-litepanel/build-image.sh --package-only
```

当前构建入口安装 `runtime/` 服务和 C 摄像头程序；不会把开发用的源码、工具和测试目录全部塞进设备运行目录。

详细的联网、SPI-NAND 烧录、MQTT 配置和语音补丁步骤见 [使用说明](docs/USAGE.md)。第三方来源见 [依赖说明](docs/THIRD_PARTY.md)。现有镜像尚未进行真实设备验证。

完整的烧录和首次部署步骤见 [RV1106 烧录与部署](docs/FLASH_AND_DEPLOY.md)。
