/* Fixed CP/M Plus v3.1 BIOS ABI; all buffers and code are in bank 1. */
#include "migration.h"
u8 call_fn; u16 call_arg;
u8 io_drive,io_write; u16 io_rec; u8 *io_buf;
u16 sys(void) __naked __sdcccall(0) {
 __asm
 ld a,(_call_fn)
 ld c,a
 ld de,(_call_arg)
 call 5
 ret
 __endasm;
}
u8 disk(void) __naked __sdcccall(0) {
 __asm
 ld a,(_io_drive)
 ld c,a
 ld e,#0
 call 0xe81b
 ld a,h
 or l
 jr z,io_failed
 ld a,#1
 call 0xe854
 ld hl,(_io_rec)
 ld a,(_io_drive)
 cp #2
 ld b,#5
 jr c,io_shift
 inc b
io_shift:
 srl h
 rr l
 djnz io_shift
 ld b,h
 ld c,l
 call 0xe81e
 ld a,(_io_drive)
 cp #2
 ld a,#31
 jr c,io_mask
 ld a,#63
io_mask:
 ld hl,(_io_rec)
 and l
 ld c,a
 ld b,#0
 call 0xe821
 ld bc,(_io_buf)
 call 0xe824
 ld a,(_io_write)
 or a
 jr nz,io_do_write
 call 0xe827
 jr io_done
io_do_write:
 cp #2
 ld c,#0
 jr z,io_write_go
 ld c,#1
io_write_go:
 call 0xe82a
io_done:
 ld l,a
 ld h,#0
 ret
io_failed:
 ld hl,#1
 ret
 __endasm;
}
void quit(void) __naked __sdcccall(0) { __asm jp 0 __endasm; }

/* Finish delayed writes while the original drive is still selected. */
u8 flush_disk(void) __naked __sdcccall(0) { __asm
 call 0xe848
 ld l,a
 ld h,#0
 ret
 __endasm; }
