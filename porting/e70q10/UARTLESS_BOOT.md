# E70Q10 UART-less diagnostic boot

## Prepared paths

- Fastboot boot image: `diagnostic-build/e70q10-diagnostic-boot.img`
- Reproducible builder: `build_diagnostic_boot.sh`
- Fastboot-only launcher: `boot_diagnostic_fastboot.sh`
- SD raw payload and descriptor: `sd-boot/`
- Official local platform tools: `../../host-tools/android-platform-tools/platform-tools/`

## Safety properties

- The launcher contains only `adb reboot fastboot` and `fastboot boot`; it has
  no `flash`, `erase`, `format`, `partition` or OEM operation.
- The initramfs never mounts internal eMMC (`mmcblk0`).
- Only the external FAT partition candidate (`mmcblk1p1`, fallback
  `mmcblk2p1`) is mounted writable for logs.
- A failed one-shot Fastboot RAM boot returns to the stock path after a power
  cycle. Removing the SD removes the external raw payload from the boot path.

## Verified RAM boot

The Linux 4.9 diagnostic image was successfully RAM-booted on 2026-07-21. The
appended E70Q10 DTB, both MMC devices, SD logging, USB CDC ACM and stock EPDC
waveform loading reached userspace. The ramdisk address is 0x84000000; the
stock 0x81800000 address must not be reused because the larger 4.9 zImage
decompressor relocation overwrites it.

## Preferred first test

Keep the external SD inserted and the USB cable connected. From the workspace:

```sh
CONFIRM_RAM_BOOT=E70Q10 ./porting/e70q10/boot_diagnostic_fastboot.sh
```

On success a USB CDC ACM device should appear. Connect at 115200 8N1. The shell
banner is `E70Q10_DIAGNOSTIC_READY`. The initramfs also creates a directory under
`ridi-dev/logs/` on the SD and writes `boot.log`, `dmesg.txt`, device lists and
mount information there.

## Standalone SD test

The SD has a 64 MiB unpartitioned raw boot area and a FAT32 partition beginning
at sector 131072. The verified NTX descriptor is at sector 2047 and the Android
boot image begins at sector 2048.

Stock U-Boot selects external-SD boot when the upgrade key and power key are
held with the card inserted and USB disconnected. For this keypad family the
upgrade key is selected from Home, Page Down, Page Up, R1 and L1 in that order;
E70Q10 has no Home key, so Page Down is the leading physical candidate. Confirm
the actual button with the non-destructive Fastboot USB-enumeration test before
depending on standalone boot.

Normal power-on without the upgrade key continues to use internal Android.

## Recovery from a silent test

1. Release all keys and hold power until the unit shuts down.
2. Remove the external SD.
3. Power on normally; stock internal Android remains unchanged.
4. If the Fastboot launcher timed out, wait for ADB before another attempt.

UART is still required if U-Boot or the kernel stops before USB CDC, EPDC and SD
logging are available.
