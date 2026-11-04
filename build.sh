#!/bin/bash
# yuanhang41 firmware build for GitHub Actions (also runs on any Linux host).
# Inputs staged by the workflow:
#   ./e5-linux          e5-linux @ release commit (with submodule)
#   ./linux-lts-e5      kernel tree @ 020b970e (pinned base)
#   ./base/kernel.config  released 41S kernel configuration (baseline)
#   ./dumps/yuanhang41-stock-boot_b.img, ./dumps/yuanhang41-stock-misc-head.bin
#   ./pkg/yuanhang41s-openwrt-*/   extracted released TF package
# Stages: kernel -> rootfs -> boot -> repack
set -euo pipefail
TOP=$PWD
REPO=$TOP/e5-linux
KERNEL=$TOP/linux-lts-e5
N=$TOP/yh41
OUT=$TOP/out
PKG=$(find "$TOP/pkg" -maxdepth 1 -type d -name 'yuanhang41s-openwrt-*' | head -1)
JOBS=${JOBS:-$(nproc)}
mkdir -p "$N" "$OUT"

case ${1:?stage: kernel|rootfs|boot|repack} in

kernel)
    cd "$REPO"
    echo "== staging qogirn6pro USB2 (HS) phy driver for the MUSB controller =="
    PH=$KERNEL/drivers/usb/phy/phy-sprd-qogirn6pro.c
    if [ ! -f "$PH" ]; then
        cp "$TOP/overlay/phy-sprd-qogirn6pro.c" "$PH"
        grep -q "SPRD_QOGIRN6PRO_USB2_PHY" "$KERNEL/drivers/usb/phy/Kconfig" || cat >> "$KERNEL/drivers/usb/phy/Kconfig" << 'KC'

config SPRD_QOGIRN6PRO_USB2_PHY
	tristate "Spreadtrum Qogirn6pro USB2 PHY Driver"
	depends on (ARCH_SPRD || COMPILE_TEST) && EXTCON
	help
	  Enable this to support the SPRD QOGIRN6PRO USB2 PHY that is part of SOC.
KC
        grep -q "SPRD_QOGIRN6PRO_USB2_PHY" "$KERNEL/drivers/usb/phy/Makefile" ||             echo 'obj-$(CONFIG_SPRD_QOGIRN6PRO_USB2_PHY)	+= phy-sprd-qogirn6pro.o' >> "$KERNEL/drivers/usb/phy/Makefile"
    fi
    echo "== staging gcore GC7202 touchscreen driver (ZTE 7541N panel) =="
    python3 "$TOP/overlay-devices/yuanhang41/gcore-touch.py" "$KERNEL"
    echo "== staging ZTE vendor spi controller for the touch bus =="
    python3 "$TOP/overlay-devices/yuanhang41/spi-zte-stage.py" "$KERNEL"
    echo "== building kernel (jobs=$JOBS) =="
    python3 devices/yuanhang41/build-kernel.py \
        --kernel "$KERNEL" \
        --build  "$N/objects" \
        --base-config "$TOP/base/kernel.config" \
        --out     "$N/kernel-out" \
        --jobs "$JOBS"
    rel=$(cat "$N/kernel-out/kernel.release")
    case "$rel" in *-yuanhang41-*) ;; *) echo "wrong release: $rel"; exit 1 ;; esac
    echo "== kernel ok: $rel =="
    ;;

