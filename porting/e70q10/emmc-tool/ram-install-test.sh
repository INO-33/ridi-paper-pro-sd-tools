#!/bin/sh
set -eu
BB=/bin/busybox
PKG=$1;JOB=$2;DEV=/dev/mmcblk0
fail() { echo "STOP: $*" >&2;exit 1; }
SECTORS=$($BB cat /sys/block/mmcblk0/size)
/bin/device-layout check "$DEV" "$SECTORS" /run >/run/test-layout.env || fail 'install-test requires existing Android8 layout'
/bin/backup-current "$PKG" "$JOB" || fail 'backup failed; no updates started'
. /run/test-layout.env
WORK=/run/install-test;$BB mkdir "$WORK" || fail 'test already running'
hashrange() {
 /bin/backup-copy --hash "$DEV" "$(( $1*65536 ))" "$(( $2*65536 ))" || fail 'preserved region read/hash failed'
}
/bin/ui-status checking userdata 0 "$((DATA_SECTORS*512))" "Checking preserved user data" || :
echo 'PRESERVE CHECK: hashing userdata/misc before cache creation and update'
DATA_BEFORE=$(hashrange "$((DATA_START/128))" "$((DATA_SECTORS/128))")
/bin/ui-status checking misc 0 4194304 || :
MISC_BEFORE=$(hashrange "$((MISC_START/128))" 64)
# Only p6 cache is formatted. Check the live kernel node against the verified raw layout.
[ -b /dev/mmcblk0p6 ] || fail 'cache node absent'
[ "$($BB cat /sys/class/block/mmcblk0p6/start)" = 2271232 ] || fail 'cache node start differs'
[ "$($BB blockdev --getsize64 /dev/mmcblk0p6)" = 67108864 ] || fail 'cache node size differs'
echo 'CACHE CREATE: Android ARM formatter, 64MiB, SELinux contexts'
export LD_LIBRARY_PATH=/system/lib
/bin/ui-status format cache 0 0 || :
/system/bin/make_ext4fs -l 67108864 -a cache -S /etc/file_contexts /dev/mmcblk0p6 || fail 'cache creation failed'
/system/bin/e2fsck -fn /dev/mmcblk0p6 || fail 'cache filesystem verification failed'
$BB sync
/bin/ui-status checking cache 0 67108864 || :
CACHE_CREATED=$(hashrange 17744 1024)
/bin/updater apply "$PKG" UPDATE-SELECTED-PAPER-PRO || fail 'image update failed'
echo 'PRESERVE CHECK: verifying userdata/misc and new cache after update'
/bin/ui-status checking userdata 0 "$((DATA_SECTORS*512))" || :
[ "$(hashrange "$((DATA_START/128))" "$((DATA_SECTORS/128))")" = "$DATA_BEFORE" ] || fail 'userdata changed'
/bin/ui-status checking cache 0 67108864 || :
[ "$(hashrange 17744 1024)" = "$CACHE_CREATED" ] || fail 'new cache changed during image update'
/bin/ui-status checking misc 0 4194304 || :
[ "$(hashrange "$((MISC_START/128))" 64)" = "$MISC_BEFORE" ] || fail 'misc changed'
printf 'userdata_sha256=%s\ncache_sha256=%s\ncache=created\ncache_fsck=passed\nmisc_sha256=%s\nuserdata=preserved\npartitioning=preserved\n' "$DATA_BEFORE" "$CACHE_CREATED" "$MISC_BEFORE" > /run/preservation.result
echo 'INSTALL TEST VERIFIED: backup and image update passed; cache created and checked; userdata and partitioning preserved.'
