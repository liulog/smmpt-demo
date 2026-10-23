# 子模块整合记录

本次仅以原有 workspace 仓库为只读来源，在 `smmpt-demo` 内创建独立 Git 副本，
没有修改原 `workspace/NEMU` 或 `workspace/opensbi` 的分支、索引、工作文件。

## NEMU

- 来源：`/home/jingyu/workspace/NEMU`，原分支 `master`，工作区干净。
- 远端：`https://github.com/liulog/NEMU.git`。
- 固定提交：`7b43ce37fc73df299eb8109ab3058743915fb75f`。
- 已获取远端并确认该版本在 `origin/master` 历史中。
- 原有 MPT CSR / walker 已满足本独立 demo 的需求，本次不修改模拟器代码。

## OpenSBI

- 来源：`/home/jingyu/workspace/opensbi`，原分支 `smmpt`。
- 原 HEAD：`963b03d730c389bf6de77beeefafac35a0e74b04`，本地有 9 个额外提交，
  这 9 个提交相对原跟踪基线没有净源码差异。
- 远端：`https://github.com/liulog/opensbi.git`。
- 本次 fetch 后远端 `smmpt` 为 `131bda94`；副本执行 `git rebase origin/smmpt` 成功，
  原 9 个提交已按 Git rebase 规则重放。
- 之后将原工作区相对 HEAD 的二进制兼容 diff 通过 `git apply --3way` 应用，
  并逐一复制 `git ls-files --others --exclude-standard` 列出的 12 个未跟踪文件。
- 恢复内容：`lib/sbi/Kconfig`、`lib/sbi/objects.mk` 的修改，实验性接口头文件与实现，
  原有 `tests/mpt/`、`docs/mpt-demo.md` 和示意图。未导入忽略的构建产物。
- 恢复后的修改单独提交到新分支 `smmpt-demo`，不覆盖远端 `smmpt` 历史。
- 恢复修改提交：`6ed11de7a7b829acd63716b39b737f61794f0c03`，已推送至该分支。

固件仍只承担平台初始化和 SBI 接口实现。父仓库 `payload/` 从原测试提取 S-mode
用例及访存探针，去除 Linux / initramfs 嵌入和跳转，改为独立结束的 NEMU 测试。

## 本次验证边界

不执行编译、构建、链接、安装，也未启动新 payload。只做源代码审查、
Shell 语法检查、日志判定器的 20 项主机侧回归，以及 Git 差异检查。
日志回归采用合成输入，覆盖完整输出、丢失权限用例、丢失完成标记、bad trap、
模拟器中止，以及错误的回归模式；不代表 guest 已执行。
README 串口预览是示意。实际 MPT 正负用例结果须在获准构建并运行后记录。
