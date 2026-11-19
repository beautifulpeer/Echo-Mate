# AIChat_demo Client 逐文件讲解版

## 1. 这个 Client 是干嘛的

AIChat_demo 的 Client 端主要跑在开发板上，负责：

- 录音
- 播放 TTS 回传音频
- WebSocket 与服务端通信
- 维护语音助手状态机
- 接收服务端下发的意图
- 在 DeskBot 中作为一个可嵌入的聊天能力模块被复用

如果说 Server 是“大脑”，那么 Client 更像“耳朵、嘴巴和现场控制器”。

---

## 2. 顶层入口文件

### 2.1 main.cc
这是独立运行 Client 的入口。

它读取三个启动参数：
- server 地址
- 端口
- token

然后构造 `Application` 对象并调用 `Run()`。

所以它只是一个很薄的启动壳，真正的核心逻辑都在 Application 里。

### 2.2 CMakeLists.txt
这是 Client 的编译说明书。

它会：
- 查找 opus、portaudio、jsoncpp、websocketpp
- 编译音频模块、WebSocket 模块、状态机模块、意图模块
- 生成核心静态库 `AIChatCore`
- 再额外生成独立可执行文件 `AIChatClient`
- 同时把 C 接口那部分也编进去

也就是说，Client 不是“一个 main.cc 编出来的小程序”，而是一个模块化程度较高的 C++ 工程。

---

## 3. Application 目录

这是 Client 端最核心的目录。

### 3.1 Application.h
这是总控制类 `Application` 的定义位置。

里面聚合了：
- 音频处理器 `audio_processor_`
- 状态机 `client_state_`
- 事件队列 `eventQueue_`
- 意图队列 `IntentQueue_`
- WebSocket 客户端 `ws_client_`
- 意图处理器 `intent_handler_`

所以这个类相当于：

> Client 端的总装配器。

### 3.2 Application.cc
这里实现了 `Application::Run()` 等关键逻辑。

它的重点不是自己干很多活，而是：

1. 初始化状态机配置
2. 启动状态处理线程
3. 从事件队列里取事件
4. 让状态机根据事件切换状态
5. 在结束时关闭 WebSocket

这个文件体现出整个 Client 的运行方式是：

> 事件驱动 + 状态机驱动。

### 3.3 StateConfig.h
定义了 Client 端的所有状态枚举：

- fault
- startup
- stopping
- idle
- listening
- thinking
- speaking

这几个状态非常贴合语音助手的真实交互过程。

### 3.4 StateConfig.cc
真正把状态和事件连起来。

它完成了两类工作：

1. 注册每个状态对应的进入/退出行为
2. 注册状态转移关系

例如：
- startup 完成后切到 idle
- listening 收到 ASR 结果切到 thinking
- thinking 收到说话消息切到 speaking
- speaking 完成后回到 listening 或 idle

所以这份文件就是整套语音交互流程图的代码实现版。

### 3.5 WS_Handler.h
声明了 WebSocket 消息分发器。

它会根据服务端发来的消息类型，进一步分发到：
- VAD 消息处理
- ASR 文本处理
- chat 结束消息处理
- TTS 状态处理
- intent 处理

### 3.6 WS_Handler.cc
负责把服务端发来的 JSON 或二进制消息真正转换成客户端事件。

你可以把它看成：

> WebSocket 协议层到本地状态机之间的翻译器。

### 3.7 IntentsRegistry.h
定义“本机支持哪些函数调用”的汇总入口。

### 3.8 IntentsRegistry.cc
它会把像 `robot_move` 这样的功能注册给系统，并生成一份 JSON 发给服务端，告诉服务端：

- 我支持哪些函数
- 每个函数叫什么
- 每个函数接受什么参数

这一步非常关键，因为它相当于给 LLM 提供了“可调用能力清单”。

---

## 4. Application/UserStates 目录

这个目录非常值得看。

里面每个文件都代表一个状态的行为实现：

- `Startup.cc/.h`：启动状态逻辑
- `Idle.cc/.h`：空闲等待状态
- `Listening.cc/.h`：开始录音和监听用户说话
- `Thinking.cc/.h`：等待服务端理解与生成回复
- `Speaking.cc/.h`：播放语音回复
- `Stop.cc/.h`：结束状态
- `Fault.cc/.h`：故障状态

