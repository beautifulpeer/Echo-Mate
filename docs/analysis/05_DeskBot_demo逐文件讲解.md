# DeskBot_demo 逐文件讲解版

## 1. 先说结论

DeskBot_demo 是 Echo-Mate 里最接近“完整产品”的部分。它本质上是一个运行在 RV1106 上的轻量桌面系统：

- 用 LVGL 做图形界面
- 用多个页面模拟“小应用”
- 用系统管理层读写时间、亮度、音量、网络状态
- 用聊天页把 AIChat 的语音能力接进来
- 用 GPIO 控制 LED 和电机

这份文档重点讲“关键源码文件”，不展开第三方库、自动生成目录和编译缓存。

---

## 2. 顶层关键文件

### 2.1 CMakeLists.txt
这是整个 DeskBot 的构建入口。

它主要做了几件事：

1. 区分本机构建和 ARM 交叉编译
2. 加入 LVGL、GUI、utils、common 四个模块
3. 链接 SDL2、json-c、curl 等桌面依赖
4. 引入 AIChat Client 作为子工程
5. 在 ARM 模式下再额外引入 yolov5 的相机能力
6. 编译完成后把配置文件和资源文件复制到 bin 目录

也就是说，这个文件决定了 DeskBot 不只是单一 UI，而是一个会把聊天与视觉能力一起打包的整合工程。

### 2.2 main.c
这是程序真正的启动入口。

逻辑非常清晰：

- 初始化 LVGL
- 根据编译配置决定使用 framebuffer、evdev 还是 SDL
- 调用 `ui_init()` 创建整个界面
- 进入无限循环，不断执行 `lv_timer_handler()`

所以 main.c 可以理解为：

> 图形界面的最外层壳子。

### 2.3 conf/dev_conf.h
这是开发板模式和仿真模式的切换开关。

你现在跑 SDL 仿真时，主要就是靠这里的 `LV_USE_SIMULATOR`。

- 设为 1：在 Ubuntu 上用 SDL 跑窗口
- 设为 0：走开发板的 framebuffer 和输入设备

### 2.4 lv_conf.h
这是 LVGL 的功能配置文件。

它控制：
- 是否启用某些控件
- 屏幕颜色深度
- 字体、缓存、特性开关

如果你后续想裁剪界面功能、优化内存占用，这个文件很关键。

---

## 3. UI 总控层

## 3.1 gui_app/ui.h
这个头文件像 UI 工程的公共入口。

它做的事情包括：

- 引入 LVGL 和自定义公共库
- 定义屏幕大小
- 暴露全局的页面管理器 `page_manager`
- 暴露系统参数结构 `ui_system_para`
- 声明图片和字体资源
- 对外提供 `ui_init()` 和消息框函数

它的作用是把“界面资源”和“系统状态”集中暴露给各个页面使用。

## 3.2 gui_app/ui.c
这是 DeskBot 的核心 UI 调度文件。

### 这个文件主要负责：

1. 注册所有页面
2. 初始化系统参数
3. 初始化 GPIO
4. 启动定时器任务
5. 处理页面切换与消息框显示

这里最重要的一段是应用数组 `ui_apps`，里面把所有页面统一注册进来，包括：

- HomePage
- SettingPage
- WeatherPage
- CalendarPage
- GameMuyuPage
- Game2048Page
- ChatBotPage
- YOLOPage
- GameMemoryPage
- DrawPage
- CalculatorPage

所以 `ui.c` 实际上就是这个桌面机器人的“应用管理器”。

---

## 4. 页面目录逐个看

所有页面都放在 `gui_app/pages/` 下。它们的设计规律比较统一：

- `ui_xxxPage.c/.h`：负责界面绘制和控件事件
- `app_xxxPage.c/.h`：负责业务逻辑、数据处理或系统调用

并不是每个页面都有 app 文件，简单页面可能只有 UI 文件。

### 4.1 ui_HomePage/
首页页面。

#### ui_HomePage.c
负责：
- 桌面图标布局
- 左右滑动翻页
- 顶部下拉控制区
- 时间和 WiFi 图标显示
- 点击图标跳转到其他页面

你可以把它理解为整个机器人桌面的“Launcher”。

#### ui_HomePage.h
首页页面的声明头文件。

---

### 4.2 ui_SettingPage/
设置页面。

主要职责通常是：
- 让用户调整系统参数
- 保存亮度、音量、联网设置、时间设置等

它和系统配置结构 `ui_system_para` 联系最紧密。

---

### 4.3 ui_WeatherPage/
天气页面。

#### ui_WeatherPage.c / ui_WeatherPage.h
负责天气页面界面、图标和显示。

#### app_WeatherPage.c / app_WeatherPage.h
负责真正的业务逻辑，例如：
- 根据城市或 adcode 查询天气
- 调用网络接口
- 解析返回结果并更新页面

这个页面会用到：
- 高德 key
- 城市编码映射文件
- curl / json-c

所以它是 DeskBot 中最典型的“有 UI + 有联网业务逻辑”的页面。

---

### 4.4 ui_CalendarPage/
日历页面。

#### ui_CalendarPage.c / ui_CalendarPage.h
负责：
- 日历显示
- 日期高亮
- 与系统时间同步

这个页面更多是纯前端展示逻辑。

---

### 4.5 ui_GameMuyuPage/
木鱼页面。

这是一个轻娱乐类页面，通常负责：
- 点击互动
- 播放或动画反馈

它更偏 UI 小应用。

### 4.6 ui_Game2048Page/
2048 小游戏页。

