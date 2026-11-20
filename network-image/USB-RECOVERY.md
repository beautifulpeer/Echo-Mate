# USB v2：网卡和维护串口

新版镜像输出：`artifacts/echomate-nmtui-usbfix/update.img`。请使用这个新目录，旧的 nmtui 镜像不含本修正。仍为 Echo-Mate SPI-NAND 完整镜像，烧录前备份设备数据。

构建入口：`bash build-echomate-usbfix-image.sh --package-only`（系统已编译时）。发布目录中的 `EchoMate-nmtui-usbfix.img` 与 `update.img` 内容相同，可用带版本名称的文件避免选错旧镜像。

## 本次修复

- 原网卡沿用 `2207:0006`，与电脑上已有 ADB 驱动绑定冲突。新开发镜像使用 `2207:4E4D`，并更新产品字符串、设备版本和序列号后缀，避免继续使用旧设备缓存。此 PID 仅用于本地开发，不宣称是正式分配的产品 PID。
- 按 Windows IAD 复合设备规范明确设置设备类别 `EF/02/01`，RNDIS 类别 `E0/01/03`，在绑定 UDC 前完成 Microsoft OS 描述符、接口顺序和配置链接。
- 移除不适用于此 SDK 内核的 `wceis` 写入，使用源码中实际支持的 class/subclass/protocol 属性。只创建实际需要的函数。
- 同时启用 CDC ACM 维护串口，Linux 端为 `ttyGS0`，由 getty 提供带密码的登录提示，与副屏协议无关。
- 生成基于芯片序列号的稳定网卡 MAC，保持 USB 网卡静态地址 `192.168.137.100/24`。
- 如果控制器无法绑定两个 USB 功能，则尝试降级到串口维护模式，PID 为 `2207:4E4E`；此时先从串口查看日志。
- 保留真正的 nmtui、NetworkManager，以及设备应用。

## 1. 烧录

使用 SocToolKit 底部“固件…”选择完整 `update.img`，点击“升级”；不要把完整 update.img 当作地址 0 的普通分区行下载。成功后关闭工具，拔 USB，松开 BOOT，正常插入并等待约一分钟。

## 2. 确认新设备

Windows PowerShell：

```powershell
Get-PnpDevice -PresentOnly |
  Where-Object { $_.InstanceId -match '^USB\\VID_2207&PID_4E4[DE]' } |
  Format-List Status,Class,FriendlyName,InstanceId
```

正常情况下应出现 USB 复合设备、RNDIS 网卡和“USB 串行设备 (COMx)”之类的项目；具体显示名称由 Windows 驱动决定。用硬件 ID 确认，不要再对旧 `VID_2207&PID_0006` 的 ADB 项反复换驱动，也不要处理旧的 `EchoMateUsbDisplay` 软件设备。

Windows 的实际枚举和自动驱动匹配仍需在实物上验证。如果新 PID 没出现，应先确认新镜像是否成功烧录和 Linux 是否正常启动。

## 3. 优先用 COM 口登录

在设备管理器的“端口 (COM 和 LPT)”找到插入板子后新增的 COM 号，例如 COM7。不需要额外 USB 转 UART 接线。

将本目录的 `Connect-EchoMate.ps1` 复制到 Windows，关闭可能占用 COM 口的程序，在普通 PowerShell 窗口执行：

```powershell
cd D:\EchoMate
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Connect-EchoMate.ps1 -Port COM7
```

把 COM7 换成实际端口。此处 Bypass 仅用于该次终端进程，不改变系统全局策略，也不关闭驱动签名验证。

按回车，用户名 `root`，密码 `root`（输入密码不显示字符）。Ctrl+] 退出电脑上的串口终端；也可使用已有的串口终端，参数为 115200、8N1、无流控。

登录后执行：

```sh
export TERM=xterm
stty rows 24 cols 80
nmtui
```

用方向键、Tab、回车选择 Activate a connection，连接 Wi-Fi。然后检查：

```sh
nmcli device status
ifconfig wlan0
tail -n 100 /var/log/echo-usb.log
tail -n 100 /var/log/NetworkManager.log
```

串口脚本是便捷工具，尚需在用户的 Windows 终端验证；它不会修改板子的配置或自动输入密码。

## 4. USB 网卡登录

若新 RNDIS 网卡已经正常出现，在 `ncpa.cpl` 中给这张网卡设置电脑 IP `192.168.137.1`、掩码 `255.255.255.0`，网关和 DNS 留空：

```powershell
Test-NetConnection 192.168.137.100 -Port 22
ssh root@192.168.137.100
```

本地 USB 登录不要求开启 Internet 共享。Windows 共享网络给板子时再运行 `echo-network usb-share`。

## 验证范围

已对 USB 配置脚本进行模拟 configfs 测试，覆盖新身份、复合设备类别、RNDIS 兼容描述符、功能顺序、重复启动、停止后重启和稳定 MAC；同时检查最终根文件系统的 getty/login、登录配置以及 nmtui 依赖。软件检查不能替代 Windows 上的实际 USB 枚举验证。

规范依据：[Microsoft IAD 设备描述符](https://learn.microsoft.com/en-us/windows-hardware/drivers/usbcon/usb-interface-association-descriptor)。