rootfs)
    cd "$REPO"
    echo "== staging root modules =="
    E5_UPSTREAM_OUT="$N/kernel-out" sh upstream/root-modules.sh
    IMG="$N/root.ext4"
    gzip -dc "$PKG/files/openwrt.ext4.gz" > "$IMG"
    REL=$(cat "$N/kernel-out/kernel.release")
    echo "== rootfs surgery for $REL =="
    CMDS="$N/fs-cmds1"; : > "$CMDS"
    # debugfs ls -p lines: /inode/mode/uid/gid/size/mtime/name (leading slash!)
    # The shipped image may carry a DIFFERENT release dir (yuanhang41s vs our
    # yuanhang41 build): drop every release directory before writing ours.
    DPOUT=$(debugfs -R "ls -p /lib/modules" "$IMG" 2>&1) || {
        echo "debugfs ls /lib/modules failed:"; echo "$DPOUT" | head -5; exit 1; }
    echo "$DPOUT" | while IFS='/' read -r _ _dmode _du _dg _dsz _dm reldir _r; do
        case "$reldir" in ''|'.'|'..'|'lost+found') continue ;; esac
        [[ "$reldir" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "SKIP-ODD:$reldir" >&2; continue; }
        FOUT=$(debugfs -R "ls -p /lib/modules/$reldir" "$IMG" 2>/dev/null) || continue
        echo "$FOUT" | while IFS='/' read -r _ _m _u _g _s _t f _x; do
            case "$f" in ''|'.'|'..') continue ;; esac
            [[ "$f" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "SKIP-ODD:$f" >&2; continue; }
            echo "rm /lib/modules/$reldir/$f" >> "$CMDS"
        done
        echo "rmdir /lib/modules/$reldir" >> "$CMDS"
    done
    echo "== $(grep -c '^rm' "$CMDS") module files to remove =="
    echo "rm /etc/e5/device-model" >> "$CMDS"
    printf '中兴远航41\n' > "$N/device-model"
    echo "write $N/device-model /etc/e5/device-model" >> "$CMDS"
    # Battery display needs no rootfs edits: once the charger probes and
    # charger-manager binds, it publishes the "battery"/"ac"/"usb" psy
    # aliases the stock readers expect.
    # Mount the orphaned charge-management card on the LuCI dashboard: the
    # stock home.js never wires mu300.charge, so thresholds/limit control
    # had no UI even with the ubus service healthy.
    echo "rm /www/luci-static/resources/view/mu300/home.js" >> "$CMDS"
    echo "write $TOP/overlay/home-charge-mount.js /www/luci-static/resources/view/mu300/home.js" >> "$CMDS"
    echo "sif /www/luci-static/resources/view/mu300/home.js uid 0" >> "$CMDS"
    echo "sif /www/luci-static/resources/view/mu300/home.js gid 0" >> "$CMDS"
    echo "sif /www/luci-static/resources/view/mu300/home.js mode 0100644" >> "$CMDS"
    # GC7202 touch firmware: the driver requests
    # gcore_firmware_<vendor>.bin from /lib/firmware at boot.
    echo "write $TOP/overlay/gcore_firmware_skyworth.bin /lib/firmware/gcore_firmware_skyworth.bin" >> "$CMDS"
    echo "sif /lib/firmware/gcore_firmware_skyworth.bin uid 0" >> "$CMDS"
    echo "sif /lib/firmware/gcore_firmware_skyworth.bin gid 0" >> "$CMDS"
    echo "sif /lib/firmware/gcore_firmware_skyworth.bin mode 0100644" >> "$CMDS"
    debugfs -w -f "$CMDS" "$IMG" > "$N/fs-log1" 2>&1
    ! grep -iE 'error|not found|cannot|failed' "$N/fs-log1" || { cat "$N/fs-log1"; exit 1; }

    T="$N/mods"; rm -rf "$T"; mkdir -p "$T"
    tar -xf "$N/kernel-out/root-modules.tar" -C "$T"
    CMDS2="$N/fs-cmds2"; : > "$CMDS2"
    (
        cd "$T"
        find "lib/modules/$REL" -type d | sort | while read -r d; do
            echo "mkdir /$d"; echo "sif /$d uid 0"; echo "sif /$d gid 0"; echo "sif /$d mode 040755"
        done
        find "lib/modules/$REL" -type f | sort | while read -r f; do
            echo "write $T/$f /$f"; echo "sif /$f uid 0"; echo "sif /$f gid 0"; echo "sif /$f mode 0100644"
        done
        find "lib/modules/$REL" -type l | sort | while read -r f; do
            echo "symlink /$f $(readlink "$f")"
            echo "sif /$f uid 0"; echo "sif /$f gid 0"
        done
    ) >> "$CMDS2"
    debugfs -w -f "$CMDS2" "$IMG" > "$N/fs-log2" 2>&1
    ! grep -iE 'error|not found|cannot|failed' "$N/fs-log2" || { cat "$N/fs-log2"; exit 1; }
    # debugfs rm only unlinks; removed module inodes stay unattached.
    # Repair once, then require a clean check.
    e2fsck -fy "$IMG" > "$N/fsck-repair.log" 2>&1
    e2fsck -fn "$IMG" > "$N/fsck.log" 2>&1 || { tail -20 "$N/fsck.log"; exit 1; }
    n=$(find "$T/lib/modules/$REL" -name '*.ko' | wc -l)
    gzip -9 -c "$IMG" > "$OUT/yuanhang41-openwrt.ext4.gz"
    echo "== rootfs ok: $n modules =="
    ;;

boot)
    echo "== busybox for the initramfs =="
    BB=$TOP/work/busybox/usr/bin/busybox
    mkdir -p "$(dirname "$BB")"
    curl -fsSL --retry 3 -o "$TOP/work/busybox/busybox.deb" \
        "http://ports.ubuntu.com/ubuntu-ports/pool/main/b/busybox/busybox-static_1.36.1-6ubuntu3.1_arm64.deb"
    (
        cd "$TOP/work/busybox"
        ar x busybox.deb
        tar --zstd -xf data.tar.zst -C . ./usr/bin/busybox
    )
    echo "== staging f2fs repair tools from the released boot image =="
    # the released rootfs has no fsck.f2fs; the tools live in the shipped
    # initramfs (same bytes as the release boot.json manifest)
    python3 -m pip install --quiet --break-system-packages lz4 2>/dev/null ||         python3 -m pip install --quiet --user lz4 || true
    FT="$N/f2fs-root"; rm -rf "$FT"; mkdir -p "$FT"
    python3 "$TOP/make-f2fs-root.py" "$PKG/files/boot.img" "$FT"
    cd "$REPO"
    python3 boot/prepare-f2fs-tools.py --root "$FT" --out "$TOP/out/boot/f2fs-tools"

    cd "$REPO"
    echo "== normalizing misc BCAB =="
    # The device's live BCAB may carry successful_boot=0 on the Android slot
    # after an unconfirmed trial boot; the builder refuses that state. Android
    # on the suffix slot does boot and run -- set its successful bit and fix
    # the CRC so the builder sees the truthful state.
    python3 - "$TOP/dumps/yuanhang41-stock-misc-head.bin" "$N/misc-head-norm.bin" << 'PY'
