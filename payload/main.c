/* SPDX-License-Identifier: BSD-2-Clause */
#include <sbi/sbi_ecall_mpt.h>

typedef unsigned long ulong;
struct result { long error; ulong value; };
volatile ulong fault_cause, fault_addr, fault_resume;
#ifndef EXPECT_ABSENT
static ulong data_pages[3 * 4096 / sizeof(ulong)] __attribute__((aligned(4096)));
/* Filled from the linked firmware ELF by build.sh, never supplied over SBI. */
static const volatile struct {
	ulong base;
	ulong size;
} fw_test_layout __attribute__((section(".fw_test_layout"), used)) = { 0, 0 };
extern char test_slots[], test_boundary_64k[], test_boundary_32m[];
#endif
extern char exec_page[];
extern ulong probe_load(ulong addr);
extern void probe_store(ulong addr, ulong value);
extern ulong probe_exec(ulong addr);
static unsigned int checks;

static struct result call(ulong eid, ulong fid, ulong arg0, ulong arg1)
{
	register ulong a0 asm("a0") = arg0;
	register ulong a1 asm("a1") = arg1;
	register ulong a6 asm("a6") = fid;
	register ulong a7 asm("a7") = eid;

	asm volatile ("ecall" : "+r"(a0), "+r"(a1) : "r"(a6), "r"(a7) : "memory");
	return (struct result) { (long)a0, a1 };
}

static struct result mpt(ulong fid, ulong a0, ulong a1)
{
	return call(SBI_EXT_MPT_DEMO, fid, a0, a1);
}

static void puts(const char *str)
{
	while (*str)
		call(1, 0, *str++, 0);
}

static void hex(ulong value)
{
	int shift;
	for (shift = 60; shift >= 0; shift -= 4)
		call(1, 0, "0123456789abcdef"[(value >> shift) & 15], 0);
}

static void check(int ok, const char *name)
{
	checks++;
	if (ok)
		return;
	puts("\nMPT-DEMO FAIL: ");
	puts(name);
	puts(" check="); hex(checks);
	puts(" scause="); hex(fault_cause);
	puts(" stval="); hex(fault_addr);
	puts("\n");
	register ulong a0 asm("a0") = 1;
	asm volatile (".word 0x0000006b" : : "r"(a0) : "memory");
	for (;;) asm volatile ("wfi");
}

#ifndef EXPECT_ABSENT
static void success(ulong fid, ulong a0, ulong a1)
{
	check(mpt(fid, a0, a1).error == 0, "SBI operation");
}

static void query(ulong addr, ulong perm)
{
	struct result r = mpt(SBI_EXT_MPT_GET_PAGE, addr, 0);
	check(!r.error && r.value == perm, "page permission");
}

static void status(ulong bits)
{
	struct result r = mpt(SBI_EXT_MPT_STATUS, 0, 0);
	check(!r.error && r.value == bits, "status");
}

static void protected_pool(void)
{
	ulong addr, offset, base = fw_test_layout.base, size = fw_test_layout.size;

	check(base >= 0x80000000UL && !(base & 4095) && size == 32 * 4096 &&
	      base + size <= 0x80200000UL, "linked firmware pool bounds");
	for (addr = base; addr < base + size; addr += 4096) {
		for (offset = 0; offset <= 4088; offset += 4088) {
			probe_load(addr + offset);
			check(fault_cause == 5 && fault_addr == addr + offset,
			      "PMP denies reading table pool");
			probe_store(addr + offset, 0);
			check(fault_cause == 7 && fault_addr == addr + offset,
			      "PMP denies writing table pool");
		}
	}
}

/* Each scratch page starts with `li a0, 42; ret`; a permitted store changes 42 to 43. */
#define CODE_42 0x0000806702a00513UL
#define CODE_43 0x0000806702b00513UL

static void access_page(ulong addr, ulong perm)
{
	ulong value = probe_load(addr);

	check(perm & SBI_MPT_R ? (!fault_cause && value == CODE_42) :
	      (fault_cause == 5 && fault_addr == addr), "independent page load");
	probe_store(addr, CODE_43);
	check(perm & SBI_MPT_W ? !fault_cause :
	      (fault_cause == 7 && fault_addr == addr), "independent page store");
	asm volatile ("fence.i" ::: "memory");
	value = probe_exec(addr);
	check(perm & SBI_MPT_X ?
	      (!fault_cause && value == (perm & SBI_MPT_W ? 43 : 42)) :
	      (fault_cause == 1 && fault_addr == addr), "independent page fetch");
}

static ulong slot_permission(unsigned int slot, unsigned int round)
{
	/* Single-denied-slot rounds distinguish aliases between all sixteen slots. */
	return round < 8 ? (slot + round) & 7 : (slot == round - 8 ? 0 : 7);
}

