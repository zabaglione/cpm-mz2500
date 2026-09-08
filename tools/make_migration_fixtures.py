#!/usr/bin/env python3
"""Private generated synthetic HDD fixtures; no ROM or old OS binary needed."""
import dataclasses,json,pathlib,sys,zlib
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import disk_geometry as dg
from cpmfs import CpmFilesystem,FlatCpmAdapter
from make_hdd_image import TOTAL_BLOCKS,partition_entry,SIGNATURE
QA=ROOT/'build/migration-qa'

def main():
    QA.mkdir(exist_ok=True)
    image=bytearray(TOTAL_BLOCKS*256)
    image[768:784]=SIGNATURE
    image[784:800]=partition_entry(0x81,32768,0,0,32,None)
    image[800:816]=partition_entry(2,32768,0,0,32800,None)
    old=dataclasses.replace(dg.SASI,off=3,dsm=2041)
    expected=[]
    for drive,base in [(2,32),(3,32800)]:
        fs=CpmFilesystem(FlatCpmAdapter(image,old,base*256));fs.format()
        files=[(0,'EMPTY.TXT',b''),(3,'SHARED.BIN',bytes(range(256))*1300),(15,'SHARED.BIN',b'User 15 data\r\n')]
        if drive==2:files += [(0,'PIP.COM',b'OLD SYSTEM FILE MUST REMAIN IN BACKUP'),(0,'TOP.BIN',bytes(range(128)))]
        else:files += [(0,'LARGE.BIN',bytes((i*37+i//251)&255 for i in range(700000)))]
        for user,name,data in files:
            fs.add_file(name,data,user)
            actual=fs.read_file(name,user)
            expected.append(dict(drive=drive,user=user,name=name,length=len(actual),crc=zlib.crc32(actual)))
        # Put TOP.BIN at the highest old allocation block: it must be compacted.
        if drive==2:
            raw=bytearray(fs._read_dir_raw())
            for off in range(0,len(raw),32):
                if raw[off+1:off+12]==b'TOP     BIN':
                    b=int.from_bytes(raw[off+16:off+18],'little');pos=base*256+3*8192
                    image[pos+2041*4096:pos+2042*4096]=image[pos+b*4096:pos+(b+1)*4096]
                    raw[off+16:off+18]=(2041).to_bytes(2,'little');raw[off+9]|=128;raw[off+10]|=128
            fs._write_dir_raw(raw)
    h=bytearray(256);h[0]=1;h[1:7]=b'IPLPRO';h[7:19]=b'CP/M-2.2   \r';h[32:36]=bytes([5,6,7,255]);image[8192:8448]=h
    (QA/'old.hdd').write_bytes(image);(QA/'expected.json').write_text(json.dumps(expected,indent=2)+'\n')
    print('Synthetic legacy HDD and expected file CRCs ready')
if __name__=='__main__':main()
