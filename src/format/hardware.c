#include "../migration/migration.h"
extern u8 cylinder,side,sector,status,drive;
extern u16 transferred;
extern u8 track[],readbuf[];
/* Status/command/track/sector are inverted. Track buffer is pre-inverted.
 * All transfer loops run with interrupts disabled. No BDOS inside DRQ loops.
 */
u8 hw_start(void) __naked __sdcccall(0) { __asm
 di
 ld a,#7
 out (0xc8),a
 ld a,#0x7f
 out (0xc9),a
 ld a,#14
 out (0xc8),a
 xor a
 out (0xc9),a
 out (0xde),a
 ld a,(_drive)
 or #0x84
 out (0xdc),a
 ld bc,#0
fmt_spin:
 ld e,#4
fmt_spin_inner:
 dec e
 jr nz,fmt_spin_inner
 dec bc
 ld a,b
 or c
 jr nz,fmt_spin
 ld a,#0xf4
 out (0xd8),a
 call fmt_settle
 call fmt_wait
 jr c,fmt_failed
 and #0xd0
 jp nz,fmt_failed
 ld l,#0
 ret
fmt_settle:
 ld a,#5
fmt_settle_loop:
 dec a
 jr nz,fmt_settle_loop
 ret
fmt_wait:
 ld de,#0
 ld b,#8
fmt_wait_loop:
 in a,(0xd8)
 cpl
 ld (_status),a
 bit 0,a
 ret z
 dec de
 ld a,d
 or e
 jr nz,fmt_wait_loop
 djnz fmt_wait_loop
 scf
 ret
fmt_failed:
 ld l,#1
 ret
 __endasm; }
u8 hw_seek(void) __naked __sdcccall(0) { __asm
 ld a,(_cylinder)
 cpl
 out (0xdb),a
 ld a,#0xe4
 out (0xd8),a
 call fmt_settle
 call fmt_wait
 jr c,fmt_failed
 and #0x90
 jr nz,fmt_failed
 ld l,#0
 ret
 __endasm; }
u8 hw_track(void) __naked __sdcccall(0) { __asm
 ld a,(_side)
 out (0xdd),a
 ld hl,#_track
 ld bc,#0
 ld (_transferred),bc
 ld a,#0x0b
 out (0xd8),a
 call fmt_settle
 ld de,#0xffff
fmt_write_poll:
 in a,(0xd8)
 cpl
 ld (_status),a
 bit 1,a
 jr nz,fmt_write_byte
 bit 0,a
 jr z,fmt_write_done
 dec de
 ld a,d
 or e
 jr nz,fmt_write_poll
 jp fmt_transfer_failed
fmt_write_byte:
 ld a,b
 cp #25
 jp nc,fmt_transfer_failed
 ld a,(hl)
 out (0xdb),a
 inc hl
 inc bc
 ld de,#0xffff
 jr fmt_write_poll
fmt_write_done:
 ld (_status),a
 ld (_transferred),bc
 and #0xf4
 jp nz,fmt_transfer_failed
 ; At least the full 16-sector template (6066 tokens) must be consumed.
 ld hl,#6066
 or a
 sbc hl,bc
 jp nc,fmt_transfer_failed
 ld l,#0
 ret
 __endasm; }
u8 hw_read(void) __naked __sdcccall(0) { __asm
 ld a,(_sector)
 cpl
 out (0xda),a
 ld hl,#_readbuf
 ld bc,#0
 ld (_transferred),bc
 ld a,#0x77
 out (0xd8),a
 call fmt_settle
 ld de,#0xffff
fmt_read_poll:
 in a,(0xd8)
 cpl
 ld (_status),a
 bit 1,a
 jr nz,fmt_read_byte
 bit 0,a
 jr z,fmt_read_done
 dec de
 ld a,d
 or e
 jr nz,fmt_read_poll
 jp fmt_transfer_failed
fmt_read_byte:
 ld a,b
 or a
 jp nz,fmt_transfer_failed
 in a,(0xdb)
 ld (hl),a
 inc hl
 inc bc
 ld de,#0xffff
 jr fmt_read_poll
fmt_read_done:
 ld (_status),a
 ld (_transferred),bc
 and #0x9c
 jp nz,fmt_transfer_failed
 ld a,b
 cp #1
 jp nz,fmt_transfer_failed
 ld a,c
 or a
 jp nz,fmt_transfer_failed
 ld l,#0
 ret
 __endasm; }
/* Preserve transferred-byte count on timeout or overrun as well. */
void fmt_failure(void) __naked __sdcccall(0) { __asm
fmt_transfer_failed:
 ld (_transferred),bc
 jp fmt_failed
 __endasm; }
void hw_stop(void) __naked __sdcccall(0) { __asm
 ; Stop a timed-out transfer before any console I/O. Leave motor state to
 ; BIOS warm boot, which invalidates its cylinder and sector caches.
 ld a,#0x2f
 out (0xd8),a
 call fmt_settle
 ret
 __endasm; }