static void independent_pages(void)
{
	ulong base = (ulong)test_slots, addr, perm;
	unsigned int round, slot;

	/* Each of the sixteen slots sees every mask, with distinct adjacent masks. */
	for (round = 0; round < 24; round++) {
		success(SBI_EXT_MPT_RESET, SBI_MPT_RWX, 0);
		for (slot = 0; slot < 16; slot++) {
			addr = base + slot * 4096;
			*(volatile ulong *)addr = CODE_42;
			success(SBI_EXT_MPT_SET_PAGE, addr, slot_permission(slot, round));
		}
		asm volatile ("fence.i" ::: "memory");
		success(SBI_EXT_MPT_ENABLE, 0, 0);
		for (slot = 0; slot < 16; slot++)
			access_page(base + slot * 4096, slot_permission(slot, round));
		success(SBI_EXT_MPT_DISABLE, 0, 0);
		for (slot = 0; slot < 16; slot++) {
			perm = slot_permission(slot, round);
			check(probe_load(base + slot * 4096) ==
			      (perm & SBI_MPT_W ? CODE_43 : CODE_42) && !fault_cause,
			      "slot recovery and denied store preservation");
		}
	}
	puts("MPT-DEMO: all 16 leaf slots with independent RWX PASS\n");
}

static void real_boundaries(void)
{
	const ulong boundaries[] = {
		(ulong)test_boundary_64k, (ulong)test_boundary_32m
	};
	unsigned int boundary, round, side;
	ulong addr, perm;

	for (boundary = 0; boundary < 2; boundary++) {
		for (round = 0; round < 8; round++) {
			success(SBI_EXT_MPT_RESET, SBI_MPT_RWX, 0);
			for (side = 0; side < 2; side++) {
				addr = boundaries[boundary] - 4096 + side * 4096;
				*(volatile ulong *)addr = CODE_42;
				success(SBI_EXT_MPT_SET_PAGE, addr, round ^ (side ? 7 : 0));
			}
			asm volatile ("fence.i" ::: "memory");
			success(SBI_EXT_MPT_ENABLE, 0, 0);
			for (side = 0; side < 2; side++)
				access_page(boundaries[boundary] - 4096 + side * 4096,
					    round ^ (side ? 7 : 0));
			success(SBI_EXT_MPT_DISABLE, 0, 0);
			for (side = 0; side < 2; side++) {
				addr = boundaries[boundary] - 4096 + side * 4096;
				perm = round ^ (side ? 7 : 0);
				check(probe_load(addr) == (perm & SBI_MPT_W ? CODE_43 : CODE_42)
				      && !fault_cause, "boundary store preservation");
			}
		}
	}
	puts("MPT-DEMO: real 64 KiB and 32 MiB boundary accesses PASS\n");
}
#endif

