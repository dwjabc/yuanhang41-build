#!/usr/bin/env python3
"""Repack the released yuanhang41s TF package as a yuanhang41 (ZTE 7541N) build.

Runner layout (env OUTDIR = artifact output):
  ./e5-linux, ./linux-lts-e5, ./pkg/yuanhang41s-openwrt-*/, yh41/kernel-out,
  out/yuanhang41-boot.{img,json,misc-slot-b-trial.bin}, out/yuanhang41-openwrt.ext4.gz

The profile id stays yuanhang41s internally (same P720S11 board: the audio, BT
and board logic is keyed on it); only the installer-facing identity, the boot
image, the rootfs modules and the metadata change.
"""
import hashlib
import json
import os
import shutil
import stat
import time
import zipfile
from pathlib import Path

TOP = Path.cwd()
OUTDIR = Path(os.environ['OUTDIR'])
SRC = next((TOP / 'pkg').glob('yuanhang41s-openwrt-*'))
KOUT = TOP / 'yh41/kernel-out'
STAGE = TOP / 'yh41/repack'

SOURCE_COMMIT = 'a8a814fd550a92d8a83150d0b7aec676cb3c79f4'
SOURCE_FINGERPRINT = '08c54d1af541ab25c3dac7e813e8a5dcd346194593097a55c087f90872e66f4a'


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    epoch = int(time.time())
    stamp = time.strftime('%Y%m%d.%H%M%S', time.gmtime(epoch))
    release = (KOUT / 'kernel.release').read_text().strip()
    kr = release.split('-', 1)[1] if '-' in release else release
    pkg_name = f'yuanhang41-openwrt-25.12.5-r{stamp}-ga8a814fd-local-k{kr}'
    priv_ver = f'r{stamp}-ga8a814fd-local'

    if STAGE.exists():
        shutil.rmtree(STAGE)
    shutil.copytree(SRC, STAGE)

    shutil.copy2(OUTDIR / 'yuanhang41-boot.img', STAGE / 'files/boot.img')
    shutil.copy2(OUTDIR / 'yuanhang41-boot.json', STAGE / 'files/boot.json')
    trial = OUTDIR / 'yuanhang41-boot.misc-slot-b-trial.bin'
    if trial.exists():
        shutil.copy2(trial, STAGE / 'files/boot-misc-slot-b.bin')
    shutil.copy2(OUTDIR / 'yuanhang41-openwrt.ext4.gz', STAGE / 'files/openwrt.ext4.gz')
    shutil.copy2(KOUT / 'config', STAGE / 'files/kernel.config')

    modules_sha = {f'modules/{ko.name}': digest(ko)
                   for ko in sorted((KOUT / 'modules').glob('*.ko'))}
    kernel_manifest = {
        'release': release,
        'sha256': {
            'Image': digest(KOUT / 'Image'),
            'Image.lk': digest(KOUT / 'Image.lk'),
            'config': digest(KOUT / 'config'),
            'kernel.release': digest(KOUT / 'kernel.release'),
            'modules.builtin': digest(KOUT / 'modules.builtin'),
            'modules.builtin.modinfo': digest(KOUT / 'modules.builtin.modinfo'),
            'modules.tar': digest(KOUT / 'modules.tar'),
            'modules.in-tree': digest(KOUT / 'modules.in-tree'),
            **modules_sha,
        },
    }
    boot_sha = digest(STAGE / 'files/boot.img')

    release_json = {
        'format': 1,
        'private_version': priv_ver,
        'image_version': f'yuanhang41-{priv_ver}',
        'package_name': pkg_name,
        'profile': 'yuanhang41s',
        'openwrt': '25.12.5',
        'kernel_release': release,
        'source_commit': SOURCE_COMMIT,
        'source_fingerprint': SOURCE_FINGERPRINT,
        'source_dirty': False,
        'build_epoch': epoch,
        'build_time_utc': time.strftime('%Y-%m-%dT%H:%M:%S+00:00', time.gmtime(epoch)),
    }
    (STAGE / 'files/RELEASE.json').write_text(json.dumps(release_json, indent=2) + '\n')
    (STAGE / 'files/VERSION').write_text(f'{pkg_name} ({release})\n')
    (STAGE / 'files/device-profile.json').write_text(
        json.dumps({'profile': 'yuanhang41s', 'android_models': ['ZTE 7541N']}) + '\n')
    (STAGE / 'files/tf-install.env').write_text(
        "PROFILE=yuanhang41s\nANDROID_MODEL='ZTE 7541N'\n")

    bc = STAGE / 'files/android-bootchain.sh'
    text = bc.read_text(encoding='utf-8')
    anchor = "    'ZTE 7546N') [ \"$(getprop ro.product.device)\" = P720S11 ] || fail 'unknown 41S board' ;;\n"
    addition = ("    'ZTE 7541N') [ \"$(getprop ro.product.device)\" = P720S11 ] || "
                "fail 'unknown yuanhang41 board' ;;\n")
    if anchor not in text:
        raise SystemExit('android-bootchain.sh anchor not found; package layout changed')
    bc.write_text(text.replace(anchor, anchor + addition), encoding='utf-8', newline='\n')

    mp = STAGE / 'module.prop'
    mod = {}
    for line in mp.read_text(encoding='utf-8').splitlines():
        k, _, v = line.partition('=')
        mod[k] = v
    mod['name'] = 'ZTE 7541N OpenWrt TF Installer'
    mod['version'] = f'yuanhang41-{priv_ver}'
    mod['versionCode'] = str(epoch)
    mp.write_text(''.join(f'{k}={v}\n' for k, v in mod.items()), encoding='utf-8')

    build = json.loads((SRC / 'files/BUILD.json').read_text(encoding='utf-8'))
    build.update({
        'private_version': priv_ver,
        'name': pkg_name,
        'profile': 'yuanhang41s',
        'source_commit': SOURCE_COMMIT,
        'source_fingerprint': SOURCE_FINGERPRINT,
        'build_epoch': epoch,
        'kernel_release': release,
        'boot_sha256': boot_sha,
        'build_type': 'local repackage; release binaries and rootfs of yuanhang41s, '
                      'self-built same-board kernel, modules written in',
        'hardware_validation': 'offline checks only; yuanhang41 (P720S11 board) not yet flashed',
        'kernel_manifest': kernel_manifest,
    })
    (STAGE / 'files/BUILD.json').write_text(json.dumps(build, indent=2, ensure_ascii=False) + '\n')

    lines = []
    for path in sorted(STAGE.rglob('*')):
        if path.is_file() and path.name != 'SHA256SUMS':
            rel = path.relative_to(STAGE).as_posix()
            lines.append(f'{digest(path)}  {rel}')
    (STAGE / 'files/SHA256SUMS').write_text('\n'.join(lines) + '\n')

    zip_path = OUTDIR / (pkg_name + '.zip')
    if zip_path.exists():
        zip_path.unlink()
    # file entries only: explicit directory markers break Info-ZIP unzip
    # (marker lacks the trailing slash / DOS dir bit, so children cannot be
    # created under what unzip already made a file)
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in sorted(STAGE.rglob('*')):
            if not path.is_file():
                continue
            arc = path.relative_to(STAGE).as_posix()
            info = zipfile.ZipInfo(arc, date_time=time.gmtime(epoch)[:6])
            mode = path.stat().st_mode & 0xFFFF
            info.external_attr = (stat.S_IMODE(mode) << 16)
            info.compress_type = zipfile.ZIP_DEFLATED
            with open(path, 'rb') as f:
                zf.writestr(info, f.read())
    print('package:', pkg_name)
    print('zip:', zip_path, f'{zip_path.stat().st_size/1e6:.1f} MB')


if __name__ == '__main__':
    main()
