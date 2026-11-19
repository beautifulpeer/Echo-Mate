# Echo-Mate RV1106 USB 真扩展屏：完整实现与安装指南

> 目标：把 RV1106 的 320×240 LCD 作为 Windows 的真正扩展屏。插入 USB 后自动扩展、自动推流；不依赖 Wi-Fi、RNDIS、VLC 或虚拟机。

## 1. 最终架构

```text
Windows 扩展桌面
  → Echo-Mate IDD 虚拟显示驱动
  → D3D11 取得桌面帧
  → 缩放至 320×240，转换为 RGB565
  → RVDS 帧协议
  → Windows USB CDC-ACM（COMx）
  → RV1106 USB Gadget（/dev/ttyGS0）
  → usb_displayd_serial
  → /run/usb-display.rgb565
  → LVGL USBDisplayPage
  → LCD
```

Windows 将 `Echo-Mate USB Display` 当作标准显示器。RV1106 则模拟为 CDC-ACM 串口，Windows 使用系统自带的 `usbser.inf`。

## 2. 适用条件

- Windows 11 x64（驱动 INF 当前声明最低 build 22000）。
- RV1106/RV1103 Linux，USB OTG 控制器支持 ConfigFS Gadget。
- LCD 分辨率为 320×240、RGB565。其他分辨率需要同时修改 Windows 驱动和接收端源码。
- 一根支持数据传输、接触可靠的 USB 线。
- RV1106 内核必须启用：

```text
CONFIG_USB_GADGET=y
CONFIG_USB_CONFIGFS=y
CONFIG_USB_CONFIGFS_ACM=y
CONFIG_USB_LIBCOMPOSITE=y
```

## 3. 安装包内容

```text
usb副屏/
├── USB副屏完整实现与安装指南.md
├── Windows/
│   ├── 一键安装.cmd / 一键安装.ps1
│   ├── 重启推流.cmd / 重启推流.ps1
│   ├── watch-echomate-usb.ps1
│   ├── EchoMateUsbDisplayTest.cer
│   ├── driver/
│   │   ├── IddSampleDriver.inf
│   │   ├── IddSampleDriver.dll
│   │   ├── iddsampledriver.cat
│   │   └── IddSampleApp.exe
│   └── source/Driver.cpp、Driver.h
└── RV1106/
    ├── install.sh
    ├── S50usbdevice
    ├── usb_displayd_serial
    ├── main-usb-display
    ├── source/usb_displayd_serial.c
    └── ui/ui_USBDisplayPage.*、ui_HomePage.c
```

请安装后保留整个文件夹，Windows 计划任务使用这里的绝对路径。

## 4. RV1106：内核准备（只做一次）

先在板上检查：

```sh
zcat /proc/config.gz | grep -E 'CONFIG_USB_(GADGET|CONFIGFS|CONFIGFS_ACM|LIBCOMPOSITE)='
```

如果没有 `CONFIG_USB_CONFIGFS_ACM=y`，在 SDK 内核配置中启用：

```text
Device Drivers
  → USB support
    → USB Gadget Support
      → USB functions configurable through configfs
        → ACM (serial) function
```

重新编译内核/固件并按开发板原厂烧录方式更新 boot/kernel 分区。不同厂商分区布局不同，不要在未确认分区表时照抄 `dd` 或写 MTD 命令。更新后再次用上面的命令确认。

本项目当前使用：

```text
VID=0x2207
PID=0x1005
Windows 端接口=USB Serial Device (COMx)
RV1106 端接口=/dev/ttyGS0
```

## 5. RV1106：运行时一键安装

把整个 `RV1106` 文件夹复制到开发板，例如 `/root/RV1106-usb-display`，然后：

```sh
cd /root/RV1106-usb-display
chmod +x install.sh
./install.sh
```

该命令会：

1. 备份原 `/etc/init.d/S50usbdevice` 和接收程序；
2. 安装 `/root/bin/usb_displayd_serial`；
3. 安装开机脚本 `/etc/init.d/S50usbdevice`；
4. 关闭 RNDIS/ADB/FunctionFS Display，仅启用 CDC-ACM；
5. 重启 USB Gadget 与接收服务。

如果开发板与本项目硬件、库和 GUI 完全相同，并希望同时覆盖已编译的主程序：

```sh
./install.sh --install-main
```

其他板型不要直接覆盖 `main`，按第 6 节把 UI 源码合入自己的工程。

验证：

```sh
ls -l /dev/ttyGS0
ps | grep '[u]sb_displayd_serial'
cat /sys/class/udc/*/state
```

正常应存在 `/dev/ttyGS0`，接收进程存在；USB 接到电脑后 UDC 状态应为 `configured`。

## 6. RV1106：把显示页合入自己的 GUI

参考 `RV1106/ui/` 中三个文件：

- `ui_USBDisplayPage.c/.h`：创建副屏页面、定时读取帧缓冲文件并刷新 LVGL 图像。
- `ui_HomePage.c`：摄像头/副屏图标的页面跳转示例。

接收端输出文件格式：

```text
偏移 0：uint32_t sequence
偏移 4：320 × 240 × 2 字节 RGB565 像素
文件：/run/usb-display.rgb565
```

GUI 定时器只在 `sequence` 改变时刷新，避免读取半帧。将源文件加入项目 CMakeLists，注册页面创建/销毁函数，并把入口图标事件切换到该页面。若 LCD 字节序不同，需要在 UI 或发送端调整 RGB565 高低字节。

