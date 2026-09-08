; RP5C15 at nCCh, n=register (SHARP I/O map; Ricoh EK-086-9908 pp.6-7).
; Gregorian window 1978..2077; CP/M day 1 = 1978-01-01.
; TIME preserves HL/DE. A=0 on success, 1 on invalid/unrepresentable date.
rtc_time:
        push hl
        push de
        push bc
        ld a,c
        cp 0ffh
        jp z,rtc_set
        call rtc_snapshot
        ; Reject non-BCD digit values before doing calendar arithmetic.
        ld hl,rtc_raw
        ld b,13
rtc_validate_digit:
        ld a,(hl)
        cp 10
        jp nc,rtc_bad
        inc hl
        djnz rtc_validate_digit
        ld hl,rtc_raw+11
        call rtc_pair_binary
        cp 78
        jr c,rtc_recent_year
        sub 78
        jr rtc_year_ready
rtc_recent_year:
        add a,22
rtc_year_ready:
        ld (rtc_year_index),a
        ld hl,rtc_raw+9
        call rtc_pair_binary
        or a
        jp z,rtc_bad
        cp 13
        jp nc,rtc_bad
        ld (rtc_month),a
        ld hl,rtc_raw+7
        call rtc_pair_binary
        or a
        jp z,rtc_bad
        ld (rtc_day),a
        ld b,a
        call rtc_month_length
        cp b
        jp c,rtc_bad
        ld a,(rtc_year_index)
        ld l,a
        ld h,0
        add hl,hl
        ld de,rtc_year_starts
        add hl,de
        ld e,(hl)
        inc hl
        ld d,(hl)
        push de
        ld a,(rtc_month)
        dec a
        ld l,a
        ld h,0
        add hl,hl
        ld de,rtc_month_starts
        add hl,de
        ld e,(hl)
        inc hl
        ld d,(hl)
        pop hl
        add hl,de
        ld a,(rtc_day)
        dec a
        ld e,a
        ld d,0
        add hl,de
        ld a,(rtc_month)
        cp 3
        jr c,rtc_day_ready
        ld a,(rtc_year_index)
        and 3
        cp 2
        jr nz,rtc_day_ready
        inc hl
rtc_day_ready:
        ld (rtc_stamp),hl
        ld a,(rtc_hour_mode)
        and 1
        jr nz,rtc_hour24
        ld a,(rtc_raw+5)
        and 2
        ld (rtc_pm),a
        ld a,(rtc_raw+5)
        and 1
        ld (rtc_raw+5),a
        ld hl,rtc_raw+4
        call rtc_pair_binary
        or a
        jp z,rtc_bad
        cp 13
        jp nc,rtc_bad
        cp 12
        jr nz,rtc_hour12_ready
        xor a
rtc_hour12_ready:
        ld b,a
        ld a,(rtc_pm)
        or a
        ld a,b
        jr z,rtc_hour_ready
        add a,12
        jr rtc_hour_ready
rtc_hour24:
        ld hl,rtc_raw+4
        call rtc_pair_binary
rtc_hour_ready:
        cp 24
        jp nc,rtc_bad
        call rtc_binary_bcd
        ld (rtc_stamp+2),a
        ld hl,rtc_raw+2
        call rtc_pair_binary
        cp 60
        jp nc,rtc_bad
        call rtc_binary_bcd
        ld (rtc_stamp+3),a
        ld hl,rtc_raw
        call rtc_pair_binary
        cp 60
        jp nc,rtc_bad
        call rtc_binary_bcd
        ld (rtc_stamp+4),a
        ld hl,rtc_stamp
        ld de,SCB+058h
        ld bc,5
        ldir
        jp rtc_ok

rtc_set:
        ld hl,(SCB+058h)
        ld a,h
        or l
        jp z,rtc_bad
        ld de,36526
        or a
        sbc hl,de
        jp nc,rtc_bad
        ld hl,(SCB+058h)
        dec hl
        xor a
        ld (rtc_year_index),a
rtc_find_year:
        ld bc,365
        ld a,(rtc_year_index)
        and 3
        cp 2
        jr nz,rtc_year_length_ready
        inc bc
rtc_year_length_ready:
        or a
        sbc hl,bc
        jr c,rtc_year_found
        ld a,(rtc_year_index)
        inc a
        ld (rtc_year_index),a
        jr rtc_find_year
rtc_year_found:
        add hl,bc
        ld a,1
        ld (rtc_month),a
rtc_find_month:
        push hl
        call rtc_month_length
        pop hl
        ld c,a
        ld b,0
        or a
        sbc hl,bc
        jr c,rtc_month_found
        ld a,(rtc_month)
        inc a
        ld (rtc_month),a
        jr rtc_find_month
