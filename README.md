# NEMU MPT：S-mode 最小验证 Demo

目标是在 NEMU 上启动 OpenSBI，再进入独立的 RV64 S-mode payload，通过实验性 SBI
接口配置 MPT，并用 load/store/fetch 验证权限。源码设计不依赖 Linux、initramfs 或用户态。

**实测状态（2026-10-24）：增强后的单核 `enabled` 用例已编译并在 NEMU `16f99384` 上运行，
2658 项 S-mode 断言通过，NEMU 以 `HIT GOOD TRAP`、trap code 0、进程返回码 0 结束。**
新增的独立权限、16 槽索引、真实 RAM 边界和完整表池保护检查均已实际执行。
原始日志、构建记录和校验值见 [本次实测归档](docs/results/2026-10-24-enabled-expanded/)。
`disabled`、`no-csr` 也已分别编译并运行通过，均为 GOOD TRAP、返回码 0：
[disabled 归档](docs/results/2026-10-24-disabled/)、[no-csr 归档](docs/results/2026-10-24-no-csr/)。

## 目录与职责

| 路径 | 职责 |
| --- | --- |
| `NEMU/` | Git 子模块，实现 `mmpt` CSR、MPT walker 和访存权限检查 |
| `opensbi/` | Git 子模块，初始化平台、提供实验性 MPT SBI 接口、维护固件内的权限表 |
| `payload/` | 独立 S-mode 程序，运行全部验证、接收并检查异常、输出串口结果 |
| `scripts/build.sh` | 显式构建入口，按模式隔离输出目录 |
| `scripts/run.sh` | 仅运行现有产物并核验结果，不自动构建 |
| `docs/integration.md` | 本地修改保留、rebase 和版本说明 |

```text
NEMU: M-mode @0x80000000
  └─ OpenSBI 初始化 + 实验性 SBI（不执行验证用例）
       └─ S-mode @0x80200000，satp=0
            ├─ SBI: RESET → SET_PAGE → ENABLE
            ├─ 实际 load/store/fetch → S-mode trap → 检查 scause/stval
            ├─ SBI: DISABLE → 确认访问恢复、拒绝的写入没有提交
            └─ 串口 PASS / FAIL → NEMU good / bad trap
```

使用 `satp=0` 让虚拟地址等于物理地址，直接观察 MPT 的物理权限控制。
页表位于 OpenSBI BSS，由现有 PMP 策略保护；S-mode 通过 SBI 管理权限，SBI 不暴露表指针。
测试构建从固件 ELF 提取表池范围嵌入 payload，用于尝试被 PMP 拒绝的读写；它不是 SBI ABI。
OpenSBI 启动时只探测并注册接口，MPT 由 S-mode 显式初始化和启用。

## 获取代码

```sh
git clone --recurse-submodules https://github.com/liulog/smmpt-demo.git
cd smmpt-demo
# 已有 checkout：
git submodule update --init --recursive
```

