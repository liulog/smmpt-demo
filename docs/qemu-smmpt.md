# QEMU + OpenSBI Smmpt Linux 启动

新增子模块与原有 NEMU / OpenSBI 路径独立：

| 子模块 | 上游分支 | 固定提交 |
| --- | --- | --- |
| `qemu-smmpt/` | `pathakraul/qemu:rpathak_smmpt_v1` | `3da028d454cea2149cc95c9f4160431b5c3b1b13` |
| `opensbi-smmpt/` | `pathakraul/opensbi:rpathak_smmpt_v5` | `bd5ca8b1d313ea19845d6e3232a3f9b1b72a7a76` |

实测状态（2026-10-24）：两项均编译成功，使用指定 Linux Image 和配套
initramfs，单 hart 启动到用户态，执行 `uname`、读取 `/proc/cpuinfo`，
然后通过 `poweroff -f` 正常关闭 QEMU，返回码 0。未修改两份上游源码。
原始日志、输入 SHA256 和检查结果见
[实测归档](results/2026-10-24-qemu-smmpt/)。

## 运行现有产物

```sh
make qemu-run
```

入口只运行，不隐式构建。预期产物路径：

- `build/qemu-smmpt/qemu-system-riscv64`
- `build/opensbi-smmpt/platform/generic/firmware/fw_dynamic.bin`

默认复用 `../linux-riscv-gate-merge/arch/riscv/boot/Image` 和
`../linux-riscv-gate-merge/rootfs.cpio.gz`，可用 `IMAGE`、`INITRD` 覆盖。
默认 `rdinit=/init`；`APPEND` 可覆盖完整内核命令行。
单 hart、1 GiB RAM、TCG、串口终端，使用 `Ctrl-a x` 退出。

自动验证（仅运行已有产物，不编译）：

```sh
make qemu-verify
```

验证脚本等待 shell 提示符后发送用户态命令和关机命令，同时要求
OpenSBI 注册 Smmpt、QEMU walker 自检、Sv39、用户态完成标记、正常关机、
无 panic 和返回码 0 全部通过。默认超时 180 秒，超时不算成功。
日志和检查记录位于 `build/qemu-smmpt/verification/`。

CPU 同时开启 `x-smsdid=on,x-smmpt=on`，SDID 为 6 位。
保持复位时的 Bare 模式，由 OpenSBI 探测并发布实际 MPT 根表。
当前 RV64 QEMU 的模式能力掩码包含 Smmpt43 和 Smmpt52；
OpenSBI 按支持情况选择模式。此次串口确认 `Platform HART Protection : pmp,smmpt`，
QEMU 自检显示固件 `0x80010000` 被拒绝、内核 `0x80200000` 可执行。
这次验证覆盖启动链和上游自检，不等同于 NEMU 的 2658 项独立权限测试。

### 指定 Image 的启动约束

该 Image 含有 `CSRRSI FAST`，只支持 Sv39；QEMU 默认允许更高层级分页，
直接启动会在 `ptp_early_pgtable_pool_init` panic。因此脚本明确设置
`sv48=off,sv57=off`，保留原始 Image。实测 `/proc/cpuinfo` 报告 `mmu : sv39`。
Linux 自带的 IEE、BITMAP、PTP 启动自检也报告通过。

配套 rootfs 的 `dev/console` 是普通文件，直接 `rdinit=/bin/sh` 会使 PID 1
因读到 EOF 退出并引发 panic。使用 rootfs 自带的 `/init`，由其挂载 devtmpfs、
重定向 console 并启动 getty，用户态交互与关机正常。

## 显式编译

本次已获授权编译新增的 QEMU `riscv64-softmmu` 和 OpenSBI `generic` 固件。
不重新编译 Linux，不执行 install 或 clean。

```sh
make qemu-build
```

脚本使用仓库相对路径，工具链从 PATH 查找；默认前缀为
`riscv64-unknown-linux-gnu-`，可通过 `CROSS_COMPILE` 覆盖，`JOBS` 默认 8。
参数可直接传给 make，例如 `make qemu-build JOBS=8`、
`make qemu-verify TIMEOUT=120`、`make qemu-run IMAGE=../path/to/Image`。
`qemu-*` 目标只使用 `qemu-smmpt/`、`opensbi-smmpt/` 及相应产物；
`nemu-*` 使用原有 NEMU 链路。运行和验证目标没有构建依赖。
QEMU configure 会在构建目录准备其标准 Python 构建环境和源码依赖。
两阶段日志分别为 `build/qemu-smmpt/build.log` 和 `build/opensbi-smmpt/build.log`。
系统需预先具备 GCC/G++、Python venv/pip、ninja、pkg-config、make、glib2 与
libfdt 开发文件和 RISC-V 工具链；脚本不安装系统依赖。
首次 configure 需要联网获取 wrap 文件固定提交的 keycodemapdb、
berkeley-softfloat-3 和 berkeley-testfloat-3；本次未执行这些依赖的测试构建。
