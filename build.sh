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
    # tests are pure-python checks of the patch stack against the kernel tree
    if [ "${RUN_TESTS:-1}" = 1 ]; then
        echo "== kernel patch-stack sanity (report only) =="
        python3 devices/common/test_power_probe.py --kernel "$KERNEL" || true
    fi
    echo "== building kernel (jobs=$JOBS) =="
    python3 devices/yuanhang41s/build-kernel.py \
        --kernel "$KERNEL" \
        --build  "$N/objects" \
        --base-config "$TOP/base/kernel.config" \
        --out     "$N/kernel-out" \
        --jobs "$JOBS"
    rel=$(cat "$N/kernel-out/kernel.release")
    case "$rel" in *-yuanhang41s-*) ;; *) echo "wrong release: $rel"; exit 1 ;; esac
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
    debugfs -R "ls -p /lib/modules/$REL" "$IMG" 2>/dev/null | while IFS='/' read -r _1 _2 _3 _4 _5 _6 name _7; do
        case "$name" in ''|'.'|'..') continue ;; esac
        echo "rm /lib/modules/$REL/$name" >> "$CMDS"
    done
    echo "rmdir /lib/modules/$REL" >> "$CMDS"
    echo "rm /etc/e5/device-model" >> "$CMDS"
    printf '中兴远航41\n' > "$N/device-model"
    echo "write $N/device-model /etc/e5/device-model" >> "$CMDS"
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
    "$BB" | head -1

    cd "$REPO"
    echo "== building boot image =="
    python3 boot/build-boot-image.py \
        --stock-boot "$TOP/dumps/yuanhang41-stock-boot_b.img" \
        --misc-head  "$TOP/dumps/yuanhang41-stock-misc-head.bin" \
        --android-slot b \
        --kernel "$N/kernel-out/Image.lk" \
        --modules "$N/kernel-out/modules" \
        --module-order devices/yuanhang41s/module-order.txt \
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