## 7. Windows：一键安装

1. 将整个 `usb副屏` 文件夹复制到 Windows 本地磁盘，路径可含中文，但安装后不要移动。
2. 双击 `Windows/一键安装.cmd`。
3. UAC 提示选择“是”。
4. 等待窗口显示：

```text
SUCCESS：驱动、发送端、自动扩展均已安装。
Sender: Running
Auto extend: Running
```

安装器会：

- 把测试签名证书加入本机 Root 和 TrustedPublisher；
- 安装 `Echo-Mate USB Display` IDD 驱动；
- 创建 `EchoMateUsbDisplay` 开机发送任务；
- 创建 `EchoMateUsbAutoExtend` 登录监控任务；
- 检测设备插入后自动执行扩展模式。

### 测试签名说明

当前包使用自签名测试证书，适合开发验证，不适合商业发行。如果 Windows 因安全策略拒绝驱动，需要在管理员终端启用测试签名后重启：

```bat
bcdedit /set testsigning on
```

若开启了 Secure Boot，测试签名可能仍被阻止。产品化时应使用 Microsoft Hardware Dev Center/Attestation 或 WHQL 正式签名，不能要求普通用户长期启用测试模式。

## 8. 使用方法

1. Windows 登录完成，RV1106 正常开机。
2. 在 RV1106 上进入 USB 副屏页面。
3. 用 USB 数据线连接电脑和 RV1106 OTG 口。
4. Windows 应出现 `USB Serial Device (COMx)`。
5. 约 2～5 秒后自动切换为扩展屏并开始显示。
6. 在 Windows“设置 → 系统 → 显示”中拖动 Echo-Mate 屏幕位置，选择主屏左侧或右侧。

拔出 USB 后监控器继续等待；再次插入会重新执行扩展模式。发送端会按设备 VID/PID 从注册表寻找 COM 口，不依赖固定的 COM5 编号。

## 9. 数据协议

每一帧为 16 字节小端帧头加 153600 字节 RGB565：

```c
struct frame_header {
    uint8_t  magic[4];      // "RVDS"
    uint16_t width;         // 320
    uint16_t height;        // 240
    uint32_t payload_size;  // 153600
    uint32_t sequence;
};
```

接收端会扫描 `RVDS` 魔数重新同步，因此 USB 短暂断开或字节错位后可以恢复。

## 10. 故障排查

### 一直显示 `waiting for usb display...`

按顺序检查：

1. Windows 设备管理器是否有 `USB Serial Device (COMx)`。
2. 是否有 `Echo-Mate USB Display`，且没有黄色感叹号。
3. 任务计划程序中 `EchoMateUsbDisplay`、`EchoMateUsbAutoExtend` 是否为 Running。
4. 双击 `Windows/重启推流.cmd`。
5. RV1106 执行：

```sh
ls -l /dev/ttyGS0
ps | grep '[u]sb_displayd_serial'
ls -l /run/usb-display.rgb565
```

### 没有 COM 口

- 更换短且质量可靠的数据线；很多线只能供电。
- 检查 USB 插座、焊点和 OTG 方向。
- VMware 若自动捕获设备，在 VMware 菜单将 RV1106 USB 断开并交还 Windows 主机。
- 确认内核 `CONFIG_USB_CONFIGFS_ACM=y`。
- 执行 `/etc/init.d/S50usbdevice restart`。

### 有 COM 口但没有画面

- 双击 `重启推流.cmd`，释放断线前残留的串口句柄。
- 执行 `DisplaySwitch.exe /extend` 或在 Windows 设置中选择“扩展这些显示器”。
- 检查 `/run/usb-display.rgb565` 的修改时间/sequence 是否变化。

### 颜色、方向或尺寸不对

- 分辨率必须在 Windows 驱动、接收端和 UI 三处一致。
- RGB565 红蓝颠倒时检查 RGB/BGR 排列。
- 图像旋转应在 Windows 捕获转换或 LVGL 页面中统一处理，不要两端同时旋转。

## 11. 移植到其他开发板

需要替换的只有四层：

1. 内核：启用 USB Gadget ConfigFS ACM。
2. Gadget 脚本：按目标 UDC 名称、VID/PID 和启动系统改写。
3. 显示接收：保留 RVDS 协议，把 RGB565 帧交给目标 framebuffer/DRM/LVGL。
4. Windows 驱动：修改目标分辨率、刷新率以及 USB VID/PID。

如果目标设备没有 USB Device/OTG 控制器，就不能采用 CDC-ACM Gadget；应改用以太网/Wi-Fi 推流、UVC、DisplayLink 类芯片或带原生 DP/HDMI 输入的方案。

## 12. 产品化建议

- 用 WinUSB 或 USB bulk function 取代 CDC-ACM，可获得更高吞吐和更清晰的流控。
- 增加帧长度校验、CRC、压缩与关键帧机制。
- USB 断开时让 Windows 端关闭串口并指数退避重连。
- 正式申请 VID/PID，并完成微软驱动正式签名。
- 将分辨率、旋转、像素格式做成握手协商，避免写死 320×240。

当前版本是可运行的 RV1106 320×240 RGB565 开发验证方案，也是移植到同类 Linux 开发板的参考基线。
