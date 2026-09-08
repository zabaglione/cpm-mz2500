#!/usr/bin/env python3
"""Independent archive/file/boot verification for the synthetic runtime test."""
import json,pathlib,sys,zlib
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from migration_archive import load_set
QA=ROOT/'build/migration-qa'

def directory_files(image,base,off):
    start=base*256+off*8192;raw=image[start:start+32768];files={}
    for i in range(0,32768,32):
        e=raw[i:i+32]
        if e[0]==229:continue
        if e[0]>15:raise ValueError('invalid user')
        key=(e[0],bytes(b&127 for b in e[1:9]).decode().rstrip()+'.'+bytes(b&127 for b in e[9:12]).decode().rstrip())
        records=(e[12]&1)*128+e[15]
        blocks=[int.from_bytes(e[j:j+2],'little') for j in range(16,32,2)]
        data=b''.join(image[start+b*4096:start+(b+1)*4096] for b in blocks if b)[:records*128]
        ex=(e[14]*32+e[12])//2
        files.setdefault(key,[]).append((ex,data,bytes(e[9:12])))
    return {k:(b''.join(d for _,d,_ in sorted(parts)),parts[0][2]) for k,parts in files.items()}

def normalized(old,base,off):
    start=base*256+off*8192;directory=bytearray(old[start:start+32768]);used=set()
    for i in range(0,32768,32):
        e=directory[i:i+32]
        if e[0]==229:continue
        used.update(b for j in range(16,32,2) if (b:=int.from_bytes(e[j:j+2],'little')))
    mapping={b:i+8 for i,b in enumerate(sorted(used))}
    for i in range(0,32768,32):
        if directory[i]==229:continue
        for j in range(16,32,2):
            b=int.from_bytes(directory[i+j:i+j+2],'little')
            if b:directory[i+j:i+j+2]=mapping[b].to_bytes(2,'little')
    return bytes(directory)+b''.join(old[start+b*4096:start+(b+1)*4096] for b in sorted(used))

def main():
    old=(QA/'old.hdd').read_bytes();new=(QA/'restored.hdd').read_bytes()
    paths=sorted(QA.glob('volume-*.d88'),key=lambda p:int(p.stem.split('-')[-1]))
    meta,archive=load_set(paths)
    assert archive==normalized(old,32,3)+normalized(old,32800,3),'archive differs from independent block remapping'
    utilities=set(__import__('make_boot_d88').DRI_UTILITIES)|{'PUTSYS.COM'}
    checked=0
    for drive,base in [(2,32),(3,32800)]:
        src=directory_files(old,base,3);dst=directory_files(new,base,5)
        for key,(data,attrs) in src.items():
            if drive==2 and key[0]==0 and key[1] in utilities:continue
            assert dst[key]==(data,attrs),f'file/attribute mismatch {drive} {key}'
            checked+=1
        if drive==2:
            for name in utilities:
                file=ROOT/'build/putsys.com' if name=='PUTSYS.COM' else ROOT/'vendor/cpm3/bin'/name.lower()
                content=file.read_bytes();assert dst[(0,name)][0][:len(content)]==content,name
    assert old[:8192]==new[:8192],'partition table/leading bytes changed'
    end=(32800+32768)*256
    assert old[end:]==new[end:],'bytes outside C/D changed'
    canonical=(ROOT/'build/cpm.hdd').read_bytes()
    assert new[8192:8192+40960]==canonical[8192:8192+40960],'new boot area differs'
    report={'user_files_preserved':checked,'new_system_files_verified':len(utilities),'volumes':meta['volumes'],'archive_crc':f'{zlib.crc32(archive):08x}','source_backup_verify':'byte-identical (runtime assertion)','boot':'CP/M Plus v3.1.0 HDD boot passed','physical_hardware':'not tested'}
    (QA/'results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
