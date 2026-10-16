#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
TOOLS="$ROOT/host-tools/android-platform-tools/platform-tools"
ADB="$TOOLS/adb"
FASTBOOT="$TOOLS/fastboot"
IMAGE="${DIAGNOSTIC_IMAGE:-$ROOT/porting/e70q10/diagnostic-build/e70q10-diagnostic-boot.img}"

[ "${CONFIRM_RAM_BOOT:-}" = E70Q10 ] || {
    echo "Set CONFIRM_RAM_BOOT=E70Q10 to authorize a one-shot RAM boot." >&2
    exit 2
}
[ -x "$ADB" ] || { echo "missing $ADB" >&2; exit 1; }
[ -x "$FASTBOOT" ] || { echo "missing $FASTBOOT" >&2; exit 1; }
[ -f "$IMAGE" ] || { echo "missing $IMAGE" >&2; exit 1; }

echo "This script calls only: adb reboot fastboot; fastboot boot <image>"
echo "It contains no flash, erase, format, partition or OEM command."

serial=$($ADB devices | awk 'NR > 1 && $2 == "device" { print $1; exit }')
[ -n "$serial" ] || { echo "no ADB device" >&2; exit 1; }
echo "ADB device: $serial"

$ADB -s "$serial" reboot fastboot

count=0
fbserial=
while [ "$count" -lt 45 ]; do
    fbserial=$($FASTBOOT devices 2>/dev/null | awk 'NR == 1 { print $1 }')
    [ -n "$fbserial" ] && break
    sleep 1
    count=$((count + 1))
done

[ -n "$fbserial" ] || {
    echo "Fastboot did not enumerate within 45 seconds." >&2
    echo "The device may have returned to stock Android; do not retry blindly." >&2
    exit 1
}

echo "Fastboot device: $fbserial"
echo "Booting diagnostic image in RAM..."
$FASTBOOT -s "$fbserial" boot "$IMAGE"

echo "Waiting up to 45 seconds for USB CDC ACM..."
count=0
acm=
while [ "$count" -lt 45 ]; do
    for candidate in /dev/ttyACM*; do
        [ -c "$candidate" ] || continue
        acm=$candidate
        break
    done
    [ -n "$acm" ] && break
    sleep 1
    count=$((count + 1))
done

if [ -n "$acm" ]; then
    # Configure the host endpoint before any bidirectional read.  Without this,
    # local echo can feed the gadget shell's own output back as shell input.
    stty -F "$acm" 115200 raw -echo -echoe -echok 2>/dev/null || true
    echo "USB CDC ACM ready: $acm (115200 raw, local echo disabled)"
    echo "Read-only observation: timeout 8s sed -n '1,120p' $acm"
else
    echo "USB CDC ACM did not enumerate within 45 seconds." >&2
    echo "Check external-SD logs before deciding whether a manual reboot is needed." >&2
fi
echo "Boot logs are also written to external SD: ridi-dev/logs/"
