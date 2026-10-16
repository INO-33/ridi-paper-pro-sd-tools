#!/bin/sh
# stdout is /run/emmc-auto.log; never wait for a host to open the USB console.
BB=/bin/busybox
PKG=${1:-/mnt/sd/e70q10-update}
SD=/mnt/sd
@CONFIG_FUNCTIONS@
read_config "$PKG" || exit 1
[ "$CONF_AUTO" = 1 ] || { echo 'AUTO DISABLED: diagnostic RAM console only.';exit 0; }
echo "AUTO START: targets=$CONF_TARGETS reboot=$CONF_REBOOT"
/bin/updater apply "$PKG" UPDATE-SELECTED-PP1A1GK166561
RC=$?
echo "AUTO APPLY EXIT=$RC"
# Store result on external SD only, after updater has released its lock.
if $BB mount -o remount,rw "$SD"; then
    STATUS="$SD/e70q10-update-status"
    if $BB mkdir -p "$STATUS" && $BB cp /run/emmc-auto.log "$STATUS/last.log" && printf 'manifest=@MANIFEST@\ntargets=%s\nexit=%s\n' "$CONF_TARGETS" "$RC" >"$STATUS/last.result"; then
        $BB sync
        $BB mount -o remount,ro "$SD" || { echo 'STOP: cannot restore read-only SD';exit 1; }
    else
        echo 'STOP: cannot persist result on SD';exit 1
    fi
else
    echo 'STOP: cannot persist result on SD';exit 1
fi
[ "$RC" = 0 ] || { echo 'AUTO FAILED: console available; no reboot.';exit "$RC"; }
[ "$CONF_REBOOT" = 1 ] || { echo 'AUTO VERIFIED: reboot disabled; console available.';exit 0; }
echo 'AUTO VERIFIED: rebooting Android.'
$BB sync
$BB reboot -f
