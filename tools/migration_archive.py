#!/usr/bin/env python3
"""Inspect/validate MIGRATE 1.0 raw 2DD backup sets on a PC (read-only)."""
import argparse,json,pathlib,struct,zlib
from d88 import D88Image
MAGIC=b'MZMG31\r\n'
VOLUME_RECORDS=4800

def load_volume(path):
    disk=D88Image(bytearray(pathlib.Path(path).read_bytes()))
    raw=b''.join(disk.read_sector(i) for i in range(2560))
    h=raw[:512]
    if h[:8]!=MAGIC or struct.unpack_from('<H',h,8)[0]!=1 or zlib.crc32(h[:508])!=struct.unpack_from('<I',h,508)[0]:
        raise ValueError('invalid volume header')
    u16=lambda o:struct.unpack_from('<H',h,o)[0]
    u32=lambda o:struct.unpack_from('<I',h,o)[0]
    info=dict(source_off=u16(10),set_id=u32(12),volume=u16(16),volumes=u16(18),records=u32(20),c_blocks=u16(24),d_blocks=u16(26),payload_records=u16(28),c_entries=u16(30),d_entries=u16(32))
    expected=min(VOLUME_RECORDS,info['records']-(info['volume']-1)*VOLUME_RECORDS)
    if info['source_off'] not in (3,4) or not 1<=info['volume']<=info['volumes']<=28 or info['payload_records']!=expected or info['records']!=512+32*(info['c_blocks']+info['d_blocks']) or info['volumes']!=(info['records']+4799)//4800:
        raise ValueError('invalid volume geometry')
    for i in range((expected+63)//64):
        chunk=raw[512+i*8192:512+(i+1)*8192]
        if zlib.crc32(chunk)!=u32(64+i*4):raise ValueError(f'payload CRC failed: volume {info["volume"]} chunk {i}')
    return info,raw[512:512+expected*128]

def load_set(paths):
    volumes=[load_volume(p) for p in paths]
    if not volumes:raise ValueError('empty backup set')
    first=volumes[0][0]
    if len(volumes)!=first['volumes']:raise ValueError('missing backup volumes')
    fixed=('source_off','set_id','volumes','records','c_blocks','d_blocks','c_entries','d_entries')
    for i,(meta,_) in enumerate(volumes,1):
        if meta['volume']!=i or any(meta[k]!=first[k] for k in fixed):raise ValueError('wrong volume/order/set')
    data=b''.join(data for _,data in volumes)
    if zlib.crc32(data)!=first['set_id']:raise ValueError('backup set content CRC failed')
    return first,data

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('volumes',nargs='+',type=pathlib.Path);args=p.parse_args()
    meta,data=load_set(args.volumes);print(json.dumps(meta,indent=2));print(f'All volumes verified: {len(data)} archive bytes')
if __name__=='__main__':main()
