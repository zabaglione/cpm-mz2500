"""Build the drive-selectable physical formatter using the migration CRT/BDOS wrapper."""
import re,subprocess

def build_format(root):
    build=root/'build'
    for name in ('main','hardware'):
        subprocess.run(['sdcc','-mz80','--std-c99','--opt-code-size','-c',str(root/f'src/format/{name}.c'),'-o',str(build/f'fmt_{name}.rel')],check=True)
    subprocess.run(['sdcc','-mz80','--no-std-crt0','--code-loc','0x0109','--data-loc','0x8000',str(build/'migcrt.rel'),str(build/'mig_io.rel'),str(build/'fmt_main.rel'),str(build/'fmt_hardware.rel'),'-o',str(build/'format.ihx')],check=True)
    memory={}
    for line in (build/'format.ihx').read_text().splitlines():
        rec=bytes.fromhex(line[1:]);assert sum(rec)&255==0
        if rec[3]==0:
            start=int.from_bytes(rec[1:3],'big')
            memory.update((start+i,b) for i,b in enumerate(rec[4:4+rec[0]]))
    assert min(memory)==256 and max(memory)<0x8000
    data=re.search(r'^_DATA\s+([0-9A-F]+)\s+([0-9A-F]+)',(build/'format.map').read_text(),re.M)
    assert data and sum(int(x,16) for x in data.groups())<0xdd00
    com=bytes(memory.get(i,0) for i in range(256,max(memory)+1))
    (build/'format.com').write_bytes(com)
    print(f'FORMAT.COM {len(com)} bytes')
    return com
