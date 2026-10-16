#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
PORT="$ROOT/porting/e70q10"
KERNEL="$ROOT/android-sources/nxp-o8.0.0_1.0.0-ga/vendor/nxp-opensource/kernel_imx"
GCC_DIR="${E70Q10_GCC_DIR:-/tmp/e70q10-android-gcc49}"
GCC="$GCC_DIR/arm-linux-androideabi-gcc"
SYSROOT="$ROOT/android-sources/nxp-o8.0.0_1.0.0-ga/prebuilts/ndk/r11/platforms/android-19/arch-arm"
SRC="$PORT/diagnostic-initramfs"
OUT="$SRC/bin"

[ -x "$GCC" ] || {
	echo "missing ARM compiler wrapper: $GCC" >&2
	echo "Build the /tmp/e70q10-android-gcc49 symlink farm first." >&2
	exit 1
}
[ -f "$SYSROOT/usr/lib/libc.a" ] || { echo "missing NDK sysroot: $SYSROOT" >&2; exit 1; }

mkdir -p "$OUT"
for tool in epdc-power-test epdc-pattern-test epdc-latency-test epdc-visibility-test touch-event-test touch-diag; do
	"$GCC" --sysroot="$SYSROOT" -idirafter "$KERNEL/include/uapi" \
		-std=gnu99 -static -Os -Wall -Wextra \
		-o "$OUT/$tool.unstripped" "$SRC/$tool.c"
	"$GCC_DIR/arm-linux-androideabi-strip" -o "$OUT/$tool" "$OUT/$tool.unstripped"
	rm -f "$OUT/$tool.unstripped"
done

sha256sum "$OUT/epdc-power-test" "$OUT/epdc-pattern-test" "$OUT/epdc-latency-test" \
	"$OUT/epdc-visibility-test" \
	"$OUT/touch-event-test" "$OUT/touch-diag"
