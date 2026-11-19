# AIChat_demo Server 逐文件讲解版

## 1. 这个 Server 的定位

Server 端是整个 AI 语音助手的大脑，主要跑在电脑上。

它负责：
- 接收板端发来的音频和状态
- 做鉴权
- 做 VAD 语音活动检测
- 做 ASR 语音转文字
- 做意图识别
- 调用大模型聊天
- 做 TTS 文字转语音
- 再把文本和音频回传给 Client

它的总体结构是：

> WebSocket 接入层 + ServiceManager 调度层 + 多个 AI 服务模块。

---

## 2. 顶层入口

### 2.1 main.py
这是服务端入口。

这个文件会：

1. 创建 `ServiceManager`
2. 启动 TTS 音频发送线程
3. 启动 WebSocket 服务器
4. 在关闭时统一清理线程和状态

所以它像一个总启动脚本。

### 2.2 service_manager.py
这是整个 Server 的核心骨架。

里面初始化并持有：
- `AudioProcessor`
- `VADService`
- `ASRService`
- `IntentService`
- `ChatService`
- `TTSService`
- 各种队列
- 线程停止信号
- 短生命周期任务管理器

这个文件最重要，因为其他服务虽然各司其职，但真正把它们串起来的是这里。

### 2.3 ws_server.py
这是网络接入层。

主要职责：
- 启动 WebSocket 服务
- 接收客户端连接
- 做请求头鉴权
- 区分二进制音频和 JSON 文本消息
- 把消息分发给 `AudioHandler` 或 `TextHandler`
- 从发送队列中取出消息再推给客户端

它的定位类似“网关层”。

---

## 3. config 目录

### 3.1 settings.py
这是全局配置文件。

里面定义了：
- 协议版本
- DashScope API key
- 意图模型和聊天模型名称
- ASR/VAD 使用 CPU 还是 CUDA
- 超时时间

如果你后续想换模型、换设备、换 key，第一步就该看这里。

---

## 4. handle 目录

这个目录是 WebSocket 收到消息后的第一层处理器。

### 4.1 auth_handler.py
负责校验客户端的：
- access token
- device id
- protocol version

只有这些条件通过了，Client 才算认证成功。

### 4.2 text_handler.py
处理所有 JSON 文本消息。

它会根据消息类型做不同事情：

- `hello`：完成握手并设置 API key
- `functions_register`：把客户端支持的函数注册进系统
- `state`：根据 idle、listening、thinking、speaking 等状态同步服务端内部状态

这份文件相当于“控制消息解析器”。

### 4.3 audio_handler.py
处理二进制音频消息。

它的工作流最关键：

1. 解包 BinProtocol
2. 把 Opus 解码成 PCM
3. 做 VAD 语音活动检测
4. 把音频送进 ASR 缓冲区
5. 一旦检测到语音结束，就生成文字
6. 再异步触发聊天任务
7. 把 ASR 文本和后续结果回发客户端

这份文件是整条音频链路的入口。

---

## 5. services 目录

这个目录是一层“服务封装层”，每个文件只做一件事。

### 5.1 vad_service.py
对 `VADModel` 做一层薄封装。

职责很单纯：
- 初始化 VAD 模型
- reset 状态
- 逐帧处理音频并返回状态码

### 5.2 asr_service.py
对 ASR 模型封装成服务。

主要职责：
- 累积音频缓冲区
- 在合适时机调用识别
- 返回用户说出的文本

### 5.3 intent_service.py
这是意图识别服务。

它会：
- 读取当前已经注册的函数列表
- 动态拼提示词
- 让 LLM 判断用户是否在“调用功能”而不只是闲聊
- 输出标准化的 `function_call` 结果

这是把普通聊天和“可执行动作”连接起来的关键模块。

### 5.4 chat_service.py
对普通对话做封装。

它负责：
- 维护对话上下文
- 设置系统角色提示
- 调用聊天模型获取完整回复或流式回复

这部分决定机器人“怎么说话”。

### 5.5 tts_service.py
对文字转语音做服务封装。

它负责：
- 初始化流式 TTS
- 逐段把文本喂给 TTS 模型
- 在结束时关闭流

这部分决定机器人“怎么发声”。

