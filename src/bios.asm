; MZ-2500 CP/M 2.2 BIOS (resident part), org 0E800h.
;
; 58K layout: CCP=D200h, BDOS=DA00h (entry DA06h), BIOS=E800h.
; Runs with interrupts permanently disabled (DI + polling: the FDC INTRQ is
; not wired to the CPU and half the commercial titles ship DI+polling).
; IM 1 is set and 0038h holds JP WBOOT purely as a recovery net.
;
; Bank regime: CPU blocks 0-7 -> physical banks 00h-07h (all RAM). The only
; temporary window is block 2 (4000h-5FFFh), swapped to the text VRAM (38h)
; or PCG (39h) between video_enter_* and video_leave. The window switches
; to the private vwin stack (the caller's stack may live anywhere,
; including 4000h-5FFFh), so those helpers pass the return address through
; DE: they clobber A and DE, and everything pushed between enter and leave
; must be popped before leave.
; B4h/B5h are only ever touched through the paired sequences below (B5h
; auto-increments the selector on every access).
;
; Console: 80x25 text, ADM-3A control subset, hardware ring scroll through
; CRTC registers 01h/02h (start address), font in PCG page 0 (F7h bit0=1).
; Keyboard: matrix scan on E8h/EAh; E8h writes always keep bit5=1 (80-column
; mode lives on the same latch as the strobe).

CCP:            equ 0d200h
BDOS_ENTRY:     equ 0da06h
BIOS_BASE:      equ 0e800h
COLDINIT:       equ 0c400h      ; one-shot overlay (reclaimed as TPA)

NUM_DRIVES:     equ 5           ; A:,B: FD  C:,D: SASI  E: EMM

; I/O ports
PORT_BANK_SEL:  equ 0b4h
PORT_BANK_VAL:  equ 0b5h
PORT_CRTC_ADDR: equ 0f4h
PORT_CRTC_DATA: equ 0f5h
PORT_KEY_STROBE: equ 0e8h
PORT_KEY_DATA:  equ 0eah
PORT_PPI_CTRL:  equ 0e3h
PORT_FDC_CMD:   equ 0d8h
PORT_FDC_TRK:   equ 0d9h
PORT_FDC_SEC:   equ 0dah
PORT_FDC_DATA:  equ 0dbh
PORT_FDC_DRIVE: equ 0dch
PORT_FDC_SIDE:  equ 0ddh
PORT_FDC_DENS:  equ 0deh
PORT_OPN_ADDR:  equ 0c8h
PORT_OPN_DATA:  equ 0c9h

; video window (CPU block 2)
VWIN:           equ 04000h
VWIN_BLOCK:     equ 2
BANK_TVRAM:     equ 038h
BANK_PCG:       equ 039h
BANK_RAM2:      equ 002h

TV_COLS:        equ 80
TV_ROWS:        equ 25
; keyboard-scan passes of drive inactivity before the motor is stopped.
; Measured (emulator DCh trace and the real machine agree): 0C000h ran
; about 16.5 seconds, so ~3000 passes/second -> 06000h is roughly 8s.
FD_IDLE_TICKS:  equ 06000h
TV_ATTR:        equ 0800h       ; attribute plane delta inside bank 38h
ATTR_NORMAL:    equ 007h        ; white on black
ATTR_STANDOUT:  equ 047h        ; white, attribute bit6 = reverse video
ATTR_STANDOUT_BIT: equ 040h     ; the reverse bit alone

        org     BIOS_BASE

; --- BIOS jump table (order fixed by CP/M 2.2) -------------------------
        jp      boot            ; cold boot
wboote: jp      wboot           ; warm boot
        jp      const           ; console status
        jp      conin           ; console input
        jp      conout          ; console output
        jp      list            ; printer output
        jp      punch           ; punch output
        jp      reader          ; reader input
        jp      home            ; head to track 0
        jp      seldsk          ; select drive
        jp      settrk          ; set track
        jp      setsec          ; set sector
        jp      setdma          ; set DMA address
        jp      read            ; read 128-byte record
        jp      write           ; write 128-byte record
        jp      listst          ; printer status
        jp      sectran         ; sector translate

; ======================================================================
; cold / warm boot
; ======================================================================
boot:
        di
        ld      sp,bios_stack_top
        call    init_common_state
        xor     a               ; cold boot: fresh screen state, motor off
        ld      (cur_row),a
        ld      (cur_col),a
        ld      (fd_motor_on),a
        ; initial drive: 0 (A:) on a floppy system; the HDD image builder
        ; patches boot_drive_default to 2 (C:) so a hard-disk boot lands on
        ; the hard disk instead of an empty floppy drive
        ld      a,(boot_drive_default)
        ld      (00004h),a
        ld      hl,0
        ld      (scroll_base),hl
        call    COLDINIT        ; one-shot HW init + banner (overlay)
        call    emm_probe
        call    emm_disk_init
        call    emm_seed        ; warm-boot cache: CCP+BDOS into the EMM
        ld      a,(emm_present)
        or      a
        jr      z,boot_no_emm
        ld      hl,msg_emm_ready
        call    print_string
boot_no_emm:
        call    sasi_probe
        ld      a,(sasi_present)
        or      a
        jr      z,boot_no_sasi
        ld      hl,msg_sasi_ready
        call    print_string
boot_no_sasi:
        jp      boot_common

wboot:
        di
        ld      sp,bios_stack_top
        ; Re-pin CPU blocks 0-7 to main RAM banks 00h-07h. Block 7 (this
        ; code) is what we run from, so remapping it to its own bank is a
        ; no-op; the others may have been remapped by the exiting program.
        ; B5h auto-increments the selector, so eight stores cover 0-7.
        xor     a
        out     (PORT_BANK_SEL),a
        ld      hl,wboot_bankmap
        ld      b,8
wboot_bank_loop:
        ld      a,(hl)
        out     (PORT_BANK_VAL),a
        inc     hl
        djnz    wboot_bank_loop
        call    flush_host      ; pending deblocked write, best effort
        call    init_common_state
        ; Re-assert the display registers the exiting program may have
        ; changed - but keep the screen contents, cursor and ring base
        ; (warm boot does not clear the screen).
        ld      a,000h
        out     (PORT_CRTC_ADDR),a
        ld      a,005h
        out     (PORT_CRTC_DATA),a
        ld      a,007h
        out     (0f6h),a
        ld      a,001h
        out     (0f7h),a
        xor     a
        out     (0cfh),a
        ld      a,020h
        out     (PORT_KEY_STROBE),a
        call    set_crtc_base
        call    reload_system   ; CCP+BDOS from cylinder 1 (EMM comes in M2)
boot_common:
        ; zero page: JP WBOOT / IOBYTE / current disk / JP BDOS / IM1 net
        ld      a,0c3h
        ld      (00000h),a
        ld      hl,wboote
        ld      (00001h),hl
        ld      (00039h),hl
        ld      a,0c3h
        ld      (00038h),a
        ld      a,0c3h
        ld      (00005h),a
        ld      hl,BDOS_ENTRY
        ld      (00006h),hl
        xor     a
        ld      (00003h),a      ; IOBYTE
        im      1
        ld      bc,00080h
        call    setdma
        ld      a,(00004h)      ; current disk/user survives warm boot
        and     00fh
        cp      NUM_DRIVES
        jr      c,boot_disk_ok
        xor     a
        ld      (00004h),a
boot_disk_ok:
        ld      a,(00004h)
        ld      c,a
        jp      CCP

wboot_bankmap:
        defb    000h,001h,002h,003h,004h,005h,006h,007h

; Reload CCP+BDOS (1600h bytes at D200h): from the EMM warm-boot cache
; when it verifies (checksum guards against programs scribbling on the
; EMM), else from the FD system area - both halves on cylinder 1
; (D200h-DFFFh = C1/H1/R3..R16, E000h-E7FFh = C1/H0/R1..R8, one seek).
reload_system:
        call    emm_restore
        ret     nc              ; warm image verified and restored
        call    sasi_reload_system
        jr      c,reload_try_fd
        jp      emm_seed        ; HD copy is good: re-seed the cache
reload_try_fd:
        call    reload_from_fd
        ret     c
        jp      emm_seed        ; FD copy is good: re-seed the cache
reload_from_fd:
        xor     a
        ld      (fd_drive),a
        call    fd_select
        ld      a,1
        call    fd_seek_cyl
        jr      c,reload_error
        ld      a,1
        ld      (fd_side),a
        ld      a,3
        ld      (fd_sec),a
        ld      hl,0d200h
        ld      b,14
reload_loop1:
        push    bc
        call    fd_read_retry
        pop     bc
        jr      c,reload_error
        inc     h               ; +256
        ld      a,(fd_sec)
        inc     a
        ld      (fd_sec),a
        djnz    reload_loop1
        xor     a
        ld      (fd_side),a
        ld      a,1
        ld      (fd_sec),a
        ld      hl,0e000h
        ld      b,8
reload_loop2:
        push    bc
        call    fd_read_retry
        pop     bc
        jr      c,reload_error
        inc     h
        ld      a,(fd_sec)
        inc     a
        ld      (fd_sec),a
        djnz    reload_loop2
        xor     a
        ret
reload_error:
        ld      hl,msg_boot_err
        call    print_string
        call    conin           ; any key: try again
        jr      reload_from_fd

msg_boot_err:
        defb    0dh,0ah,"BOOT ERR - CHECK DISK, HIT KEY",0dh,0ah,0
msg_emm_ready:
        defb    "E: EMM RAM DISK (620K) + FAST WARM BOOT",0dh,0ah,0
msg_sasi_ready:
        defb    "C: D: SASI HARD DISK (8M x 2)",0dh,0ah,0
