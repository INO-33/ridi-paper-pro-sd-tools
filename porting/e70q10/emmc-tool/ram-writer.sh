#!/bin/sh
set -eu
BB=${UPDATER_BB:-/bin/busybox}
STREAM=${UPDATER_STREAM:-/bin/stream-write}
ui(){ [ ! -x /bin/ui-status ] || /bin/ui-status "$@"; }
READER=${UPDATER_READER:-/bin/backup-copy}
fail() { echo "STOP: $*" >&2;exit 1; }
[ $# -ge 2 ] || fail 'usage: updater check|apply PACKAGE [TOKEN]; updater rehearse DISK PACKAGE'
MODE=$1;PKG=$2;DEV=/dev/mmcblk0
if [ "$MODE" = rehearse ]; then
    DEV=$2;PKG=$3
    [ -f "$DEV" ] && [ ! -b "$DEV" ] || fail 'rehearsal needs regular file'
    BYTES=$($BB stat -c %s "$DEV");SECTORS=$((BYTES/512))
    [ "$((BYTES%512))" = 0 ] || fail 'invalid disk size'
else
    [ "$BB" = /bin/busybox ] && [ "$STREAM" = /bin/stream-write ] && [ "$READER" = /bin/backup-copy ] || fail 'production tools fixed'
    [ -b "$DEV" ] || fail 'internal eMMC absent'
    SECTORS=$($BB cat /sys/block/mmcblk0/size)
    CID=$($BB cat /sys/block/mmcblk0/device/cid)
    [ "${#CID}" = 32 ] || fail 'invalid eMMC identity'
    case "$CID" in *[!0-9a-fA-F]*) fail 'invalid eMMC CID';; esac
    $BB grep -q mmcblk0 /proc/mounts && fail 'eMMC mounted'
    $BB grep -q mmcblk0 /proc/swaps && fail 'eMMC used as swap'
    for x in /sys/block/dm-* /sys/block/mmcblk0/holders/* /sys/block/mmcblk0/mmcblk0p*/holders/*; do
        [ ! -e "$x" ] || fail 'active block holder or mapper'
    done
    case "$MODE" in check) ;; apply)
        [ "${3:-}" = UPDATE-SELECTED-PAPER-PRO ] || fail 'update token missing'
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
 "$READER" --hash "$DEV" "$(( $1*$2 ))" "$(( $1*$3 ))" || fail 'device read/hash error'
}
# A native model/partition parser emits only fixed keys and numeric values into RAM.
LAYOUT=${UPDATER_LAYOUT:-/bin/device-layout}
[ "$MODE" = rehearse ] || [ "$LAYOUT" = /bin/device-layout ] || fail 'production layout tool fixed'
"$LAYOUT" check "$DEV" "$SECTORS" "$WORK" >"$WORK/layout.env" || fail 'unsupported model or layout'
. "$WORK/layout.env"
PREFIX_BEFORE=$(rangehash 512 1 104447)
TABLE_LIST="0 $(printf '%s' "$TABLE_SECTORS" | $BB tr ',' ' ')"
: >"$WORK/tables.before"
for SECTOR in $TABLE_LIST; do printf '%s %s\n' "$SECTOR" "$(rangehash 512 "$SECTOR" 1)" >>"$WORK/tables.before";done
check_layout() {
 "$LAYOUT" check "$DEV" "$SECTORS" "$WORK" >/dev/null || fail 'partition layout changed'
 [ "$(rangehash 512 1 104447)" = "$PREFIX_BEFORE" ] || fail 'this device protected firmware changed'
 while read -r SECTOR EXPECTED; do
  [ "$(rangehash 512 "$SECTOR" 1)" = "$EXPECTED" ] || fail 'partition table bytes changed'
 done <"$WORK/tables.before"
}
# Strict fixed ranges, unique canonical order, and a nonempty available selection.
ROWS=$($BB wc -l < manifest.tsv)
[ "$ROWS" -ge 1 ] && [ "$ROWS" -le 3 ] || fail 'one to three image rows required'
LAST=0;SELECTED=
while read -r FILE START COUNT RAW COMP; do
    case "$FILE:$START:$COUNT" in
        system.raw.gz:172032:2097152) ROLE=system;RANK=1;;
        vendor.raw.gz:14733312:524288) ROLE=vendor;RANK=2;;
        boot.raw.gz:104448:65536) ROLE=boot;RANK=3;;
        *) fail 'write outside boot/system/vendor rejected';;
    esac
    [ "$RANK" -gt "$LAST" ] || fail 'duplicate/unordered manifest';LAST=$RANK
    is_selected "$ROLE" || continue
    SELECTED=${SELECTED:+$SELECTED,}$ROLE
    [ -f "$FILE" ] || fail "selected payload absent: $FILE"
done < manifest.tsv
[ "$SELECTED" = "$CONF_TARGETS" ] || fail "selected partition missing from manifest"
# Preserve current mutable misc and cache/data by never writing their ranges.
# First sector of vendor must remain zero for this U-Boot's legacy BCB check.
echo "UPDATE CHECK PASSED: layout and selection ($CONF_TARGETS); image validation performed on PC."
[ "$MODE" != check ] || exit 0
while read -r FILE START COUNT RAW COMP; do
    ROLE=${FILE%.raw.gz}
    is_selected "$ROLE" || continue
    [ "$ROLE" != vendor ] || START=$VENDOR_START
    ui write "$ROLE" 0 "$((COUNT*512))"
    WRITE_STARTED=$($BB date +%s)
    echo "WRITING $FILE sector=$START sectors=$COUNT"
    $BB gzip -dc "$FILE" >"$FIFO" & PID=$!
    if ! "$STREAM" "$DEV" "$START" "$COUNT" <"$FIFO"; then
        kill "$PID" 2>/dev/null || :
        wait "$PID" 2>/dev/null || :
        fail 'bounded image write failed'
    fi
    wait "$PID" || fail 'gzip failed while writing'
    WRITE_DONE=$($BB date +%s)
    echo "WRITE TIME $FILE seconds=$((WRITE_DONE-WRITE_STARTED))"
    ui verify "$ROLE" 0 "$((COUNT*512))"
    echo "READBACK VERIFY $FILE"
    [ "$(rangehash 1048576 "$((START/2048))" "$((COUNT/2048))")" = "$RAW" ] || fail "readback mismatch: $FILE"
    READBACK_DONE=$($BB date +%s)
    echo "READBACK PASSED $FILE seconds=$((READBACK_DONE-WRITE_DONE))"
done < manifest.tsv
ui checking "" 0 0 "Final partition and firmware checks"
check_layout
$BB sync
echo "UPDATE VERIFIED. Selected=$CONF_TARGETS; all other partitions retained."
