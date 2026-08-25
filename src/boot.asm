; MZ-2500 CP/M boot image, bank 06 front: handoff stub + font + cold-init
; overlay. The IPL loads two 8KB banks (06h -> C000h-DFFFh image,
; 07h -> E000h-FFFFh image) and jumps here at C000h with CPU blocks 0-6
; already mapped to banks 00h-06h and block 7 still on the firmware's 0Fh.
;
; Layout of this assembly unit (one binary, C000h..):
;   C000h  stub (below)
;   C100h  console font (96 x 8 bytes, generated)
;   C400h  cold-init overlay (one-shot; the space becomes TPA afterwards)
; CCP (D200h) and BDOS (DA00h) are separate binaries; make_boot_d88.py
; splices everything into the bank images.

BIOS_BOOT:      equ 0e800h
BIOS_CONOUT:    equ 0e80ch      ; jump-table entry #4 (boot,wboot,const,conin,conout)

        org     0c000h

boot_stub:
        di
        ; The pre-boot firmware can leave SIO interrupts armed with an
        ; unknown WR2 vector, and the SIO sits outside the C6h mask
        ; (same quiesce sequence the shipped titles use).
        xor     a
        out     (0cdh),a
        out     (0a1h),a
        out     (0a3h),a
        ld      a,018h
        out     (0a1h),a
        out     (0a3h),a
        ld      sp,0c000h       ; empty TPA below us: safe scratch stack
        ; map CPU block 7 (E000h-FFFFh) from the firmware's 0Fh onto our
        ; bank 07h, where the BDOS tail and the BIOS were just loaded
        ld      a,7
        out     (0b4h),a
        ld      a,007h
        out     (0b5h),a
        jp      BIOS_BOOT

        defs    0c100h-$,0

; --- console font (referenced by the cold-init overlay) ----------------
        include "generated_font.inc"

        defs    0c400h-$,0

; --- one-shot cold-init overlay ---------------------------------------
; Runs once from BIOS boot (on the BIOS stack, which lives in bank 07h,
; so CPU block 2 can be swapped without the stack tricks the resident
; BIOS needs). Afterwards C400h-D1FFh is plain TPA.
coldinit:
        ; 8255: explicit mode word (A/C out, B in), then the proven idle
        ; port C value 58h (BST=1 idle, NST=0 - bit1's rising edge would
        ; reset the CPU, so port C is written exactly once, carefully).
        ld      a,082h
        out     (0e3h),a
        ld      a,058h
        out     (0e2h),a
        ; keyboard/display latch: 80-column bit up, strobe idle
        ld      a,020h
        out     (0e8h),a
        ; text CRTC: 25 rows, single page, 8-colour text; start address 0;
        ; black background
        ld      a,000h
        out     (0f4h),a
        ld      a,005h
        out     (0f5h),a
        ld      a,001h
        out     (0f4h),a
        xor     a
        out     (0f5h),a
        ld      a,002h
        out     (0f4h),a
        xor     a
        out     (0f5h),a
        ld      a,00bh
        out     (0f4h),a
        xor     a
        out     (0f5h),a
        ld      a,00ch
        out     (0f4h),a
        xor     a
        out     (0f5h),a
        ; graphic mask + 8-line (256-glyph) text font from PCG
        ld      a,007h
        out     (0f6h),a
        ld      a,001h
        out     (0f7h),a
        ; bank 39h shows PCG RAM (not the kanji ROM window)
        xor     a
        out     (0cfh),a

        ; load the font into PCG page 0: swap CPU block 2 to bank 39h,
        ; clear the whole 2KB glyph page, copy 96 glyphs to code*8
        ld      a,2
        out     (0b4h),a
        ld      a,039h
        out     (0b5h),a
        ld      hl,04000h
        ld      bc,00800h
coldinit_pcg_clear:
        ld      (hl),0
        inc     hl
        dec     bc
        ld      a,b
        or      c
        jr      nz,coldinit_pcg_clear
        ld      hl,font_data
        ld      de,04000h+FONT_FIRST_CODE*8
        ld      bc,FONT_DATA_SIZE
        ldir
        ld      a,2
        out     (0b4h),a
        ld      a,002h
        out     (0b5h),a

        ; clear the screen and greet through the resident CONOUT
        ld      c,01ah
        call    BIOS_CONOUT
        ld      hl,coldinit_banner
coldinit_banner_loop:
        ld      a,(hl)
        or      a
        ret     z
        ld      c,a
        push    hl
        call    BIOS_CONOUT
        pop     hl
        inc     hl
        jr      coldinit_banner_loop

coldinit_banner:
        defb    "MZ-2500 CP/M 2.2 (58K)",0dh,0ah
        defb    "EMM/SASI port project",0dh,0ah,0ah,0

 if $>=0d200h
        defs    BAD_coldinit_overflows_into_ccp
 endif
