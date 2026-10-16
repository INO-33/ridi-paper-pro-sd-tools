# E70Q10 next boot

The 2026-07-29 failed attempt wrote Android sparse images directly with `dd`.
The kernel and RAM ADB worked, but `/system/bin/sh` was absent because sparse
images are not mountable block-device filesystems.

Correct raw ext4 images are now prepared:

- `/media/juwon/build/android-out/e70q10_reference_agl_stockpath/target/product/e70q10/system.raw.img`
- `/media/juwon/build/android-out/e70q10_reference_agl_stockpath/target/product/e70q10/vendor.raw.img`

The stock-compatible, DT-appended RAM boot image is:

- `/home/juwon/ridi/porting/e70q10/e70q10-agl-stockpath-current-ramboot.img`

## Tomorrow

1. Force-reboot to stock if the device is still in the RAM diagnostic state.
2. Remove the SD and connect it to the PC.
3. Confirm its device name with `lsblk`.
4. For `/dev/sda`, run:

```bash
cd /home/juwon/ridi
CONFIRM_E70Q10_SD=/dev/sda \
  android-sources/nxp-o8.0.0_1.0.0-ga/device/ridi/e70q10/tools/write_sd_images.sh \
  /dev/sda
```

5. Put the SD back into the reader and RAM-boot only the stock-compatible
   image above. Do not use the ordinary build output `boot.img`.