rtc_month_found:
        add hl,bc
        ld a,l
        inc a
        ld hl,rtc_raw+7
        call rtc_store_binary
        ld a,(rtc_month)
        ld hl,rtc_raw+9
        call rtc_store_binary
        ld a,(rtc_year_index)
        add a,78
        cp 100
        jr c,rtc_write_year
        sub 100
rtc_write_year:
        ld hl,rtc_raw+11
        call rtc_store_binary
        ; Weekday: 1978-01-01 was Sunday.
        ld hl,(SCB+058h)
        dec hl
        ld de,7
rtc_week_loop:
        or a
        sbc hl,de
        jr nc,rtc_week_loop
        add hl,de
        ld a,l
        ld (rtc_raw+6),a
        ld a,(SCB+05ah)
        call rtc_validate_bcd
        jp c,rtc_bad
        cp 024h
        jp nc,rtc_bad
        ld hl,rtc_raw+4
        call rtc_store_bcd
        ld a,(SCB+05bh)
        call rtc_validate_bcd
        jp c,rtc_bad
        cp 060h
        jp nc,rtc_bad
        ld hl,rtc_raw+2
        call rtc_store_bcd
        ld a,(SCB+05ch)
        call rtc_validate_bcd
        jp c,rtc_bad
        cp 060h
        jp nc,rtc_bad
        ld hl,rtc_raw
        call rtc_store_bcd
        ; Stop counters, select bank 1, configure 24h and leap cycle.
        ld bc,00dcch
        in a,(c)
        ld (rtc_saved_mode),a
        and 4
        or 1
        out (c),a
        ld b,10
        ld a,1
        out (c),a
        inc b
        ld a,(rtc_year_index)
        add a,2
        and 3
        out (c),a
        ld b,13
        ld a,(rtc_saved_mode)
        and 4
        out (c),a
        ld b,0
        ld hl,rtc_raw
rtc_write_digits:
        ld a,(hl)
        out (c),a
        inc hl
        inc b
        ld a,b
        cp 13
        jr c,rtc_write_digits
        ld b,15
        ld a,2
        out (c),a           ; reset subsecond divider before starting
        ld b,13
        ld a,(rtc_saved_mode)
        or 8
        and 13
        out (c),a
rtc_ok:
        xor a
        jr rtc_return
rtc_bad:
        ld a,1
rtc_return:
        pop bc
        pop de
        pop hl
        ret

rtc_snapshot:
        ld bc,00dcch
        in a,(c)
        ld (rtc_saved_mode),a
        and 4
        or 1
        out (c),a
        ld b,10
        in a,(c)
        ld (rtc_hour_mode),a
        ld b,13
        ld a,(rtc_saved_mode)
        and 4
        out (c),a
        ld hl,rtc_raw
        ld b,0
rtc_read_digits:
        in a,(c)
        and 15
        ld (hl),a
        inc hl
        inc b
        ld a,b
        cp 13
        jr c,rtc_read_digits
        ld a,(rtc_saved_mode)
        out (c),a
        ret
rtc_pair_binary:
        ld e,(hl)
        inc hl
        ld a,(hl)
        add a,a
        ld d,a
        add a,a
        add a,a
        add a,d
        add a,e
        ret
rtc_binary_bcd:
        ld d,0
rtc_bcd_loop:
        cp 10
        jr c,rtc_bcd_done
        sub 10
        inc d
        jr rtc_bcd_loop
rtc_bcd_done:
        ld e,a
        ld a,d
        rlca
        rlca
        rlca
        rlca
        or e
        ret
rtc_store_binary:
        call rtc_binary_bcd
rtc_store_bcd:
        ld d,a
        and 15
        ld (hl),a
        inc hl
        ld a,d
        rrca
        rrca
        rrca
        rrca
        and 15
        ld (hl),a
        ret
rtc_validate_bcd:
        ld d,a
        and 15
        cp 10
        jr nc,rtc_bcd_bad
        ld a,d
        and 0f0h
        cp 0a0h
        jr nc,rtc_bcd_bad
        ld a,d
        or a
        ret
rtc_bcd_bad:
        scf
        ret
rtc_month_length:
        ld a,(rtc_month)
        dec a
        ld e,a
        ld d,0
        ld hl,rtc_month_days
        add hl,de
        ld a,(rtc_month)
        cp 2
        ld a,(hl)
        ret nz
        ld a,(rtc_year_index)
        and 3
        cp 2
        ld a,28
        ret nz
        inc a
        ret
rtc_saved_mode: defb 0
rtc_hour_mode: defb 0
rtc_pm: defb 0
rtc_year_index: defb 0
rtc_month: defb 0
rtc_day: defb 0
rtc_stamp: defs 5,0
rtc_raw: defs 13,0
        include "generated_rtc.inc"