; patched to 2 by make_hdd_image.py inside the hard-disk boot copy
boot_drive_default:
        defb    0

; BDOS function 13 (disk reset - the CCP calls it on every warm boot)
; hard-selects drive A: in the stock kernel, which spins the floppy up
; before every prompt on a hard-disk system. make_boot_d88.py redirects
; func13's final "jp select" here and fills this stub with
;   ld a,(0004h) / and 0fh / ld (curdsk),a / jp select
; so the reset re-selects the CURRENT drive - byte-identical behaviour
; to stock whenever the current drive IS A:. The addresses live inside
; the BDOS, so the builder assembles these 11 bytes itself.
bdos_reset_hook:
        defs    16

; State shared by cold and warm boot. Everything the BIOS reads must be
; written here or in boot before first use (warm-boot contract: no RAM
; power-on value is ever assumed). Warm boot deliberately preserves
; cur_row/cur_col/scroll_base (screen survives) and fd_motor_on (the
; spindle really is still turning).
init_common_state:
        xor     a
        ld      (esc_state),a
        ld      (csi_saved_row),a
        ld      (csi_saved_col),a
        ld      a,ATTR_NORMAL
        ld      (cur_attr),a
        ld      (cur_attr_sp),a
        ld      a,7
        ld      (sgr_fg),a
        xor     a
        ld      (sgr_bg),a
        ld      (key_ready),a
        ld      (hst_valid),a
        ld      (hst_dirty),a
        ld      (unacnt),a
        ld      (seldsk_cur),a
        xor     a
        ld      (fd_not_ready),a
        ld      (fd_absent_mask),a      ; re-probe drives after ^C (media swap)
        ld      hl,FD_IDLE_TICKS
        ld      (fd_idle),hl
        ld      a,0ffh
        ld      (fd_cyl_cache),a
        ld      (fd_cyl_cache+1),a
        ld      (fd_sel_last),a
        ld      (fd_last_side),a
        ld      hl,prev_matrix
        ld      b,14
init_matrix_loop:
        ld      (hl),0
        inc     hl
        djnz    init_matrix_loop
        ld      hl,00080h
        ld      (dma_addr),hl
        ret

; ======================================================================
; console output - ADM-3A subset with hardware ring scroll
; ======================================================================
; C = character
conout:
        push    af
        push    bc
        push    de
        push    hl
        ld      a,(esc_state)
        or      a
        jr      nz,conout_escape
        ld      a,c
        cp      020h
        jr      c,conout_control
        cp      07fh
        jr      z,conout_done   ; DEL prints nothing
        call    put_char_advance
conout_done:
        pop     hl
        pop     de
        pop     bc
        pop     af
        ret

conout_control:
        cp      00dh
        jr      nz,conout_not_cr
        xor     a
        ld      (cur_col),a
        jr      conout_done
conout_not_cr:
        cp      00ah
        jr      nz,conout_not_lf
        call    line_feed
        jr      conout_done
conout_not_lf:
        cp      008h
        jr      nz,conout_not_bs
        ld      a,(cur_col)
        or      a
        jr      z,conout_done
        dec     a
        ld      (cur_col),a
        jr      conout_done
conout_not_bs:
        cp      00ch
        jr      nz,conout_not_right
        ld      a,(cur_col)
        cp      TV_COLS-1
        jr      nc,conout_done
        inc     a
        ld      (cur_col),a
        jr      conout_done
conout_not_right:
        cp      00bh
        jr      nz,conout_not_up
        ld      a,(cur_row)
        or      a
        jr      z,conout_done
        dec     a
        ld      (cur_row),a
        jr      conout_done
conout_not_up:
        cp      01ah
        jr      nz,conout_not_clear
        call    clear_screen
        jr      conout_done
conout_not_clear:
        cp      01eh
        jr      nz,conout_not_home
        xor     a
        ld      (cur_row),a
        ld      (cur_col),a
        jr      conout_done
conout_not_home:
        cp      01bh
        jr      nz,conout_not_esc
        ld      a,1
        ld      (esc_state),a
        jr      conout_done
conout_not_esc:
        cp      007h
        jr      nz,conout_done
        call    bell
        jr      conout_done

; Escape sequences. Three dialects coexist behind the byte after ESC:
;   ESC = row+20h col+20h   ADM-3A cursor addressing (TeleVideo/Kaypro too)
;   ESC [ ...               ANSI/VT100 CSI subset (H f J K A B C D m s u)
;   ESC T Y ( )             TeleVideo extras: clear-EOL, clear-EOS,
;                           standout on (dim), standout off (bright)
; Anything else after ESC is swallowed (insert/delete line and char
; included - nothing in the target set has needed them yet).
conout_escape:
        ld      hl,esc_state
        ld      a,(hl)
        cp      1
        jr      nz,conout_esc_row
        ld      a,c
        cp      "="
        jr      nz,conout_esc_not_adm
        ld      (hl),2
        jp      conout_done
conout_esc_not_adm:
        cp      "["
        jr      nz,conout_esc_not_csi
        ld      (hl),4
        xor     a
        ld      (csi_p1),a
        ld      (csi_p2),a
        ld      (csi_idx),a
        jp      conout_done
conout_esc_not_csi:
        cp      "T"
        jr      nz,conout_esc_not_ceol
        call    clear_to_eol
        jr      conout_esc_abort
conout_esc_not_ceol:
        cp      "Y"
        jr      nz,conout_esc_not_ceos
        call    clear_to_eos
        jr      conout_esc_abort
conout_esc_not_ceos:
        cp      "("
        jr      nz,conout_esc_not_so
        xor     a
        ld      (sgr_fg),a
        ld      a,7
        ld      (sgr_bg),a
        call    sgr_recompute
        jr      conout_esc_abort
conout_esc_not_so:
        cp      ")"
        jr      nz,conout_esc_abort
        ld      a,7
        ld      (sgr_fg),a
        xor     a
        ld      (sgr_bg),a
        call    sgr_recompute
        jr      conout_esc_abort
conout_esc_row:
        cp      2
        jr      nz,conout_esc_col
        ld      a,c
        sub     020h
        cp      TV_ROWS
        jr      c,conout_esc_row_ok
        ld      a,TV_ROWS-1
conout_esc_row_ok:
        ld      (esc_row),a
        ld      (hl),3
        jp      conout_done
conout_esc_col:
        cp      3
        jp      nz,csi_char
        ld      a,c
        sub     020h
        cp      TV_COLS
        jr      c,conout_esc_col_ok
        ld      a,TV_COLS-1
conout_esc_col_ok:
        ld      (cur_col),a
        ld      a,(esc_row)
        ld      (cur_row),a
conout_esc_abort:
        ld      hl,esc_state
        ld      (hl),0
        jp      conout_done

; ---- ANSI CSI accumulator (esc_state = 4) ----
; Digits build the current parameter, ';' moves to the second one,
; private markers (<=>? etc.) are skipped, 40h-7Eh executes and ends.
csi_char:
        ld      a,c
        cp      "0"
        jr      c,csi_not_digit
        cp      "9"+1
        jr      nc,csi_not_digit
        ld      hl,csi_p1
        ld      a,(csi_idx)
        or      a
        jr      z,csi_digit_have
        inc     hl              ; second and later parameters share p2
csi_digit_have:
        ld      a,(hl)
        add     a,a
        ld      d,a             ; d = p*2
        add     a,a
        add     a,a             ; a = p*8
        add     a,d             ; a = p*10
        ld      d,a
        ld      a,c
        sub     "0"
        add     a,d
        ld      (hl),a
        jp      conout_done
csi_not_digit:
        cp      ";"
        jr      nz,csi_not_semi
        ld      hl,csi_idx
        inc     (hl)
        jp      conout_done
csi_not_semi:
        cp      040h
        jp      c,conout_done   ; private markers: skip, stay in CSI
        ld      hl,esc_state
        ld      (hl),0          ; final byte: sequence ends here
        cp      "H"
        jp      z,csi_cup
        cp      "f"
        jp      z,csi_cup
        cp      "A"
        jp      z,csi_up
        cp      "B"
        jp      z,csi_down
        cp      "C"
        jp      z,csi_right
        cp      "D"
        jp      z,csi_left
        cp      "J"
        jp      z,csi_ed
        cp      "K"
        jp      z,csi_el
        cp      "m"
        jp      z,csi_sgr
        cp      "s"
        jp      z,csi_save
        cp      "u"
        jp      z,csi_restore
        jp      conout_done     ; everything else: ignore

; ESC [ r ; c H - 1-based, missing/0 parameters mean 1
csi_cup:
        ld      a,(csi_p1)
        call    csi_one_based
        cp      TV_ROWS
        jr      c,csi_cup_row_ok
        ld      a,TV_ROWS-1
csi_cup_row_ok:
        ld      (cur_row),a
        ld      a,(csi_p2)
        call    csi_one_based
        cp      TV_COLS
        jr      c,csi_cup_col_ok
        ld      a,TV_COLS-1
csi_cup_col_ok:
        ld      (cur_col),a
        jp      conout_done
csi_one_based:
        or      a
        jr      nz,csi_one_dec
        ret                     ; 0 -> row/col 0
csi_one_dec:
        dec     a
        ret

; ESC [ n A/B/C/D - move n (default 1), clamped at the screen edges
csi_count:
        ld      a,(csi_p1)
        or      a
        ret     nz
        inc     a
        ret
csi_up:
        call    csi_count
        ld      b,a
        ld      a,(cur_row)
        sub     b
        jr      nc,csi_up_ok
        xor     a
csi_up_ok:
        ld      (cur_row),a
        jp      conout_done
csi_down:
        call    csi_count
        ld      b,a
        ld      a,(cur_row)
        add     a,b
        cp      TV_ROWS
        jr      c,csi_down_ok
        ld      a,TV_ROWS-1
csi_down_ok:
        ld      (cur_row),a
        jp      conout_done
csi_right:
        call    csi_count
        ld      b,a
        ld      a,(cur_col)
        add     a,b
        cp      TV_COLS
        jr      c,csi_right_ok
        ld      a,TV_COLS-1
csi_right_ok:
        ld      (cur_col),a
        jp      conout_done
csi_left:
        call    csi_count
        ld      b,a
        ld      a,(cur_col)
        sub     b
        jr      nc,csi_left_ok
        xor     a
csi_left_ok:
        ld      (cur_col),a
        jp      conout_done

; ESC [ J (cursor to end of screen) / ESC [ 2 J (whole screen)
csi_ed:
        ld      a,(csi_p1)
        cp      2
        jr      nz,csi_ed_not_all
        call    clear_screen
        jp      conout_done
csi_ed_not_all:
        or      a
        jp      nz,conout_done  ; 1J (start to cursor) unused: ignore
        call    clear_to_eos
        jp      conout_done

; ESC [ K - cursor to end of line
csi_el:
        ld      a,(csi_p1)
        or      a
        jp      nz,conout_done
        call    clear_to_eol
        jp      conout_done

; ESC [ p1 ; p2 m - SGR. 0 resets, 7 swaps ink/paper, 30-37 set the ink
; and 40-47 the paper (ANSI RGB order mapped to the MZ attribute's GRB).
; The text attribute holds ONE colour: paper=black cells show ink in it,
; anything else renders as reverse video in the paper colour (ink lost -
; the closest the hardware gets to coloured backgrounds).
csi_sgr:
        ld      a,(csi_p1)
        call    sgr_apply
        ld      a,(csi_idx)
        or      a
        jp      z,conout_done   ; single parameter form
        ld      a,(csi_p2)
        call    sgr_apply
        jp      conout_done
sgr_apply:
        or      a
        jr      nz,sgr_not_reset
        ld      a,7
        ld      (sgr_fg),a
        xor     a
        ld      (sgr_bg),a
        jr      sgr_recompute
sgr_not_reset:
        cp      7
        jr      nz,sgr_not_swap
        ld      a,(sgr_fg)
        ld      b,a
        ld      a,(sgr_bg)
        ld      (sgr_fg),a
        ld      a,b
        ld      (sgr_bg),a
        jr      sgr_recompute
sgr_not_swap:
        sub     30
        cp      8
        jr      nc,sgr_not_fg
        call    sgr_map
        ld      (sgr_fg),a
        jr      sgr_recompute
sgr_not_fg:
        sub     10              ; 40-47 -> 0-7
        cp      8
        ret     nc              ; anything else: ignore
        call    sgr_map
        ld      (sgr_bg),a
        ; fall through
; One colour per cell, decided per character class:
; - spaces show the paper colour (reverse block when bg is set) - that is
;   how block-styled UIs (2048's tiles, panels) are painted
; - visible glyphs keep coloured ink; the paper colour wins only when the
;   ink is black or white (text on a coloured panel becomes a colour
;   block, coloured sprites stay visible on coloured/white paper)
sgr_recompute:
        ld      a,(sgr_bg)
        or      a
        jr      nz,sgr_sp_paper
        ld      a,(sgr_fg)
        jr      sgr_sp_store
sgr_sp_paper:
        or      ATTR_STANDOUT_BIT
sgr_sp_store:
        ld      (cur_attr_sp),a
        ld      a,(sgr_bg)
        or      a
        jr      z,sgr_plain
        ld      a,(sgr_fg)
        or      a
        jr      z,sgr_paper
        cp      7
        jr      nz,sgr_plain
sgr_paper:
        ld      a,(sgr_bg)
        or      ATTR_STANDOUT_BIT
        ld      (cur_attr),a
        ret
sgr_plain:
        ld      a,(sgr_fg)
        ld      (cur_attr),a
        ret
; A = ANSI colour 0-7 (R=1,G=2,B=4) -> MZ attribute colour (B=1,R=2,G=4)
sgr_map:
        push    hl
        ld      hl,sgr_map_tab
        add     a,l
        ld      l,a
        ld      a,h
        adc     a,0
        ld      h,a
        ld      a,(hl)
        pop     hl
        ret
sgr_map_tab:
        defb    0,2,4,6,1,3,5,7

csi_save:
        ld      a,(cur_row)
        ld      (csi_saved_row),a
        ld      a,(cur_col)
        ld      (csi_saved_col),a
        jp      conout_done
csi_restore:
        ld      a,(csi_saved_row)
        ld      (cur_row),a
        ld      a,(csi_saved_col)
        ld      (cur_col),a
        jp      conout_done

; blank (20h / ATTR_NORMAL) from the cursor to the end of the line;
; cursor does not move
clear_to_eol:
        call    cursor_cell
        ld      a,(cur_col)
        ld      b,a
        ld      a,TV_COLS
        sub     b
        ld      b,a
        call    video_enter_tvram
clear_eol_loop:
        push    hl
        ld      de,VWIN
        add     hl,de
        ld      (hl),020h
        ld      de,TV_ATTR
        add     hl,de
        ld      (hl),ATTR_NORMAL
        pop     hl
        inc     hl
        ld      a,h
        and     007h
        ld      h,a
        djnz    clear_eol_loop
        call    video_leave     ; stack-switching pair: never tail-call
        ret

; blank from the cursor to the end of the screen; cursor does not move
clear_to_eos:
        call    clear_to_eol
        ld      a,(cur_row)
        ld      (clear_saved_row),a
clear_eos_next:
        ld      a,(cur_row)
        inc     a
        cp      TV_ROWS
        jr      nc,clear_eos_done
        ld      (cur_row),a
        call    clear_row       ; preserves cur_col
        jr      clear_eos_next
clear_eos_done:
        ld      a,(clear_saved_row)
        ld      (cur_row),a
        ret

; write printable char in A at the cursor, advance, wrap
put_char_advance:
        ld      (conout_char),a
        call    cursor_cell
        ld      (conout_cell),hl
        call    video_enter_tvram
        ld      hl,(conout_cell)
        ld      de,VWIN
        add     hl,de
        ld      a,(conout_char)
        ld      (hl),a          ; code plane
        ld      hl,(conout_cell)
        ld      de,VWIN+TV_ATTR
        add     hl,de
        ld      a,(conout_char)
        cp      020h
        ld      a,(cur_attr)
        jr      nz,put_attr_glyph
        ld      a,(cur_attr_sp)
put_attr_glyph:
        ld      (hl),a
        call    video_leave
        ld      a,(cur_col)
        inc     a
        ld      (cur_col),a
        cp      TV_COLS
        ret     c
        xor     a
        ld      (cur_col),a
        ; fall through: wrap advances one line
line_feed:
        ld      a,(cur_row)
        inc     a
        cp      TV_ROWS
        jr      c,line_feed_store
        ; scroll: advance the ring base one row, clear the new bottom row
        ld      hl,(scroll_base)
        ld      de,TV_COLS
        add     hl,de
        ld      a,h
        and     007h
        ld      h,a
        ld      (scroll_base),hl
        call    set_crtc_base
        ld      a,TV_ROWS-1
        ld      (cur_row),a
        jp      clear_row       ; clears row 24, returns
line_feed_store:
        ld      (cur_row),a
        ret

; program CRTC text start address (registers 01h/02h) from scroll_base
set_crtc_base:
        ld      hl,(scroll_base)
        ld      a,001h
        out     (PORT_CRTC_ADDR),a
        ld      a,l
        out     (PORT_CRTC_DATA),a
        ld      a,002h
        out     (PORT_CRTC_ADDR),a
        ld      a,h
        out     (PORT_CRTC_DATA),a
        ret

; HL = ring cell index of (cur_row, cur_col):
; (scroll_base + row*80 + col) & 7FFh
cursor_cell:
        ld      a,(cur_row)
        ld      l,a
        ld      h,0
        add     hl,hl           ; *2
        add     hl,hl           ; *4
        add     hl,hl           ; *8
        add     hl,hl           ; *16
        ld      b,h
        ld      c,l             ; BC = row*16
        add     hl,hl           ; *32
        add     hl,hl           ; *64
        add     hl,bc           ; *80
        ld      a,(cur_col)
        ld      c,a
        ld      b,0
        add     hl,bc
        ld      bc,(scroll_base)
        add     hl,bc
        ld      a,h
        and     007h
        ld      h,a
        ret

; clear the row cur_row (code=20h attr=07h), preserving cur_col
clear_row:
        ld      a,(cur_col)
        ld      (clear_saved_col),a
        xor     a
        ld      (cur_col),a
        call    cursor_cell
        call    video_enter_tvram
        ld      b,TV_COLS
clear_row_loop:
        push    hl
        ld      de,VWIN
        add     hl,de
        ld      (hl),020h
        ld      de,TV_ATTR
        add     hl,de
        ld      (hl),ATTR_NORMAL
        pop     hl
        inc     hl
        ld      a,h
        and     007h
        ld      h,a
        djnz    clear_row_loop
        call    video_leave
        ld      a,(clear_saved_col)
        ld      (cur_col),a
        ret

; clear the whole text screen (all 2048 ring cells), keep the ring base
clear_screen:
        call    video_enter_tvram
        ld      hl,VWIN
        ld      bc,00800h
clear_screen_loop:
        ld      (hl),020h
        push    hl
        ld      de,TV_ATTR
        add     hl,de
        ld      (hl),ATTR_NORMAL
        ld      de,TV_ATTR
        add     hl,de
        ld      (hl),0          ; text2 plane
        pop     hl
        inc     hl
        dec     bc
        ld      a,b
        or      c
        jr      nz,clear_screen_loop
        call    video_leave
        xor     a
        ld      (cur_row),a
        ld      (cur_col),a
        ret

; ~30ms beep through 8255 port C bit 2 (set/reset via the control port)
bell:
        ld      a,005h          ; set PC2
        out     (PORT_PPI_CTRL),a
        ld      bc,08000h
bell_wait:
        dec     bc
        ld      a,b
        or      c
        jr      nz,bell_wait
        ld      a,004h          ; reset PC2
        out     (PORT_PPI_CTRL),a
        ret

; print zero-terminated string at HL through conout
print_string:
        ld      a,(hl)
        or      a
        ret     z
        ld      c,a
        push    hl
        call    conout
        pop     hl
        inc     hl
        jr      print_string

; --- video window helpers ---------------------------------------------
; See the header comment: these switch to the private vwin stack, so the
; return address travels through DE. They clobber A and DE. Everything
; pushed between enter and leave must be popped before leave.
video_enter_tvram:
        pop     de              ; return address (still the caller's stack)
        ld      (vwin_saved_sp),sp
        ld      sp,vwin_stack_top
        ld      a,VWIN_BLOCK
        out     (PORT_BANK_SEL),a
        ld      a,BANK_TVRAM
        out     (PORT_BANK_VAL),a
        push    de
        ret

video_enter_pcg:
        pop     de
        ld      (vwin_saved_sp),sp
        ld      sp,vwin_stack_top
        ld      a,VWIN_BLOCK
        out     (PORT_BANK_SEL),a
        ld      a,BANK_PCG
        out     (PORT_BANK_VAL),a
        push    de
        ret

video_leave:
        pop     de              ; return address (vwin stack)
        ld      a,VWIN_BLOCK
        out     (PORT_BANK_SEL),a
        ld      a,BANK_RAM2
        out     (PORT_BANK_VAL),a
        ld      sp,(vwin_saved_sp)
        push    de
        ret

; ======================================================================
; console input - matrix scan, make-edge decode
; ======================================================================
const:
        push    bc
        push    de
        push    hl
        call    scan_keyboard
        pop     hl
        pop     de
        pop     bc
        ld      a,(key_ready)
        or      a
        ret     z
        ld      a,0ffh
        ret

conin:
        push    bc
        push    de
        push    hl
        call    cursor_show
conin_wait:
        call    scan_keyboard
        ld      a,(key_ready)
        or      a
        jr      z,conin_wait
        xor     a
        ld      (key_ready),a
        call    cursor_hide
        pop     hl
        pop     de
        pop     bc
        ld      a,(key_char)
        ret

; reverse-video the cursor cell / restore it
cursor_show:
        call    cursor_cell
        ld      (conout_cell),hl
        call    video_enter_tvram
        ld      hl,(conout_cell)
        ld      de,VWIN+TV_ATTR
        add     hl,de
        ld      a,(hl)
        ld      (cursor_saved_attr),a
        or      040h
        ld      (hl),a
        call    video_leave
        ret

cursor_hide:
        call    cursor_cell
        ld      (conout_cell),hl
        call    video_enter_tvram
        ld      hl,(conout_cell)
        ld      de,VWIN+TV_ATTR
        add     hl,de
        ld      a,(cursor_saved_attr)
        ld      (hl),a
        call    video_leave
        ret

; One full matrix pass. Newly-pressed keys are decoded through
; keymap_table; the first hit lands in key_char/key_ready.
; E8h writes always carry bit5 (80-column) and bit4 (strobe enable).
scan_keyboard:
        ; motor idle timer: the scan runs continuously while CP/M waits at
        ; the console, so counting passes here stops the drive (and its
        ; lamp) after ~8 idle seconds; the next disk access spins it up.
        ld      a,(fd_motor_on)
        or      a
        jr      z,scan_motor_done
        ld      hl,(fd_idle)
        dec     hl
        ld      (fd_idle),hl
        ld      a,h
        or      l
        jr      nz,scan_motor_done
        ld      a,080h          ; select off: motor and lamp stop
        out     (PORT_FDC_DRIVE),a
        xor     a
        ld      (fd_motor_on),a
        ld      a,0ffh
        ld      (fd_sel_last),a ; re-sync the track register on reselect
scan_motor_done:
        ld      hl,prev_matrix
        ld      b,0             ; row
scan_row:
        ld      a,b
        or      030h            ; bit5=80col, bit4=strobe
        out     (PORT_KEY_STROBE),a
        in      a,(PORT_KEY_DATA)
        cpl                     ; active-low -> pressed bits
        ld      d,a             ; D = pressed now
        ld      a,(hl)
        cpl
        and     d               ; new presses this pass
        ld      e,a
        ld      (hl),d          ; remember state
        ld      a,e
        or      a
        call    nz,decode_new_keys
        inc     hl
        inc     b
        ld      a,b
        cp      14
        jr      c,scan_row
        ; leave the latch with bit5 still up (any-key sense mode)
        ld      a,020h
        out     (PORT_KEY_STROBE),a
        ret

; B = row, E = new-press bits
decode_new_keys:
        push    hl
        push    bc
        ld      c,0             ; bit index
decode_bit_loop:
        srl     e
        jr      c,decode_hit
        inc     c
        ld      a,c
        cp      8
        jr      c,decode_bit_loop
        pop     bc
        pop     hl
        ret
decode_hit:
        ; index = (row*8 + bit)*2 (+1 when SHIFT held)
        ld      a,b
        add     a,a
        add     a,a
        add     a,a
        add     a,c
        ld      l,a
        ld      h,0
        add     hl,hl
        ld      bc,keymap_table
        add     hl,bc
        ; Sample the modifier row RIGHT NOW: the scan visits row 11 after
        ; the letter rows, so prev_matrix would lag one pass behind when
        ; SHIFT goes down together with the key (the emulator's --type
        ; does exactly that).
        ld      a,KEY_MOD_ROW
        or      030h
        out     (PORT_KEY_STROBE),a
        in      a,(PORT_KEY_DATA)
        cpl
        ld      e,a             ; E = live modifier bits
        and     KEY_MOD_SHIFT_MASK
        jr      z,decode_no_shift
        inc     hl
decode_no_shift:
        ld      a,(hl)
        or      a
        jr      z,decode_none
        ld      d,a
        ld      a,e
        and     KEY_MOD_CTRL_MASK
        ld      a,d
        jr      z,decode_store
        cp      040h            ; CTRL folds 40h-7Fh onto 00h-1Fh
        jr      c,decode_store
        and     01fh
decode_store:
        ld      (key_char),a
        ld      a,0ffh
        ld      (key_ready),a
decode_none:
        pop     bc
        pop     hl
        ret

; ======================================================================
; printer / punch / reader stubs
; ======================================================================
list:
        ret
listst:
        ld      a,0ffh
        ret
punch:
        ret
reader:
        ld      a,01ah          ; EOF
        ret

; ======================================================================
; disk interface - deblocked 128B records over 256B devices
; ======================================================================
home:
        ld      bc,0
        ; fall through
settrk:
        ld      (trk),bc
        ret
setsec:
        ld      (sec),bc
        ret
setdma:
        ld      (dma_addr),bc
        ret
sectran:
        ld      l,c             ; identity (no skew yet)
        ld      h,b
        ret

seldsk:
        ld      hl,0
        ld      a,c
        cp      NUM_DRIVES
        ret     nc
        ld      (seldsk_cur),a
        cp      4
        jr      z,seldsk_emm
        cp      2
        jr      nc,seldsk_sasi
        ld      l,a
        ld      h,0
        add     hl,hl           ; *2
        ld      de,dph_table
        add     hl,de
        ld      e,(hl)
        inc     hl
        ld      d,(hl)
        ex      de,hl
        ret
seldsk_emm:
        ld      a,(emm_present)
        or      a
        ret     z               ; HL=0: no board, no drive
        ld      hl,dph_e
        ret
seldsk_sasi:
        ld      a,(sasi_present)
        or      a
        ret     z
        ld      a,(seldsk_cur)
        cp      3
        ld      hl,dph_c
        ret     nz
        ld      hl,dph_d
        ret

; --- deblocking (DRI skeleton, one shared 256B host buffer) ------------
; BDOS passes the write type in C (CP/M 2.2 System Interface):
; 0 = deferrable write to an allocated block, 1 = directory (flush now),
; 2 = first write into a freshly allocated block (no preread needed).
WRALL:  equ 0                   ; write to allocated
WRDIR:  equ 1                   ; write to directory
WRUAL:  equ 2                   ; write to unallocated

read:
        xor     a
        ld      (unacnt),a
        ld      a,1
        ld      (rsflag),a
        ld      (readop),a
        ld      a,WRUAL
        ld      (wrtype),a
        jr      rwoper

write:
        xor     a
        ld      (readop),a
        ld      a,c
        ld      (wrtype),a
        cp      WRUAL
        jr      nz,write_check_una
        ; first write into a freshly allocated block: the rest of that
        ; block needs no preread
        ld      a,(seldsk_cur)
        ld      (unadsk),a
        ld      hl,(trk)
        ld      (unatrk),hl
        ld      hl,(sec)
        ld      (unasec),hl
        ; records per block: SASI (C:/D:) uses 4KB blocks, the rest 2KB
        ld      a,(seldsk_cur)
        cp      2
        jr      c,write_una_2k
        cp      4
        jr      nc,write_una_2k
        ld      a,32
        jr      write_una_store
write_una_2k:
        ld      a,16
write_una_store:
        ld      (unacnt),a
write_check_una:
        ld      a,(unacnt)
        or      a
        jr      z,write_alloc
        dec     a
        ld      (unacnt),a
        ; still inside the unallocated run?
        ld      a,(seldsk_cur)
        ld      hl,unadsk
        cp      (hl)
        jr      nz,write_not_una
        ld      hl,(unatrk)
        ld      de,(trk)
        ld      a,l
        cp      e
        jr      nz,write_not_una
        ld      a,h
        cp      d
        jr      nz,write_not_una
        ld      hl,(unasec)
        ld      de,(sec)
        ld      a,l
        cp      e
        jr      nz,write_not_una
        ; match: skip the preread, advance the run
        inc     hl
        ld      (unasec),hl
        xor     a
        ld      (rsflag),a
        jr      rwoper
write_not_una:
        xor     a
        ld      (unacnt),a
write_alloc:
        ld      a,1
        ld      (rsflag),a
        ; fall through
rwoper:
        ; target host sector: (seldsk_cur, trk, sec>>1)
        ld      a,(sec)
        srl     a
        ld      (req_psec),a
        ld      a,(hst_valid)
        or      a
        jr      z,rw_need_fill
        ld      a,(hst_drive)
        ld      hl,seldsk_cur
        cp      (hl)
        jr      nz,rw_flush_fill
        ld      hl,(hst_trk)
        ld      de,(trk)
        ld      a,l
        cp      e
        jr      nz,rw_flush_fill
        ld      a,h
        cp      d
        jr      nz,rw_flush_fill
        ld      a,(hst_psec)
        ld      hl,req_psec
        cp      (hl)
        jr      z,rw_buffer_ok
rw_flush_fill:
        call    flush_host      ; write back a dirty buffer first
        jr      c,rw_error
rw_need_fill:
        ld      a,(seldsk_cur)
        ld      (hst_drive),a
        ld      hl,(trk)
        ld      (hst_trk),hl
        ld      a,(req_psec)
        ld      (hst_psec),a
        ld      a,(rsflag)
        or      a
        jr      z,rw_no_preread
        call    host_read
        jr      c,rw_error
        jr      rw_mark_valid
rw_no_preread:
        ; fresh block: the half we do not copy must not leak old data
        ld      hl,hstbuf
        ld      b,0
rw_zero_loop:
        ld      (hl),0e5h
        inc     hl
        djnz    rw_zero_loop
rw_mark_valid:
        ld      a,1
        ld      (hst_valid),a
rw_buffer_ok:
        ; copy 128 bytes between hstbuf half and the DMA buffer
        ld      a,(sec)
        and     001h
        rrca                    ; bit0 -> bit7: offset 0 or 80h
        ld      l,a
        ld      h,0
        ld      de,hstbuf
        add     hl,de
        ld      de,(dma_addr)
        ld      a,(readop)
        or      a
        jr      nz,rw_do_copy   ; read: hstbuf -> DMA
        ex      de,hl           ; write: DMA -> hstbuf
        ld      a,1
        ld      (hst_dirty),a
rw_do_copy:
        ld      bc,128
        ldir
        ; directory writes flush immediately
        ld      a,(readop)
        or      a
        jr      nz,rw_ok
        ld      a,(wrtype)
        cp      WRDIR
        jr      nz,rw_ok
        call    flush_host
        jr      c,rw_error
rw_ok:
        xor     a
        ret
rw_error:
        ld      a,1
        ret

; write the host buffer back if dirty; carry set on error
flush_host:
        ld      a,(hst_dirty)
        or      a
        ret     z
        call    host_write
        ret     c
        xor     a
        ld      (hst_dirty),a
        ret

; --- host sector I/O dispatch (0/1 = FD, 2/3 = SASI, 4 = EMM) ----------
host_read:
        ld      a,(hst_drive)
        cp      4
        jp      z,emm_host_read
        cp      2
        jp      nc,sasi_host_read
        ; a drive confirmed empty stays synthesized-empty until the next
        ; warm boot (^C after a media change re-probes it)
        call    fd_absent_bit
        ld      c,a
        ld      a,(fd_absent_mask)
        and     c
        jr      nz,fd_read_synth
        xor     a
        ld      (fd_absent_retry),a
host_read_attempt:
        xor     a
        ld      (fd_not_ready),a
        call    fd_setup_from_host
        jr      c,fd_read_absent
        ld      hl,hstbuf
        call    fd_read_retry
        jr      c,fd_read_absent
        ; genuine data came back: the drive is definitely populated
        call    fd_absent_bit
        cpl
        ld      c,a
        ld      a,(fd_absent_mask)
        and     c
        ld      (fd_absent_mask),a
        xor     a
        ret
fd_read_absent:
        ; Distinguish "no medium" from a transient READY drop (spin-up,
        ; head load): only after a fresh spin-up retry still reports
        ; not-ready do we treat the drive as empty. BDOS function 13 logs
        ; drive A: in even on a floppy-less hard-disk boot, so an empty
        ; drive answers with a synthesized empty directory, not an error.
        ld      a,(fd_not_ready)
        or      a
        scf
        ret     z               ; a real read failure stays an error
        ld      a,(fd_absent_retry)
        or      a
        jr      nz,fd_read_confirmed_absent
        ld      a,1
        ld      (fd_absent_retry),a
        xor     a               ; force a full reselect + spin-up wait
        ld      (fd_motor_on),a
        ld      a,0ffh
        ld      (fd_sel_last),a
        jr      host_read_attempt
fd_read_confirmed_absent:
        call    fd_absent_bit
        ld      c,a
        ld      a,(fd_absent_mask)
        or      c
        ld      (fd_absent_mask),a
fd_read_synth:
        ld      hl,hstbuf
        ld      b,0
fd_absent_fill:
        ld      (hl),0e5h
        inc     hl
        inc     b
        jr      nz,fd_absent_fill
        xor     a
        ret

; A = latch bit for the current FD host drive (01h = drive 0, 02h = drive 1)
fd_absent_bit:
        ld      a,(hst_drive)
        and     001h
        inc     a
        ret
host_write:
        ld      a,(hst_drive)
        cp      4
        jp      z,emm_host_write
        cp      2
        jp      nc,sasi_host_write
        call    fd_absent_bit
        ld      c,a
        ld      a,(fd_absent_mask)
        and     c
        jr      z,host_write_present
        ld      a,1             ; writing to a confirmed-empty drive fails
        scf
        ret
host_write_present:
        call    fd_setup_from_host
        ret     c
        ld      hl,hstbuf
        jp      fd_write_retry

; from hst_drive/hst_trk/hst_psec: select drive, seek, set fd_side/fd_sec
fd_setup_from_host:
        ld      a,(hst_drive)
        ld      (fd_drive),a
        call    fd_select
        ld      a,(hst_trk)     ; logical track 0-159 (low byte is enough)
        srl     a               ; cylinder
        call    fd_seek_cyl
        ret     c
        ld      a,(hst_trk)
        and     001h
        ld      (fd_side),a
        ld      a,(hst_psec)
        inc     a               ; sectors are 1-based
        ld      (fd_sec),a
        xor     a
        ret

; ======================================================================
; FD physical driver (MB8876). Command/status/track/sector registers are
; inverted on the bus (cpl both ways); the data register is NOT (the disk
; image is stored inverted, the two cancel).
; ======================================================================

; ======================================================================
; SASI (MZ-1E30) - hard-disk drives C:/D: on fixed 8MB partitions
;
; Ports: A4h data (access auto-ACKs), A5h write bit5=SEL / bit3=RST,
; A5h read = REQ|ACK|BSY|MSG|C/D|I/O (bits 7..2). Xebec S1410 class 0:
; READ(6)=08h / WRITE(6)=0Ah, CDB = {op, LBA[20:16], LBA[15:8], LBA[7:0],
; nblocks, 0}, 256-byte blocks. Every wait is bounded; recovery is one
; RST pulse and a single retry.
; ======================================================================
PORT_SASI_DATA: equ 0a4h
PORT_SASI_CTRL: equ 0a5h

; Bus phases, as (status AND FCh) values - the sequence both the shipped
; option ROM and both emulators agree on: during SEL only BSY is awaited
; (REQ and C/D appear after SEL drops), and every transfer step waits for
; its exact phase pattern.
SASI_PH_FREE:   equ 000h
SASI_PH_CMD:    equ 0a8h        ; BSY|REQ|C/D
SASI_PH_DOUT:   equ 0a0h        ; BSY|REQ
SASI_PH_DIN:    equ 0a4h        ; BSY|REQ|I/O
SASI_PH_STAT:   equ 0ach        ; BSY|REQ|C/D|I/O
SASI_PH_MSG:    equ 0bch        ; BSY|REQ|MSG|C/D|I/O

; wait until (status & FCh) == D; A = full status, carry on timeout
sasi_wait_phase:
        push    de
        ld      e,8             ; 8 x 64Ki polls
        push    bc
        ld      bc,0
sasi_wp_loop:
        in      a,(PORT_SASI_CTRL)
        and     0fch
        cp      d
        jr      z,sasi_wp_ok
        dec     bc
        ld      a,b
        or      c
        jr      nz,sasi_wp_loop
        dec     e
        jr      nz,sasi_wp_loop
        pop     bc
        pop     de
        scf
        ret
sasi_wp_ok:
        pop     bc
        pop     de
        or      a
        ret

; pulse RST (bounded recovery between retries)
sasi_reset:
        ld      a,008h
        out     (PORT_SASI_CTRL),a
        xor     a
        out     (PORT_SASI_CTRL),a
        ld      b,010h
sasi_reset_wait:
        djnz    sasi_reset_wait
        ret

; select target ID 0; carry on failure
sasi_select:
        ld      d,SASI_PH_FREE
        call    sasi_wait_phase
        ret     c
        ld      a,001h          ; ID 0 bit on the data bus
        out     (PORT_SASI_DATA),a
        ld      a,020h          ; SEL up
        out     (PORT_SASI_CTRL),a
        ; only BSY answers while SEL is up
        push    de
        ld      de,04000h
sasi_sel_wait:
        in      a,(PORT_SASI_CTRL)
        bit     5,a
        jr      nz,sasi_sel_ok
        dec     de
        ld      a,d
        or      e
        jr      nz,sasi_sel_wait
        pop     de
        xor     a
        out     (PORT_SASI_CTRL),a
        scf
        ret
sasi_sel_ok:
        pop     de
        xor     a               ; SEL down: target proceeds to command phase
        out     (PORT_SASI_CTRL),a
        ret

; send the 6-byte CDB at sasi_cdb; carry on phase error
sasi_send_cdb:
        ld      hl,sasi_cdb
        ld      b,6
sasi_cdb_loop:
        push    bc
        ld      d,SASI_PH_CMD
        call    sasi_wait_phase
        pop     bc
        ret     c
        ld      a,(hl)
        out     (PORT_SASI_DATA),a
        inc     hl
        djnz    sasi_cdb_loop
        or      a
        ret

; transfer one 256-byte block to/from (sasi_dst); direction per the phase
sasi_data_in:
        ld      hl,(sasi_dst)
        ld      b,0
sasi_di_loop:
        push    bc
        ld      d,SASI_PH_DIN
        call    sasi_wait_phase
        pop     bc
        ret     c
        in      a,(PORT_SASI_DATA)
        ld      (hl),a
        inc     hl
        inc     b
        jr      nz,sasi_di_loop
        or      a
        ret

sasi_data_out:
        ld      hl,(sasi_dst)
        ld      b,0
sasi_do_loop:
        push    bc
        ld      d,SASI_PH_DOUT
        call    sasi_wait_phase
        pop     bc
        ret     c
        ld      a,(hl)
        out     (PORT_SASI_DATA),a
        inc     hl
        inc     b
        jr      nz,sasi_do_loop
        or      a
        ret

; status + message-in; carry when the target reports an error
sasi_finish:
        ld      d,SASI_PH_STAT
        call    sasi_wait_phase
        ret     c
        in      a,(PORT_SASI_DATA)
        ld      (sasi_status),a
        ld      d,SASI_PH_MSG
        call    sasi_wait_phase
        ret     c
        in      a,(PORT_SASI_DATA) ; message (00h), completes the command
        ld      a,(sasi_status)
        or      a
        ret     z
        scf
        ret

; build the CDB for hst_trk/hst_psec on the selected partition.
; LBA(21bit) = partition base + trk*32 + psec
sasi_build_cdb:
        ld      hl,(hst_trk)
        xor     a               ; A:HL = trk << 5
        add     hl,hl
        rla
        add     hl,hl
        rla
        add     hl,hl
        rla
        add     hl,hl
        rla
        add     hl,hl
        rla
        ld      c,a             ; C = LBA[20:16] so far
        ld      a,(hst_psec)
        ld      e,a
        ld      d,0
        add     hl,de
        jr      nc,sasi_cdb_no_carry1
        inc     c
sasi_cdb_no_carry1:
        ld      a,(seldsk_cur)
        cp      3
        jr      z,sasi_cdb_drive_d
        ld      de,SASI_BASE_C_LOW
        ld      a,SASI_BASE_C_HIGH
        jr      sasi_cdb_add_base
sasi_cdb_drive_d:
        ld      de,SASI_BASE_D_LOW
        ld      a,SASI_BASE_D_HIGH
sasi_cdb_add_base:
        add     hl,de
        jr      nc,sasi_cdb_no_carry2
        inc     c
sasi_cdb_no_carry2:
        add     a,c
        and     01fh            ; LUN 0
        ld      (sasi_cdb+1),a
        ld      a,h
        ld      (sasi_cdb+2),a
        ld      a,l
        ld      (sasi_cdb+3),a
        ld      a,1
        ld      (sasi_cdb+4),a
        xor     a
        ld      (sasi_cdb+5),a
        ret

; one command attempt: opcode in A. carry on any failure.
sasi_command:
        ld      (sasi_cdb),a
        call    sasi_select
        ret     c
        call    sasi_send_cdb
        ret     c
        ld      a,(sasi_cdb)
        cp      00ah            ; WRITE(6)?
        jr      z,sasi_cmd_write
        cp      008h            ; READ(6)?
        jr      z,sasi_cmd_read
        jp      sasi_finish     ; TEST UNIT READY etc.: no data phase
sasi_cmd_read:
        call    sasi_data_in
        ret     c
        jp      sasi_finish
sasi_cmd_write:
        call    sasi_data_out
        ret     c
        jp      sasi_finish

; hst_* -> one 256B block via hstbuf, retry once after an RST
sasi_host_io:
        ld      (sasi_op),a
        ld      hl,hstbuf
        ld      (sasi_dst),hl
        call    sasi_build_cdb
        ld      a,(sasi_op)
        call    sasi_command
        ret     nc
        call    sasi_reset
        call    sasi_build_cdb
        ld      a,(sasi_op)
        call    sasi_command
        ret     nc
        ld      a,1             ; deblocker error convention
        scf
        ret

sasi_host_read:
        ld      a,008h
        jr      sasi_host_io
sasi_host_write:
        ld      a,00ah
        jr      sasi_host_io

; read one 256B block from the HD1 partition: DE = partition record,
; HL = destination. HL/DE preserved; carry on error.
sasi_read_hd1:
        push    hl
        push    de
        ld      (sasi_dst),hl
        ld      hl,SASI_BASE_C_LOW
        add     hl,de
        ld      a,SASI_BASE_C_HIGH
        adc     a,0
        and     01fh
        ld      (sasi_cdb+1),a
        ld      a,h
        ld      (sasi_cdb+2),a
        ld      a,l
        ld      (sasi_cdb+3),a
        ld      a,1
        ld      (sasi_cdb+4),a
        xor     a
        ld      (sasi_cdb+5),a
        ld      a,008h
        call    sasi_command
        pop     de
        pop     hl
        ret

; warm-boot reload from the hard-disk system area. The partition's boot
; record (partition record 0, "IPLPRO") authenticates the copy; then
; CCP+BDOS come from records 34..47 (-> D200h) and 48..55 (-> E000h),
; mirroring the bank layout the device boot loaded.
sasi_reload_system:
        ld      a,(sasi_present)
        or      a
        jr      z,sasi_rl_fail
        ld      de,0
        ld      hl,hstbuf
        call    sasi_read_hd1
        jr      c,sasi_rl_fail
        xor     a
        ld      (hst_valid),a
        ld      hl,hstbuf+1
        ld      de,sasi_iplpro_sig
        ld      b,6
sasi_rl_sig:
        ld      a,(de)
        cp      (hl)
        jr      nz,sasi_rl_fail
        inc     hl
        inc     de
        djnz    sasi_rl_sig
        ld      de,34
        ld      hl,0d200h
        ld      b,14
sasi_rl_loop1:
        push    bc
        call    sasi_read_hd1
        pop     bc
        jr      c,sasi_rl_fail
        inc     h
        inc     de
        djnz    sasi_rl_loop1
        ld      de,48
        ld      hl,0e000h
        ld      b,8
sasi_rl_loop2:
        push    bc
        call    sasi_read_hd1
        pop     bc
        jr      c,sasi_rl_fail
        inc     h
        inc     de
        djnz    sasi_rl_loop2
        xor     a
        ret
sasi_rl_fail:
        scf
        ret

sasi_iplpro_sig:
        defb    "IPLPRO"

; cold-boot probe: TEST UNIT READY on ID 0 must select and return 00h
sasi_probe:
        xor     a
        ld      (sasi_present),a
        ld      hl,sasi_cdb
        ld      b,6
sasi_probe_zero:
        ld      (hl),0
        inc     hl
        djnz    sasi_probe_zero
        xor     a               ; TEST UNIT READY
        call    sasi_command
        ret     c
        ld      a,1
        ld      (sasi_present),a
        ret

; ======================================================================
; EMM (MZ-1R37 640KB) - warm-boot cache + RAM disk E:
;
; ACh write latches address[19:16] from bus A15-A8 (register B of an
; OUT (C),A) and address[15:8] from the data byte; ADh then reads/writes
; with address[7:0] on A15-A8. No auto-increment, and B IS the low
; address byte, so INI/OUTI/INIR/OTIR (which decrement B) are forbidden -
; every transfer is an explicit in a,(c)/out (c),a loop.
;
; Layout: 0x00000 header block ("CPM22WB1" + len + checksum16),
; 0x00100-0x016FF CCP+BDOS warm image, 0x03F00 RAM-disk label block
; ("EMMDISK1"), 0x04000+ drive E: data (BDOS track 2 onward, OFF=2).
; EMM contents survive RESET (no reset line), so the label decides
; between "format" (power-on zeroes) and "preserve files".
; ======================================================================
EMM_ADDR_PORT:  equ 0ach
EMM_DATA_PORT:  equ 0adh
EMM_WARM_PAGE:  equ 001h        ; addr[15:8] of the warm image (hi=0)
EMM_WARM_PAGES: equ 016h        ; 1600h bytes
EMM_LABEL_PAGE: equ 03fh

; latch addr[19:16]=D, addr[15:8]=E
emm_latch:
        push    bc
        ld      b,d
        ld      c,EMM_ADDR_PORT
        ld      a,e
        out     (c),a
        pop     bc
        ret

; copy one 256-byte page EMM(D:E:00) -> HL, adding bytes into BC checksum
emm_read_page:
        call    emm_latch
        push    de
        ld      d,b
        ld      e,c             ; DE = running checksum
        ld      bc,EMM_DATA_PORT
emm_read_page_loop:
        in      a,(c)
        ld      (hl),a
        inc     hl
        ; checksum += byte
        push    hl
        ld      l,a
        ld      h,0
        add     hl,de
        ex      de,hl
        pop     hl
        inc     b
        jr      nz,emm_read_page_loop
        ld      b,d
        ld      c,e
        pop     de
        ret

; copy one 256-byte page HL -> EMM(D:E:00), adding bytes into BC checksum
emm_write_page:
        call    emm_latch
        push    de
        ld      d,b
        ld      e,c
        ld      bc,EMM_DATA_PORT
emm_write_page_loop:
        ld      a,(hl)
        out     (c),a
        inc     hl
        push    hl
        ld      l,a
        ld      h,0
        add     hl,de
        ex      de,hl
        pop     hl
        inc     b
        jr      nz,emm_write_page_loop
        ld      b,d
        ld      c,e
        pop     de
        ret

; probe for the board using the header block's reserved bytes (ours, so
; no RAM-disk data is at risk). Absent EMM reads FFh and ignores writes.
emm_probe:
        xor     a
        ld      (emm_present),a
        ld      d,0
        ld      e,0
        call    emm_latch
        ld      bc,EMM_DATA_PORT
        ld      b,00ch          ; header+12 (reserved)
        ld      a,0abh
        out     (c),a
        ld      b,00dh
        ld      a,05ah
        out     (c),a
        ld      b,00ch
        in      a,(c)
        cp      0abh
        ret     nz
        ld      b,00dh
        in      a,(c)
        cp      05ah
        ret     nz
        ld      a,1
        ld      (emm_present),a
        ret

; cold/warm seed: copy D200h-E7FFh into the warm area and stamp the header
emm_seed:
        ld      a,(emm_present)
        or      a
        ret     z
        ld      hl,0d200h
        ld      d,0
        ld      e,EMM_WARM_PAGE
        ld      bc,0
emm_seed_loop:
        push    de
        call    emm_write_page
        pop     de
        inc     e
        ld      a,e
        cp      EMM_WARM_PAGE+EMM_WARM_PAGES
        jr      c,emm_seed_loop
        ; header block via hstbuf (invalidated below)
        push    bc
        ld      hl,hstbuf
        ld      de,emm_signature
        ex      de,hl
        ld      bc,8
        ld      de,hstbuf
        ldir
        pop     bc
        ld      hl,hstbuf+8
        ld      (hl),EMM_WARM_PAGES     ; length in pages
        inc     hl
        ld      (hl),0
        inc     hl
        ld      (hl),c                  ; checksum16
        inc     hl
        ld      (hl),b
        ld      hl,hstbuf
        ld      d,0
        ld      e,0
        ld      bc,0
        call    emm_write_page
        xor     a
        ld      (hst_valid),a
        ld      (hst_dirty),a
        ret

; warm-boot restore: header valid + checksum match -> copy back, CF clear.
emm_restore:
        ld      a,(emm_present)
        or      a
        jr      z,emm_restore_fail
        ld      hl,hstbuf
        ld      d,0
        ld      e,0
        ld      bc,0
        call    emm_read_page
        xor     a
        ld      (hst_valid),a
        ld      hl,hstbuf
        ld      de,emm_signature
        ld      b,8
emm_restore_sig:
        ld      a,(de)
        cp      (hl)
        jr      nz,emm_restore_fail
        inc     hl
        inc     de
        djnz    emm_restore_sig
        ld      a,(hstbuf+8)
        cp      EMM_WARM_PAGES
        jr      nz,emm_restore_fail
        ld      hl,0d200h
        ld      d,0
        ld      e,EMM_WARM_PAGE
        ld      bc,0
emm_restore_loop:
        push    de
        call    emm_read_page
        pop     de
        inc     e
        ld      a,e
        cp      EMM_WARM_PAGE+EMM_WARM_PAGES
        jr      c,emm_restore_loop
        ld      a,(hstbuf+10)
        cp      c
        jr      nz,emm_restore_fail
        ld      a,(hstbuf+11)
        cp      b
        jr      nz,emm_restore_fail
        xor     a
        ret
emm_restore_fail:
        scf
        ret

emm_signature:
        defb    "CPM22WB1"
emm_label:
        defb    "EMMDISK1"

; RAM disk bring-up: label present -> keep files; absent (power-on zero
; fill) -> E5-fill the directory (16 pages at 0x04000) and write the label.
emm_disk_init:
        ld      a,(emm_present)
        or      a
        ret     z
        ld      hl,hstbuf
        ld      d,0
        ld      e,EMM_LABEL_PAGE
        ld      bc,0
        call    emm_read_page
        xor     a
        ld      (hst_valid),a
        ld      hl,hstbuf
        ld      de,emm_label
        ld      b,8
emm_disk_check:
        ld      a,(de)
        cp      (hl)
        jr      nz,emm_disk_format
        inc     hl
        inc     de
        djnz    emm_disk_check
        ret                     ; label intact: files survive the reset
emm_disk_format:
        ld      hl,hstbuf
        ld      b,0
emm_disk_fill:
        ld      (hl),0e5h
        inc     hl
        inc     b
        jr      nz,emm_disk_fill
        ld      e,040h          ; directory pages 40h-4Fh (0x04000, 4KB)
emm_disk_dir_loop:
        ld      hl,hstbuf
        ld      d,0
        ld      bc,0
        push    de
        call    emm_write_page
        pop     de
        inc     e
        ld      a,e
        cp      050h
        jr      c,emm_disk_dir_loop
        ; write the label block
        ld      hl,hstbuf
        ld      b,0
emm_disk_zero:
        ld      (hl),0
        inc     hl
        inc     b
        jr      nz,emm_disk_zero
        ld      hl,emm_label
        ld      de,hstbuf
        ld      bc,8
        ldir
        ld      hl,hstbuf
        ld      d,0
        ld      e,EMM_LABEL_PAGE
        ld      bc,0
        call    emm_write_page
        xor     a
        ld      (hst_valid),a
        ret

; E: host sector I/O: 20-bit offset = trk*2000h + psec*100h
; -> addr[19:16] = trk>>3, addr[15:8] = ((trk&7)<<5) | psec
emm_host_setup:
        ld      a,(hst_trk)
        srl     a
        srl     a
        srl     a
        ld      d,a
        ld      a,(hst_trk)
        and     007h
        rrca                    ; <<5 == rrca x3
        rrca
        rrca
        ld      e,a
        ld      a,(hst_psec)
        or      e
        ld      e,a
        ret

emm_host_read:
        call    emm_host_setup
        ld      hl,hstbuf
        ld      bc,0
        call    emm_read_page
        xor     a
        ret

emm_host_write:
        call    emm_host_setup
        ld      hl,hstbuf
        ld      bc,0
        call    emm_write_page
        xor     a
        ret

; select drive (fd_drive), motor on, MFM. First spin-up gets a wait.
fd_select:
        ld      hl,FD_IDLE_TICKS        ; any disk access re-arms the idle timer
        ld      (fd_idle),hl
        ld      a,007h          ; SSG mixer: all channels off (quiet select)
        out     (PORT_OPN_ADDR),a
        ld      a,07fh
        out     (PORT_OPN_DATA),a
        ld      a,00eh          ; SSG port A: DRSEL=0 (internal drives 1/2)
        out     (PORT_OPN_ADDR),a
        xor     a
        out     (PORT_OPN_DATA),a
        xor     a
        out     (PORT_FDC_DENS),a       ; MFM
        ld      a,(fd_drive)
        and     003h
        or      084h                    ; motor on + drive select enable
        out     (PORT_FDC_DRIVE),a
        ld      a,(fd_motor_on)
        or      a
        jr      nz,fd_select_sync
        ld      a,1
        ld      (fd_motor_on),a
        ; ~1s spin-up (real drives; the emulator spins instantly)
        ld      bc,0
fd_spinup_outer:
        ld      e,4
fd_spinup_inner:
        dec     e
        jr      nz,fd_spinup_inner
        dec     bc
        ld      a,b
        or      c
        jr      nz,fd_spinup_outer
fd_select_sync:
        ; On a drive change the controller's track register still holds the
        ; OTHER drive's cylinder; a SEEK would step relative to it and land
        ; the new drive's head on the wrong cylinder (RNF). Re-sync: known
        ; position -> load the track register, unknown -> RESTORE.
        ld      a,(fd_drive)
        and     001h
        ld      c,a
        ld      a,(fd_sel_last)
        cp      c
        ret     z
        ld      a,c
        ld      (fd_sel_last),a
        ld      b,0
        ld      hl,fd_cyl_cache
        add     hl,bc
        ld      a,(hl)
        cp      0ffh
        jr      nz,fd_sel_known
        ld      a,00bh          ; RESTORE parks the head, track register = 0
        cpl
        out     (PORT_FDC_CMD),a
        call    fd_settle
        push    hl
        call    fd_wait_not_busy
        pop     hl
        ld      (hl),0
        ret
fd_sel_known:
        cpl
        out     (PORT_FDC_TRK),a
        ret

; seek to cylinder A on the selected drive. A per-drive cylinder cache
; avoids zero-distance SEEKs (the controller misbehaves on those).
; carry set on error.
fd_seek_cyl:
        ld      (fd_target_cyl),a
        ld      c,a
        ld      a,(fd_drive)
        and     001h
        ld      e,a
        ld      d,0
        ld      hl,fd_cyl_cache
        add     hl,de
        ld      a,(hl)
        cp      c
        jr      nz,fd_seek_do
        xor     a               ; already there
        ret
fd_seek_do:
        ld      a,c
        cpl
        out     (PORT_FDC_DATA),a
        ld      a,01bh          ; SEEK (proven command form)
        cpl
        out     (PORT_FDC_CMD),a
        call    fd_settle
        push    hl
        push    bc
        call    fd_wait_not_busy
        pop     bc
        pop     hl
        jr      c,fd_seek_fail
        and     098h            ; not-ready / seek error / CRC are fatal
        jr      nz,fd_seek_fail
        ld      (hl),c          ; cache the new cylinder
        xor     a
        ret
fd_seek_fail:
        bit     7,a             ; drive not ready (no medium)?
        jr      z,fd_seek_fail2
        ld      a,1
        ld      (fd_not_ready),a
fd_seek_fail2:
        ld      (hl),0ffh       ; position unknown
        scf
        ret

fd_settle:
        ld      a,005h
fd_settle_loop:
        dec     a
        jr      nz,fd_settle_loop
        ret

; wait for BUSY to clear; A = status (logical), carry on timeout
fd_wait_not_busy:
        ld      de,0
        ld      b,8             ; 8 x 65536 polls
fd_wnb_loop:
        in      a,(PORT_FDC_CMD)
        cpl
        bit     0,a
        ret     z
        dec     de
        ld      a,d
        or      e
        jr      nz,fd_wnb_loop
        djnz    fd_wnb_loop
        scf
        ret

; read one 256-byte sector into HL (fd_side/fd_sec preset).
; 3 in-place retries, then RESTORE+reseek, twice. HL preserved.
fd_read_retry:
        ld      a,2
        ld      (fd_world),a
fd_read_world:
        ld      a,3
        ld      (fd_tries),a
fd_read_try:
        push    hl
        call    fd_read_sector
        pop     hl
        ret     nc
        ld      a,(fd_tries)
        dec     a
        ld      (fd_tries),a
        jr      nz,fd_read_try
        call    fd_reseek
        ld      a,(fd_world)
        dec     a
        ld      (fd_world),a
        jr      nz,fd_read_world
        scf
        ret

fd_write_retry:
        ld      a,2
        ld      (fd_world),a
fd_write_world:
        ld      a,3
        ld      (fd_tries),a
fd_write_try:
        push    hl
        call    fd_write_sector
        pop     hl
        ret     nc
        ld      a,(fd_tries)
        dec     a
        ld      (fd_tries),a
        jr      nz,fd_write_try
        call    fd_reseek
        ld      a,(fd_world)
        dec     a
        ld      (fd_world),a
        jr      nz,fd_write_world
        scf
        ret

; world retry: RESTORE (head truly at 0 after), then seek back
fd_reseek:
        push    hl
        ld      a,00bh          ; RESTORE
        cpl
        out     (PORT_FDC_CMD),a
        call    fd_settle
        call    fd_wait_not_busy
        ld      a,(fd_drive)
        and     001h
        ld      e,a
        ld      d,0
        ld      hl,fd_cyl_cache
        add     hl,de
        ld      (hl),0          ; RESTORE parks at cylinder 0
        ld      a,(fd_target_cyl)
        call    fd_seek_cyl
        pop     hl
        ret

; one sector read, no retry. HL=buffer (advances by 256). carry on error.
fd_read_sector:
        ld      a,(fd_side)
        out     (PORT_FDC_SIDE),a
        ; after a side change the head needs the E (settle) delay - the
        ; proven real-hardware rule; same-side reads skip it for speed
        ld      b,088h          ; READ SECTOR (proven command form)
        push    hl
        ld      hl,fd_last_side
        cp      (hl)
        ld      (hl),a
        pop     hl
        jr      z,fd_read_side_same
        ld      b,08ch          ; READ with E=1 (head settle)
fd_read_side_same:
        ld      a,(fd_sec)
        cpl
        out     (PORT_FDC_SEC),a
        ld      a,b
        cpl
        out     (PORT_FDC_CMD),a
        call    fd_settle
        ld      bc,PORT_FDC_DATA
        ld      de,04000h       ; bounded byte-wait budget
fd_read_wait:
        in      a,(PORT_FDC_CMD)
        cpl
        bit     1,a             ; DRQ?
        jr      nz,fd_read_byte
        bit     0,a             ; still busy?
        jr      z,fd_read_done
        dec     de
        ld      a,d
        or      e
        jr      nz,fd_read_wait
        scf
        ret
fd_read_byte:
        in      a,(c)           ; data register: no cpl
        ld      (hl),a
        inc     hl
        ld      de,04000h
        jr      fd_read_wait
fd_read_done:
        and     09ch            ; not-ready / RNF / CRC / lost are fatal
        ret     z
        bit     7,a
        jr      z,fd_read_err
        push    af
        ld      a,1
        ld      (fd_not_ready),a
        pop     af
fd_read_err:
        scf
        ret

; one sector write from HL (advances by 256). carry on error.
fd_write_sector:
        ld      a,(fd_side)
        out     (PORT_FDC_SIDE),a
        ld      b,0a8h          ; WRITE SECTOR (same flag form as read)
        push    hl
        ld      hl,fd_last_side
        cp      (hl)
        ld      (hl),a
        pop     hl
        jr      z,fd_write_side_same
        ld      b,0ach          ; WRITE with E=1 (head settle)
fd_write_side_same:
        ld      a,(fd_sec)
        cpl
        out     (PORT_FDC_SEC),a
        ld      a,b
        cpl
        out     (PORT_FDC_CMD),a
        call    fd_settle
        ld      bc,PORT_FDC_DATA
        ld      de,04000h
fd_write_wait:
        in      a,(PORT_FDC_CMD)
        cpl
        bit     1,a
        jr      nz,fd_write_byte
        bit     0,a
        jr      z,fd_write_done
        dec     de
        ld      a,d
        or      e
        jr      nz,fd_write_wait
        scf
        ret
fd_write_byte:
        ld      a,(hl)
        out     (c),a           ; data register: no cpl
        inc     hl
        ld      de,04000h
        jr      fd_write_wait
fd_write_done:
        and     0fch            ; not-ready/WP/fault/RNF/CRC/lost are fatal
        ret     z
        scf
        ret

; ======================================================================
; generated tables
; ======================================================================
        include "generated_dpb.inc"
        include "generated_keymap.inc"

; ======================================================================
; disk parameter headers (A:, B: share the FD DPB; separate ALV/CSV)
; ======================================================================
dph_table:
        defw    dph_a,dph_b

dph_a:
        defw    0,0,0,0
        defw    dirbuf,dpb_fd,csv_a,alv_a
dph_b:
        defw    0,0,0,0
        defw    dirbuf,dpb_fd,csv_b,alv_b
dph_e:
        defw    0,0,0,0
        defw    dirbuf,dpb_emm,csv_e,alv_e
dph_c:
        defw    0,0,0,0
        defw    dirbuf,dpb_sasi,csv_c,alv_c
dph_d:
        defw    0,0,0,0
        defw    dirbuf,dpb_sasi,csv_d,alv_d

; ======================================================================
; data (all initialised by code before first use)
; ======================================================================
vwin_saved_sp:  defs 2
conout_char:    defs 1
conout_cell:    defs 2
clear_saved_col: defs 1
cursor_saved_attr: defs 1
cur_row:        defs 1
cur_col:        defs 1
scroll_base:    defs 2
esc_state:      defs 1
esc_row:        defs 1
cur_attr:       defs 1
csi_p1:         defs 1
csi_p2:         defs 1
csi_idx:        defs 1
csi_saved_row:  defs 1
csi_saved_col:  defs 1
sgr_fg:         defs 1
sgr_bg:         defs 1
cur_attr_sp:    defs 1
clear_saved_row: defs 1
key_ready:      defs 1
key_char:       defs 1
prev_matrix:    defs 14
seldsk_cur:     defs 1
trk:            defs 2
sec:            defs 2
dma_addr:       defs 2
readop:         defs 1
rsflag:         defs 1
wrtype:         defs 1
unacnt:         defs 1
unadsk:         defs 1
unatrk:         defs 2
unasec:         defs 2
req_psec:       defs 1
hst_valid:      defs 1
hst_dirty:      defs 1
hst_drive:      defs 1
hst_trk:        defs 2
hst_psec:       defs 1
fd_drive:       defs 1
fd_motor_on:    defs 1
fd_sel_last:    defs 1
fd_not_ready:   defs 1
fd_absent_retry: defs 1
fd_absent_mask: defs 1
fd_last_side:   defs 1
fd_idle:        defs 2
fd_side:        defs 1
fd_sec:         defs 1
fd_target_cyl:  defs 1
fd_cyl_cache:   defs 2
fd_tries:       defs 1
fd_world:       defs 1
dirbuf:         defs 128
csv_a:          defs DPB_FD_CSV_BYTES
csv_b:          defs DPB_FD_CSV_BYTES
csv_e:          defs DPB_EMM_CSV_BYTES
csv_c:          defs DPB_SASI_CSV_BYTES
csv_d:          defs DPB_SASI_CSV_BYTES
alv_a:          defs DPB_FD_ALV_BYTES
alv_b:          defs DPB_FD_ALV_BYTES
alv_e:          defs DPB_EMM_ALV_BYTES
alv_c:          defs DPB_SASI_ALV_BYTES
alv_d:          defs DPB_SASI_ALV_BYTES
emm_present:    defs 1
sasi_present:   defs 1
sasi_status:    defs 1
sasi_op:        defs 1
sasi_dst:       defs 2
sasi_cdb:       defs 6
hstbuf:         defs 256
vwin_stack:     defs 32
vwin_stack_top:
bios_stack:     defs 64
bios_stack_top:

BIOS_END:       equ $
