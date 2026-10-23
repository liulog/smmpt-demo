/* SPDX-License-Identifier: BSD-2-Clause */
OUTPUT_ARCH(riscv)
ENTRY(_start)
PHDRS
{
	text PT_LOAD FLAGS(5);
	data PT_LOAD FLAGS(6);
}
SECTIONS
{
	. = 0x80200000;
	.text : { *(.text.entry) *(.text .text.*) } :text
	.rodata : { *(.rodata .rodata.*) } :text
	. = ALIGN(4096);
	.test_exec : { *(.test_exec) } :text
	. = ALIGN(4096);
	.fw_test_layout : { KEEP(*(.fw_test_layout)) } :data
	.data : { *(.data .data.*) *(.sdata .sdata.*) } :data
	.bss (NOLOAD) : {
		__bss_start = .;
		*(.bss .bss.*) *(.sbss .sbss.*) *(COMMON)
		. = ALIGN(16);
		. += 16384;
		__stack_top = .;
		__bss_end = .;
	} :data
	ASSERT(. < 0x80400000, "Standalone payload exceeds reserved 2 MiB")
	/* Dedicated RAM scratch areas; symbols do not enlarge the firmware image. */
	test_slots = 0x81000000;
	test_boundary_64k = 0x81010000;
	test_boundary_32m = 0x82000000;
}
