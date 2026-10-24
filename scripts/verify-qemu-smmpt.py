#!/usr/bin/env python3
"""Boot existing artifacts, exercise a guest shell, and require clean shutdown."""
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import subprocess
import time


def main():
    os.chdir(Path(__file__).resolve().parent.parent)
    out = Path(os.environ.get("RESULT_DIR", "build/qemu-smmpt/verification"))
    out.mkdir(parents=True, exist_ok=True)
    log_path = out / "console.log"
    commands = (
        "uname -a\n"
        "cat /proc/cpuinfo\n"
        "if test -r /proc/cpuinfo && uname -r; then "
        "printf '\\nSMMPT-USERSPACE-%s\\n' PASS; fi\n"
        "poweroff -f\n"
    )
    started = time.monotonic()
    deadline = started + float(os.environ.get("TIMEOUT", "180"))
    sent = False
    timed_out = False
    data = bytearray()
    with log_path.open("wb") as log:
        proc = subprocess.Popen(
            ["bash", "scripts/run-qemu-smmpt.sh"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        selector = selectors.DefaultSelector()
        selector.register(proc.stdout, selectors.EVENT_READ)
        try:
            while selector.get_map():
                if time.monotonic() >= deadline:
                    timed_out = True
                    proc.terminate()
                    break
                for key, _ in selector.select(timeout=0.5):
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    log.write(chunk)
                    log.flush()
                    data.extend(chunk)
                    if b"Kernel panic" in data:
                        proc.terminate()
                    if not sent and re.search(rb"(?:^|[\r\n])[^\r\n]*# $", data):
                        proc.stdin.write(commands.encode())
                        proc.stdin.flush()
                        sent = True
            try:
                code = proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                code = proc.wait()
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            selector.close()
            proc.stdin.close()
            proc.stdout.close()
    text = data.decode(errors="replace").replace("\r", "")
    checks = {
        "no_timeout": not timed_out,
        "qemu_exit_zero": code == 0,
        "smmpt_hart_protection": bool(re.search(r"Platform HART Protection\s+:.*\bsmmpt\b", text)),
        "walker_selftest": "QEMU: SELFTEST fw(0x80010000)=DENY(ok)  kernel(0x80200000)=PERMIT(ok)" in text,
        "linux_boot": "Linux version " in text,
        "guest_shell": sent,
        "userspace_command": "\nSMMPT-USERSPACE-PASS\n" in text,
        "sv39": bool(re.search(r"^mmu\s+: sv39$", text, re.MULTILINE)),
        "guest_poweroff": "reboot: Power down" in text,
        "no_panic": "Kernel panic" not in text,
    }
    inputs = [
        Path("build/qemu-smmpt/qemu-system-riscv64"),
        Path("build/opensbi-smmpt/platform/generic/firmware/fw_dynamic.bin"),
        Path(os.environ.get("IMAGE", "../linux-riscv-gate-merge/arch/riscv/boot/Image")),
        Path(os.environ.get("INITRD", "../linux-riscv-gate-merge/rootfs.cpio.gz")),
    ]
    record = {
        "checks": checks, "exit_code": code,
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "command": ["bash", "scripts/run-qemu-smmpt.sh"],
        "guest_commands": commands.splitlines(),
        "overrides": {k: os.environ[k] for k in ("IMAGE", "INITRD", "APPEND", "TIMEOUT") if k in os.environ},
        "sources": {p: subprocess.check_output(["git", "-C", p, "rev-parse", "HEAD"], text=True).strip()
                    for p in ("qemu-smmpt", "opensbi-smmpt")},
        "source_status": {p: subprocess.check_output(["git", "-C", p, "status", "--porcelain"], text=True)
                          for p in ("qemu-smmpt", "opensbi-smmpt")},
        "sha256": {},
    }
    for path in inputs:
        if path.is_file():
            with path.open("rb") as stream:
                record["sha256"][str(path)] = hashlib.file_digest(stream, "sha256").hexdigest()
    for path in map(Path, ("scripts/run-qemu-smmpt.sh", "scripts/verify-qemu-smmpt.py")):
        record["sha256"][str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    (out / "run.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(checks, indent=2))
    print(f"Console: {log_path}")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
