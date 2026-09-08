.module crt0
.globl _main
.area _HEADER (ABS)
.org 0x100
ld sp,#0xdf00
call _main
jp 0
.area _CODE
.area _HOME
.area _INITIALIZER
.area _GSINIT
.area _GSFINAL
.area _DATA
.area _INITIALIZED
.area _BSEG
.area _BSS
.area _HEAP
