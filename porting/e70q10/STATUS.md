# E70Q10 Android 8 port status

## Safe recovery baseline

- Complete 7,820,083,200-byte eMMC image: verified across all 30 split files
  with device/host POSIX CRC and host SHA-256.
- Logical `/data` archive: CRC, length and gzip stream verified.
- Emergency restore script: prepared but **never executed**. It is restricted
  to an independent recovery environment and requires an explicit destructive
  confirmation variable.
- No partition, boot, recovery, U-Boot or eMMC content was written during this
  preparation.

## Prepared

- Stock boot/recovery/system/device/misc images and extracted filesystem.
- Stock U-Boot, kernel/config, waveform, NTX firmware/hwcfg/logo, Wi-Fi module
  and configuration, IDC and keylayout references.
- Official Tolino Epos kernel/U-Boot sources used as the closest E70Q10 board
  reference. The stock kernel itself has no runtime DT; it uses a static board
  file and ATAG boot.
- E70Q10 Linux DTS, NXP 4.9 kernel config fragment and exact Netronix
  1872x1404 EPDC mode/timing patch. The physical panel is ED078KH3 U2-ZA;
  Netronix's public code names the shared resolution profile ED078KH1.
- NXP 4.9 `zImage` and DTB compile successfully. The untrimmed appended image is
  9,999,502 bytes, confirming that it cannot be written to the stock 6 MiB boot
  partition.
- Linux 4.9 successfully RAM-boots with its ramdisk moved from the stock
  0x81800000 address to 0x84000000. The original address was overwritten by
  zImage decompressor relocation because the uncompressed Image is about 22 MiB.
- Appended DTB recognition, eMMC and external SD enumeration, SD log writes,
  USB CDC ACM, stock waveform loading and EPDC framebuffer registration are
  verified on hardware.
- Minimal Android product tree under `device/ridi/e70q10`.
- Full pinned NXP Android O8.0.0_1.0.0 GA source checkout.
- RC5T619 support has been added by extending the 4.9 RN5T618 regmap/MFD
  driver with the Tolino-published five-buck/ten-LDO register map. A minimal
  TPS65185 regulator driver now provides DISPLAY/VCOM/V3P3 using the GPIOs
  observed on the stock E70Q10. Both are hardware-verified in RAM-boot tests;
  no eMMC partition was written.
- The RC5T619 probe is now hardware-verified: all five DCDC rails, ten LDOs
  and both RTC LDOs report the expected stock voltages. TPS65185 manual bind
  also verified revision 0x65 and the existing -1560 mV VCOM setting. Its
  automatic probe needed the vendor wake-up settling delay/I2C retry, now
  included in the v3 RAM-test build.
- The v7 RAM test explicitly requested EPDC hardware initialization with
  `FBIOPUT_VSCREENINFO`, waited for waveform setup, and completed a 1x1 update
  at 1872x1404 with collision status 0. The test then blanked the framebuffer;
  DISPLAY and VCOM were disabled and TPS65185 powerup/pwrgood/vcom GPIOs were
  low. Logs are preserved under
  `pmic-test/logs-v7/boot-19700101-000004-1/`.
- The v8 test cleared all 10,813,440 framebuffer bytes to RGB565 white before
  requesting EPDC initialization. The kernel again reported successful full
  initialization and a completed 1x1 update with collision status 0, but the
  physical panel still showed stripes. This rules out stale framebuffer data;
  panel data/control timing, pin configuration and waveform compatibility are
  the next display suspects. The test log is under
  `pmic-test/logs-v8/boot-19700101-000003-1/`.
- A read-only dump of the stock TPS65185 registers confirmed ENABLE=0x20,
  UPSEQ0=0xe1, UPSEQ1=0x00, DWNSEQ0=0x1e, REVID=0x65 and a 1560 mV VCOM
  magnitude. These match the 4.9 bring-up driver's sequencing values.
- The Tolino-port v2 RAM test corrected the missing 16-bit SDDO / 8 pixels per
  SDCLK TCE setting and produced a uniform white panel. The update completed
  without collision, underrun or kernel warning, and automatic panel
  power-down succeeded. A small upper-right black square is being checked as
  the likely aligned/rotated residue of the diagnostic program's final 1x1
  partial update. The prepared v3 test removes that partial update and uses a
  single full-screen 16-step GC16 pattern.
- The v3 RAM test displayed all sixteen grayscale bands cleanly from black to
  white. The upper-right square disappeared, confirming it was an aligned 1x1
  partial-update artifact rather than panel damage. Pixel packing, EPDC data-
  lane order, PxP P5N conversion and the stock GC16 waveform are now verified.

## Still required before any flash

1. Forward-port or replace the CYTTSP5 touch, RC5T619 RTC, LM3630A front-light
   and RTL8189FS Wi-Fi drivers. Stock 3.0.35 `.ko` files cannot be loaded into
   the 4.9 kernel. The minimal RC5T619 regulator and TPS65185 EPDC regulator
   paths are now validated but still need production hardening.
2. Implement the Oreo EPDC userspace/HAL update path. The stock waveform and
   kernel update-completion path are now minimally validated, but full/partial
   refresh modes, temperature selection and repeated-update behavior are not.
3. Verify GPIO polarity and the physical page-key direction on hardware.
4. Resolve the stock partition-size mismatch: boot is about 6 MiB and system is
   384 MiB, which are too small for the normal NXP Oreo layout. Do not repartition
   until a serial console, RAM boot and independent recovery restore are proven.
5. Produce a minimal initramfs/diagnostic kernel and boot it without writing
   internal storage. Confirm UART, eMMC read-only access, EPDC, touch and power
   management in that order.

The generated DTB and kernel are engineering artifacts, not a flashable ROM.
