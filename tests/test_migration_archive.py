import pathlib,sys,struct,tempfile,unittest,zlib
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from d88 import make_blank_d88,D88Image
from migration_archive import load_set,load_volume

class MigrationArchiveTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=pathlib.Path(self.temp.name)
        self.data=bytes((i*37)&255 for i in range((512+150*32)*128))
        self.paths=[]
        for volume in (1,2):
            payload=self.data[(volume-1)*4800*128:volume*4800*128]
            raw=bytearray(655360);h=bytearray(512);h[:8]=b'MZMG31\r\n'
            for offset,value in [(8,1),(10,3),(16,volume),(18,2),(24,150),(26,0),(28,len(payload)//128),(30,1),(32,0)]:struct.pack_into('<H',h,offset,value)
            struct.pack_into('<I',h,12,zlib.crc32(self.data));struct.pack_into('<I',h,20,len(self.data)//128)
            raw[512:512+len(payload)]=payload
            for i in range((len(payload)+8191)//8192):struct.pack_into('<I',h,64+i*4,zlib.crc32(raw[512+i*8192:512+(i+1)*8192]))
            struct.pack_into('<I',h,508,zlib.crc32(h[:508]));raw[:512]=h
            d=make_blank_d88('MIGRATION TEST')
            for i in range(2560):d.write_sector(i,raw[i*256:(i+1)*256])
            p=self.root/f'volume-{volume}.d88';p.write_bytes(d.data);self.paths.append(p)
    def test_complete_set(self):
        meta,data=load_set(self.paths);self.assertEqual(data,self.data);self.assertEqual(meta['volumes'],2)
    def test_missing_volume(self):
        with self.assertRaises(ValueError):load_set(self.paths[:1])
    def test_wrong_order_or_duplicate(self):
        for paths in (self.paths[::-1],[self.paths[0],self.paths[0]]):
            with self.assertRaises(ValueError):load_set(paths)
    def test_incomplete_header(self):
        d=D88Image(bytearray(self.paths[0].read_bytes()));d.write_sector(0,bytes(256));self.paths[0].write_bytes(d.data)
        with self.assertRaisesRegex(ValueError,'header'):load_volume(self.paths[0])
    def test_corrupt_payload(self):
        d=D88Image(bytearray(self.paths[0].read_bytes()));r=bytearray(d.read_sector(5));r[10]^=1;d.write_sector(5,r);self.paths[0].write_bytes(d.data)
        with self.assertRaisesRegex(ValueError,'CRC'):load_volume(self.paths[0])
    def test_wrong_set_identity(self):
        d=D88Image(bytearray(self.paths[1].read_bytes()));h=bytearray(d.read_sector(0)+d.read_sector(1));h[12]^=1;struct.pack_into('<I',h,508,zlib.crc32(h[:508]));d.write_sector(0,h[:256]);d.write_sector(1,h[256:]);self.paths[1].write_bytes(d.data)
        with self.assertRaisesRegex(ValueError,'set'):load_set(self.paths)
