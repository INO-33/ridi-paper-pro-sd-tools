#!/bin/sh
BB=/bin/busybox
PKG=${1:-/mnt/sd/e70q10-update}
SD=/mnt/sd
ui(){ [ ! -x /bin/ui-status ] || /bin/ui-status "$@"; }
trap 'RC=$?; if [ "$RC" != 0 ]; then REASON=$($BB grep "STOP:" /run/emmc-auto.log | $BB tail -n 1); ui failed "" 0 0 "${REASON:-Updater stopped; inspect USB or SD log}"; fi' EXIT
ui starting
@CONTROL@
read_control "$PKG" || exit 1
[ "$CONF_AUTO" = 1 ] || { echo 'AUTO DISABLED';ui idle;exit 0; }
echo "AUTO START: operation=$CONF_OPERATION targets=$CONF_TARGETS job=$CONF_JOB"
# Fail before the costly backup if required RAM formatter assets were not unpacked.
if [ "$CONF_OPERATION" = install ] || [ "$CONF_OPERATION" = install-test ]; then
 for REQUIRED in /bin/backup-copy /bin/stream-write /system/bin/linker /system/bin/make_ext4fs /system/bin/e2fsck /system/lib/libc.so /etc/file_contexts; do
  [ -s "$REQUIRED" ] || { echo "STOP: missing RAM asset $REQUIRED; use repaired RAM image";exit 1; }
 done
 LD_LIBRARY_PATH=/system/lib /system/bin/e2fsck -V || { echo 'STOP: RAM formatter libraries cannot load';exit 1; }
fi
[ -s /bin/backup-copy ] || { echo 'STOP: backup/hash tool missing';exit 1; }
ui checking
CID=$($BB cat /sys/block/mmcblk0/device/cid)
[ "${#CID}" = 32 ] || { echo 'STOP: invalid CID';exit 1; }
case "$CID" in *[!0-9a-fA-F]*) echo 'STOP: invalid CID';exit 1;; esac
SECTORS=$($BB cat /sys/block/mmcblk0/size)
# Validate real raw hwcfg and partitions before SD status or internal writes.
/bin/device-layout plan /dev/mmcblk0 "$SECTORS" /run > /run/device.env || exit 1
. /run/device.env
case "$CONF_OPERATION:$CURRENT_KIND" in install:stock|install-test:unified|update:unified|backup:stock|backup:unified) ;; *) echo 'STOP: operation does not match current layout; no internal writes';exit 1;; esac
STATUS=$SD/e70q10-update-status
KEY=$CONF_JOB-$CONF_OPERATION-$CONF_MANIFEST-$CONF_TARGETS
[ "$CONF_FORMAT" != 5 ] || KEY=$KEY-backup-$CONF_BACKUP
# A successful operation is one-shot. Rebooting RAM cannot repeat a data wipe.
if [ -f "$STATUS/completed" ] && [ "$($BB cat "$STATUS/completed")" = "$CID:$KEY" ]; then
 echo 'ALREADY COMPLETED: no automatic writes or reboot.';ui completed '' 1 1 'No writes: completed job';exit 0
fi
# Adapt format=2 data to the pinned legacy image writer without executing SD code.
WORK=/run/selected-package
$BB mkdir "$WORK" || exit 1
for NAME in manifest.tsv system.raw.gz vendor.raw.gz boot.raw.gz; do
 [ ! -f "$PKG/$NAME" ] || $BB ln -s "$PKG/$NAME" "$WORK/$NAME"
done
printf 'format=1\nmanifest=%s\ntargets=%s\nautostart=0\nreboot=0\n' "$CONF_MANIFEST" "$CONF_TARGETS" >"$WORK/update.conf"
# Record in-progress state before potentially destructive installation.
$BB mount -o remount,rw "$SD" || exit 1
$BB mkdir -p "$STATUS" || exit 1
printf 'job=%s\ncid=%s\noperation=%s\nmanifest=%s\ntargets=%s\nbackup=%s\nstate=running\n' "$CONF_JOB" "$CID" "$CONF_OPERATION" "$CONF_MANIFEST" "$CONF_TARGETS" "$CONF_BACKUP" >"$STATUS/last.result"
$BB sync;$BB mount -o remount,ro "$SD" || exit 1
case "$CONF_OPERATION" in
 install) /bin/initial-install "$WORK" "$CONF_JOB" "$CONF_BACKUP";;
 install-test) /bin/install-test "$WORK" "$CONF_JOB";;
 backup) /bin/backup-current "$WORK" "$CONF_JOB" backup-only;;
 update)
  if [ "$CONF_BACKUP" = required ]; then
   /bin/backup-current "$WORK" "$CONF_JOB" backup-only
   BACK_RC=$?
   if [ "$BACK_RC" != 0 ]; then echo 'STOP: backup failed; no updates started';(exit "$BACK_RC")
   else /bin/updater apply "$WORK" UPDATE-SELECTED-PAPER-PRO;fi
  else /bin/updater apply "$WORK" UPDATE-SELECTED-PAPER-PRO;fi;;
esac
RC=$?
echo "AUTO APPLY EXIT=$RC"
if [ "$RC" != 0 ]; then
 echo 'AUTO FAILED: no reboot'
elif [ "$CONF_REBOOT" = 1 ]; then
 echo 'AUTO VERIFIED: saving result, then requesting reboot'
else
 echo 'AUTO VERIFIED: reboot disabled'
fi
$BB mount -o remount,rw "$SD" || exit 1
$BB cp /run/emmc-auto.log "$STATUS/last.log" || exit 1
[ ! -f /run/preservation.result ] || $BB cp /run/preservation.result "$STATUS/preservation.result" || exit 1
printf 'job=%s\ncid=%s\noperation=%s\nmanifest=%s\ntargets=%s\nbackup=%s\nexit=%s\n' "$CONF_JOB" "$CID" "$CONF_OPERATION" "$CONF_MANIFEST" "$CONF_TARGETS" "$CONF_BACKUP" "$RC" >"$STATUS/last.result" || exit 1
if [ "$RC" = 0 ]; then
 printf '%s:%s\n' "$CID" "$KEY" >"$STATUS/completed.tmp" || exit 1
 $BB sync;$BB mv "$STATUS/completed.tmp" "$STATUS/completed" || exit 1
fi
$BB sync;$BB mount -o remount,ro "$SD" || exit 1
[ "$RC" = 0 ] || exit "$RC"
if [ "$CONF_OPERATION" = backup ]; then ui success "" 1 1 "Full eMMC backup verified; no internal writes";else ui success "" 1 1 "All selected partitions verified";fi
$BB sleep 3
[ "$CONF_REBOOT" = 1 ] || exit 0
$BB sync;$BB reboot -f
