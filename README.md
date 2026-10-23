# NEMU MPT：S-mode 最小验证 Demo

目标是在 NEMU 上启动 OpenSBI，再进入独立的 RV64 S-mode payload，通过实验性 SBI
接口配置 MPT，并用 load/store/fetch 验证权限。源码设计不依赖 Linux、initramfs 或用户态。

**当前状态：已提交源码，未编译、未运行，功能是否正确尚未验证。**
没有可提供的实测串口日志。构建脚本、启动流程和下述用例均待实际验证。

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
页表位于 OpenSBI BSS，由现有 PMP 策略保护；S-mode 通过 SBI 管理权限，不接收固件表指针。
OpenSBI 启动时只探测并注册接口，MPT 由 S-mode 显式初始化和启用。

## 获取代码

```sh
git clone --recurse-submodules https://github.com/liulog/smmpt-demo.git
cd smmpt-demo
# 已有 checkout：
git submodule update --init --recursive
```

子模块固定版本以父仓库 gitlink 为准。NEMU 固定为本地已有的
`7b43ce37fc73df299eb8109ab3058743915fb75f`；OpenSBI 基于最新获取的
`origin/smmpt`（`131bda94`）rebase 后恢复本地修改，另存于 `smmpt-demo` 分支。

## 实验性 SBI 接口

EID 为 `0x084d5054`，使用 SBI v0.2 调用约定：`a7=EID`、`a6=FID`，
参数放在 `a0/a1`，返回 `a0=error`、`a1=value`。可通过 SBI Base probe-extension 发现接口。
定义见 [`sbi_ecall_mpt.h`](opensbi/include/sbi/sbi_ecall_mpt.h)。

| FID | 操作 | 参数 / 返回值 |
| --- | --- | --- |
| 0 | RESET | `a0=默认权限`，重建表并回收池 |
| 1 | SET_PAGE | `a0=4 KiB 对齐 PA`，`a1=权限` |
| 2 | GET_PAGE | `a0=PA`，返回该页 MPT 权限 |
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

## 待运行的验证用例

以下描述源码中的用例意图，不表示用例已经运行或通过。

- SBI 发现、未初始化状态、非法参数、未知 FID、启用时拒绝修改。
- RESET 默认全拒绝 / RWX、邻页权限保留、64 KiB / 32 MiB / 16 GiB 索引边界。
- 32 页固件表池耗尽时不留下部分更新，RESET 后可重新使用。
- 全部 8 种 RWX 组合的真实读、写、取指；拒绝时检查 `scause=5/7/1` 和目标 `stval`。
- 关闭 MPT 恢复访问；失败 store 不改变原数据；独立检查 PMP 对固件的保护。
- SBI 功能关闭、NEMU 没有 MPT CSR 时的接口缺席回归。

边界和池耗尽用例只查询权限元数据，不访问那些可能没有 RAM 的物理地址。
真实访问探针只针对 payload 中独立对齐的 data / executable 页面。
当前 payload 不覆盖 Sv39 页表遍历、跨页非对齐访存、多 hart 或虚拟化场景。

## 构建与运行

以下是供明确授权后执行的命令，本次尚未执行。需要主机 GCC/G++、make、Python 3、
rsync、dtc，以及 RV64 交叉工具链；NEMU 还需要 readline、SDL2、zlib 等开发依赖。
不自动安装依赖。NEMU 自身的依赖规则可能需要联网获取 SoftFloat 等资源。
路径不能包含空白字符。

```sh
# 主路径：构建 NEMU、S-mode payload 和 OpenSBI
bash scripts/build.sh enabled
# 单独运行，不会触发构建
bash scripts/run.sh enabled

# 可选回归，各自独立构建、运行
bash scripts/build.sh disabled
bash scripts/run.sh disabled
bash scripts/build.sh no-csr
bash scripts/run.sh no-csr
```

可通过 `CROSS_COMPILE=riscv64-unknown-elf-` 切换工具链前缀，`JOBS=8` 控制构建并行度，
`TIMEOUT=120` 控制运行超时秒数。默认前缀为 `riscv64-unknown-linux-gnu-`。

构建复制 NEMU 到 `build/<mode>/nemu/`，不改变子模块配置，并禁用 NEMU 自动 Git 提交。
配置禁用 `PERF_OPT`，显式启用并检查 PMP/PMA；保留 64-bit `paddr_t` 所需的
4 GiB 稀疏内存 backing，DT 描述从 `0x80000000` 开始的 2 GiB RAM。
OpenSBI 在 `0x80000000`，payload 在 `0x80200000`，DTB 重定位到 `0x88000000`。

所有产物位于 `build/<mode>/`：`payload.elf/bin`、`nemu.dtb`、`nemu.config`、
`opensbi/platform/generic/firmware/fw_payload.bin`、`manifest.txt` 和分阶段构建日志。
运行后生成 `console.log`、`nemu-runtime.log`。**必须同时通过 S-mode 完成标记与
NEMU `HIT GOOD TRAP` 校验**；超时或指令预算耗尽不算成功。

## 实际验证状态

| 项目 | 状态 |
| --- | --- |
| Shell 语法检查 | 已通过 `bash -n scripts/build.sh scripts/run.sh` |
| 日志判定器检查 | 20 项合成输入检查通过；仅检查日志判定逻辑 |
| 编译与链接 | 未执行 |
| OpenSBI 启动与 SBI 注册 | 未运行验证 |
| S-mode MPT 权限与异常用例 | 未运行验证 |
| 串口实测日志 | 无 |

待实际构建并运行后，才能根据留存的原始日志填写结果、展示串口输出。
此前版本包含手写的预期 PASS 日志，该段没有实测依据，现已删除。

OpenSBI 子模块原有 `tests/mpt/` 和 `docs/mpt-demo.md` 随本地修改保留。
其中历史文档里的结果声明未在本次工作中核验，不作为本仓库验证通过的依据。