import struct, sys, zlib
raw = bytearray(open(sys.argv[1], 'rb').read()[:4096])
bc = bytearray(raw[0x800:0x820])
assert bc[4:8] == b'BCAB', 'no BCAB magic'
suffix = bytes(bc[:2])
idx = 12 if suffix == b'_a' else 14
assert struct.unpack('<I', bc[28:32])[0] == zlib.crc32(bytes(bc[:28])), 'BCAB CRC mismatch'
bc[idx] |= 0x80  # successful_boot: Android runs from this slot
bc[28:32] = struct.pack('<I', zlib.crc32(bytes(bc[:28])))
raw[0x800:0x820] = bc
open(sys.argv[2], 'wb').write(raw)
print('normalized slot %s info byte: %#04x' % (suffix.decode(), bc[idx]))
PY

    echo "== building boot image =="
    python3 boot/build-boot-image.py \
        --f2fs-tools "$TOP/out/boot/f2fs-tools" \
        --stock-boot "$TOP/dumps/yuanhang41-stock-boot_b.img" \
        --misc-head  "$N/misc-head-norm.bin" \
        --android-slot b \
        --kernel "$N/kernel-out/Image.lk" \
        --modules "$N/kernel-out/modules" \
        --module-order devices/yuanhang41/module-order.txt \
        --busybox "$BB" \
        --out "$OUT/yuanhang41-boot.img"
    ls -la "$OUT"/yuanhang41-boot.*
    ;;

repack)
    echo "== repack =="
    OUTDIR=$OUT python3 "$TOP/repack.py"
    for z in "$OUT"/*.zip; do (cd "$OUT" && sha256sum "$(basename "$z")" > "$(basename "$z").sha256"); done
    ls -la "$OUT"
    ;;

esac
