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
from relocate_cpm3 import relocate, relocate_banked
from d88 import D88Image
from cpmfs import CpmFilesystem, D88CpmAdapter, FlatCpmAdapter


class Cpm3Test(unittest.TestCase):
    def test_pinned_vendor_inputs(self):
        fetch_cpm3.verify_binaries()

    def test_relocation_preserves_instructions_and_resolves_externals(self):
        for name,base,size,externals in (
            ('resbdos3.spr',0xE200,0x600,{0xFC:0xB200,0xFF:0xE800}),
            ('bnkbdos3.spr',0xB200,0x2E00,{0xFB:0xE700,0xFD:0xE200,0xFF:0xE800})):
            spr = (fetch_cpm3.VENDOR/'bin'/name).read_bytes()
            result = relocate(spr,base,size,externals)
            for i,old in enumerate(spr[256:256+size]):
                marked = spr[256+size+i//8] & (128 >> (i%8))
                expected = externals.get(old,base+old*256)//256 if marked else old
                self.assertEqual(result[i],expected,hex(i))
        res,bnk = relocate_banked(
            (fetch_cpm3.VENDOR/'bin/resbdos3.spr').read_bytes(),
            (fetch_cpm3.VENDOR/'bin/bnkbdos3.spr').read_bytes())
        self.assertEqual(res[0x5F9:0x5FB],bytes.fromhex('00 e0'))
        self.assertEqual(res[0x5FE:0x600],bytes.fromhex('06 e2'))
        self.assertEqual((len(res),len(bnk)),(0x600,0x2E00))

    def test_invalid_spr_rejected(self):
        spr = (fetch_cpm3.VENDOR/'bin/resbdos3.spr').read_bytes()
        for bad in (b'',spr[:255],spr[:1700],bytes(256)):
            with self.assertRaises(ValueError):
                relocate(bad,0xE200,0x600,{0xFC:0xB200,0xFF:0xE800})
        with self.assertRaises(ValueError):
            relocate(spr,0xE201,0x600,{})
        with self.assertRaises(ValueError):
            relocate(spr,0xE200,0x600,{})

    def test_rtc_calendar_table_matches_gregorian_dates(self):
        import datetime
        import re
        source = (ROOT/'src/generated_rtc.inc').read_text()
        values = [int(x) for x in re.findall(r'defw (\d+)\s*$',source,re.M)]
        epoch = datetime.date(1978,1,1)
        self.assertEqual(values,[(datetime.date(y,1,1)-epoch).days+1
                                 for y in range(1978,2078)])
        self.assertEqual((datetime.date(2077,12,31)-epoch).days+1,36525)

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
