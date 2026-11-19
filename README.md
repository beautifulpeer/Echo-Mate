<h1 align="center">Echo-Mate</h1>

<br>

## 1. Overview

本项目是一个十分硬核，功能超多的桌面机器人。是基于RV1106，有LVGL菜单，可以陪你聊天，翻译，看天气，能跑AI相机，小巧的linux桌面助手和开发板~

硬件开源地址：https://oshwhub.com/no_chicken/ai-desktop-robot-echo

演示视频链接: https://www.bilibili.com/video/BV161ZaYyEmF/

油炸鸡开源官网手册地址: https://no-chicken.com/

<p align="center">
   <img border="1px" width="75%" src="./assets/main_pic.jpeg">
</p>



## 2. 功能演示

1. 功能演示截图

   <p align="center">
      <img border="1px" width="100%" src="./assets/show.png">
   </p>

2. Desk-Bot demo 功能表

   <p align="center">
      <img border="1px" width="75%" src="./assets/func_map.png">
   </p>

3. 开发板参数

   <p align="center">
      <img border="1px" width="75%" src="./assets/board_detail.png">
   </p>

   | 参数          | Value                  |
   | ------------- | ---------------------- |
   | 芯片          | RV1106                 |
   | 处理器        | 单核Cortex A7          |
   | NPU           | 1TOPS,支持int4、in8、int16 |
   | 内存          | 256MB DDR3L            |
   | Wi-Fi+蓝牙    | RTL8723bs              |
   | 屏幕接口      | 显示 SPI + 触摸 IIC    |
   | 屏幕型号      | P024C128-CTP           |
   | 喇叭 MIC 接口 | MX1.25mm               |
   | 存储介质      | SD卡 或 NAND FLASH     |
   | 空闲GPIO      | 8个GPIO引出排针        |

<br>

## 3. 开发环境

推荐使用 Ubuntu 22.04 LTS。此 GitHub 版本已将 Demo、LVGL 和模型源码纳入普通目录，无需初始化子模块，也不依赖 Git LFS。

```shell
git clone https://github.com/beautifulpeer/Echo-Mate.git
cd Echo-Mate
python3 scripts/setup-deps.py
```

模型保存在本仓库的 `deps-v1` Release 附件中。恢复脚本从 beautifulpeer/Echo-Mate 下载并校验大小和 SHA-256，恢复后的 `model.pt` 留在本地。首次发布时需等待 Actions 中的 Publish verified model dependency 工作流完成。若 Fork 尚未开启 Actions，请先在 Actions 页面启用并运行此工作流。

本机 API 密钥和 Wi-Fi 密码不会随仓库发布。AI 服务请先配置：

```shell
cd Demo/AIChat_demo/Server
cp .env.minimax.example .env.minimax
# 编辑 .env.minimax，填写 MINIMAX_API_KEY 和自定义 AICHAT_ACCESS_TOKEN
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
sh start_minimax.sh
```

客户端配置 `Demo/DeskBot_demo/utils/system_para.conf` 中的服务器地址、令牌和所需 API 密钥；令牌需与服务端一致。Wi-Fi 配置中 `YOUR_WIFI_SSID` 和 `YOUR_WIFI_PASSWORD` 需替换为自己的配置。

完整 SPI-NAND 镜像构建：按 SDK 文档安装依赖后，执行 `bash build-echomate-full-image.sh`；其他板型请先阅读 SDK 文档选择对应配置。Python 启动脚本默认使用当前环境的 `python3`，也可通过 `PYTHON` 指定解释器。

保留运行依赖、模型、交叉编译工具链和 USB 副屏安装文件；日志、旧备份、构建缓存和本机凭据不随发布。全量镜像编译与设备烧录尚需在对应环境验证。

SDK开发环境与系统配置详见SDK文件夹中的[README.md](./SDK/README.md).

桌面机器人demo, 如何烧录使用详见Demo文件夹的[README.md](https://github.com/No-Chicken/Demo4Echo/blob/main/DeskBot_demo/README.md).

<br>

## 4. 仓库目录说明

```
Echo-Mate/
├── Demo/                  # Echo开发板的demo
│   ├── DeskBot_demo/      # AI桌面机器人
│   └── xxx_demo/          # xxx对应的独立子demo
├── SDK/                   # SDK文件夹
│   ├── rv1106-sdk/        # 基于luckfox的SDK
│   └── README             # SDK和开发板使用相关说明
```
