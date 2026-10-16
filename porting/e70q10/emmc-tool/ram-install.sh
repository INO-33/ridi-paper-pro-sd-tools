#!/bin/sh
set -eu
BB=/bin/busybox
PKG=$1;JOB=$2
DEV=/dev/mmcblk0
[ -b "$DEV" ] || { echo 'STOP: internal eMMC absent';exit 1; }
$BB grep -q mmcblk0 /proc/mounts && { echo 'STOP: eMMC mounted';exit 1; }
$BB grep -q mmcblk0 /proc/swaps && { echo 'STOP: eMMC used as swap';exit 1; }
for X in /sys/block/dm-* /sys/block/mmcblk0/holders/* /sys/block/mmcblk0/mmcblk0p*/holders/*; do [ ! -e "$X" ] || { echo 'STOP: active block holder';exit 1; };done
fail() { echo "STOP: $*" >&2;exit 1; }
BACKUP_POLICY=${3:-required}
case "$BACKUP_POLICY" in required|none) ;; *) fail 'invalid backup policy';; esac
SECTORS=$($BB cat /sys/block/mmcblk0/size)
hashrange() {
 /bin/backup-copy --hash "$DEV" "$(( $1*$2 ))" "$(( $1*$3 ))" || fail 'eMMC read/hash failure'
}
if [ "$BACKUP_POLICY" = required ]; then
 /bin/backup-current "$PKG" "$JOB" || fail 'backup failed; install stopped'
 WORK=/run/backup-operation
 . "$WORK/layout.env"
 . "$WORK/backup.env"
 [ "$CURRENT_KIND" = stock ] || fail 'real install requires stock layout'
 PREFIX_BEFORE=$($BB cat "$WORK/protected.sha256")
 $BB mkdir "$WORK/snapshot"
 /bin/device-layout snapshot "$BACK" "$SECTORS" "$WORK/snapshot" >"$WORK/snapshot.env" || fail 'backup geometry unsupported'
 BACK_PREFIX=$(/bin/backup-copy --hash "$BACK/emmc.part00" 512 "$((104447*512))") || fail 'backup protected read'
 [ "$BACK_PREFIX" = "$PREFIX_BEFORE" ] || fail 'backup protected firmware mismatch'
 . "$WORK/snapshot.env"
 MISC_OFFSET=$((CURRENT_MISC_START*512));MISC_BYTES=$((CURRENT_MISC_SECTORS*512))
 [ "$MISC_BYTES" -gt 0 ] && [ "$MISC_BYTES" -le 4194304 ] || fail 'misc size invalid'
 : >"$WORK/misc";LEFT=$MISC_BYTES
 while [ "$LEFT" -gt 0 ]; do
  INDEX=$((MISC_OFFSET/268435456));OFFSET=$((MISC_OFFSET%268435456));TAKE=$((268435456-OFFSET));[ "$TAKE" -le "$LEFT" ] || TAKE=$LEFT
  NAME=$($BB printf 'emmc.part%02d' "$INDEX")
  $BB dd if="$BACK/$NAME" bs=512 skip=$((OFFSET/512)) count=$((TAKE/512)) 2>/dev/null >>"$WORK/misc" || fail 'snapshot misc extraction'
  LEFT=$((LEFT-TAKE));MISC_OFFSET=$((MISC_OFFSET+TAKE))
 done
else
 echo 'BACKUP DISABLED: capturing only required misc and protected metadata in RAM'
 WORK=/run/install-operation;$BB mkdir "$WORK" || fail 'install already running'
 /bin/device-layout plan "$DEV" "$SECTORS" "$WORK" >"$WORK/layout.env" || fail 'unsupported model or stock layout'
 . "$WORK/layout.env"
 [ "$CURRENT_KIND" = stock ] || fail 'real install requires stock layout'
 PREFIX_BEFORE=$(hashrange 512 1 104447)
 MISC_OFFSET=$((CURRENT_MISC_START*512));MISC_BYTES=$((CURRENT_MISC_SECTORS*512))
 [ "$MISC_BYTES" -gt 0 ] && [ "$MISC_BYTES" -le 4194304 ] || fail 'misc size invalid'
 MISC_BEFORE=$(/bin/backup-copy --hash "$DEV" "$MISC_OFFSET" "$MISC_BYTES") || fail 'misc source read'
 /bin/backup-copy --read "$DEV" "$MISC_OFFSET" "$MISC_BYTES" >"$WORK/misc" || fail 'misc RAM capture'
 [ "$(/bin/backup-copy --hash "$WORK/misc" 0 "$MISC_BYTES")" = "$MISC_BEFORE" ] || fail 'misc RAM capture mismatch'
fi
[ "$($BB stat -c %s "$WORK/misc")" = "$MISC_BYTES" ] || fail 'short misc capture'
. "$WORK/layout.env"
/bin/ui-status layout "" 0 0 || :
# Each table's trusted copy is in RAM, rather than editable SD metadata.
for SECTOR in $(printf '%s' "$TABLE_SECTORS" | $BB tr ',' ' '); do
 $BB dd if="$WORK/ebr.sector$SECTOR.bin" of="$DEV" bs=512 seek="$SECTOR" count=1 conv=notrunc 2>/dev/null || fail 'EBR write failed'
 $BB sync
 [ "$(hashrange 512 "$SECTOR" 1)" = "$($BB sha256sum "$WORK/ebr.sector$SECTOR.bin" | $BB cut -d ' ' -f 1)" ] || fail 'EBR readback failed'
done
$BB dd if="$WORK/mbr.sector0.bin" of="$DEV" bs=512 count=1 conv=notrunc 2>/dev/null || fail 'MBR write failed'
$BB sync
[ "$(hashrange 512 0 1)" = "$($BB sha256sum "$WORK/mbr.sector0.bin" | $BB cut -d ' ' -f 1)" ] || fail 'MBR readback failed'
/bin/device-layout check "$DEV" "$SECTORS" "$WORK" >/dev/null || fail 'committed layout differs'
$BB blockdev --rereadpt "$DEV" || fail 'cannot reread partition table; no filesystem formatting attempted'
$BB mdev -s
for PART in 6 7 9; do
 [ -b /dev/mmcblk0p$PART ] || fail 'partition node absent'
done
[ "$($BB cat /sys/class/block/mmcblk0p6/start)" = 2271232 ] || fail 'cache node start differs'
[ "$($BB cat /sys/class/block/mmcblk0p7/start)" = 2404352 ] || fail 'data node start differs'
[ "$($BB cat /sys/class/block/mmcblk0p9/start)" = "$MISC_START" ] || fail 'misc node start differs'
[ "$($BB blockdev --getsize64 /dev/mmcblk0p6)" = 67108864 ] || fail 'cache size differs'
[ "$($BB blockdev --getsize64 /dev/mmcblk0p7)" = "$DATA_BYTES" ] || fail 'data size differs'
[ "$($BB blockdev --getsize64 /dev/mmcblk0p9)" = 4194304 ] || fail 'misc size differs'
# Android's formatter creates empty filesystems; no userdata/cache payload is shipped.
export LD_LIBRARY_PATH=/system/lib
/bin/ui-status format cache 0 0 || :
/system/bin/make_ext4fs -l 67108864 -a cache -S /etc/file_contexts /dev/mmcblk0p6 || fail 'cache formatting failed'
/bin/ui-status format userdata 0 0 || :
/system/bin/make_ext4fs -l "$DATA_BYTES" -a data -S /etc/file_contexts /dev/mmcblk0p7 || fail 'userdata formatting failed'
/system/bin/e2fsck -fn /dev/mmcblk0p6 || fail 'cache check failed'
/system/bin/e2fsck -fn /dev/mmcblk0p7 || fail 'userdata check failed'
if [ -f "$WORK/misc" ]; then
 $BB dd if=/dev/zero of=/dev/mmcblk0p9 bs=65536 count=64 2>/dev/null || fail 'misc initialization'
 $BB dd if="$WORK/misc" of=/dev/mmcblk0p9 bs=512 conv=notrunc 2>/dev/null || fail 'misc restore'
fi
/bin/updater apply "$PKG" UPDATE-SELECTED-PAPER-PRO || fail 'image installation failed'
[ "$(hashrange 512 1 104447)" = "$PREFIX_BEFORE" ] || fail 'protected firmware changed'
echo "INSTALL VERIFIED: backup=$BACKUP_POLICY; original misc retained; empty userdata/cache created."
