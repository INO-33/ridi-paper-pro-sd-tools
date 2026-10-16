#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
PORT="$ROOT/porting/e70q10"
SRC="$PORT/diagnostic-initramfs"
OUT="$PORT/control-build"
BUSYBOX="$ROOT/ridi-paper-pro-stock-4.4.2-20260721/files/system/bin/busybox"
KERNEL="$ROOT/ridi-paper-pro-stock-4.4.2-20260721/unpacked/boot/kernel.bin"
MKBOOTIMG="$ROOT/android-sources/nxp-o8.0.0_1.0.0-ga/system/core/mkbootimg/mkbootimg"

[ -f "$BUSYBOX" ] || { echo "missing stock static BusyBox: $BUSYBOX" >&2; exit 1; }
[ -f "$KERNEL" ] || { echo "missing stock kernel: $KERNEL" >&2; exit 1; }
[ -f "$MKBOOTIMG" ] || { echo "missing mkbootimg: $MKBOOTIMG" >&2; exit 1; }

mkdir -p "$OUT"
BUILD_TMP=$(mktemp -d "$OUT/.rootfs.XXXXXX")
trap 'rm -rf "$BUILD_TMP"' EXIT HUP INT TERM
ROOTFS="$BUILD_TMP/rootfs"
mkdir -p "$ROOTFS/bin" "$ROOTFS/sbin" "$ROOTFS/etc" "$ROOTFS/usr/bin" \
    "$ROOTFS/usr/sbin" "$ROOTFS/dev" "$ROOTFS/proc" "$ROOTFS/sys" "$ROOTFS/run" \
    "$ROOTFS/tmp" "$ROOTFS/root" "$ROOTFS/mnt/sd"

cp -a "$BUSYBOX" "$ROOTFS/bin/busybox"
cp -a "$SRC/init" "$ROOTFS/init"
cp -a "$SRC/bin/save-logs" "$ROOTFS/bin/save-logs"
cp -a "$SRC/bin/touch-diag" "$ROOTFS/bin/touch-diag"
cp -a "$SRC/etc/motd" "$ROOTFS/etc/motd"
chmod 0755 "$ROOTFS/init" "$ROOTFS/bin/busybox" "$ROOTFS/bin/save-logs" \
    "$ROOTFS/bin/touch-diag"

for applet in sh ash cat cp date dmesg echo find hostname ln ls mkdir mdev mount \
    mountpoint poweroff reboot rm sha256sum sleep sync uname umount grep sed; do
    ln -snf busybox "$ROOTFS/bin/$applet"
done

(
    cd "$ROOTFS"
    find . -print0 | sort -z | cpio --null -o --format=newc --owner=0:0
) | gzip -9n >"$OUT/stock-compatible-diagnostic-initramfs.cpio.gz"

# Keep the stock ATAG-era command line shape. ntx_prebooti() appends the
# board-specific hwcfg, waveform and boot-mode arguments before kernel entry.
CMDLINE="console=ttymxc0,115200 init=/init androidboot.console=ttymxc0 video=mxcepdcfb:E060SCM,bpp=16 video=mxc_elcdif_fb:off no_console_suspend loglevel=8 ignore_loglevel panic=10 ${STOCK_CMDLINE_EXTRA:-}"

python3 "$MKBOOTIMG" \
    --kernel "$KERNEL" \
    --ramdisk "$OUT/stock-compatible-diagnostic-initramfs.cpio.gz" \
    --cmdline "$CMDLINE" \
    --base 0x80800000 \
    --kernel_offset 0x00008000 \
    --ramdisk_offset 0x01000000 \
    --second_offset 0x00f00000 \
    --tags_offset 0x00000100 \
    --pagesize 2048 \
    --board E70Q10-CTRL \
    --output "$OUT/e70q10-stock-kernel-control-boot.img"

sha256sum "$OUT/stock-compatible-diagnostic-initramfs.cpio.gz" \
    "$OUT/e70q10-stock-kernel-control-boot.img" >"$OUT/SHA256SUMS"

echo "Built: $OUT/e70q10-stock-kernel-control-boot.img"
wc -c "$OUT/stock-compatible-diagnostic-initramfs.cpio.gz" \
    "$OUT/e70q10-stock-kernel-control-boot.img"