也就是说，状态机不是只在配置文件里有名字，而是每个状态都单独拆成了自己的文件。

这种设计的好处是：
- 很清晰
- 好扩展
- 以后要加状态时不容易把所有逻辑写乱

---

## 5. Audio 目录

### 5.1 AudioProcess.h
定义音频处理类。

它负责：
- 启动和停止录音
- 启动和停止播放
- 管理录音队列和播放队列
- PCM 与 Opus 编解码
- 把音频封装成二进制协议帧
- 从二进制帧里解包出音频数据

这是整个 Client 的音频核心。

### 5.2 AudioProcess.cc
对应实现文件。

里面通常会包含：
- PortAudio 回调
- Opus 编解码器初始化与回收
- 音频帧拆分与缓存管理

如果你以后想改录音参数、换音频输入设备、调帧大小，这里最值得看。

---

## 6. WebSocket 目录

### 6.1 WebsocketClient.h
定义 WebSocket 客户端类和二进制协议结构。

重点包括：
- 连接、关闭、终止
- 发送文本消息
- 发送二进制音频数据
- 设置消息回调和关闭回调
- 维护连接状态

### 6.2 WebsocketClient.cc
真正对 websocketpp 进行封装，实现连接建立、消息接收和发送。

它是 Client 和 Server 对话的网络通道。

---

## 7. Intent 目录

### 7.1 IntentHandler.h
这是本地函数调用分发器。

它会保存：
- 函数名
- 对应的回调函数

当服务端发来某个意图时，比如 `robot_move`，它就能找到本地该执行哪段逻辑。

### 7.2 IntentHandler.cc
实现回调注册和执行逻辑。

它是“语音理解结果 -> 本地动作”的关键中间层。

---

## 8. Events 目录

### 8.1 AppEvents.h
统一定义事件枚举，例如：
- startup_done
- wake_detected
- vad_no_speech
- asr_received
- speaking_end
- dialogue_end
- fault_happen

这些事件是状态切换的触发条件。

### 8.2 EventQueue.h
定义一个线程安全的模板事件队列。

这个文件虽然小，但很重要，因为 Application 的状态处理线程就是从这里取事件的。

---

## 9. UserIntents 目录

### 9.1 RobotMove.h / RobotMove.cc
这是一个示例意图处理器。

它的职责是：
- 从 JSON 参数中读出 `direction`
- 识别 forward、backward、left、right 等控制指令

在独立 Client 里它主要是打印或转发逻辑；在 DeskBot 里则会被进一步转成 GPIO 动作。

---

## 10. c_interface 目录

这是 AIChat Client 被 DeskBot 复用的关键。

### 10.1 AIchat_c_interface.h
暴露了一组 C 风格接口，包括：
- 创建应用对象
- 运行应用
- 停止应用
- 销毁对象
- 获取当前状态
- 获取 intent 数据

### 10.2 AIchat_c_interface.cc
把这些 C 接口真正映射到 C++ 的 `Application` 对象上。

这么做的原因很现实：

- DeskBot 主体是 C + LVGL 风格代码
- AIChat Client 是 C++
- 所以必须有一层 C 接口做桥接

### 10.3 test.c
一般用于简单测试这层接口能否被 C 代码正常调用。

---

## 11. third_party 目录怎么看

这里主要是第三方依赖，例如：
- Snowboy 唤醒词资源
- 音频提示音资源

在业务理解阶段，不建议先深挖；把它看成“依赖资源包”即可。

---

## 12. 推荐阅读顺序

建议按下面顺序看 Client：

1. `main.cc`
2. `Application/Application.h`
3. `Application/Application.cc`
4. `Application/StateConfig.cc`
5. `Events/AppEvents.h`
6. `Audio/AudioProcess.h`
7. `WebSocket/WebsocketClient.h`
8. `Application/WS_Handler.cc`
9. `Intent/IntentHandler.*`
10. `c_interface/AIchat_c_interface.*`

---

## 13. 一句话总结

AIChat_demo Client 的设计很工整：

> 用 WebSocket 负责联机，用 AudioProcess 负责采集和播放，用状态机把整条语音交互流程串起来，再通过 C 接口嵌入到 DeskBot 中。
