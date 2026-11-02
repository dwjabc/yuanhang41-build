#!/usr/bin/env python3
"""Extract the f2fs repair tool root from a released e5-linux boot image.

The shipped initramfs carries the aarch64/musl tool bundle that
boot/prepare-f2fs-tools.py expects as its --root input, so the rebuilt boot
image keeps the same tools (and manifest hashes) as the release.
"""
import struct, subprocess, sys, lz4.block  # pip lz4 for legacy-frame blocks
from pathlib import Path

NEEDED = ('sbin/fsck.f2fs', 'sbin/resize.f2fs', 'lib/ld-musl-aarch64.so.1',
          'lib/libf2fs.so.10', 'lib/libuuid.so.1', 'lib/libgcc_s.so.1',
          'usr/bin/ucode', 'lib/libucode.so.20230711', 'lib/libjson-c.so.5',
          'usr/lib/ucode/fs.so', 'usr/sbin/resize2fs', 'lib/libe2p.so.2',
          'lib/libext2fs.so.2', 'lib/libcom_err.so.0')

def main(boot_img, out_root):
    data = open(boot_img, 'rb').read()
    ks, rs = struct.unpack_from('<II', data, 8)
    page = 4096
    roff = page + ((ks + page - 1) // page) * page
    ram = data[roff:roff + rs]
    magic = struct.unpack('<I', ram[:4])[0]
    out = bytearray()
    if magic == 0x184C2102:  # legacy lz4: [csize][8MiB window] blocks
        off = 4
        while off + 4 <= len(ram):
            csize = struct.unpack_from('<I', ram, off)[0]
            off += 4
            if csize == 0 or csize > len(ram) - off:
                break
            out += lz4.block.decompress(ram[off:off + csize],
                                        uncompressed_size=8 * 1024 * 1024)
            off += csize
    else:
        sys.exit('unexpected ramdisk magic: %08x' % magic)
    print('initramfs cpio:', len(out), 'bytes')

    root = Path(out_root)
    off = 0
    got = []
    while off + 110 <= len(out):
        if out[off:off + 6] != b'070701':
            break
        f = lambda i: int(out[off + 6 + i * 8: off + 6 + (i + 1) * 8], 16)
        mode, fsize, namesize = f(1), f(6), f(11)
        name_off = off + 110
        name = out[name_off:name_off + namesize - 1].decode('utf8', 'replace')
        data_off = (name_off + namesize + 3) & ~3
        blob = out[data_off:data_off + fsize]
        off = (data_off + fsize + 3) & ~3
        if name in NEEDED and (mode & 0o170000) == 0o100000:
            dest = root / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(blob)
            dest.chmod(0o755)
            got.append(name)
        if name == 'TRAILER!!!':
            break
    missing = set(NEEDED) - set(got)
    if missing:
        sys.exit('missing from initramfs: ' + ', '.join(sorted(missing)))
    print('extracted', len(got), 'files:', ', '.join(sorted(got)))

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
