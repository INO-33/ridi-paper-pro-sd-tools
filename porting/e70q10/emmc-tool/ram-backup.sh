#!/bin/sh
set -eu
BB=/bin/busybox
PKG=$1
JOB=${2:-}
PURPOSE=${3:-install}
case "$PURPOSE" in install|backup-only) ;; *) echo 'STOP: unknown backup purpose';exit 1;; esac
[ "${#JOB}" = 32 ] || { echo 'STOP: missing job identity';exit 1; }
case "$JOB" in *[!0-9a-f]*) echo 'STOP: invalid job';exit 1;; esac
DEV=/dev/mmcblk0
SD=/mnt/sd
CID=$($BB cat /sys/block/mmcblk0/device/cid)
SECTORS=$($BB cat /sys/block/mmcblk0/size)
[ "${#CID}" = 32 ] || { echo 'STOP: invalid CID';exit 1; }
case "$CID" in *[!0-9a-fA-F]*) echo 'STOP: invalid CID';exit 1;; esac
ui(){ [ ! -x /bin/ui-status ] || /bin/ui-status "$@"; }
fail() { echo "STOP: $*" >&2;exit 1; }
[ -b "$DEV" ] || fail 'eMMC absent'
$BB grep -q mmcblk0 /proc/mounts && fail 'eMMC mounted'
$BB grep -q mmcblk0 /proc/swaps && fail 'eMMC swap'
for X in /sys/block/dm-* /sys/block/mmcblk0/holders/* /sys/block/mmcblk0/mmcblk0p*/holders/*; do [ ! -e "$X" ] || fail 'active block holder';done
WORK=/run/backup-operation
$BB mkdir "$WORK" || fail 'initial installer already started'
hashrange() {
 /bin/backup-copy --hash "$DEV" "$(( $1*$2 ))" "$(( $1*$3 ))" || fail 'eMMC read/hash failure'
}
/bin/device-layout plan "$DEV" "$SECTORS" "$WORK" >"$WORK/layout.env" || fail 'unsupported model or layout'
. "$WORK/layout.env"
PREFIX_BEFORE=$(hashrange 512 1 104447)
[ "$($BB sha256sum "$PKG/manifest.tsv" | $BB cut -d ' ' -f 1)" = '@MANIFEST@' ] || fail 'manifest changed'
# Payload contents are verified on PC. Only metadata/range checks run before backup.
while read -r FILE START COUNT RAW COMP; do
 case "$FILE:$START:$COUNT" in system.raw.gz:172032:2097152|vendor.raw.gz:14733312:524288|boot.raw.gz:104448:65536) ;; *) fail 'invalid install payload';; esac
 [ "$PURPOSE" = backup-only ] || [ -f "$PKG/$FILE" ] || fail 'install payload absent'
done < "$PKG/manifest.tsv"
if [ "$PURPOSE" = backup-only ]; then echo 'BACKUP ONLY: full eMMC snapshot; no OS image writes or formatting';else echo 'IMAGES: PC validated; device readback follows writes';fi
copy_verified() {
 SOURCE=$1;DEST=$2;OFFSET=$3;SIZE=$4
 STARTED=$($BB date +%s)
 HASH=$(/bin/backup-copy --copy-hash "$SOURCE" "$DEST" "$OFFSET" "$SIZE") || fail 'backup copy/hash/flush failure; snapshot incomplete'
 [ "${#HASH}" = 64 ] || fail 'backup stream hash failed'
 [ "$($BB stat -c %s "$DEST")" = "$SIZE" ] || fail 'backup short copy'
 COPIED=$($BB date +%s)
 echo "BACKUP READBACK $DEST; copy+hash seconds=$((COPIED-STARTED))"
 ui backup-check "${NAME:-eMMC}" "${TOTAL:-0}" "$BYTES"
 READ_HASH=$(/bin/backup-copy --hash "$DEST" 0 "$SIZE") || fail 'backup readback failed'
 [ "$READ_HASH" = "$HASH" ] || fail 'backup SD readback mismatch' 
 CHECKED=$($BB date +%s)
 echo "BACKUP VERIFIED PIECE $DEST; readback seconds=$((CHECKED-COPIED))"
}
BACK=$SD/e70q10-backups/$CID/$JOB
# Never silently replace a backup. Completed backups are rechecked on retries.
check_backup_shape() {
 N=0
 while [ "$N" -lt "$(( (BYTES+268435455)/268435456 ))" ]; do
  NAME=$($BB printf 'emmc.part%02d' "$N")
  SIZE=$((BYTES-N*268435456));[ "$SIZE" -lt 268435456 ] || SIZE=268435456
  [ -f "$BACK/$NAME" ] && [ "$($BB stat -c %s "$BACK/$NAME")" = "$SIZE" ] || fail 'backup piece missing or wrong size'
  [ "$($BB grep -c "  $NAME$" "$BACK/SHA256SUMS")" = 1 ] || fail 'backup checksum coverage differs'
  N=$((N+1))
 done
 [ "$($BB grep -c "^cid=$CID$" "$BACK/device.txt")" = 1 ] || fail 'backup metadata CID differs'
 [ "$($BB grep -c "^userarea_bytes=$BYTES$" "$BACK/device.txt")" = 1 ] || fail 'backup metadata capacity differs'
 [ "$($BB grep -c '  device.txt$' "$BACK/SHA256SUMS")" = 1 ] || fail 'backup metadata not checksummed'
 EXPECTED=$(((BYTES+268435455)/268435456+1))
 for NAME in boot0 boot1; do
  if [ -b /dev/mmcblk0$NAME ]; then
   [ -f "$BACK/$NAME.bin" ] && [ "$($BB grep -c "  $NAME.bin$" "$BACK/SHA256SUMS")" = 1 ] || fail 'boot area backup absent'
   EXPECTED=$((EXPECTED+1))
  fi
 done
 [ "$($BB wc -l < "$BACK/SHA256SUMS")" -eq "$EXPECTED" ] || fail 'unexpected backup checksum rows'
}
$BB mount -o remount,rw "$SD" || fail 'SD not writable for backup'
if [ -d "$BACK" ]; then
 [ -f "$BACK/complete" ] || fail 'incomplete backup exists; preserve and inspect it before retry'
 [ "$($BB cat "$BACK/complete")" = "$CID:$BYTES" ] || fail 'backup identity differs'
 check_backup_shape
 ui backup-check '' 0 0 'Checking existing completed backup'
 while read -r EXPECTED_HASH NAME; do
  [ "$(/bin/backup-copy --hash "$BACK/$NAME" 0 "$($BB stat -c %s "$BACK/$NAME")")" = "$EXPECTED_HASH" ] || fail 'existing backup corrupt'
 done <"$BACK/SHA256SUMS"
else
 FREE=$($BB df -Pk "$SD" | $BB tail -n 1 | $BB awk '{print $4}')
 [ "$FREE" -ge "$((BYTES/1024+131072))" ] || fail 'SD space insufficient for this eMMC backup; use a larger SD'
 $BB mkdir -p "$BACK"
 printf 'cid=%s\nuserarea_bytes=%s\nchunk_bytes=268435456\n' "$CID" "$BYTES" >"$BACK/device.txt"
 : >"$BACK/SHA256SUMS"
 N=0;TOTAL=0
 while [ "$TOTAL" -lt "$BYTES" ]; do
  COUNT=4096;LEFT=$(((BYTES-TOTAL)/65536));[ "$LEFT" -ge "$COUNT" ] || COUNT=$LEFT
  NAME=$($BB printf 'emmc.part%02d' "$N")
  ui backup "$NAME" "$TOTAL" "$BYTES"
  echo "BACKUP $NAME"
  copy_verified "$DEV" "$BACK/$NAME" "$((N*268435456))" "$((COUNT*65536))"
  printf '%s  %s\n' "$HASH" "$NAME" >>"$BACK/SHA256SUMS"
  TOTAL=$((TOTAL+COUNT*65536));N=$((N+1))
 done
 for NAME in boot0 boot1; do
  NODE=/dev/mmcblk0$NAME
  if [ -b "$NODE" ]; then
   SIZE=$($BB blockdev --getsize64 "$NODE")
   [ "$SIZE" -gt 0 ] && [ "$SIZE" -lt 67108864 ] || fail 'unexpected boot region size'
   ui backup "$NAME" 0 "$SIZE"
   copy_verified "$NODE" "$BACK/$NAME.bin" 0 "$SIZE"
   printf '%s  %s.bin\n' "$HASH" "$NAME" >>"$BACK/SHA256SUMS"
  fi
 done
 # Every piece is already independently read back. Do not rescan the entire SD.
 (cd "$BACK";$BB sha256sum device.txt >>SHA256SUMS) || fail 'backup metadata hash failed'
 check_backup_shape
 $BB sync
 printf '%s:%s\n' "$CID" "$BYTES" >"$BACK/complete.tmp"
 $BB sync;$BB mv "$BACK/complete.tmp" "$BACK/complete";$BB sync
fi
$BB mount -o remount,ro "$SD" || fail 'cannot protect SD payloads'
printf '%s\n' "$PREFIX_BEFORE" >"$WORK/protected.sha256"
printf 'BACK=%s\n' "$BACK" >"$WORK/backup.env"
echo 'BACKUP VERIFIED: current job snapshot.'
