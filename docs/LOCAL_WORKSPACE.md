# 本地维护方式

本地 `main` 跟踪自己的 GitHub 仓库 `beautifulpeer/Echo-Mate`。远端 `origin` 为自己的 GitHub，`upstream` 仅保留原作者地址供参考，`gitee` 保留此前的副本。日常提交使用 `git push origin main`。

Demo、LVGL、语音模型源码与 rkmpi 已作为普通目录统一管理，不需要再执行子模块更新。语音模型使用 `python3 scripts/setup-deps.py` 从自己的 GitHub Release 恢复。

## 本地配置与备份

整理前的 Git 暂存区、配置、文件差异和子仓库入口保存在 `.github-migration/alignment-backup/`，该目录不会提交。旧提交保存在本地分支 `backup/pre-align-20261119`。原子仓库历史仍保存在主仓库 `.git/modules/`，没有删除。

以下七个已跟踪文件保留本机内容，并设置本地 `skip-worktree` 标志，避免把真实配置或含本地配置的运行程序带入日常提交：

- `system_para.conf`
- `Demo/DeskBot_demo/utils/system_para.conf`
- `SDK/rv1106-sdk/project/app/wifi_app/wpa_supplicant.conf`
- `SDK/rv1106-sdk/sysdrv/tools/board/android-tools/echomate-bin/system_para.conf`
- `SDK/rv1106-sdk/sysdrv/tools/board/android-tools/echomate-bin/main`
- `docs/usb副屏/RV1106/main-usb-display`
- `docs/usb副屏/SHA256SUMS.txt`

这只是当前克隆的本地 Git 设置，不会随仓库上传，也不等同于凭据保护机制。若确实需要提交其中某个文件，先将其整理为不包含真实凭据的发布内容，再执行 `git update-index --no-skip-worktree -- 文件路径`，检查差异后按需提交。普通源码修改仍会正常显示。

本机 `.env`、日志、进程状态、旧备份和构建缓存继续留在本地并由忽略规则排除。新增的真实密钥或密码也必须留在本地配置中。

## GitHub 连接

本次环境通过本机 Clash HTTP 代理 `127.0.0.1:7897`，使用 SSH 连接 `ssh.github.com:443`。专用 SSH 密钥和代理参数记录在当前仓库的本地 Git 配置，不会提交；本机需保持 Clash 运行。换电脑后应配置自己的 SSH 身份和网络连接，不要复制或上传私钥。
