# E70Q10 RTL8189FTV Linux 4.9 port

## Recovered hardware path

- Chip: Realtek RTL8189FTV (`8189fs`)
- Interface: USDHC3, 4-bit SDIO
- SDIO ID: `024c:f179`
- Wi-Fi 3.3 V enable: GPIO4_29, active low
- Reset: GPIO5_0, active low, then deassert high
- Optional host interrupt: GPIO4_31
- Bluetooth is not present.

These assignments come from the public Tolino Epos Netronix board source and
match the RIDI stock GPIO/MMC capture.

## Driver source

The public Tolino Epos source contains Realtek driver
`v4.3.24.10_24994.20171103`, including RTL8188F firmware and PHY tables.  It
contains compatibility branches for Linux 4.x and is built as an external
module against the exact E70Q10 4.9 kernel output.

The E70Q10 profile disables:

- external PHY parameter files;
- Bluetooth coexistence;
- concurrent/P2P virtual interface mode;
- the old Netronix Android platform-device power hook.

The vendor MP objects remain compiled because this Realtek release exposes
shared firmware and EFUSE types only under `CONFIG_MP_INCLUDED` even though
ordinary HAL/debug code references them.  MP mode is not enabled at runtime.

DT `mmc-pwrseq` and a fixed regulator perform power/reset sequencing instead.

## Build

Build only after the matching E70Q10 kernel has finished:

```sh
export PATH=/home/juwon/ridi/host-tools/android8-bin:$PATH
export CROSS_COMPILE=/home/juwon/ridi/android-sources/nxp-o8.0.0_1.0.0-ga/prebuilts/gcc/linux-x86/arm/arm-linux-androideabi-4.9/bin/arm-linux-androideabi-

KROOT=/home/juwon/ridi/android-sources/nxp-o8.0.0_1.0.0-ga/vendor/nxp-opensource/kernel_imx
KOUT=/media/juwon/build/android-out/e70q10_reference/target/product/e70q10/obj/KERNEL_OBJ
WIFI=/home/juwon/ridi/reference-sources/tolino-epos/kernel_imx/drivers/net/wireless/rtl8189fs

make -C "$KROOT" O="$KOUT" \
    ARCH=arm CROSS_COMPILE="$CROSS_COMPILE" HOSTCFLAGS=-fcommon \
    imx6sl-e70q10.dtb

make -C "$KROOT" O="$KOUT" \
    ARCH=arm CROSS_COMPILE="$CROSS_COMPILE" HOSTCFLAGS=-fcommon \
    M="$WIFI" CONFIG_RTL8189FS=m -j6 modules
```

Expected module:

```text
reference-sources/tolino-epos/kernel_imx/drivers/net/wireless/rtl8189fs/8189fs.ko
```

## RAM-only test

Use the new zImage and DTB in a one-shot `fastboot boot` image.  After Android
ADB returns:

```sh
adb push 8189fs.ko /data/local/tmp/8189fs.ko
adb shell 'insmod /data/local/tmp/8189fs.ko'
adb shell 'dmesg | grep -Ei "8189|rtl|mmc2|sdio" | tail -n 80'
adb shell 'ip link show wlan0'
adb shell 'iw dev wlan0 scan | sed -n "1,120p"'
```

The first test only verifies enumeration and scanning.  Do not connect to an
access point until probe, suspend, unload, and front-light operation have been
checked together.

## Android 8 follow-up

The clean AGL image already contains `iw` and the Wi-Fi permission feature.
Framework Wi-Fi, `wpa_supplicant`, the module installation path, init loading,
SELinux, and power policy still need device-product integration after the
kernel hardware test succeeds.

## Hardware validation (2026-07-29)

The Linux 4.9 RAM boot enumerated SDIO function `024c:f179` on USDHC3 as
`mmc2:0001:1`. The external `8189fs.ko` loaded with matching module version
information, downloaded its embedded 8188F firmware, created `wlan0`, and
successfully scanned multiple 2.4 GHz access points. Bringing `wlan0` down and
unloading the module also completed without a surprise-removal or kernel error.

No access-point credentials were installed during this hardware-only test.