---

## 6. models 目录

如果说 services 是服务层，那么 models 才是底层 AI 能力提供者。

### 6.1 vad_model.py
这里加载的是 FunAudioLLM 相关的 VAD 模型。

它会：
- 维护音频缓冲区
- 检测是否开始说话、结束说话、长时间无语音
- 返回状态码给上层 VADService

这是整个系统是否“懂得何时开始识别”的关键。

### 6.2 asr_model.py
这里加载的是 SenseVoiceSmall 相关的 ASR 模型。

它会：
- 接收累计的 PCM 音频
- 调用 `AutoModel` 做语音识别
- 返回最终文本

所以它就是“听懂你说什么”的具体实现。

### 6.3 llm_model.py
这里封装了 DashScope 大模型调用。

主要职责：
- 管理 messages 历史
- 设置 system prompt
- 获取非流式回复
- 获取流式回复

这部分决定机器人的文本理解与语言生成效果。

### 6.4 tts_model.py
这里封装了 CosyVoice 风格的流式 TTS 调用。

它会：
- 初始化 SpeechSynthesizer
- 注册回调
- 连续合成 PCM 语音片段
- 在回调里把音频数据回传出去

它决定机器人“声音怎么出来”。

### 6.5 FunAudioLLM/
这是模型权重或相关代码所在目录。

通常不用先读，除非你准备替换模型或排查模型加载问题。

---

## 7. threads 目录

### 7.1 audio_send_thread.py
负责从 `audio_queue` 中持续取出 TTS 生成的 PCM 数据。

然后它会：
- 切成帧
- 编码成 Opus
- 再打包成二进制消息
- 放入 WebSocket 发送队列

这是“服务端说出来的声音怎么送回板端”的关键线程。

### 7.2 task_manager.py
基于线程池做简化任务管理。

它适合处理像“识别后立刻去聊天和生成语音”这种短生命周期任务。

### 7.3 tts_thread.py
这是另一个 TTS 生成线程相关文件。

从当前入口看，主流程里更主要的是 `audio_send_thread.py`，`tts_thread.py` 偏保留或扩展设计。

---

## 8. tools 目录

### 8.1 audio_processor.py
这是服务端的音频打包与编解码工具类。

它负责：
- 定义 BinProtocol 头格式
- 打包和解包二进制音频帧
- PCM 与 Opus 的转换
- 音频文件读写和参数设置

Client 和 Server 两边都各有一份音频处理逻辑，但实现语言不同。

### 8.2 registry.py
这是函数注册中心。

它会：
- 记录有哪些可调用函数
- 用 Pydantic 生成参数校验模型
- 在需要时执行真实函数

这一层是“工具调用能力”的基础设施。

### 8.3 logger.py
统一日志输出。

服务端出问题时通常先看这里打印的日志。

---

## 9. test 目录

这是单功能测试目录。

通常会放：
- chat 测试
- asr 测试
- tts 测试
- 其他单点调试脚本

它适合你后续排查问题时先做局部验证。

---

## 10. 服务端完整数据流

按源码来理解，一次完整交互大致是：

1. Client 建立 WebSocket 连接
2. `auth_handler.py` 完成鉴权
3. Client 发送 `hello` 和函数注册消息
4. Client 不断上传音频帧
5. `audio_handler.py` 解码并送入 VAD / ASR
6. `intent_service.py` 判断有没有函数调用
7. `chat_service.py` 生成聊天文本
8. `tts_service.py` 生成语音
9. `audio_send_thread.py` 编码并回传到 Client

这样整条链路就闭环了。

---

## 11. 推荐阅读顺序

建议你按这个顺序读：

1. `main.py`
2. `service_manager.py`
3. `ws_server.py`
4. `handle/text_handler.py`
5. `handle/audio_handler.py`
6. `services/intent_service.py`
7. `services/chat_service.py`
8. `services/tts_service.py`
9. `models/llm_model.py`
10. `tools/registry.py`

---

## 12. 一句话总结

AIChat_demo Server 的设计核心是：

> 用一个 WebSocket 服务接收音频和控制消息，再由 ServiceManager 把 VAD、ASR、意图识别、聊天和 TTS 一步步串起来。
