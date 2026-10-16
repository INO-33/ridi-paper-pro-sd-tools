#!/bin/sh
set -eu
BB=${UPDATER_BB:-/bin/busybox}
COUNTER=${UPDATER_COUNTER:-/bin/countbytes}
fail() { echo "STOP: $*" >&2;exit 1; }
[ $# -ge 2 ] || fail 'usage: updater check|apply PACKAGE [TOKEN]; updater rehearse DISK PACKAGE'
MODE=$1;PKG=$2;DEV=/dev/mmcblk0
if [ "$MODE" = rehearse ]; then
    DEV=$2;PKG=$3
    [ -f "$DEV" ] && [ ! -b "$DEV" ] || fail 'rehearsal needs regular file'
    [ "$($BB stat -c %s "$DEV")" = 7818182656 ] || fail 'wrong capacity'
else
    [ "$BB" = /bin/busybox ] && [ "$COUNTER" = /bin/countbytes ] || fail 'production tools fixed'
    [ -b "$DEV" ] || fail 'internal eMMC absent'
    [ "$($BB cat /sys/block/mmcblk0/size)" = 15269888 ] || fail 'wrong capacity'
    [ "$($BB cat /sys/block/mmcblk0/device/cid)" = 15010038474d45345201bbd3fe618400 ] || fail 'wrong CID'
    $BB grep -q mmcblk0 /proc/mounts && fail 'eMMC mounted'
    $BB grep -q mmcblk0 /proc/swaps && fail 'eMMC used as swap'
    for x in /sys/block/dm-* /sys/block/mmcblk0/holders/* /sys/block/mmcblk0/mmcblk0p*/holders/*; do
        [ ! -e "$x" ] || fail 'active block holder or mapper'
    done
    case "$MODE" in check) ;; apply)
        [ "${3:-}" = UPDATE-SELECTED-PP1A1GK166561 ] || fail 'update token missing'
        $BB grep -q ' /mnt/sd .*ro[, ]' /proc/mounts || fail 'package SD must be read-only'
        ;; *) fail 'unknown mode';; esac
fi
@CONFIG_FUNCTIONS@
cd "$PKG"
read_config . || fail "SD config rejected"
[ "$($BB sha256sum manifest.tsv | $BB cut -d ' ' -f 1)" = '@MANIFEST@' ] || fail 'manifest differs; use matching RAM image'
WORK=${UPDATER_WORK:-/run/emmc-updater}
$BB mkdir -p "$WORK"
$BB mkdir "$WORK/lock" || fail 'updater already running'
FIFO=$WORK/stream
trap '$BB rm -f "$FIFO"; $BB rmdir "$WORK/lock"' EXIT HUP INT TERM
$BB rm -f "$FIFO";$BB mkfifo "$FIFO"
rangehash() {
    $BB dd if="$DEV" bs="$1" skip="$2" count="$3" 2>/dev/null >"$FIFO" & PID=$!
    H=$($BB sha256sum "$FIFO" | $BB cut -d ' ' -f 1)
    wait "$PID" || fail 'device read error'
    echo "$H"
}
check_layout() {
@TABLE_CHECKS@
    [ "$(rangehash 512 1 104447)" = 1348b6b5c92b9959ac82707ffb7695f7cda45db3f8af445155928713d6d7b8c8 ] || fail 'protected prefix differs'
}
check_layout
# Strict fixed ranges, unique canonical order, and a nonempty available selection.
ROWS=$($BB wc -l < manifest.tsv)
[ "$ROWS" -ge 1 ] && [ "$ROWS" -le 3 ] || fail 'one to three image rows required'
LAST=0;SELECTED=
while read -r FILE START SECTORS RAW COMP; do
    case "$FILE:$START:$SECTORS" in
        system.raw.gz:172032:2097152) ROLE=system;RANK=1;;
        vendor.raw.gz:14733312:524288) ROLE=vendor;RANK=2;;
        boot.raw.gz:104448:65536) ROLE=boot;RANK=3;;
        *) fail 'write outside boot/system/vendor rejected';;
    esac
    [ "$RANK" -gt "$LAST" ] || fail 'duplicate/unordered manifest';LAST=$RANK
    is_selected "$ROLE" || continue
    SELECTED=${SELECTED:+$SELECTED,}$ROLE
    echo "VERIFYING $FILE"
    [ "$($BB sha256sum "$FILE" | $BB cut -d ' ' -f 1)" = "$COMP" ] || fail "compressed hash: $FILE"
    $BB gzip -dc "$FILE" >"$FIFO" & PID=$!
    H=$($BB sha256sum "$FIFO" | $BB cut -d ' ' -f 1)
    wait "$PID" || fail "gzip failure: $FILE"
    [ "$H" = "$RAW" ] || fail "raw hash: $FILE"
    $BB gzip -dc "$FILE" >"$FIFO" & PID=$!
    SIZE=$($COUNTER <"$FIFO")
    wait "$PID" || fail "gzip size failure: $FILE"
    [ "$SIZE" -eq "$((SECTORS*512))" ] || fail "expanded size: $FILE"
done < manifest.tsv
[ "$SELECTED" = "$CONF_TARGETS" ] || fail "selected partition missing from manifest"
# Preserve current mutable misc and cache/data by never writing their ranges.
# First sector of vendor must remain zero for this U-Boot's legacy BCB check.
echo "UPDATE CHECK PASSED: current layout and selected payloads ($CONF_TARGETS)."
[ "$MODE" != check ] || exit 0
while read -r FILE START SECTORS RAW COMP; do
    ROLE=${FILE%.raw.gz}
    is_selected "$ROLE" || continue
    echo "WRITING $FILE sector=$START sectors=$SECTORS"
    $BB gzip -dc "$FILE" >"$FIFO" & PID=$!
    $BB dd if="$FIFO" of="$DEV" bs=65536 seek=$((START/128)) conv=notrunc 2>/dev/null || fail 'write failed'
    wait "$PID" || fail 'gzip failed while writing'
    $BB sync
    [ "$(rangehash 65536 "$((START/128))" "$((SECTORS/128))")" = "$RAW" ] || fail "readback mismatch: $FILE"
    echo "READBACK PASSED $FILE"
done < manifest.tsv
check_layout
$BB sync
echo "UPDATE VERIFIED. Selected=$CONF_TARGETS; all other partitions retained."
