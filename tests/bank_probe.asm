; Direct bank-switch and cross-bank MOVE checks, executed as a real transient.
        org 0100h
SEL: equ 0e851h
XMOVE: equ 0e857h
MOVE: equ 0e84bh
        ld sp,stack_top
        ; Temporarily borrow common TPA E000h-E1FFh, restoring loader bytes.
        ld hl,0e000h
        ld de,saved_common
        ld bc,512
        ldir
        ld hl,snippet
        ld de,0e000h
        ld bc,snippet_end-snippet
        ldir
        ld a,033h
        ld (02000h),a
        call 0e000h
        ld (status),a
        ld hl,saved_common
        ld de,0e000h
        ld bc,512
        ldir
        ld a,(status)
        or a
        jp nz,failed
        ld hl,source
        ld bc,384
        xor a
fill:
        ld (hl),a
        inc hl
        inc a
        dec bc
        push af
        ld a,b
        or c
        jr z,filled
        pop af
        jr fill
filled:
        pop af
        ld bc,0001h             ; bank 1 source -> bank 0 destination
        call XMOVE
        ld de,source
        ld hl,03000h
        ld bc,384
        call MOVE
        ld bc,0100h             ; bank 0 source -> bank 1 destination
        call XMOVE
        ld de,03000h
        ld hl,destination
        ld bc,384
        call MOVE
        ld hl,source
        ld de,destination
        ld bc,384
compare:
        ld a,(de)
        cp (hl)
        jp nz,failed
        inc hl
        inc de
        dec bc
        ld a,b
        or c
        jr nz,compare
        ; No XMOVE: a second MOVE must stay in the currently selected bank.
        ld hl,destination
        ld (hl),0
        ld de,source
        inc de
        ld bc,1
        call MOVE
        ld a,(destination)
        cp 1
        jp nz,failed
        ; A zero-byte MOVE must not touch either memory or the pointers.
        ld hl,destination
        ld de,source
        ld bc,0
        call MOVE
        ld a,(destination)
        cp 1
        jp nz,failed
        ; Upper TPA lies over banked BDOS addresses, but must stay independent.
        ld hl,0d000h
        ld bc,256
        ld a,05ah
fill_high:
        ld (hl),a
        inc hl
        dec bc
        ld a,b
        or c
        ld a,05ah
        jr nz,fill_high
        ld c,12
        call 5
        cp 031h
        jp nz,failed
        ld hl,0d000h
        ld b,0
check_high:
        ld a,(hl)
        cp 05ah
        jp nz,failed
        inc hl
        djnz check_high
        ld de,pass_message
        jr done
failed:
        ld de,fail_message
done:
        ld c,9
        call 5
        jp 0
; Copied to common TPA; only fixed common operands and relative branches.
snippet:
        ld (0e180h),sp
        ld sp,0e1f0h
        ld bc,01234h
        ld de,05678h
        ld hl,09abch
        xor a
        call SEL
        ld a,b
        cp 012h
        jr nz,snip_bad
        ld a,c
        cp 034h
        jr nz,snip_bad
        ld a,d
        cp 056h
        jr nz,snip_bad
        ld a,e
        cp 078h
        jr nz,snip_bad
        ld a,h
        cp 09ah
        jr nz,snip_bad
        ld a,l
        cp 0bch
        jr nz,snip_bad
        ld a,055h
        ld (02000h),a
        ld a,1
        call SEL
        ld a,(02000h)
        cp 033h
        jr nz,snip_bad
        xor a
        jr snip_done
snip_bad:
        ld a,1
        call SEL
        ld a,1
snip_done:
        ld sp,(0e180h)
        ret
snippet_end:
status: defb 0
pass_message: defb "BANKTEST PASS: SELMEM XMOVE MOVE UPPER-TPA",13,10,"$"
fail_message: defb "BANKTEST FAIL",13,10,"$"
saved_common: defs 512,0
source: defs 384,0
destination: defs 384,0
        defs 128,0
stack_top:
