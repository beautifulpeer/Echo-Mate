# hand_gesture_demo (RV1106)

把 `/home/lubancat/lzd/hand_gesture`（PC/RK3588）中"手势识别"功能，移植到 RV1106（Luckfox Pico / Echo-Mate 开发板），并替换原 `yolov5_demo` 作为 `Echo-Mate/Demo/` 中的一个独立示例。

## 功能

- 单手 21 关键点检测（手掌 + 关键点 + 左右手）
- 静态手势识别：Fist / Open Palm / Thumb Up/Down / Index / Victory / OK / I Love You / Pinky
- 实时叠加骨架、指尖、掌心框、手势标签、帧率
- 输出到 `/dev/fb0`（MIPI/HDMI/DSI），无显示设备时仍可 headless 运行

## 目录

```text
hand_gesture_demo/
├── cpp/                  # C++ 源码 + CMake 构建
│   ├── main.cc
│   ├── hand_landmark.h
│   ├── gesture_classifier.{h,cc}
│   ├── rknpu2/hand_landmark_rv1106.cc
│   ├── CMakeLists.txt
│   ├── toolchain.cmake
│   ├── 3rdparty/         # 来自原 yolov5_demo（librknnmrt, jpeg, rga, stb）
│   ├── lib/              # prebuilt OpenCV-mobile-4.10.0 static libs
│   └── rv1106_hand_gesture_demo/   # 编译产物（install 目标）
└── model/
    ├── palm_detector.rknn
    ├── hand_landmarks.rknn
    └── config.json
```

## 编译

```bash
cd /home/lubancat/lzd/Echo-Mate/Demo/hand_gesture_demo/cpp
mkdir -p build && cd build
cmake -DCMAKE_BUILD_TYPE=Release ..
make -j
make install    # 输出到 ../rv1106_hand_gesture_demo/
```

工具链：`/home/lubancat/lzd/Echo-Mate/SDK/rv1106-sdk/tools/linux/toolchain/arm-rockchip830-linux-uclibcgnueabihf/`

## 部署到板端

把 `rv1106_hand_gesture_demo/` 整个目录 scp 到板端任意位置，例如 `/root/hand_gesture/`：

```bash
scp -r rv1106_hand_gesture_demo/ root@<board-ip>:/root/hand_gesture/
```

板端运行：

```bash
cd /root/hand_gesture/rv1106_hand_gesture_demo
export LD_LIBRARY_PATH=$PWD/lib:$LD_LIBRARY_PATH
./rknn_hand_gesture_demo .   # '.' = deploy_dir，模型会从 ./model/ 加载
```

可选参数：

```text
--camera N    摄像头节点（默认 0；Luckfox Pico GC2056 通常为 11）
--width W     摄像头宽
--height H    摄像头高
```

## 模型说明

当前 demo 的 `model/` 目录**直接复用了 RK3588 上验证过的 FP16 RKNN 模型**（来自 `/home/lubancat/lzd/hand_gesture/models/rk3588/`）。
RKNN 格式跨 RK3588/RV1106 可加载（librknnmrt 兼容），但精度可能略有下降。
若板端推理异常/精度低，可用 `rknn-toolkit2` 在主机上把 MediaPipe `hand_landmarker.task` 重新转成 `target_platform=rv1106` 的模型并替换。

## 已知限制

- 当前 palm decoder 是简化版（top-1 palm + 简单 SSD 解码 + NMS），不支持 7-关键点对齐；用于演示够用。
- 当前只取分数最高的一只手（多手场景下忽略其它手）。
- MediaPipe 2-model 格式的 RKNN 输出 tensor 名称/顺序在不同 toolkit 版本下可能不同；如果 `detect_palms` / `detect_landmarks` 找不到输出，会按默认值回退，**遇到没有检测结果时**，请用 `rknn_query` 打印 tensor 属性再调。