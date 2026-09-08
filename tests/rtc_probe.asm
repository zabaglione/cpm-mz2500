; Set/read calendar boundary cases via actual CP/M Plus BDOS 104/105.
; Restores the saved date/time before returning, including after failure.
        org 0100h
        ld sp,stack_top
        ld c,105
        ld de,saved_stamp
        call 5
        ld ix,cases
        ld b,case_count
next_case:
        push bc
        push ix
        pop de
        ld c,104
        call 5
        ld de,actual
        ld c,105
        call 5
        ; Function 104 sets seconds to zero; 105 returns BCD seconds in A.
        cp 3
        jr nc,failed
        push ix
        pop hl
        ld de,actual
        ld b,4
compare:
        ld a,(de)
        cp (hl)
        jr nz,failed
        inc hl
        inc de
        djnz compare
        ld de,5
        add ix,de
        pop bc
        djnz next_case
        push bc
        ld de,0302h             ; 12 PM in the chip's 12-hour format
        ld a,012h
        call check_12_hour
        jr nz,failed
        ld de,0102h             ; 12 AM
        xor a
        call check_12_hour
        jr nz,failed
        ld de,0301h             ; 11 PM
        ld a,023h
        call check_12_hour
        jr nz,failed
        pop bc
        ld hl,pass_message
        jr restore
failed:
        pop bc
        ld hl,fail_message
restore:
        push hl
        ld c,104
        ld de,saved_stamp
        call 5
        pop de
        ld c,9
        call 5
        jp 0
; Exercise the BIOS 12-hour conversion using explicit hardware digits.
check_12_hour:
        push af
        ld bc,00dcch
        ld a,1
        out (c),a
        ld b,10
        xor a
        out (c),a
        ld b,13
        out (c),a
        ld b,4
        ld a,e
        out (c),a
        inc b
        ld a,d
        out (c),a
        ld b,13
        ld a,8
        out (c),a
        ld de,actual
        ld c,105
        call 5
        pop af
        ld hl,actual+2
        cp (hl)
        ret
cases:
        include "generated_rtc_cases.inc"
cases_end:
case_count: equ (cases_end-cases)/5
actual: defs 5,0
saved_stamp: defs 5,0
pass_message: defb "RTCTEST PASS: BCD CALENDAR LEAP CENTURY READ-WRITE",13,10,"$"
fail_message: defb "RTCTEST FAIL",13,10,"$"
        defs 128,0
stack_top:
