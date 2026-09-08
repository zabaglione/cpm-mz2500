"""Relocate the pinned DRI banked CP/M Plus SPR modules."""
from __future__ import annotations

def relocate(spr: bytes, base: int, length: int, externals: dict[int,int]) -> bytes:
    if base & 255 or base + length > 65536 or len(spr) < 256:
        raise ValueError("invalid SPR placement/header")
    size = int.from_bytes(spr[1:3],"little")
    if size != length or len(spr) < 256+size+(size+7)//8:
        raise ValueError("unexpected or truncated SPR")
    data = bytearray(spr[256:256+size])
    bitmap = spr[256+size:]
    for i in range(size):
        if bitmap[i//8] & (128 >> (i%8)):
            page = data[i]
            if page in externals:
                data[i] = externals[page] >> 8
            elif page < (size+255)//256:
                data[i] = page+(base>>8)
            else:
                raise ValueError(f"unknown SPR external page {page:02X}")
    return bytes(data)

def relocate_banked(res: bytes, banked: bytes) -> tuple[bytes,bytes]:
    res_base,bnk_base,bios = 0xE200,0xB200,0xE800
    scb_page = 0xE700
    r = bytearray(relocate(res,res_base,0x600,{0xFC:bnk_base,0xFF:bios}))
    b = relocate(banked,bnk_base,0x2E00,{0xFB:scb_page,0xFD:res_base,0xFF:bios})
    scb = 0x59C
    if r[scb+5] != 0x31:
        raise ValueError("unexpected BDOS version")
    for offset,value in ((0x13,0),(0x1A,79),(0x1C,24),(0x2E,1),(0x2F,0)):
        r[scb+offset]=value
    r[scb+0x5D:scb+0x5F] = bytes.fromhex('00 e0')
    return bytes(r),b
