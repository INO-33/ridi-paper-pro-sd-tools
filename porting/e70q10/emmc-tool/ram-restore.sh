#!/bin/sh
set -eu
BB=/bin/busybox
DEV=/dev/mmcblk0
SD=/mnt/sd
PKG=${1:-/mnt/sd/e70q10-update}
WORK=/run/restore-operation
CID=@CID@
BYTES=@BYTES@
JOB=@JOB@
MANIFEST=@MANIFEST@
BACK=$SD/e70q10-backups/$CID/@BACKUP_JOB@
STATUS=$SD/e70q10-update-status
ui(){ [ ! -x /bin/ui-status ] || /bin/ui-status "$@"; }
fail(){ echo "STOP: $*";exit 1; }
# Always stop without reboot on any failure; save an explicit result where possible.
finish(){
 RC=$?;trap - EXIT HUP INT TERM
 if [ "$RC" != 0 ]; then
  echo 'RESTORE FAILED: no reboot; do not boot partially restored OS'
  ui failed '' 0 0 'Rollback stopped; inspect SD log'
  if $BB mount -o remount,rw "$SD"; then
   $BB mkdir -p "$STATUS"
   printf 'format=5\njob=%s\noperation=restore\nmanifest=%s\ntargets=emmc\nbackup=none\nexit=1\n' "$JOB" "$MANIFEST" >"$STATUS/last.result"
   $BB cp /run/emmc-auto.log "$STATUS/last.log" || :
   $BB sync;$BB mount -o remount,ro "$SD" || :
  fi
 fi
 exit "$RC"
}
trap finish EXIT
trap 'exit 1' HUP INT TERM
[ -b "$DEV" ] || fail 'eMMC absent'
[ "$($BB cat /sys/block/mmcblk0/device/cid)" = "$CID" ] || fail 'backup belongs to a different device'
[ "$(( $($BB cat /sys/block/mmcblk0/size)*512 ))" = "$BYTES" ] || fail 'eMMC capacity differs'
$BB grep -q mmcblk0 /proc/mounts && fail 'eMMC mounted'
$BB grep -q mmcblk0 /proc/swaps && fail 'eMMC swap'
for X in /sys/block/dm-* /sys/block/mmcblk0/holders/* /sys/block/mmcblk0/mmcblk0p*/holders/*;do [ ! -e "$X" ] || fail 'active block holder';done
[ ! -L "$BACK" ] && [ -d "$BACK" ] || fail 'backup absent or linked'
[ "$($BB sha256sum "$PKG/update.conf" | $BB cut -d ' ' -f 1)" = '@CONF_SHA@' ] || fail 'SD restore config differs from RAM'
if [ -f "$STATUS/completed" ] && [ "$($BB cat "$STATUS/completed")" = "$CID:restore-$JOB-$MANIFEST" ];then echo 'ALREADY COMPLETED: no writes or reboot';ui completed;exit 0;fi
$BB mkdir "$WORK" || fail 'rollback already started in this RAM session'
$BB mount -o remount,ro "$SD" || fail 'cannot protect backup SD'
$BB grep -q ' /mnt/sd .*ro[, ]' /proc/mounts || fail 'SD must be read-only'
$BB cat >"$WORK/checks" <<'CHECKS'
@CHECKS@
CHECKS
$BB cat >"$WORK/sizes" <<'SIZES'
@SIZES@
SIZES
$BB cat >"$WORK/pieces" <<'PIECES'
@PIECES@
PIECES
[ "$($BB cat "$BACK/complete")" = "$CID:$BYTES" ] || fail 'backup incomplete'
echo 'RESTORE PREFLIGHT: verifying every backup byte before any eMMC write'
while read -r NAME SIZE;do
 [ ! -L "$BACK/$NAME" ] && [ -f "$BACK/$NAME" ] || fail 'linked or missing backup file'
 [ "$($BB stat -c %s "$BACK/$NAME")" = "$SIZE" ] || fail 'backup file size changed'
 ui backup-check "$NAME" 0 "$SIZE"
 EXPECTED=$($BB awk -v n="$NAME" '$2==n {print $1}' "$WORK/checks")
 [ "$(/bin/backup-copy --hash "$BACK/$NAME" 0 "$SIZE")" = "$EXPECTED" ] || fail 'backup hash mismatch'
done <"$WORK/sizes"
# These areas were never modified by our installer. Refuse instead of flashing firmware.
[ "$(/bin/backup-copy --hash "$DEV" 512 53476864)" = '@PREFIX_SHA@' ] || fail 'protected firmware/recovery differs; separate recovery required'
for NAME in boot0 boot1;do
 NODE=/dev/mmcblk0$NAME
 [ -b "$NODE" ] || fail 'boot area absent'
 SIZE=$($BB awk -v n="$NAME.bin" '$1==n {print $2}' "$WORK/sizes")
 [ "$($BB blockdev --getsize64 "$NODE")" = "$SIZE" ] || fail 'boot area capacity differs'
 EXPECTED=$($BB awk -v n="$NAME.bin" '$2==n {print $1}' "$WORK/checks")
 [ "$(/bin/backup-copy --hash "$NODE" 0 "$SIZE")" = "$EXPECTED" ] || fail 'boot firmware differs; no firmware writes permitted'
done
# Save sector zero in RAM before writes. Commit the original MBR only after all data.
$BB dd if="$BACK/emmc.part00" of="$WORK/mbr" bs=512 count=1 2>/dev/null
[ "$($BB sha256sum "$WORK/mbr" | $BB cut -d ' ' -f 1)" = '@MBR_SHA@' ] || fail 'MBR backup differs'
$BB mount -o remount,rw "$SD" || fail 'cannot save rollback running status'
$BB mkdir -p "$STATUS"
printf 'job=%s\noperation=restore\nmanifest=%s\ntargets=emmc\nbackup=none\nstate=running\n' "$JOB" "$MANIFEST" >"$STATUS/last.result"
$BB sync;$BB mount -o remount,ro "$SD" || fail 'cannot protect snapshot'
$BB mkfifo "$WORK/fifo"
echo 'RESTORE WRITES START: user data, partitions and OS revert to snapshot'
while read -r NAME SKIP START COUNT EXPECTED;do
 ui write "$NAME" 0 "$((COUNT*512))"
 $BB dd if="$BACK/$NAME" bs=1048576 skip="$SKIP" 2>/dev/null >"$WORK/fifo" & PID=$!
 if ! /bin/stream-write "$DEV" "$START" "$COUNT" <"$WORK/fifo";then kill "$PID" 2>/dev/null || :;wait "$PID" 2>/dev/null || :;fail 'rollback write failed';fi
 wait "$PID" || fail 'backup read failed during write'
 ui verify "$NAME" 0 "$((COUNT*512))"
 [ "$(/bin/backup-copy --hash "$DEV" "$((START*512))" "$((COUNT*512))")" = "$EXPECTED" ] || fail 'rollback readback mismatch'
 echo "RESTORE READBACK VERIFIED $NAME"
done <"$WORK/pieces"
/bin/stream-write "$DEV" 0 1 <"$WORK/mbr" || fail 'original MBR commit failed'
[ "$(/bin/backup-copy --hash "$DEV" 0 512)" = '@MBR_SHA@' ] || fail 'MBR readback differs'
[ "$(/bin/backup-copy --hash "$DEV" 512 53476864)" = '@PREFIX_SHA@' ] || fail 'protected firmware changed'
echo 'RESTORE VERIFIED: entire user area equals snapshot; boot0/boot1 unchanged and matching'
$BB mount -o remount,rw "$SD" || fail 'cannot save restore result'
printf 'job=%s\noperation=restore\nmanifest=%s\ntargets=emmc\nbackup=none\nexit=0\n' "$JOB" "$MANIFEST" >"$STATUS/last.result"
$BB cp /run/emmc-auto.log "$STATUS/last.log"
printf '%s:restore-%s-%s\n' "$CID" "$JOB" "$MANIFEST" >"$STATUS/completed.tmp"
$BB sync;$BB mv "$STATUS/completed.tmp" "$STATUS/completed";$BB sync
$BB mount -o remount,ro "$SD" || fail 'SD protection failed'
ui success '' 1 1 'Rollback verified; rebooting'
$BB sleep 3
$BB reboot -f