void demo_main(void)
{
	struct result r = call(0x10, 3, SBI_EXT_MPT_DEMO, 0);
#ifndef EXPECT_ABSENT
	ulong page = (ulong)data_pages + 4096;
	ulong code = (ulong)exec_page;
	unsigned int i;

	puts("\nMPT-DEMO: S-mode tests starting\n");
	check(!r.error && r.value == 1, "base probe");
	status(0);
	check(mpt(SBI_EXT_MPT_ENABLE, 0, 0).error == -10, "enable before reset");
	check(mpt(SBI_EXT_MPT_GET_PAGE, page, 0).error == -10, "get before reset");
	check(mpt(SBI_EXT_MPT_SET_PAGE, page, 1).error == -10, "set before reset");
	check(mpt(99, 0, 0).error == -2, "unknown FID");
	check(mpt(SBI_EXT_MPT_RESET, 8, 0).error == -3, "invalid reset");
	success(SBI_EXT_MPT_RESET, 0, 0);
	success(SBI_EXT_MPT_SET_PAGE, page, 7);
	query(page, 7);
	query(page - 4096, 0);
	query(page + 4096, 0);
	query((1UL << 43) - 4096, 0);
	success(SBI_EXT_MPT_RESET, 7, 0);
	status(1);
	probe_load(0x80000000);
	check(fault_cause == 5 && fault_addr == 0x80000000,
	      "PMP protects firmware even with MPT disabled");
	check(mpt(SBI_EXT_MPT_SET_PAGE, page + 1, 1).error == -3, "unaligned");
	check(mpt(SBI_EXT_MPT_SET_PAGE, 1UL << 43, 1).error == -3, "out of range");
	check(mpt(SBI_EXT_MPT_GET_PAGE, 1UL << 43, 0).error == -3, "get range");
	check(mpt(SBI_EXT_MPT_SET_PAGE, page, 8).error == -3, "invalid permissions");
	check(mpt(SBI_EXT_MPT_SET_PAGE, 0x80000000, 1).error == -5, "firmware protected");
	/* Split paths around each indexing boundary; never access these addresses. */
	const ulong boundaries[] = { 1UL << 16, 1UL << 25, 1UL << 34 };
	for (i = 0; i < 3; i++) {
		ulong addr = boundaries[i];
		success(SBI_EXT_MPT_SET_PAGE, addr - 4096, 2);
		success(SBI_EXT_MPT_SET_PAGE, addr, 1);
		query(addr - 8192, 7);
		query(addr - 4096, 2);
		query(addr, 1);
		query(addr + 4096, 7);
	}
	/* Sixteen distinct root entries each need two child tables; only 31 free. */
	success(SBI_EXT_MPT_RESET, 7, 0);
	for (i = 1; i <= 15; i++)
		success(SBI_EXT_MPT_SET_PAGE, (ulong)i << 34, 1);
	check(mpt(SBI_EXT_MPT_SET_PAGE, 16UL << 34, 1).error == -1, "pool exhaustion");
	query(16UL << 34, 7);
	query(15UL << 34, 1);
	/* The failed two-page split must leave the last free page usable. */
	success(SBI_EXT_MPT_SET_PAGE, (1UL << 34) + (1UL << 25), 2);
	query((1UL << 34) + (1UL << 25), 2);
	check(mpt(SBI_EXT_MPT_SET_PAGE, (1UL << 34) + (2UL << 25), 1).error == -1,
	      "pool fully exhausted after last single split");
	success(SBI_EXT_MPT_RESET, 7, 0);
	query(15UL << 34, 7);
	puts("MPT-DEMO: ABI, splitting, exhaustion PASS\n");

	/* Exercise all eight permission combinations with real S-mode accesses. */
	for (i = 0; i < 8; i++) {
		success(SBI_EXT_MPT_DISABLE, 0, 0);
		*(volatile ulong *)page = 123;
		success(SBI_EXT_MPT_SET_PAGE, page, i);
		success(SBI_EXT_MPT_SET_PAGE, code, i);
		query(page, i);
		query(page - 4096, 7);
		query(page + 4096, 7);
		success(SBI_EXT_MPT_ENABLE, 0, 0);
		status(3);
		check(mpt(SBI_EXT_MPT_RESET, 7, 0).error == -4, "reset while enabled");
		check(mpt(SBI_EXT_MPT_SET_PAGE, page, 7).error == -4, "set while enabled");
		ulong value = probe_load(page);
		check(i & 1 ? (!fault_cause && value == 123) :
			(fault_cause == 5 && fault_addr == page), "load enforcement");
		probe_store(page, 456);
		check(i & 2 ? !fault_cause :
			(fault_cause == 7 && fault_addr == page), "store enforcement");
		value = probe_exec(code);
		check(i & 4 ? (!fault_cause && value == 42) :
			(fault_cause == 1 && fault_addr == code), "execute enforcement");
		success(SBI_EXT_MPT_DISABLE, 0, 0);
		check(probe_load(page) == (i & 2 ? 456 : 123) && !fault_cause,
		      "disable restores access and denied stores do not commit");
		puts("MPT-DEMO: permissions="); hex(i);
		puts(" load/store/fetch + recovery PASS\n");
	}
	puts("MPT-DEMO: all RWX combinations and access faults PASS\n");
	/* RW data and execute-only code must coexist without sharing a permission. */
	success(SBI_EXT_MPT_RESET, SBI_MPT_RWX, 0);
	*(volatile ulong *)page = 123;
	success(SBI_EXT_MPT_SET_PAGE, page, SBI_MPT_R | SBI_MPT_W);
	success(SBI_EXT_MPT_SET_PAGE, code, SBI_MPT_X);
	success(SBI_EXT_MPT_ENABLE, 0, 0);
	check(probe_load(page) == 123 && !fault_cause, "RW data load with X-only code");
	probe_store(page, 456);
	check(!fault_cause, "RW data store with X-only code");
	probe_load(code);
	check(fault_cause == 5 && fault_addr == code, "X-only code is unreadable");
	check(probe_exec(code) == 42 && !fault_cause, "X-only code executes");
	probe_exec(page);
	check(fault_cause == 1 && fault_addr == page, "RW data is non-executable");
	success(SBI_EXT_MPT_DISABLE, 0, 0);
	check(probe_load(page) == 456 && !fault_cause, "independent data write committed");
	puts("MPT-DEMO: RW data and X-only code coexist PASS\n");
	independent_pages();
	real_boundaries();
	success(SBI_EXT_MPT_RESET, SBI_MPT_RWX, 0);
	protected_pool();
	success(SBI_EXT_MPT_ENABLE, 0, 0);
	protected_pool();
	success(SBI_EXT_MPT_DISABLE, 0, 0);
	puts("MPT-DEMO: entire firmware table pool read/write protection PASS\n");
	/* Finish with MPT enabled and permissive RAM/MMIO permissions. */
	success(SBI_EXT_MPT_RESET, 7, 0);
	success(SBI_EXT_MPT_ENABLE, 0, 0);
	status(3);
	puts("MPT-DEMO PASS checks=0x"); hex(checks);
	puts("; standalone S-mode payload, MPT enabled\n");
#else
	check(!r.error && !r.value, "extension should be absent");
	check(mpt(SBI_EXT_MPT_STATUS, 0, 0).error == -2, "absent extension call");
	puts("MPT-DEMO: absent-extension regression PASS\n");
#endif
	register ulong a0 asm("a0") = 0;
	asm volatile (".word 0x0000006b" : : "r"(a0) : "memory");
	for (;;) asm volatile ("wfi");
}

void unexpected_trap_report(void)
{
	check(0, "unexpected trap");
	for (;;) asm volatile ("wfi");
}
