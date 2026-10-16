#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
PORT="$ROOT/porting/e70q10"
SRC="$PORT/diagnostic-initramfs"
OUT="${DIAGNOSTIC_OUT:-$PORT/diagnostic-build}"
# Use the device-extracted static BusyBox.  Besides working on 4.9, it remains
# compatible with the stock 3.0.35 kernel and gives us one known-good ramdisk
# userspace for control tests.
BUSYBOX="$ROOT/ridi-paper-pro-stock-4.4.2-20260721/files/system/bin/busybox"
MKBOOTIMG="$ROOT/android-sources/nxp-o8.0.0_1.0.0-ga/system/core/mkbootimg/mkbootimg"
KERNEL="${DIAGNOSTIC_KERNEL:-$PORT/artifacts/zImage+imx6sl-e70q10.dtb}"
IMAGE_NAME="${DIAGNOSTIC_IMAGE_NAME:-e70q10-diagnostic-boot.img}"
WAVEFORM="$PORT/stock-blobs/critical/waveform.bin"
EPDC_TEST="$SRC/bin/epdc-power-test"
EPDC_PATTERN_TEST="$SRC/bin/epdc-pattern-test"
TOUCH_TEST="$SRC/bin/touch-event-test"
TOUCH_DIAG="$SRC/bin/touch-diag"
DIAGNOSTIC_EPDC_DIAG_TOOL="${DIAGNOSTIC_EPDC_DIAG_TOOL:-}"

[ -f "$BUSYBOX" ] || { echo "missing stock-compatible ARM BusyBox: $BUSYBOX" >&2; exit 1; }
[ -f "$MKBOOTIMG" ] || { echo "missing mkbootimg: $MKBOOTIMG" >&2; exit 1; }
[ -f "$KERNEL" ] || { echo "missing appended-DTB kernel: $KERNEL" >&2; exit 1; }
[ -f "$WAVEFORM" ] || { echo "missing stock EPDC waveform: $WAVEFORM" >&2; exit 1; }
[ -f "$EPDC_TEST" ] || { echo "missing EPDC test tool: $EPDC_TEST" >&2; exit 1; }
[ -f "$EPDC_PATTERN_TEST" ] || { echo "missing EPDC pattern tool: $EPDC_PATTERN_TEST" >&2; exit 1; }
[ -f "$TOUCH_TEST" ] || { echo "missing touch test tool: $TOUCH_TEST" >&2; exit 1; }
[ -f "$TOUCH_DIAG" ] || { echo "missing touch diagnostic tool: $TOUCH_DIAG" >&2; exit 1; }
if [ -n "$DIAGNOSTIC_EPDC_DIAG_TOOL" ]; then
    [ -f "$DIAGNOSTIC_EPDC_DIAG_TOOL" ] || {
        echo "missing EPDC diagnostic tool: $DIAGNOSTIC_EPDC_DIAG_TOOL" >&2
        exit 1
    }
fi

mkdir -p "$OUT"
BUILD_TMP=$(mktemp -d "$OUT/.rootfs.XXXXXX")
trap 'rm -rf "$BUILD_TMP"' EXIT HUP INT TERM
ROOTFS="$BUILD_TMP/rootfs"
mkdir -p "$ROOTFS/bin" "$ROOTFS/sbin" "$ROOTFS/etc" "$ROOTFS/usr/bin" \
    "$ROOTFS/usr/sbin" "$ROOTFS/dev" "$ROOTFS/proc" "$ROOTFS/sys" "$ROOTFS/run" \
    "$ROOTFS/tmp" "$ROOTFS/root" "$ROOTFS/mnt/sd" \
    "$ROOTFS/lib/firmware/imx/epdc"

cp -a "$BUSYBOX" "$ROOTFS/bin/busybox"
cp -a "$SRC/init" "$ROOTFS/init"
cp -a "$SRC/bin/save-logs" "$ROOTFS/bin/save-logs"
cp -a "$EPDC_TEST" "$ROOTFS/bin/epdc-power-test"
cp -a "$EPDC_PATTERN_TEST" "$ROOTFS/bin/epdc-pattern-test"
cp -a "$TOUCH_TEST" "$ROOTFS/bin/touch-event-test"
cp -a "$TOUCH_DIAG" "$ROOTFS/bin/touch-diag"
if [ -n "$DIAGNOSTIC_EPDC_DIAG_TOOL" ]; then
    cp -a "$DIAGNOSTIC_EPDC_DIAG_TOOL" "$ROOTFS/bin/epdc_diag"
fi
cp -a "$SRC/etc/motd" "$ROOTFS/etc/motd"
cp -a "$WAVEFORM" "$ROOTFS/lib/firmware/imx/epdc/epdc_ED078KH1.fw"
chmod 0755 "$ROOTFS/init" "$ROOTFS/bin/busybox" "$ROOTFS/bin/save-logs" \
    "$ROOTFS/bin/epdc-power-test" "$ROOTFS/bin/epdc-pattern-test" \
    "$ROOTFS/bin/touch-event-test"
chmod 0755 "$ROOTFS/bin/touch-diag"
if [ -n "$DIAGNOSTIC_EPDC_DIAG_TOOL" ]; then
    chmod 0755 "$ROOTFS/bin/epdc_diag"
fi

for applet in sh ash cat cp date dd dmesg echo find grep head hexdump hostname ln \
    ls mkdir mdev mount mountpoint poweroff reboot rm cttyhack setsid sha256sum \
    sleep stty sync tail uname umount wc; do
    ln -snf busybox "$ROOTFS/bin/$applet"
done

(
    cd "$ROOTFS"
    find . -print0 | sort -z | cpio --null -o --format=newc --owner=0:0
) | gzip -9n >"$OUT/diagnostic-initramfs.cpio.gz"

CMDLINE='console=ttymxc0,115200 earlyprintk=serial,ttymxc0,115200 init=/init loglevel=8 ignore_loglevel printk.time=1 panic=10 androidboot.hardware=E70Q10 video=mxcepdcfb:ED078KH1,bpp=16'
CMDLINE_EXTRA="${DIAGNOSTIC_CMDLINE_EXTRA:-}"
CMDLINE="$CMDLINE $CMDLINE_EXTRA"

# The 22 MiB uncompressed 4.9 Image forces the roughly 10 MiB zImage to
# relocate above 0x81500000 while decompressing.  The stock 0x81800000
# ramdisk address is inside that scratch range and gets overwritten.

python3 "$MKBOOTIMG" \
    --kernel "$KERNEL" \
    --ramdisk "$OUT/diagnostic-initramfs.cpio.gz" \
    --cmdline "$CMDLINE" \
    --base 0x80800000 \
    --kernel_offset 0x00008000 \
    --ramdisk_offset 0x03800000 \
    --second_offset 0x00f00000 \
    --tags_offset 0x00000100 \
    --pagesize 2048 \
    --board E70Q10-DIAG \
    --os_version 8.0.0 \
    --os_patch_level 2017-12-05 \
    --output "$OUT/$IMAGE_NAME"

sha256sum "$OUT/diagnostic-initramfs.cpio.gz" \
    "$OUT/$IMAGE_NAME" >"$OUT/SHA256SUMS"

echo "Built: $OUT/$IMAGE_NAME"
wc -c "$OUT/diagnostic-initramfs.cpio.gz" "$OUT/$IMAGE_NAME"
