#!/usr/bin/env python3
"""Exercise CP/M Plus on an external MZ-2500 CLI binary.

No emulator implementation is imported or inspected. ROMs stay external.
All input/output disks, logs and screenshots stay in the ignored build/qa.
"""
from __future__ import annotations
import argparse
import json
import pathlib
import subprocess
from d88 import D88Image
from cpmfs import CpmFilesystem, D88CpmAdapter, FlatCpmAdapter
import disk_geometry as dg

ROOT = pathlib.Path(__file__).resolve().parents[1]
QA = ROOT/'build/qa'
PASS = 'P3TEST PASS: BDOS 31 SCB PARSE MULTI RANDOM FLUSH'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--emulator',required=True,type=pathlib.Path)
    parser.add_argument('--rom-dir',type=pathlib.Path)
    parser.add_argument('--sasi-rom',type=pathlib.Path)
    args = parser.parse_args()
    QA.mkdir(parents=True,exist_ok=True)
    subprocess.run(['z80asm','-o',str(QA/'p3test.com'),str(ROOT/'tests/cpm3_probe.asm')],check=True)
    probe = (QA/'p3test.com').read_bytes()
    large = bytes((i*37+i//251)&255 for i in range(70000))
    floppy = D88Image(bytearray((ROOT/'build/cpm_boot.d88').read_bytes()))
    fs = CpmFilesystem(D88CpmAdapter(floppy,dg.FD))
    for name,data in [('P3TEST.COM',probe),('LARGE.BIN',large),
                      ('BATCH.SUB',b'P3TEST\r\nDIR P3CHECK.DAT\r\n')]:
        fs.add_file(name,data)
    (QA/'probe.d88').write_bytes(floppy.data)
    results = []

    def run(name,options,expected,frames):
        command = [str(args.emulator.resolve()),*map(str,options),'--frames',str(frames),
                   '--screen-report','--cpu-report','--screenshot',str(QA/f'{name}.ppm')]
        p = subprocess.run(command,capture_output=True,text=True,timeout=90)
        output = p.stdout+p.stderr
        (QA/f'{name}.log').write_text(output)
        if p.returncode or any(x not in output for x in expected) or 'P3TEST FAIL' in output:
            raise AssertionError(f'{name}: runtime check failed; see build/qa/{name}.log')
        results.append(name)
        print(f'PASS {name}',flush=True)
        return output

    fd = ['--disk-a',QA/'probe.d88']
    run('fd-api',fd+['--type','P3TEST\\r:600','--disk-save',f'0:{QA}/api-result.d88'],[PASS,'A>'],1800)
    result = D88Image(bytearray((QA/'api-result.d88').read_bytes()))
    actual = CpmFilesystem(D88CpmAdapter(result,dg.FD)).read_file('P3CHECK.DAT')
    assert actual == bytes(i&255 for i in range(384)), 'multi-record file bytes differ'
    run('fd-no-expansions',fd+['--no-emm','--no-sasi','--ram-fill','a5',
                             '--type','SHOW\\r:1000','--type','P3TEST\\r:1700'],[PASS,'Space:'],2900)
    run('fd-large-copy',fd+['--disk-b',ROOT/'build/cpm_data.d88',
                          '--type','PIP B:=A:LARGE.BIN[V]\\r:600',
                          '--disk-save',f'1:{QA}/large-result.d88'],['A>'],10000)
    result = D88Image(bytearray((QA/'large-result.d88').read_bytes()))
    assert CpmFilesystem(D88CpmAdapter(result,dg.FD)).read_file('LARGE.BIN')[:len(large)] == large
    run('emm-warm-cold',fd+['--type','PIP E:=A:P3TEST.COM[V]\\r:600',
                          '--type','E:\\r:1600','--type','P3TEST\\r:1750',
                          '--reboot-at','2800','--type','E:\\r:3400',
                          '--type','P3TEST\\r:3550'],[PASS,'E>P3TEST'],4500)
    run('fd-submit',fd+['--type','SUBMIT BATCH\\r:600'],[PASS,'P3CHECK  DAT'],3000)

    image = bytearray((ROOT/'build/cpm.hdd').read_bytes())
    fs = CpmFilesystem(FlatCpmAdapter(image,dg.SASI,dg.SASI_BASE_C*256))
    for name,data in [('P3TEST.COM',probe),('LARGE.BIN',large),
                      ('BATCH.SUB',b'P3TEST\r\nDIR P3CHECK.DAT\r\n')]:
        fs.add_file(name,data)
    (QA/'probe.hdd').write_bytes(image)
    mounted = ['--hdf',QA/'probe.hdd','--hdf-block','256']
    # FD boot with SASI mounted is ROM-independent and tests the same drivers.
    run('hdd-io',fd+mounted+['--type','C:\\r:600','--type','SHOW\\r:800',
        '--type','P3TEST\\r:1300','--type','PIP D:=C:LARGE.BIN[V]\\r:2000',
        '--type','SUBMIT BATCH\\r:7000','--hdf-save',QA/'hdd-result.hdd'],[PASS,'C>'],9500)
    result = bytearray((QA/'hdd-result.hdd').read_bytes())
    fs = CpmFilesystem(FlatCpmAdapter(result,dg.SASI,dg.SASI_BASE_D*256))
    assert fs.read_file('LARGE.BIN')[:len(large)] == large
    assert result[:dg.SASI_BASE_C*256] == image[:dg.SASI_BASE_C*256]
    run('putsys',fd+mounted+['--type','PUTSYS\\r:600',
        '--hdf-save',QA/'putsys.hdd'],['DONE - press the IPL button'],5000)
    result = (QA/'putsys.hdd').read_bytes()
    reserved_end = (dg.SASI_BASE_C*256)+dg.SASI.off*dg.SASI.spt*128
    assert result[reserved_end:] == image[reserved_end:], 'PUTSYS changed filesystem data'
    assert result[:dg.SASI_BASE_C*256] == image[:dg.SASI_BASE_C*256], 'PUTSYS changed partitions'
    # Exact boot-area equality includes the HDD boot-drive patch.
    assert result[dg.SASI_BASE_C*256:reserved_end] == image[dg.SASI_BASE_C*256:reserved_end]
    # A legacy/non-Plus destination must be rejected before any write.
    legacy = bytearray(image)
    legacy[dg.SASI_BASE_C*256+7:dg.SASI_BASE_C*256+16] = b'CP/M-2.2 '
    (QA/'legacy-header.hdd').write_bytes(legacy)
    run('putsys-reject-old',fd+['--hdf',QA/'legacy-header.hdd','--hdf-block','256',
        '--type','PUTSYS\\r:600','--hdf-save',QA/'legacy-after.hdd'],
        ['CP/M Plus boot media required on A: and C:'],2400)
    assert (QA/'legacy-after.hdd').read_bytes() == legacy, 'rejected media was written'
    if bool(args.rom_dir) != bool(args.sasi_rom):
        parser.error('--rom-dir and --sasi-rom must be supplied together')
    if args.rom_dir:
        run('hdd-native-ipl',['--hdf',QA/'putsys.hdd','--hdf-block','256','--real-ipl',
            '--rom-dir',args.rom_dir,'--sasi-rom',args.sasi_rom,
            '--type','SHOW\\r:1000','--type','P3TEST\\r:1500',
            '--type','SUBMIT BATCH\\r:2300'],[PASS,'C>','P3CHECK  DAT'],4300)
    (QA/'results.json').write_text(json.dumps({'passed':results,'physical_hardware':'not tested'},indent=2)+'\n')
    print(f'{len(results)} runtime scenarios passed; physical hardware not tested')

if __name__ == '__main__':
    main()
