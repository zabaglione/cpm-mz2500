"""CP/M Plus relocation, binary provenance, and boot-area integrity."""
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import fetch_cpm3
import disk_geometry as dg
import make_boot_d88 as boot
import make_hdd_image as hdd
from relocate_cpm3 import relocate_bdos
from d88 import D88Image
from cpmfs import CpmFilesystem, D88CpmAdapter, FlatCpmAdapter


class Cpm3Test(unittest.TestCase):
    def test_pinned_vendor_inputs(self):
        fetch_cpm3.verify_binaries()

    def test_relocation_preserves_instructions_and_resolves_bios(self):
        spr = (fetch_cpm3.VENDOR / 'bin/bdos3.spr').read_bytes()
        result = relocate_bdos(spr, 0xC700, 0xE800)
        length = int.from_bytes(spr[1:3], 'little')
        scb_changes = {0x1E9C+x for x in (0x13, 0x1A, 0x1C, 0x2E, 0x2F)}
        bios_calls = 0
        for i, old in enumerate(spr[256:256+length]):
            if i in scb_changes:
                continue
            relocated = bool(spr[256+length+i//8] & (128 >> (i%8)))
            expected = (0xE8 if old == 255 else old+0xC7) if relocated else old
            self.assertEqual(result[i], expected, hex(i))
            bios_calls += relocated and old == 255
        self.assertEqual(bios_calls, 47)
        self.assertEqual(result[0x1EFE:0x1F00], bytes.fromhex('06 c7'))
        self.assertEqual(len(result), 0x2100)

    def test_invalid_spr_rejected(self):
        spr = (fetch_cpm3.VENDOR / 'bin/bdos3.spr').read_bytes()
        for bad in (b'', spr[:255], spr[:9000], bytes(256)):
            with self.assertRaises(ValueError):
                relocate_bdos(bad, 0xC700, 0xE800)
        for addresses in ((0xC701, 0xE800), (0xC600, 0xE800), (0xE800, 0xC700)):
            with self.assertRaises(ValueError):
                relocate_bdos(spr, *addresses)

    def test_floppy_banks_do_not_overlap_filesystem(self):
        disk = D88Image(bytearray((ROOT/'build/cpm_boot.d88').read_bytes()))
        self.assertEqual(disk.read_sector(16), boot.make_ipl_header())
        for i, bank in enumerate(boot.IPL_DEST_BANKS):
            sectors = list(range(i*32,i*32+16))+list(range(i*32+48,i*32+64))
            self.assertLess(max(sectors), dg.FD.off*16)
            self.assertEqual(b''.join(disk.read_sector(s) for s in sectors),
                             (ROOT/f'build/cpm_bank{bank:02x}.bin').read_bytes())
        fs = CpmFilesystem(D88CpmAdapter(disk,dg.FD))
        self.assertEqual(fs.read_file('CCP.COM'),
                         (fetch_cpm3.VENDOR/'bin/ccp.com').read_bytes())

    def test_hdd_reserved_area_and_utilities(self):
        import json
        image = bytearray((ROOT/'build/cpm.hdd').read_bytes())
        layout = json.loads((ROOT/'build/cpm_layout.json').read_text())
        base = dg.SASI_BASE_C*256
        expected = bytearray(b''.join((ROOT/f'build/cpm_bank{bank:02x}.bin').read_bytes()
                                     for bank in boot.IPL_DEST_BANKS))
        expected[layout['boot_drive_default']-boot.BOOT_BASE] = 2
        self.assertLessEqual(16*256+len(expected),dg.SASI.off*dg.SASI.spt*128)
        self.assertEqual(image[base+16*256:base+16*256+len(expected)],expected)
        self.assertEqual(image[base:base+256],boot.make_ipl_header())
        fs = CpmFilesystem(FlatCpmAdapter(image,dg.SASI,base))
        for name in boot.DRI_UTILITIES:
            source = (fetch_cpm3.VENDOR/'bin'/name.lower()).read_bytes()
            self.assertEqual(fs.read_file(name)[:len(source)],source)

if __name__ == '__main__':
    unittest.main()
