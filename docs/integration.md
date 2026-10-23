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
当时 `disabled`、`no-csr` 未构建、未运行；后续回归结果见下文。

第一次沙箱构建因网络阻断而缺失依赖；获准联网后完成构建。
构建时发现 `__NOT_DEFINED=1` 实际会启用 NEMU 自动提交规则，原脚本对该开关的理解错误，
导致父仓库产生一条没有文件变更的本地自动提交。脚本已改为显式传入 `git_commit=`，
重新执行 enabled 构建和运行，确认未再产生自动提交。归档保留此次最终运行的原始日志。
最终构建是增量构建，沿用此前成功编译的对象；未执行 clean 或安装。

此前仅做过 Shell 语法检查、日志判定器 20 项合成输入检查和 Git 差异检查。
早先 README 手写的预期 PASS 日志已撤下；当前展示内容从此次实测串口原文提取。

## 单核审查修复及增强用例实测

保留 NEMU 的单 hart 验证范围和六个实验性 SBI FID。修复旧 Linux runner 的
自动 Git 提交开关，撤下其无归档日志支撑的历史成功声明。
父仓库增加真实 RAM 边界访问、独立页权限、16 槽索引和完整固件表池保护检查，
并检查耗尽失败不泄漏最后一个可分配表页。

构建准备改为同步受版本控制的 NEMU 文件、删除过期副本源码，并按锁文件获取依赖；
运行入口增加源码与产物记录核验，旧二进制不能作为修改后源码的验证结果。
随后用户明确授权编译验证，执行 `bash scripts/build.sh enabled` 和
`bash scripts/run.sh enabled`，均返回 0。增强后的 payload 完成 2658 项断言，
NEMU GOOD TRAP，pc=`0x8020135a`，trap code=0。

NEMU 进行了增量构建和重新链接，二进制哈希与旧归档一致；payload 重新编译。
OpenSBI 首次链接确定表池范围，向 payload 专用数据节写入该范围后再次链接，
两次均为 `0x80047000–0x80066fff`。所有验证在 S-mode 执行。
此次没有 clean、安装或运行历史 Linux runner；随后单独授权并执行了 disabled/no-csr 回归，见下文。

新证据位于 [增强用例归档](results/2026-10-24-enabled-expanded/)，保存串口、
模拟器和构建原始日志、实际输入及产物哈希、表池范围和运行元数据。
其中提交号记录基线，构建时的实际改动由 `build-record.json` 的文件哈希标识。
旧 [183 项断言归档](results/2026-10-24-enabled/) 保持原样。
8 项主机侧工具检查也已通过，但它们与此次 NEMU guest 实测分别记录。

历史 OpenSBI 提交不重写，也不代作者补 DCO 签署。若将来提交上游，应从干净基线
整理 lib/docs/tests 补丁，由贡献者确认并签署 DCO；当前是实验 fork。

## 接口缺席回归与提交

用户另行授权后，分别执行 `bash scripts/build.sh disabled`、
`bash scripts/build.sh no-csr`，以及相应的 `scripts/run.sh` 命令，四条命令均返回 0。
这两个输出目录此前没有产物，按锁定提交获取依赖后独立构建了 NEMU、payload 和固件。

两种模式都完成 Base probe 与直接 STATUS 调用两项检查，输出
`MPT-DEMO: absent-extension regression PASS`，最终在 `0x802002be` GOOD TRAP、trap code 0。
disabled 固件没有 ecall_mpt 符号，NEMU 的 MPT 配置开启；no-csr 固件包含该符号，
但 NEMU 的 MPT 配置关闭，验证了 CSR 不存在时安全跳过接口注册的路径。

完整原始证据分别保存在 [disabled 归档](results/2026-10-24-disabled/) 和
[no-csr 归档](results/2026-10-24-no-csr/)。归档提交号记录构建时的基线，
文件哈希记录当时包含修复的工作区。两个接口缺席模式不属于权限矩阵验证。

OpenSBI 的 runner/docs 修复提交为 `5ffcb7e461a66a5fa30a5af39cf3f626e2f48758`，
父仓库更新 gitlink 引用该提交。固件源码文件内容与归档的输入哈希保持一致。
