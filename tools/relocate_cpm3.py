"""Relocate the pinned DRI nonbanked BDOS SPR for a native IPL image.

SPR: 256-byte header, little-endian module length at +1, code, then a
MSB-first relocation bitmap. FF-page references name the BIOS; all other
marked bytes are module-relative high bytes. The SCB is embedded three
pages below BIOS (DRI GENCPM layout, without the optional page chop).
See docs/cpm3-port.md for the primary-source references.
"""

def relocate_bdos(spr: bytes, base: int, bios: int) -> bytes:
    if base & 255 or bios & 255 or not 0 < base < bios < 65536:
        raise ValueError("BDOS and BIOS require ordered page-aligned addresses")
    if len(spr) < 256:
        raise ValueError("truncated SPR header")
    length = int.from_bytes(spr[1:3], "little")
    if length != 0x20E7 or base + ((length + 255) & ~255) != bios:
        raise ValueError("unexpected nonbanked BDOS layout")
    if len(spr) < 256 + length + (length + 7) // 8:
        raise ValueError("truncated SPR code/bitmap")
    code = bytearray(spr[256:256+length])
    bitmap = spr[256+length:]
    for offset in range(length):
        if bitmap[offset//8] & (0x80 >> (offset % 8)):
            page = code[offset]
            if page == 0xFF:
                code[offset] = bios >> 8
            elif page <= 0x20:
                code[offset] = page + (base >> 8)
            else:
                raise ValueError(f"unsupported SPR relocation page {page:02X}")
    scb = bios - 0x264 - base
    if code[scb+5] != 0x31:
        raise ValueError("BDOS does not report CP/M Plus 3.1")
    code[scb+0x13] = 0  # default boot drive (HDD builder patches to C)
    code[scb+0x1A] = 79  # last screen column
    code[scb+0x1C] = 24  # last screen row
    code[scb+0x2E] = 1   # destructive backspace
    code[scb+0x2F] = 0   # rubout mode
    return bytes(code).ljust(bios-base, b"\0")
