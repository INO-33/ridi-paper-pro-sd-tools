#!/bin/sh
set -eu
ROOT=${RIDI_ROOT:-/home/juwon/ridi}
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
TOOLS="$ROOT/host-tools/android-platform-tools/platform-tools"
IMAGE="$SCRIPT_DIR/ram-installer.img"
[ -f "$IMAGE" ] || IMAGE="$ROOT/deliverables/e70q10-emmc-android8-20261001/ram-installer.img"
SERIAL=PP1A1GK166561
[ "${CONFIRM_RAM_BOOT:-}" = E70Q10 ] || { echo 'Set CONFIRM_RAM_BOOT=E70Q10'; exit 2; }
[ -f "$IMAGE" ] || { echo 'RAM image missing'; exit 1; }
case "${1:-}" in
 --from-fastboot) ;;
 '') "$TOOLS/adb" -s "$SERIAL" get-state >/dev/null
     "$TOOLS/adb" -s "$SERIAL" reboot fastboot ;;
 *) echo 'usage: boot_ram_installer.sh [--from-fastboot]';exit 2;;
esac
n=0
while [ "$n" -lt 45 ]; do
 "$TOOLS/fastboot" devices | awk -v s="$SERIAL" '$1==s { found=1 } END {exit !found}' && break
 sleep 1;n=$((n+1))
done
[ "$n" -lt 45 ] || { echo 'Target fastboot serial not found. No flash attempted.';exit 1; }
"$TOOLS/fastboot" -s "$SERIAL" boot "$IMAGE"
echo 'RAM boot sent. Open USB CDC ACM console; no automatic installation.'
