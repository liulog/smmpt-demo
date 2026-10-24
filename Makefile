# Explicit build targets only; run/verify never depend on a build target.
.DEFAULT_GOAL := help

NEMU_MODE ?= enabled

.PHONY: help nemu-build nemu-run nemu-verify qemu-build qemu-run qemu-verify

help:
	@printf '%s\n' \
	  'NEMU (standalone S-mode payload):' \
	  '  make nemu-build                  Build NEMU, payload and its OpenSBI' \
	  '  make nemu-verify                 Run existing artifacts and check results' \
	  '  make nemu-run                    Same as nemu-verify' \
	  '  NEMU_MODE=enabled|disabled|no-csr (default: enabled)' \
	  '' \
	  'QEMU Smmpt (Linux):' \
	  '  make qemu-build                  Build qemu-smmpt and opensbi-smmpt' \
	  '  make qemu-run                    Start an interactive Linux console' \
	  '  make qemu-verify                 Verify boot, guest commands and shutdown' \
	  '' \
	  'Run/verify only use existing artifacts. Builds require explicit authorization.' \
	  'No install or clean targets. Pass JOBS, CROSS_COMPILE, TIMEOUT as needed.' \
	  'QEMU also accepts IMAGE, INITRD, APPEND and RESULT_DIR (verification logs).'

nemu-build:
	bash scripts/build.sh "$(NEMU_MODE)"

nemu-run nemu-verify:
	bash scripts/run.sh "$(NEMU_MODE)"

qemu-build:
	bash scripts/build-qemu-smmpt.sh

qemu-run:
	bash scripts/run-qemu-smmpt.sh

qemu-verify:
	python3 -B scripts/verify-qemu-smmpt.py
