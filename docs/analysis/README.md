# Echo-Mate 项目分析索引

这组文档基于项目自带 README、环境搭建手册，以及关键源码入口整理，目的是帮助你快速理解 Echo-Mate 的整体定位、每个 demo 的作用，以及代码框架之间的关系。

## 文档列表

1. [01_手册与环境搭建摘要.md](./01_手册与环境搭建摘要.md)
   - 汇总官网“环境搭建”页面和仓库中的 SDK 说明
   - 适合先了解依赖、SDK、编译方式、板端运行前提

2. [02_各Demo功能说明.md](./02_各Demo功能说明.md)
   - 逐个解释仓库中的主要 demo 是干什么的
   - 包含适用平台、运行方式、与 Echo-Mate 主工程的关系

3. [03_代码框架分析.md](./03_代码框架分析.md)
   - 从源码入口出发，拆解 UI、状态机、服务端、视觉 demo 的结构
   - 更适合准备二次开发时阅读

4. [04_建议阅读路径.md](./04_建议阅读路径.md)
   - 给出推荐阅读顺序和扩展建议
   - 方便后续快速上手改功能

5. [05_DeskBot_demo逐文件讲解.md](./05_DeskBot_demo逐文件讲解.md)
   - 对 DeskBot 主工程按关键文件和目录逐个说明
   - 适合准备改 UI、改设置页、改聊天页时阅读

6. [06_AIChat_demo_Client逐文件讲解.md](./06_AIChat_demo_Client逐文件讲解.md)
   - 对 AIChat 客户端的入口、状态机、音频、网络和 C 接口逐个说明

7. [07_AIChat_demo_Server逐文件讲解.md](./07_AIChat_demo_Server逐文件讲解.md)
   - 对 Server 端的 WebSocket、服务管理器、模型和线程逐个说明

8. [08_yolov5_demo逐文件讲解.md](./08_yolov5_demo逐文件讲解.md)
   - 对视觉 demo 的入口、后处理和 C 接口逐个说明

9. [09_rkmpi_demos逐文件讲解.md](./09_rkmpi_demos逐文件讲解.md)
   - 对多媒体与 RTSP 相关样例集合逐个说明

## 一句话总结

- **Echo-Mate 不是单一 demo，而是一个基于 RV1106 的桌面机器人项目集合。**
- **DeskBot_demo 是“整机应用”。**
- **AIChat_demo、yolov5_demo、rkmpi_demos 更像独立能力样例或子模块。**
- **SDK 目录负责底层系统、内核、驱动、镜像的构建。**
- **如果要逐文件理解代码，直接从第 5 到第 9 份文档开始看即可。**
