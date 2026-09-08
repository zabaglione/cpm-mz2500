; Runtime contract probe: real BDOS calls, no emulator-specific traps.
        org 0100h
        ld sp,probe_stack_top
        ld c,12
        call 5
        cp 031h
        jp nz,failed
        ld de,scb_query
        ld c,49
        call 5
        ld a,l
        cp 031h
        jp nz,failed
        ld de,parse_query
        ld c,152
        call 5
        ld a,h
        and l
        cp 0ffh
        jp z,failed
        ld hl,parsed_fcb+1
        ld de,parsed_name
        ld b,11
parse_check:
        ld a,(de)
        cp (hl)
        jp nz,failed
        inc de
        inc hl
        djnz parse_check
        ld de,probe_fcb
        ld c,19
        call 5
        ld de,probe_fcb
        ld c,22
        call 5
        cp 0ffh
        jp z,failed
        ld hl,write_buffer
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
        ld de,write_buffer
        ld c,26
        call 5
        ld de,3
        ld c,44
        call 5
        ld de,probe_fcb
        ld c,21
        call 5
        or a
        jp nz,failed
        ld de,read_buffer
        ld c,26
        call 5
        ld de,probe_fcb
        ld c,33
        call 5
        or a
        jp nz,failed
        ld hl,write_buffer
        ld de,read_buffer
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
        ld de,1
        ld c,44
        call 5
        ld de,probe_fcb
        ld c,16
        call 5
        cp 0ffh
        jp z,failed
        ld c,48
        ld de,0
        call 5
        or a
        jp nz,failed
        ld de,pass_message
        jr finish
failed:
        ld de,fail_message
finish:
        ld c,9
        call 5
        jp 0
scb_query: defb 5,0,0,0
parse_query: defw parse_text,parsed_fcb
parse_text: defb "CHECK.DAT",0
parsed_name: defb "CHECK   DAT"
parsed_fcb: defs 36,0
probe_fcb: defb 0,"P3CHECK DAT"
        defs 24,0
pass_message: defb "P3TEST PASS: BDOS 31 SCB PARSE MULTI RANDOM FLUSH",13,10,"$"
fail_message: defb "P3TEST FAIL",13,10,"$"
write_buffer: defs 384,0
read_buffer: defs 384,0
        defs 96,0
probe_stack_top:
