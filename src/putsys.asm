; PUTSYS.COM - copy the CP/M system from the boot floppy onto the SASI
; hard disk's boot area, so the HDD system can be updated without pulling
; the SD card out of the drive.
;
; What it copies (via direct BIOS calls; every target lies in RESERVED
; tracks - the C: filesystem and the partition table are never touched):
;   FD LBA 16          -> HD1 partition record 0   (IPLPRO boot header)
;   FD LBA 0-15,48-63  -> records 16-47            (bank06 image)
;   FD LBA 32-47,80-95 -> records 48-79            (bank07 image)
; In BIOS terms: drive A: tracks 0-5 (its OFF=6 system area) to drive C:
; tracks 0-2 (its OFF=3 boot area), 128-byte record by record, with
; write-type 1 (directory) so every record flushes to the disk at once.
;
; Usage: with the NEW boot floppy in drive A (either booted from it, or
; inserted under the old hard-disk system):  PUTSYS
; Then press the IPL button: the cold boot loads the new system from the
; hard disk and re-seeds the EMM warm-boot cache.

BDOS:           equ 00005h
BF_CONOUT:      equ 2
BF_PRINT:       equ 9

; BIOS jump-table offsets (base recovered from the warm-boot vector at
; 0001h, which holds BIOS+3).
; NOTE: names must not start with a register letter + underscore -
; z80asm 1.8 silently assembles "ld a,B_WRITE" as "ld a,b"(!).
JT_SELDSK:      equ 27
JT_SETTRK:      equ 30
JT_SETSEC:      equ 33
JT_SETDMA:      equ 36
JT_READ:        equ 39
JT_WRITE:       equ 42

        include "generated_putsys.inc"

; where the boot-drive byte lands on the hard disk (bank07 = records 48+)
BDD_OFF:        equ BOOT_DRIVE_BYTE_ADDR - 0e000h
BDD_REC:        equ 48 + BDD_OFF / 256
BDD_TRK:        equ BDD_REC / 32
BDD_SEC:        equ (BDD_REC & 01fh) * 2 + (BDD_OFF & 0ffh) / 128
BDD_BUFO:       equ BDD_OFF & 07fh

        org     00100h

start:
        ld      sp,local_stack_top
        ld      de,msg_banner
        ld      c,BF_PRINT
        call    BDOS
        ; drive C: must exist (SASI board present with a medium)
        ld      c,2
        call    bios_seldsk
        ld      a,h
        or      l
        jp      z,no_hard_disk

        ld      ix,ranges
next_range:
        ld      a,(ix+2)        ; sectors in this range
        or      a
        jp      z,all_done
copy_range:
        call    copy_sector
        inc     (ix+0)
        inc     (ix+1)
        dec     (ix+2)
        jr      nz,copy_range
        ld      de,3
        add     ix,de
        jr      next_range

; copy one 256-byte sector ((ix+0)=FD LBA -> (ix+1)=HD record) as two
; 128-byte records
copy_sector:
        xor     a
        ld      (rec_half),a
copy_half:
        ; --- read the record from A: ---
        ld      c,0
        call    bios_seldsk
        ld      a,(ix+0)        ; FD LBA 0-95
        rrca
        rrca
        rrca
        rrca
        and     00fh
        ld      c,a             ; track = lba >> 4  (0-5)
        ld      b,0
        call    bios_settrk
        ld      a,(ix+0)
        and     00fh
        add     a,a
        ld      hl,rec_half
        add     a,(hl)
        ld      c,a             ; record = (lba & 0Fh)*2 + half
        ld      b,0
        call    bios_setsec
        ld      bc,buffer
        call    bios_setdma
        call    bios_read
        or      a
        jp      nz,io_error
        ; --- write the record to C: ---
        ld      c,2
        call    bios_seldsk
        ld      a,(ix+1)        ; HD partition record 0-79
        rrca
        rrca
        rrca
        rrca
        rrca
        and     007h
        ld      c,a             ; track = record >> 5  (0-2)
        ld      b,0
        call    bios_settrk
        ld      a,(ix+1)
        and     01fh
        add     a,a
        ld      hl,rec_half
        add     a,(hl)
        ld      c,a             ; record = (rec & 1Fh)*2 + half
        ld      b,0
        call    bios_setsec
        ld      bc,buffer
        call    bios_setdma
        ld      c,1             ; directory-type write: immediate flush
        call    bios_write
        or      a
        jp      nz,io_error
        ld      hl,rec_half
        inc     (hl)
        ld      a,(hl)
        cp      2
        jr      c,copy_half
        ; one progress dot per sector
        ld      e,"."
        ld      c,BF_CONOUT
        call    BDOS
        ret

all_done:
        ; the copied image is the FLOPPY system: re-apply the hard-disk
        ; builder's one-byte patch so the booted system lands on C:
        ld      c,2
        call    bios_seldsk
        ld      bc,BDD_TRK
        call    bios_settrk
        ld      bc,BDD_SEC
        call    bios_setsec
        ld      bc,buffer
        call    bios_setdma
        call    bios_read
        or      a
        jp      nz,io_error
        ld      a,2
        ld      (buffer+BDD_BUFO),a
        ld      bc,buffer
        call    bios_setdma
        ld      c,1
        call    bios_write
        or      a
        jp      nz,io_error
        ld      de,msg_done
        jr      say_and_exit
no_hard_disk:
        ld      de,msg_no_hd
        jr      say_and_exit
io_error:
        ld      de,msg_error
say_and_exit:
        ld      c,BF_PRINT
        call    BDOS
        jp      00000h          ; warm boot

; --- BIOS trampolines --------------------------------------------------
; The offset rides in A so BC (the BIOS argument register) stays intact;
; HL/DE are scratch for every entry used here (SELDSK only RETURNS HL).
bios_seldsk:
        ld      a,JT_SELDSK
        jr      bios_call
bios_settrk:
        ld      a,JT_SETTRK
        jr      bios_call
bios_setsec:
        ld      a,JT_SETSEC
        jr      bios_call
bios_setdma:
        ld      a,JT_SETDMA
        jr      bios_call
bios_read:
        ld      a,JT_READ
        jr      bios_call
bios_write:
        ld      a,JT_WRITE
bios_call:
        ld      hl,(00001h)     ; BIOS+3
        ld      e,a
        ld      d,0
        add     hl,de
        ld      de,-3
        add     hl,de
        jp      (hl)            ; BIOS routine returns to our caller

; --- data --------------------------------------------------------------
; (fd_lba_start, hd_record_start, sector_count) triplets, 0-count ends
ranges:
        defb    16,0,1          ; boot header
        defb    0,16,16         ; bank06 first half
        defb    48,32,16        ; bank06 second half
        defb    32,48,16        ; bank07 first half
        defb    80,64,16        ; bank07 second half
        defb    0,0,0

msg_banner:
        defb    0dh,0ah,"PUTSYS - floppy system -> hard disk boot area"
        defb    0dh,0ah,"$"
msg_done:
        defb    0dh,0ah,"DONE - press the IPL button to boot the new system"
        defb    0dh,0ah,"$"
msg_no_hd:
        defb    0dh,0ah,"NO HARD DISK (C: not present)",0dh,0ah,"$"
msg_error:
        defb    0dh,0ah,"DISK I/O ERROR - hard disk unchanged in part",0dh,0ah,"$"

rec_half:
        defb    0
buffer:
        defs    128
        defs    64
local_stack_top:
