; Resident CP/M Plus BIOS. Bank 0 = physical 08h..0Eh; bank 1 = 00h..06h.
; E000h..FFFFh is common physical bank 07h. All hardware code runs in bank 0.
; DI/polling BIOS: the hardware gateway is non-reentrant and uses a common stack.
        include "generated_core.inc"
SCB:    equ 0e79ch
CCP_CACHE: equ 0a500h
CCP_SIZE: equ 0c80h
        org 0e800h
        jp cold_boot
        jp warm_boot
        jp gate_const
        jp gate_conin
        jp gate_conout
        jp gate_list
        jp gate_punch
        jp gate_reader
        jp gate_home
        jp gate_seldsk
        jp gate_settrk
        jp gate_setsec
        jp setdma
        jp read
        jp write
        jp gate_listst
        jp gate_sectran
        jp gate_ready
        jp gate_not_ready
        jp gate_not_ready
        jp gate_devtbl
        jp noop
        jp gate_drvtbl
        jp noop
        jp gate_flush
        jp move
        jp gate_time
        jp selmem
        jp setbnk
        jp xmove
        jp reserved
        jp reserved
        jp reserved

cold_boot:
        di
        ld sp,gate_stack_top
        xor a
        call selmem
        call CORE_boot
        jr start_ccp
warm_boot:
        di
        ld sp,gate_stack_top
        xor a
        call selmem
        call CORE_wboot
start_ccp:
        ld a,0c3h
        ld (0),a
        ld (5),a
        ld (038h),a
        ld hl,0e803h
        ld (1),hl
        ld (039h),hl
        ld hl,(SCB+062h)
        ld (6),hl
        ; page zero belongs to the TPA bank: repeat after selecting it.
        ld bc,0100h
        call xmove
        ld hl,0100h
        ld de,CCP_CACHE
        ld bc,CCP_SIZE
        call move
        ld a,1
        call selmem
        ld a,0c3h
        ld (0),a
        ld (5),a
        ld (038h),a
        ld hl,0e803h
        ld (1),hl
        ld (039h),hl
        ld hl,(SCB+062h)
        ld (6),hl
        xor a
        ld (3),a
        ld a,(SCB+013h)
        ld (4),a
        im 1
        jp 0100h

; Restore all registers except A/flags, as required by SELMEM.
selmem:
        push bc
        push hl
        and 1
        ld (current_bank),a
        or a
        ld hl,map_system
        jr z,select_map
        ld hl,map_tpa
select_map:
        xor a
        out (0b4h),a
        ld b,7
select_loop:
        ld a,(hl)
        out (0b5h),a
        inc hl
        djnz select_loop
        pop hl
        pop bc
        ret
setbnk:
        and 1
        ld (dma_bank),a
        ret
setdma:
        ld (logical_dma),bc
        ret
xmove:
        ld a,c
        and 1
        ld (move_source),a
        ld a,b
        and 1
        ld (move_dest),a
        ld a,1
        ld (move_pending),a
        ret
; MOVE advances HL/DE, handles zero length, and restores the caller's bank.
move:
        ld (move_sp),sp
        ld sp,move_stack_top
        ld a,(current_bank)
        ld (move_return),a
        ld a,(move_pending)
        or a
        jr nz,move_begin
        ld a,(current_bank)
        ld (move_source),a
        ld (move_dest),a
move_begin:
        xor a
        ld (move_pending),a
move_loop:
        ld a,b
        or c
        jr z,move_done
        ld a,(move_source)
        call selmem
        ld a,(de)
        ld (move_byte),a
        ld a,(move_dest)
        call selmem
        ld a,(move_byte)
        ld (hl),a
        inc hl
        inc de
        dec bc
        jr move_loop
move_done:
        ld a,(move_return)
        call selmem
        ld sp,(move_sp)
        ret

read:
        push hl
        ld hl,read_bridge
        ld (gateway_target+1),hl
        pop hl
        jp gateway
write:
        push hl
        ld hl,write_bridge
        ld (gateway_target+1),hl
        pop hl
        jp gateway
read_bridge:
        ld bc,disk_bounce
        call CORE_setdma
        call CORE_read
        or a
        ret nz
        ld a,(dma_bank)
        ld b,a
        ld c,0
        call xmove
        ld hl,(logical_dma)
        ld de,disk_bounce
        ld bc,128
        call move
        xor a
        ret
write_bridge:
        push bc
        ld a,(dma_bank)
        ld c,a
        ld b,0
        call xmove
        ld hl,disk_bounce
        ld de,(logical_dma)
        ld bc,128
        call move
        ld bc,disk_bounce
        call CORE_setdma
        pop bc
        jp CORE_write

gateway:
        ld (caller_sp),sp
        ld sp,gate_stack_top
        ld a,(current_bank)
        ld (caller_bank),a
        xor a
        call selmem
gateway_target:
        call 0
        push af
        ld a,(caller_bank)
        call selmem
        pop af
        ld sp,(caller_sp)
        ret
noop:
        ret
reserved:
        jp 0
gate_const:
        push hl
        ld hl,CORE_const
        ld (gateway_target+1),hl
        pop hl
        jp gateway
gate_conin:
        push hl
        ld hl,CORE_conin
        ld (gateway_target+1),hl
        pop hl
        jp gateway
gate_conout:
        push hl
        ld hl,CORE_conout
        ld (gateway_target+1),hl
        pop hl
        jp gateway
gate_list:
        push hl
        ld hl,CORE_list
        ld (gateway_target+1),hl
        pop hl
        jp gateway
gate_punch:
        push hl
        ld hl,CORE_punch
        ld (gateway_target+1),hl
        pop hl
        jp gateway
gate_reader:
        push hl
        ld hl,CORE_reader
        ld (gateway_target+1),hl
        pop hl
        jp gateway
gate_home:
        push hl
        ld hl,CORE_home
        ld (gateway_target+1),hl
        pop hl
        jp gateway
gate_seldsk:
        push hl
        ld hl,CORE_seldsk
        ld (gateway_target+1),hl
        pop hl
        jp gateway
gate_settrk:
        push hl
        ld hl,CORE_settrk
        ld (gateway_target+1),hl
        pop hl
        jp gateway
gate_setsec:
        push hl
        ld hl,CORE_setsec
        ld (gateway_target+1),hl
        pop hl
        jp gateway
gate_listst:
        push hl
        ld hl,CORE_listst
        ld (gateway_target+1),hl
        pop hl
        jp gateway
gate_sectran:
        push hl
        ld hl,CORE_sectran
        ld (gateway_target+1),hl
        pop hl
        jp gateway
gate_ready:
        push hl
        ld hl,CORE_ready
        ld (gateway_target+1),hl
        pop hl
        jp gateway
gate_not_ready:
        push hl
        ld hl,CORE_not_ready
        ld (gateway_target+1),hl
        pop hl
        jp gateway
gate_devtbl:
        push hl
        ld hl,CORE_devtbl
        ld (gateway_target+1),hl
        pop hl
        jp gateway
gate_drvtbl:
        push hl
        ld hl,CORE_drvtbl
        ld (gateway_target+1),hl
        pop hl
        jp gateway
gate_flush:
        push hl
        ld hl,CORE_flush
        ld (gateway_target+1),hl
        pop hl
        jp gateway
gate_time:
        push hl
        ld hl,CORE_rtc_time
        ld (gateway_target+1),hl
        pop hl
        jp gateway
map_system: defb 8,9,10,11,12,13,14
map_tpa: defb 0,1,2,3,4,5,6
current_bank: defb 0
dma_bank: defb 1
logical_dma: defw 080h
caller_bank: defb 0
caller_sp: defw 0
move_source: defb 0
move_dest: defb 0
move_return: defb 0
move_pending: defb 0
move_byte: defb 0
move_sp: defw 0
        defs 32,0
move_stack_top:
disk_bounce: defs 128,0
        defs 192,0
gate_stack_top:
COMMON_END: equ $