子模块固定版本以父仓库 gitlink 为准。NEMU 已从
`OpenXiangShan/NEMU` 的 `master` 拉取并快进到
`16f993840b97afb491a12fc43ce50eb58f49e101`，不带本地模拟器补丁；OpenSBI 基于获取的
`origin/smmpt`（`131bda94`）rebase 后恢复本地修改，另存于 `smmpt-demo` 分支。当前 OpenSBI gitlink 为 `c77d1220`，包含旧 runner 的自动提交修复及历史证据说明。
已移除基线之后 9 个没有文件变化的自动提交，仅保留两个有效提交；
清理前后文件树完全一致，详情见 [历史清理记录](docs/integration.md#opensbi-历史清理)。

## 实验性 SBI 接口

EID 为 `0x084d5054`，使用 SBI v0.2 调用约定：`a7=EID`、`a6=FID`，
参数放在 `a0/a1`，返回 `a0=error`、`a1=value`。可通过 SBI Base probe-extension 发现接口。
定义见 [`sbi_ecall_mpt.h`](opensbi/include/sbi/sbi_ecall_mpt.h)。

| FID | 操作 | 参数 / 返回值 |
| --- | --- | --- |
| 0 | RESET | `a0=默认权限`，重建表并回收池 |
| 1 | SET_PAGE | `a0=4 KiB 对齐 PA`，`a1=权限` |
| 2 | GET_PAGE | `a0=4 KiB 对齐 PA`，返回该页 MPT 权限 |
| 3 | ENABLE | 发布根表并启用 MPT |
| 4 | DISABLE | 关闭 MPT |
| 5 | STATUS | bit0 已初始化，bit1 已启用 |

权限为 `R=1, W=2, X=4`，`0` 表示全部拒绝，`7` 表示 RWX。
启用时禁止 RESET / SET_PAGE；修改应先 DISABLE，完成后再 ENABLE。
GET_PAGE 返回 MPT 表的权限；实际访问还受 PMP/PMA 约束。

这是匹配本仓库 NEMU 实现的私有实验协议：`mmpt=CSR 0x382`，mode=1，
三级表、每项 16 组 3-bit 权限、地址范围 `<2^43`，最小粒度 4 KiB。
不是已批准的标准 Smmpt/SBI ABI。当前仅支持单 hart RV64 root domain，
S-mode 可主动关闭 MPT，因此不作为对恶意 S-mode 的隔离机制。

## 验证用例

本仓库只验证单 hart RV64。多核不属于当前目标。

| 用例 | 本次实测 |
| --- | --- |
| SBI 发现、非法参数/状态、未知 FID、启用时拒绝修改 | 通过 |
| RESET、邻页与 64 KiB / 32 MiB / 16 GiB 元数据边界 | 通过 |
| 表池耗尽、失败分裂后最后一页仍可分配、RESET 回收 | 通过 |
| 全部 8 种 RWX 的真实访问及 scause/stval、失败写入不提交 | 通过 |
| RW 数据页与仅 X 代码页同时生效 | 通过 |
| 16 个权限槽逐一测试全部 RWX，并逐槽单独拒绝以检测索引混淆 | 通过 |
| RAM 内 64 KiB / 32 MiB 边界两侧真实读、写、取指 | 通过 |
| 表池每页首尾读写被拒绝，分别在 MPT 开/关时检查 | 通过 |
| `disabled` / `no-csr` 接口缺席回归 | 两个模式均通过 |

真实边界测试只使用 DT RAM 内的专用 scratch 地址：`0x81000000–0x81010fff`、
`0x81fff000–0x82000fff`，与固件、payload、栈和 DTB 分开，见 `payload/link.ld`。
16 GiB 边界超出当前 RAM，仍只验证表管理元数据。
当前用例不覆盖 Sv39 页表遍历、跨页非对齐访存、AMO/LR-SC 或虚拟化；
这些单核扩展场景不计入当前通过范围。

## 构建与运行

本次已获授权并执行全部三个模式的构建和运行命令。复现需要主机 GCC/G++、make、Python 3、
rsync、dtc，以及 RV64 交叉工具链；NEMU 还需要 readline、SDL2、zlib 等开发依赖。
不自动安装系统依赖。准备脚本会按 `scripts/nemu-deps.json` 的固定提交获取 NEMU 依赖，可能需要联网。
路径不能包含空白字符。

```sh
# 主路径：构建 NEMU、S-mode payload 和 OpenSBI
bash scripts/build.sh enabled
# 单独运行，不会触发构建
bash scripts/run.sh enabled

# 接口缺席回归（本次均已执行），各自独立构建、运行
bash scripts/build.sh disabled
bash scripts/run.sh disabled
bash scripts/build.sh no-csr
bash scripts/run.sh no-csr
```

可通过 `CROSS_COMPILE=riscv64-unknown-elf-` 切换工具链前缀，`JOBS=8` 控制构建并行度，
`TIMEOUT=120` 控制运行超时秒数。默认前缀为 `riscv64-unknown-linux-gnu-`。

构建只同步 NEMU 受版本控制的文件到 `build/<mode>/nemu/`，删除副本中的过期源码，
保留生成的 build 目录和受锁定的依赖目录；NEMU 源码须无已跟踪修改。
准备脚本在 make 前检查依赖提交及已跟踪文件，版本不符时停止，不隐式切换已有依赖。
不改变 NEMU 子模块配置，并禁用自动 Git 提交。锁文件固定源码依赖；主机工具链和系统库
仍由用户环境提供，因此不承诺跨环境二进制逐字节一致。
配置禁用 `PERF_OPT`，显式启用并检查 PMP/PMA；保留 64-bit `paddr_t` 所需的
4 GiB 稀疏内存 backing，DT 描述从 `0x80000000` 开始的 2 GiB RAM。
OpenSBI 在 `0x80000000`，payload 在 `0x80200000`，DTB 重定位到 `0x88000000`。

enabled 构建先链接固件以定位 `tables`，将范围写入 payload 的专用数据节，再重新链接固件；
两次表池范围必须一致。本次均为 `0x80047000–0x80066fff`，共 32 页、128 KiB。
零范围的中间 payload 不用于运行。验证逻辑仍全部在 S-mode。

所有产物位于 `build/<mode>/`：`payload.elf/bin`、`nemu.dtb`、`nemu.config`、
`opensbi/platform/generic/firmware/fw_payload.bin`、`manifest.txt` 和分阶段构建日志。
`build-record.json` 记录实际输入源码和产物哈希，构建结束检查输入未变化。
`run.sh` 运行前核对记录，拒绝缺失记录、源码变化或产物被替换的情况；不会自动构建。
旧版产物没有该记录，不能被当前入口当作新版本验证结果。
运行后生成 `console.log`、`nemu-runtime.log`。**必须同时通过 S-mode 完成标记与
NEMU `HIT GOOD TRAP` 校验**；超时或指令预算耗尽不算成功。

## 本次实测结果与串口输出

以下内容直接摘自本次 [原始串口日志](docs/results/2026-10-24-enabled-expanded/console.log)，
仅省略其他启动信息：

```text
Experimental SBI Extensions : mptdemo
MPT-DEMO: S-mode tests starting
MPT-DEMO: ABI, splitting, exhaustion PASS
MPT-DEMO: permissions=0000000000000000 load/store/fetch + recovery PASS
MPT-DEMO: permissions=0000000000000001 load/store/fetch + recovery PASS
MPT-DEMO: permissions=0000000000000002 load/store/fetch + recovery PASS
MPT-DEMO: permissions=0000000000000003 load/store/fetch + recovery PASS
MPT-DEMO: permissions=0000000000000004 load/store/fetch + recovery PASS
MPT-DEMO: permissions=0000000000000005 load/store/fetch + recovery PASS
MPT-DEMO: permissions=0000000000000006 load/store/fetch + recovery PASS
MPT-DEMO: permissions=0000000000000007 load/store/fetch + recovery PASS
MPT-DEMO: all RWX combinations and access faults PASS
MPT-DEMO: RW data and X-only code coexist PASS
MPT-DEMO: all 16 leaf slots with independent RWX PASS
MPT-DEMO: real 64 KiB and 32 MiB boundary accesses PASS
MPT-DEMO: entire firmware table pool read/write protection PASS
MPT-DEMO PASS checks=0x0000000000000a62; standalone S-mode payload, MPT enabled
```

[原始 NEMU 日志](docs/results/2026-10-24-enabled-expanded/nemu-runtime.log)记录了
`HIT GOOD TRAP`，guest 结束地址为 `0x000000008020135a`，trap code 为 `0`，
累计执行 10,667,644 条 guest 指令。`bash scripts/run.sh enabled` 返回 `0`，
源码/产物校验及全部新增串口标记检查通过。
模拟器日志中的 MPT / PMP 拒绝访问记录来自负向测试，不是忽略的测试失败。

| 项目 | 本次结果 |
| --- | --- |
| enabled 的 NEMU 构建 | 增量构建、重新链接成功；二进制哈希与旧归档相同 |
| payload / OpenSBI | payload 重新编译，固件两次链接成功，表池范围一致 |
| S-mode 单核用例 | 2658 项断言通过 |
| NEMU 结束状态 | GOOD TRAP，trap code 0，进程返回码 0 |
| `disabled` | 独立构建、运行通过；关闭固件 MPT 扩展，接口不存在 |
| `no-csr` | 独立构建、运行通过；固件保留 MPT 实现，缺少 CSR 时安全跳过注册 |

两个接口缺席模式的原始串口都包含以下一行：

```text
MPT-DEMO: absent-extension regression PASS
```

该标记位于两项 S-mode 检查之后：Base probe 返回接口不存在，直接调用 STATUS 返回
`SBI_ERR_NOT_SUPPORTED`。两个模式都在 `0x802002be` GOOD TRAP、trap code 0、进程返回码 0；
它们验证接口缺席处理，不重复 enabled 的 2658 项权限检查。
已核对配置与 ELF：disabled 的 NEMU 启用 MPT，但固件不含 `ecall_mpt`；
no-csr 的 NEMU 关闭 MPT，而固件包含 `ecall_mpt`。

本次没有执行 clean 或安装。`build-record.json` 保存实际工作区输入文件和产物哈希；
`manifest.txt` 中的提交号是基线，不能单独表示构建时尚未提交的修改。
`run.json` 记录基线、工作区状态、命令、依赖版本及验证范围；`SHA256SUMS` 校验归档文件。
本次结果仅支持单 hart、RV64、Bare 地址模式的上述用例。

此前父仓库 `d0c00d4` 的 183 项断言结果继续保存在
[历史归档](docs/results/2026-10-24-enabled/)，没有覆盖或改写。
OpenSBI 子模块原有 `tests/mpt/` 和 `docs/mpt-demo.md` 随本地修改保留；
旧文档中缺少原始日志支撑的成功声明已撤下，当前维护入口是父仓库的独立程序。
