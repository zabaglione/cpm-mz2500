#!/usr/bin/env python3
"""Independently check the physical geometry and MIGRATE archive after runtime QA."""
import json,pathlib
from d88 import D88Image
from migration_archive import load_set
ROOT=pathlib.Path(__file__).resolve().parents[1]

def main():
    qa=ROOT/'build/format-qa'
    for name in ("formatted.d88","formatted-a.d88"):
        disk=D88Image(bytearray((qa/name).read_bytes()))
        for i,offset in enumerate(disk.sector_positions):
            c,h=divmod(i//16,2);r=i%16+1
            assert disk.data[offset:offset+4]==bytes([c,h,r,1]),f'CHRN mismatch {i}'
            assert disk.read_sector(i)==bytes([0xe5])*256,f'data mismatch {i}'
    meta,data=load_set([qa/'backup-volume.d88'])
    assert meta['source_off']==3 and meta['volumes']==1
    assert data==bytes([0xe5])*65536,'empty-directory backup differs'
    report={'drives_verified':['A:','B:'],'physical_tracks_per_disk':160,'sectors_per_disk':2560,'decoded_fill':'E5','migration_backup_verify':'passed','physical_hardware':'not tested'}
    (qa/'geometry-results.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
