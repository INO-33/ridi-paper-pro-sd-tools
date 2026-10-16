# RIDI PAPER PRO (E70Q10) Android 8 port

Target baseline: NXP Android `O8.0.0_1.0.0 GA` (`android-8.0.0_r25`) with
the NXP `o8.0.0_1.0.0-ga` Linux/U-Boot tag.  The SoC is i.MX6SoloLite,
1 GiB LPDDR2, and the stock kernel is a non-DT 3.0.35 board-file kernel.

## Confirmed hardware

- PCB: Netronix E70Q10, revision 0x10
- Display: 7.8-inch 1872x1404 16-bit E Ink, i.MX6SL EPDC, TPS65185 PMIC
- Waveform: stock raw waveform retained in `stock-blobs/critical/waveform.bin`
- Touch: Cypress CYTTSP5/CYTT21X at I2C bus 1 address 0x24;
  IRQ GPIO5_6 (global 134), reset GPIO5_13 (global 141)
- Front light: LM3630A at I2C bus 1 address 0x38
- Power/RTC: Ricoh RC5T619 at I2C bus 2 address 0x32
- Wi-Fi: RTL8189FS over SDIO; stock module is kernel-version-specific
- Storage: eMMC plus external microSD
- Keys: GPIO 90, 94, 96 and 98; touch/power-related GPIOs 88 and 136
- Hall sensor: TLE4913

## Porting rule

The KitKat `.ko` and HAL `.so` files are evidence/reference, not binaries that
can normally be loaded by the 4.9/Oreo stack.  Port their source-level behavior
or use the NXP Oreo implementation.  Reuse only data blobs whose format is not
kernel/Android ABI-dependent: waveform, Wi-Fi firmware/configuration, touch
configuration, keylayout/IDC, hardware configuration and calibration tables.

The first boot target is a minimal `userdebug` image with serial/ADB, framebuffer,
eMMC and touch.  Add EPDC waveform loading, front light, PMIC/charger, Wi-Fi and
suspend/resume one subsystem at a time.  Do not replace the stock bootloader
until a RAM-booted kernel and a recovery restore path are proven.

## Boot protocol

The stock U-Boot passes ATAGs and has no usable runtime DT.  For the first 4.9
test kernel, enable `CONFIG_ARM_APPENDED_DTB` and `CONFIG_ARM_ATAG_DTB_COMPAT`,
then append the compiled E70Q10 DTB to `zImage`.  This avoids changing U-Boot.

The first NXP 4.9 engineering build completed successfully. Its untrimmed
`zImage` is 9,972,368 bytes and the appended-DTB image is 9,999,502 bytes, so it
does **not** fit the stock 6 MiB boot partition. The files in `artifacts/` are
build evidence and a RAM-boot development input, not flashable images.
