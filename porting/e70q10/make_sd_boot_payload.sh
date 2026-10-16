#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
PORT="$ROOT/porting/e70q10"
SRC="$PORT/diagnostic-build/e70q10-diagnostic-boot.img"
OUT="$PORT/sd-boot"
HEADER="$OUT/ntx-kernel-header-sector.bin"
PAYLOAD="$OUT/e70q10-diagnostic-boot.img"

[ -f "$SRC" ] || { echo "missing diagnostic boot image: $SRC" >&2; exit 1; }
mkdir -p "$OUT"
cp -a "$SRC" "$PAYLOAD"

size=$(wc -c < "$PAYLOAD")
max_size=$((63 * 1024 * 1024))
[ "$size" -le "$max_size" ] || {
    echo "boot image is too large for the reserved SD raw area" >&2
    exit 1
}

# Netronix reads a 16-byte descriptor from the end of sector 2047. It expects
# ff f5 af ff at +0 and a little-endian uint32 payload length at +8.
dd if=/dev/zero of="$HEADER" bs=512 count=1 status=none
hex=$(printf '%08x' "$size")
little=$(printf '%s' "$hex" | sed -E 's/(..)(..)(..)(..)/\4\3\2\1/')
printf 'fff5afff00000000%s00000000\n' "$little" | xxd -r -p | \
    dd of="$HEADER" bs=1 seek=496 conv=notrunc status=none

sha256sum "$HEADER" "$PAYLOAD" >"$OUT/SHA256SUMS"

{
    printf '%s\n' 'E70Q10 external-SD diagnostic boot payload' ''
    printf '%s\n' 'Sector size:               512 bytes'
    printf '%s\n' 'FAT32 partition start:      sector 131072 (64 MiB)'
    printf '%s\n' 'NTX header sector:          sector 2047'
    printf '%s\n' 'NTX header descriptor:      byte offset 496 within sector 2047'
    printf '%s\n' 'Android boot image sector:  sector 2048 (1 MiB)'
    printf 'Android boot image bytes:   %s\n\n' "$size"
    printf '%s\n' 'Normal power-on does not select this payload. Stock U-Boot must enter its'
    printf '%s\n' 'external-SD/upgrade boot mode. Removing the SD always removes this payload from'
    printf '%s\n' 'the boot path. No internal-eMMC location is part of this layout.'
} >"$OUT/LAYOUT.txt"

echo "Prepared SD boot payload: $OUT"
xxd -s 480 -l 32 "$HEADER"
wc -c "$HEADER" "$PAYLOAD"
