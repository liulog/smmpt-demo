# 子模块整合记录

本次仅以原有 workspace 仓库为只读来源，在 `smmpt-demo` 内创建独立 Git 副本，
没有修改原 `workspace/NEMU` 或 `workspace/opensbi` 的分支、索引、工作文件。

## NEMU

- 来源：`/home/jingyu/workspace/NEMU`，原分支 `master`，工作区干净。
- 最初从本地复制的提交为 `7b43ce37fc73df299eb8109ab3058743915fb75f`，
  与原 `../NEMU` 当时的源码提交一致。
- 后按用户要求添加 `upstream=https://github.com/OpenXiangShan/NEMU.git`，
  执行 fetch 和 `git pull --ff-only upstream master`，快进 17 个提交。
- 当前固定提交：`16f993840b97afb491a12fc43ce50eb58f49e101`，与本次获取的
  `upstream/master` 完全一致，没有本地模拟器源码补丁。
- `.gitmodules` 改为直接从 OpenXiangShan 上游获取。原 `../NEMU` 未被修改。

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

## 实际构建与验证（2026-10-24）

用户明确授权后，执行 `bash scripts/build.sh enabled`，成功构建 NEMU、payload 和
OpenSBI；随后执行 `bash scripts/run.sh enabled`。S-mode 183 项断言通过，
NEMU GOOD TRAP，命令返回 0。原始日志和产物哈希见 [归档](results/2026-10-24-enabled/)。
`disabled`、`no-csr` 未构建、未运行。

第一次沙箱构建因网络阻断而缺失依赖；获准联网后完成构建。
构建时发现 `__NOT_DEFINED=1` 实际会启用 NEMU 自动提交规则，原脚本对该开关的理解错误，
导致父仓库产生一条没有文件变更的本地自动提交。脚本已改为显式传入 `git_commit=`，
重新执行 enabled 构建和运行，确认未再产生自动提交。归档保留此次最终运行的原始日志。
最终构建是增量构建，沿用此前成功编译的对象；未执行 clean 或安装。

此前仅做过 Shell 语法检查、日志判定器 20 项合成输入检查和 Git 差异检查。
早先 README 手写的预期 PASS 日志已撤下；当前展示内容从此次实测串口原文提取。
