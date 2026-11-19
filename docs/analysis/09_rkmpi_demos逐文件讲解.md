# rkmpi_demos 逐文件讲解版

## 1. 这组 demo 的定位

rkmpi_demos 更像是一套“多媒体与视觉能力样例库”，而不是单一应用。

它主要用于展示：
- 视频采集
- RTSP 推流
- OpenCV 图像处理
- RetinaFace 人脸检测
- YOLO 目标识别
- OSD 叠加显示

所以它在 Echo-Mate 仓库中的意义更偏：

> 底层视频链路参考工程。

---

## 2. 顶层文件逐个看

### 2.1 README.md / README_CN.md
这是总说明文档。

它告诉你：
- 这套例程支持哪些 CPU 和系统
- 每个例程能实现什么效果
- 如何编译和运行
- RTSP 地址怎么拉流预览

如果你第一次看 rkmpi_demos，先读这个就对了。

### 2.2 build.sh
这是最重要的使用入口脚本。

它的功能是：
- 提供交互式菜单
- 让你从多个 example 中选一个来编译
- 自动创建 build 目录
- 自动执行 cmake 和 make install
- 生成最终部署目录

换句话说，它相当于这一整套样例的“编译调度器”。

### 2.3 CMakeLists.txt
这是通用构建模板。

它做了几件事：
- 从环境变量里读取 Luckfox SDK 路径
- 配置交叉编译器
- 根据选择的 example 动态指定源码目录
- 链接 OpenCV、Rockchip 多媒体库、RTSP 相关库
- 最终把二进制和模型文件安装到 install 目录

它说明这套样例并不是各自独立写死编译，而是复用同一套构建骨架。

---

## 3. example 目录

这是你最应该关注的目录，每个子目录都是一个具体 demo。

### 3.1 luckfox_pico_rtsp_opencv/
这个例程主要展示：
- 摄像头采集
- OpenCV 图像处理
- RTSP 推流输出

适合用来理解最基础的视频采集和网络串流链路。

### 3.2 luckfox_pico_rtsp_opencv_capture/
这个例程更偏向“捕获与处理”。

你可以把它理解成：
- 在基础 RTSP / OpenCV 链路上
- 增加了帧抓取、保存或单帧处理逻辑

适合做摄像头接入调试。

### 3.3 luckfox_pico_rtsp_retinaface/
这个例程引入了 RetinaFace 人脸检测。

主要用于学习：
- 人脸检测模型如何接入
- 检测结果如何叠加到视频上
- 如何通过 RTSP 实时查看识别效果

### 3.4 luckfox_pico_rtsp_retinaface_osd/
它和前一个例程类似，但更强调 OSD 叠加显示。

也就是说，它不仅做人脸检测，还会把结果更完整地绘制到视频流中。

### 3.5 luckfox_pico_rtsp_yolov5/
这个例程是目标检测版本，核心是：
- 摄像头输入
- yolov5 推理
- RTSP 推流

它和独立的 yolov5_demo 很像，但更偏向“视频流场景”，而不是本地 LCD 页面显示场景。

---

## 4. 3rdparty 目录

这里主要放第三方依赖和平台能力封装，例如：
- allocator
- librga
- rknpu2

这部分通常负责：
- 图像格式转换
- 内存分配
- NPU 推理调用

如果你后续要做平台层优化，可能会进入这里；如果只是理解业务流程，先知道它们是底层支持库即可。

---

## 5. include 目录

这个目录汇总了许多 Rockchip 多媒体与 AI 相关头文件。

例如会涉及：
- 音视频编解码
- AIQ 图像质量调节
- ADEC / AENC / AIO
- RKNN 等接口

它更多是平台 SDK 头文件集合，而不是业务逻辑源代码。

---

## 6. lib 目录

存放预编译好的库文件。

在编译各个 demo 时，CMake 会从这里链接所需的底层库。

这也是为什么 rkmpi_demos 看起来“源码量没那么大，但功能很强”的原因：

> 很多能力其实在库里已经准备好了。

---

## 7. install 目录

这里是构建后的输出目录。

每次你选一个例程编译之后，会生成对应的部署文件夹，例如：
- opencv_demo
- retinaface_demo
- yolov5_demo

真正上传到开发板运行的，通常就是这里的产物。

---

## 8. images 目录

放的是说明图片和演示效果图。

用于 README 展示，不是核心业务代码。

---

## 9. 这组 demo 适合什么场景

如果你的目标是：

### 想做视频推流
重点看：
- `build.sh`
- `CMakeLists.txt`
- `example/luckfox_pico_rtsp_opencv/`

### 想做人脸识别
重点看：
- `example/luckfox_pico_rtsp_retinaface/`
- `example/luckfox_pico_rtsp_retinaface_osd/`

### 想做视频版目标检测
重点看：
- `example/luckfox_pico_rtsp_yolov5/`

### 想理解平台多媒体链路
结合：
- `include/`
- `lib/`
- `3rdparty/`
一起看

---

## 10. 推荐阅读顺序

1. `README_CN.md`
2. `build.sh`
3. `CMakeLists.txt`
4. `example/` 下你感兴趣的具体例程
5. `3rdparty/` 和 `include/` 中相关能力文件

---

## 11. 一句话总结

rkmpi_demos 的本质是：

> 围绕 Luckfox / Rockchip 平台的视频采集、推流和视觉识别能力，提供的一套工程化样例集合。
