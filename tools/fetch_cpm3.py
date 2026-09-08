#!/usr/bin/env python3
"""Fetch SHA256-pinned DRI CP/M Plus binaries and their source archive."""
from __future__ import annotations
import hashlib
import io
import pathlib
import urllib.request
import zipfile

PROJECT = pathlib.Path(__file__).resolve().parents[1]
VENDOR = PROJECT / 'vendor' / 'cpm3'
ARCHIVES = {
    'bin': ('https://www.seasip.info/Cpm/software/cpm3bin_unix.zip',
            'ec24f6e1fa173d33bcd2555dfae8296471fc8ea144c72e8cbe2166971451da82'),
    'src': ('https://www.seasip.info/Cpm/software/cpm3src_unix.zip',
            'd90cda1f25112ace3b436c4054304ace423331caa1f034c44f26698728a9fdb7'),
}
FILES = {
    'LICENSE.txt': (
        'https://raw.githubusercontent.com/brouhaha/cpm22/'
        '01018abbccce0bdf4874b0b2ed1a048c5fcc2987/LICENSE.txt',
        'a9bcdbc66bb31b86882e84469f133b3bd5598f46423b4c6bbb6bedb9f2eac754'),
    '../font8x8/font8x8_basic.h': (
        'https://raw.githubusercontent.com/dhepper/font8x8/'
        '8e279d2d864e79128e96188a6b9526cfa3fbfef9/font8x8_basic.h',
        '49d8df366296b203ca3211bc0672cf2a762135bf12710735b6292756b19dffd5'),
}


def checked(data: bytes, digest: str) -> bytes:
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError('SHA256 mismatch; refusing unverified input')
    return data


def obtain(path: pathlib.Path, url: str, digest: str) -> bytes:
    if path.is_file():
        return checked(path.read_bytes(), digest)
    with urllib.request.urlopen(url, timeout=45) as response:
        data = checked(response.read(), digest)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data


def verify_binaries() -> None:
    """Fail closed on changed unpacked build inputs, without network access."""
    archive = checked((VENDOR / 'bin.zip').read_bytes(), ARCHIVES['bin'][1])
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        for entry in z.infolist():
            if entry.is_dir():
                continue
            if (VENDOR / 'bin' / entry.filename).read_bytes() != z.read(entry):
                raise ValueError(f'modified CP/M vendor file: {entry.filename}')


def main() -> None:
    for group, (url, digest) in ARCHIVES.items():
        archive = obtain(VENDOR / f'{group}.zip', url, digest)
        with zipfile.ZipFile(io.BytesIO(archive)) as z:
            for entry in z.infolist():
                name = pathlib.PurePosixPath(entry.filename)
                if name.is_absolute() or '..' in name.parts:
                    raise ValueError('unsafe archive member')
                if entry.is_dir():
                    continue
                target = VENDOR / group / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(z.read(entry))
    for name, (url, digest) in FILES.items():
        obtain(VENDOR / name, url, digest)
    verify_binaries()
    print('vendor/cpm3 ready (pinned DRI CP/M Plus 3.1)')


if __name__ == '__main__':
    main()
