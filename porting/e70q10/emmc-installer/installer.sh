#!/bin/sh
set -eu
BB=${INSTALLER_BB:-/bin/busybox}
fail() { echo "STOP: $*" >&2; exit 1; }
[ $# -ge 2 ] || fail 'usage: installer check|install|restore PACKAGE [CONFIRM_TOKEN] ; rehearse DISK PACKAGE'
MODE=$1
PKG=$2
DEV=/dev/mmcblk0
TEST=0
if [ "$MODE" = rehearse ] || [ "$MODE" = rehearse-restore ]; then
    DEV=$2; PKG=$3; TEST=1
    [ "$MODE" != rehearse-restore ] || MODE=restore
    [ -f "$DEV" ] && [ ! -b "$DEV" ] || fail 'rehearsal requires a regular file'
    [ "$($BB stat -c %s "$DEV")" = 7818182656 ] || fail 'wrong rehearsal file size'
else
    [ "$BB" = /bin/busybox ] || fail 'production BusyBox path is fixed'
    [ -b "$DEV" ] || fail 'internal eMMC absent'
    [ "$($BB cat /sys/block/mmcblk0/size)" = 15269888 ] || fail 'wrong capacity'
    [ "$($BB cat /sys/block/mmcblk0/device/cid)" = 15010038474d45345201bbd3fe618400 ] || fail 'wrong CID'
    $BB grep -q 'mmcblk0' /proc/mounts && fail 'internal storage mounted'
    $BB grep -q 'mmcblk0' /proc/swaps && fail 'internal storage in swap'
    # Device mapper could conceal an eMMC backing device. The RAM environment needs none.
    for x in /sys/block/dm-* /sys/block/mmcblk0/holders/* /sys/block/mmcblk0/mmcblk0p*/holders/*; do
        [ ! -e "$x" ] || fail 'device mapper or block holder active'
    done
    case "$MODE" in check) ;; install|restore)
        [ "${3:-}" = "WRITE-PP1A1GK166561-15010038474d45345201bbd3fe618400" ] || fail 'confirmation token missing'
        $BB grep -q ' /mnt/sd .*ro[, ]' /proc/mounts || fail 'package SD must be mounted read-only'
        ;; *) fail 'unknown mode';; esac
fi
cd "$PKG"
PKG=$($BB pwd)
# The manifest digest is pinned inside the RAM image, never sourced from SD.
EXPECTED_MANIFEST=@MANIFEST@
[ "$($BB sha256sum manifest.tsv | $BB cut -d ' ' -f 1)" = "$EXPECTED_MANIFEST" ] || fail 'manifest changed'
WORK=${INSTALLER_WORK:-/run/emmc-installer}
$BB mkdir -p "$WORK"
$BB mkdir "$WORK/lock" || fail 'another installer is running'
FIFO=$WORK/stream
$BB rm -f "$FIFO"
trap '$BB rm -f "$FIFO"; $BB rmdir "$WORK/lock"' EXIT HUP INT TERM
hash_range() {
    # All large ranges are 64-KiB aligned. Seek/count stay below 2^31 on ARM32.
    $BB dd if="$DEV" bs=65536 skip="$1" count="$2" 2>/dev/null >"$FIFO" & DP=$!
    H=$($BB sha256sum "$FIFO" | $BB cut -d ' ' -f 1)
    wait "$DP" || fail 'device read failed'
    echo "$H"
}
$BB mkfifo "$FIFO"
$BB dd if="$DEV" bs=512 skip=1 count=104447 2>/dev/null >"$FIFO" & DP=$!
PREFIX=$($BB sha256sum "$FIFO" | $BB cut -d ' ' -f 1)
wait "$DP" || fail 'protected area read failed'
[ "$PREFIX" = '@PREFIX@' ] || fail 'protected area differs from September backup'
$BB dd if="$DEV" of="$WORK/mbr.before" bs=512 count=1 2>/dev/null
MBR=$($BB sha256sum "$WORK/mbr.before" | $BB cut -d ' ' -f 1)
case "$MBR" in @OLDMBR@|@NEWMBR@) ;; *) fail 'unexpected MBR';; esac
[ "$MODE" != restore ] || {
    [ -d backup ] || fail 'put the complete September backup in package/backup'
    [ "$($BB sha256sum backup.sha256 | $BB cut -d ' ' -f 1)" = "@BACKUP@" ] || fail 'backup manifest changed'
    [ "$($BB sha256sum original-mbr.sector0.bin | $BB cut -d ' ' -f 1)" = "@OLDMBR@" ] || fail 'original MBR changed'
    (cd backup; $BB sha256sum -c "$PKG/backup.sha256") || fail 'backup validation failed'
    # Restore the user area after 51 MiB from 30 backup pieces; original MBR last.
    $BB dd if=backup/emmc.part00 of="$DEV" bs=65536 skip=816 seek=816 conv=notrunc 2>/dev/null
    n=1
    while [ "$n" -lt 30 ]; do
        f=$($BB printf 'backup/emmc.part%02d' "$n")
        $BB dd if="$f" of="$DEV" bs=65536 seek=$((n * 4096)) conv=notrunc 2>/dev/null
        n=$((n + 1))
    done
    $BB sync
    [ "$(hash_range 816 118480)" = '@RESTORE@' ] || fail 'restored range readback failed; MBR not committed'
    $BB dd if=original-mbr.sector0.bin of="$DEV" bs=512 count=1 conv=notrunc 2>/dev/null
    $BB sync
    [ "$($BB sha256sum "$DEV" | $BB cut -d ' ' -f 1)" = '7783c8529e3b89df29a076f2fb8ac7e4216e7e8bca864db50ae872be1e3baf6f' ] || fail 'full restore hash mismatch'
    echo 'RESTORE VERIFIED. Reboot manually.'
    exit 0
}
# Validate compressed hashes, decompression exit status, expanded byte sizes and raw hashes
# for every payload before the first write. Read-only SD keeps inputs stable afterwards.
while read -r KIND FILE START SECTORS RAW COMP; do
    [ "$($BB sha256sum "$FILE" | $BB cut -d ' ' -f 1)" = "$COMP" ] || fail "compressed hash: $FILE"
    $BB gzip -dc "$FILE" >"$FIFO" & GP=$!
    GOT=$($BB sha256sum "$FIFO" | $BB cut -d ' ' -f 1)
    wait "$GP" || fail "gzip error: $FILE"
    [ "$GOT" = "$RAW" ] || fail "raw hash: $FILE"
    $BB gzip -dc "$FILE" >"$FIFO" & GP=$!
    SIZE=$(${INSTALLER_COUNTER:-/bin/countbytes} <"$FIFO")
    wait "$GP" || fail "gzip size error: $FILE"
    [ "$SIZE" -eq "$((SECTORS * 512))" ] || fail "expanded size: $FILE"
done < manifest.tsv
echo 'CHECK PASSED: identity, protection, table and all payloads.'
[ "$MODE" != check ] || exit 0
while read -r KIND FILE START SECTORS RAW COMP; do
    echo "Writing $FILE at sector $START"
    $BB gzip -dc "$FILE" >"$FIFO" & GP=$!
    if [ "$KIND" = image ]; then
        $BB dd if="$FIFO" of="$DEV" bs=65536 seek=$((START / 128)) conv=notrunc 2>/dev/null || fail 'write error'
    else
        $BB dd if="$FIFO" of="$DEV" bs=512 seek="$START" conv=notrunc 2>/dev/null || fail 'table write error'
    fi
    wait "$GP" || fail 'gzip failed while writing'
    $BB sync
    if [ "$KIND" = image ]; then
        GOT=$(hash_range "$((START / 128))" "$((SECTORS / 128))")
    else
        $BB dd if="$DEV" bs=512 skip="$START" count="$SECTORS" 2>/dev/null >"$FIFO" & DP=$!
        GOT=$($BB sha256sum "$FIFO" | $BB cut -d ' ' -f 1)
        wait "$DP" || fail 'table read failed'
    fi
    [ "$GOT" = "$RAW" ] || fail "readback mismatch: $FILE"
done < manifest.tsv
$BB dd if="$DEV" bs=512 skip=1 count=104447 2>/dev/null >"$FIFO" & DP=$!
AFTER=$($BB sha256sum "$FIFO" | $BB cut -d ' ' -f 1)
wait "$DP" || fail 'final protected read failed'
[ "$AFTER" = "$PREFIX" ] || fail 'protected area changed'
$BB sync
echo 'INSTALL VERIFIED. U-Boot/recovery/waveform preserved. Reboot manually; kernel will reread partitions.'
