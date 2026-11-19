# 独立 GitHub 版本

目标仓库：https://github.com/beautifulpeer/Echo-Mate

当前本地目录的分支、配置保留和后续提交方式见 [本地维护说明](LOCAL_WORKSPACE.md)。

保留原项目历史和许可证，纳入本地 SDK、Demo 和运行依赖修改。Demo 与嵌套子模块均展开为实际文件。API 密钥和 Wi-Fi 密码使用待填写配置。

大模型不再以分块写入 Git，改为本仓库 deps-v1 Release 附件。Actions 根据 dependencies.json 从原模型源获取数据，只有大小和 SHA-256 与本地版本一致时才发布。使用者执行 python3 scripts/setup-deps.py，从 beautifulpeer 自己的 Release 下载。

工作流只对 beautifulpeer/Echo-Mate 生效，使用 GitHub 自动提供的 GITHUB_TOKEN 和 contents: write 权限，不需要个人密码或令牌。Fork 若禁用 Actions，请在 Actions 页面启用并运行 Publish verified model dependency。

已核对本地模型、脚本语法和发布结构；全量编译及硬件运行仍需验证。GitHub 网络不通或 Release 尚未发布时，不能声称完成迁移。
