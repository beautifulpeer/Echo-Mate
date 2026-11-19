## DeskBot demo

### 1.编译
1. **在电脑上运行SDL仿真**

    注意更改conf/dev_conf, 将`LV_USE_SIMULATOR`置`1`
    
    ```sh
    cd ./DeskBot_demo
    mkdir ./build
    cd ./build
    cmake ..
    make
    ```

    然后就可以在ubuntu上运行了

    ```sh
    cd ../bin
    ./main
    ```

2. **编译到开发板上运行**

    注意更改conf/dev_conf, 将`LV_USE_SIMULATOR`置`0`

    ```sh
    cd ./build
    cmake .. -DTARGET_ARM=ON
    make
    ```

    然后把可执行文件所在的文件夹`/bin`, copy到开发板, 在开发板上就能运行了

    **注意:** 

    ```sh
    cd ../bin
    ./main
    ```

### 2.Server运行

python环境搭建详见[AI语言助手demo(Server端)](../AIChat_demo/Server/README.md), 然后进入你搭好的虚拟环境中，运行即可

``` sh
python ./main.py --access_token="123456"
```

### 3.注意

**!! 使用前请先修改`./bin/system_para.conf`中的内容 !!**

1. `./bin/system_para.conf`中有高德API key，需要换成你的API key，用于天气等数据的获取

2. 每个page可视为一个APP, 想要自行添加可以参考模版添加

3. 你的个人电脑运行服务端`server`时, 需要跟开发板`Client`端, 连接到同一个网络下, AI chat才能正常访问. 当然, 你也可以使用电脑进行网络共享(默认开发板是172.32.0.93, 电脑是172.32.0.100).

### 4.Wi-Fi 连接与 WPA2-PSK 排查

#### 4.1 配置说明

小米路由器中的家庭 Wi-Fi 加密方式应为 `WPA2-PSK`，不是 `WPA2-PSA`。但是在 `wpa_supplicant.conf` 中，`key_mgmt` 不能写成 `WPA2-PSK`，仍然要写 `WPA-PSK`。WPA2 由 `proto=RSN` 指定。

在开发板上编辑 `/etc/wpa_supplicant.conf`：

```conf
ctrl_interface=/var/run/wpa_supplicant
ap_scan=1
update_config=1
country=CN

network={
    ssid="你的2.4G Wi-Fi名称"
    psk="你的Wi-Fi密码"
    proto=RSN
    key_mgmt=WPA-PSK
    pairwise=CCMP
    group=CCMP
    scan_ssid=1
}
```

说明：

- `proto=RSN` 表示 WPA2；`key_mgmt=WPA-PSK` 是 WPA2 家用密码的正确写法。
- `CCMP` 就是路由器界面中常见的 AES 加密。
- `psk` 为 8～63 个字符时必须带双引号。如果密码中有双引号、反斜杠或中文，建议先用纯英文和数字密码排查。

#### 4.2 小米路由器设置

当无密码时能连接、设置密码后不能连接，通常不是 DHCP 问题，而是开发板与路由器没有完成加密认证。本 SDK 使用较旧的 `wpa_supplicant 2.6`，且当前没有启用 802.11w，因此路由器建议设置为：

- 开启 2.4 GHz，不要只开 5 GHz。
- 安全模式选择“WPA2-个人版”或“WPA2-PSK”。
- 加密算法选择 AES/CCMP，不要选 TKIP。
- 关闭 WPA3 和 WPA2/WPA3 混合模式。
- 关闭 PMF/802.11w 强制模式；如果可选，设为“关闭”或“可选”。
- 关闭“双频合一”进行排查，给 2.4 GHz 使用独立 SSID。
- 首次排查时，SSID 和密码先只使用英文字母和数字。

#### 4.3 在开发板上手动测试

先停止旧进程，再以调试模式运行：

```sh
killall udhcpc 2>/dev/null
killall wpa_supplicant 2>/dev/null
ifconfig wlan0 down
ifconfig wlan0 up
mkdir -p /var/run/wpa_supplicant
wpa_supplicant -dd -D nl80211 -i wlan0 -c /etc/wpa_supplicant.conf
```

如果日志中出现 `CTRL-EVENT-CONNECTED` 或 `WPA_COMPLETED`，说明 WPA2 已认证成功。按 `Ctrl+C` 退出调试，然后在后台启动并获取 IP：

```sh
wpa_supplicant -B -D nl80211 -i wlan0 -c /etc/wpa_supplicant.conf
sleep 5
wpa_cli -i wlan0 status
udhcpc -i wlan0 -f -q
```

`wpa_cli` 正常输出应包含：

```text
wpa_state=COMPLETED
ssid=你的Wi-Fi名称
```

结果判断：

- `wpa_state=COMPLETED` 但没有 IP：Wi-Fi 密码和 WPA2 认证已成功，问题在 DHCP。执行 `ifconfig wlan0 0.0.0.0` 后重试 `udhcpc -i wlan0 -f -v`。
- 日志出现 `pre-shared key may be incorrect`：密码错误，或密码包含未正确处理的特殊字符。
- 日志出现 `no suitable network` 或一直找不到 SSID：检查 2.4 GHz、信道、SSID 和 `scan_ssid=1`。
- 路由器一开 WPA3 就失败：当前的 `wpa_supplicant 2.6` 不适合直接使用 WPA3/SAE，请保持 WPA2-PSK + AES。

#### 4.4 将 Wi-Fi 信息编译进固件

在实际使用的 Echo-Mate 板级配置文件末尾添加：

```sh
export LF_WIFI_SSID="你的2.4G Wi-Fi名称"
export LF_WIFI_PSK="你的Wi-Fi密码"
```

SPI NAND 对应：

```text
SDK/rv1106-sdk/project/cfg/BoardConfig_IPC/BoardConfig-SPI_NAND-Buildroot-RV1106_Echo_Mate-DeskMate.mk
```

SD 卡对应：

```text
SDK/rv1106-sdk/project/cfg/BoardConfig_IPC/BoardConfig-SD_CARD-Buildroot-RV1106_Echo_Mate-DeskMate.mk
```

然后在 SDK 根目录重新编译并打包：

```sh
cd SDK/rv1106-sdk
./build.sh clean app
./build.sh clean rootfs
./build.sh app
./build.sh rootfs
./build.sh firmware
```

Wi-Fi 密码会以明文写入板级配置，请不要将包含真实密码的文件提交到公开仓库。