这类文件通常包含：
- 网格绘制
- 分数显示
- 手势输入处理
- 游戏状态更新

### 4.7 ui_GameMemoryPage/
记忆小游戏页。

定位和 2048 类似，属于小型交互游戏。

### 4.8 ui_DrawPage/
画板页面。

用于触摸绘制，主要考察：
- 输入事件响应
- 画布刷新
- 简单图形处理

### 4.9 ui_CalculatorPage/
计算器页面。

#### ui_CalculatorPage.c / ui_CalculatorPage.h
负责按键、输入框和结果显示。

#### app_CalculatorPage.c / app_CalculatorPage.h
负责表达式计算、结果输出等业务逻辑。

---

### 4.10 ui_ChatBotPage/
这是整个 DeskBot 最值得精读的一组文件。

#### ui_ChatBotPage.c
负责聊天机器人的“脸”和状态动画。

具体来说，它会根据 AIChat 当前状态切换表现：
- idle：待机动画
- listening：倾听动画
- thinking：思考动画
- speaking：说话动画

所以这个文件本质上是“AI 状态可视化前端”。

#### ui_ChatBotPage.h
聊天页面声明文件。

#### app_ChatBotPage.c
这是聊天页真正的业务桥接层。

它完成了很关键的几件事：

1. 创建 AIChat 应用实例
2. 在独立线程中运行 AIChat Client
3. 轮询当前 AI 状态
4. 读取识别出的意图
5. 如果识别到 `robot_move`，就驱动 GPIO 让机器人前进、后退、左转、右转

这也是整个 Echo-Mate 最能体现“语音理解 -> 动作执行”的文件之一。

#### app_ChatBotPage.h
聊天页业务接口声明。

---

### 4.11 ui_YOLOPage/
这是视觉识别页面。

它的定位通常是：
- 作为 DeskBot 中的视觉入口页
- 调用 yolov5 的 C 接口拿图像或结果
- 在 LVGL 页面中显示 AI 相机相关内容

它说明 DeskBot 并不只是语音机器人，也能挂接视觉能力。

---

## 5. common 公共层

这个目录是 DeskBot 真正的系统能力基础层。

### 5.1 common/sys_manager/sys_manager.h
这个头文件定义了系统参数结构，是全项目最重要的数据结构之一。

里面保存的信息包括：
- 日期和时间
- 屏幕亮度
- 音量
- WiFi 状态
- 是否自动同步时间
- 是否自动定位
- 城市、adcode、高德 key
- AIChat 服务地址、端口、token、设备 ID 等

它相当于整机的“配置中心”。

### 5.2 common/sys_manager/sys_manager.c
对应的实现文件，负责：
- 设置亮度
- 设置音量
- 设置系统时间
- 获取当前时间
- 获取星期几
- 检查 WiFi 连接状态
- 通过 IP 自动定位
- 通过 NTP 自动校时
- 保存和读取系统参数文件

所以这个文件就是：

> DeskBot 的系统服务层。

### 5.3 common/gpio_manager/gpio_manager.h
定义 GPIO 引脚和常用接口。

这里把 LED 和电机引脚抽象成了宏，例如：
- 蓝灯
- 电机 1、2 的控制引脚

### 5.4 common/gpio_manager/gpio_manager.c
真正通过 sysfs 等方式访问 GPIO。

聊天页里的运动控制最终就是走这一层。

### 5.5 common/event_manager/event_manager.h
定义一个简化版事件总线，包括：
- 事件类型
- 队列
- 处理器注册
- 分发函数

### 5.6 common/event_manager/event_manager.c
实现上面的事件系统。

### 5.7 common/event_manager/global_events.h
统一定义全局事件枚举。

---

## 6. utils 工具与运行时资源

### 6.1 utils/system_para.conf
这是运行时最重要的配置文件模板。

里面一般会保存：
- 亮度和音量
- 城市位置
- 高德 API key
- AIChat 服务端地址和 token

如果你以后要改接自己的服务器，最常见就是改这里。

### 6.2 utils/gaode_adcode.json
城市名和高德 adcode 的映射表。

天气和定位页面会依赖它。

### 6.3 utils/cacert.pem
HTTPS 证书文件。

联网访问天气等 HTTPS 接口时可能会用到。

### 6.4 utils/mouse_cursor_icon.c
仿真环境下的鼠标图标等资源支持。

---

## 7. lvgl 目录怎么看

这个目录基本是第三方 GUI 框架本体，不建议第一次就深挖。

建议你初学时把它当作“图形引擎”，重点先看自己的业务代码：

- `main.c`
- `gui_app/ui.c`
- `gui_app/pages/`
- `common/sys_manager/`
- `common/gpio_manager/`

等你以后需要：
- 优化性能
- 增加控件
- 裁剪内存

再去深入 `lvgl/`。

---

## 8. 推荐阅读顺序

如果你准备开始改 DeskBot，我建议按这个顺序读：

1. `main.c`
2. `conf/dev_conf.h`
3. `gui_app/ui.h`
4. `gui_app/ui.c`
5. `gui_app/pages/ui_HomePage/`
6. `gui_app/pages/ui_ChatBotPage/`
7. `common/sys_manager/`
8. `common/gpio_manager/`
9. 其他页面按需阅读

---

## 9. 一句话总结

DeskBot_demo 的核心设计思想是：

> 用 LVGL 做一个小桌面，把天气、日历、聊天、视觉和小游戏都包装成独立页面，再通过系统层与 AI 层把它们连起来。
