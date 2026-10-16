#!/bin/busybox sh
export PATH=/bin
bb=/bin/busybox
$bb mount -t devtmpfs devtmpfs /dev
$bb mount -t proc proc /proc
$bb mount -t sysfs sysfs /sys
$bb mount -t tmpfs tmpfs /run
$bb mount -t tmpfs tmpfs /tmp
$bb mkdir -p /sys/kernel/config /mnt/sd
$bb mount -t configfs configfs /sys/kernel/config
$bb mdev -s
# Fixed external controller, no fallback to internal media. Never auto-install.
for n in 1 2 3 4 5 6 7 8 9 10; do
 [ -b /dev/mmcblk1p1 ] && break
 $bb sleep 1; $bb mdev -s
done
$bb mount -t vfat -o ro,nosuid,nodev /dev/mmcblk1p1 /mnt/sd || echo 'SD absent: insert FAT32 SD, mount manually read-only.'
G=/sys/kernel/config/usb_gadget/e70q10_installer
$bb mkdir -p "$G/strings/0x409" "$G/configs/c.1/strings/0x409" "$G/functions/acm.GS0"
echo 0x1fc9 >"$G/idVendor"
echo 0x0135 >"$G/idProduct"
echo PP1A1GK166561 >"$G/strings/0x409/serialnumber"
echo RIDI >"$G/strings/0x409/manufacturer"
echo 'E70Q10 RAM installer' >"$G/strings/0x409/product"
echo 'Installer console' >"$G/configs/c.1/strings/0x409/configuration"
$bb ln -s "$G/functions/acm.GS0" "$G/configs/c.1/acm.GS0"
for x in /sys/class/udc/*; do [ -e "$x" ] && { echo "${x##*/}" >"$G/UDC"; break; }; done
while :; do
 if [ -c /dev/ttyGS0 ]; then
  $bb stty -F /dev/ttyGS0 raw -echo
  echo 'RAM INSTALLER READY. No writes on boot. Run: installer check /mnt/sd/e70q10-install' >/dev/ttyGS0
  /bin/sh </dev/ttyGS0 >/dev/ttyGS0 2>&1
 fi
 $bb sleep 2; $bb mdev -s
done
