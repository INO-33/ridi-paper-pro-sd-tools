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
# Fixed external controller. Valid SD control enables selected automatic updates.
for n in 1 2 3 4 5 6 7 8 9 10; do
 [ -b /dev/mmcblk1p1 ] && break
 $bb sleep 1; $bb mdev -s
done
$bb mount -t vfat -o ro,nosuid,nodev /dev/mmcblk1p1 /mnt/sd || echo 'SD absent: insert FAT32 SD, mount manually read-only.'
G=/sys/kernel/config/usb_gadget/e70q10_updater
$bb mkdir -p "$G/strings/0x409" "$G/configs/c.1/strings/0x409" "$G/functions/acm.GS0"
echo 0x1fc9 >"$G/idVendor"
echo 0x0135 >"$G/idProduct"
echo PP1A1GK166561 >"$G/strings/0x409/serialnumber"
echo RIDI >"$G/strings/0x409/manufacturer"
echo 'E70Q10 RAM updater' >"$G/strings/0x409/product"
echo 'Updater console' >"$G/configs/c.1/strings/0x409/configuration"
$bb ln -s "$G/functions/acm.GS0" "$G/configs/c.1/acm.GS0"
for x in /sys/class/udc/*; do [ -e "$x" ] && { echo "${x##*/}" >"$G/UDC"; break; }; done
# The worker logs to RAM without blocking on an unopened USB terminal.
if [ -f /mnt/sd/e70q10-update/update.conf ]; then
 /bin/auto-update /mnt/sd/e70q10-update >/run/emmc-auto.log 2>&1 &
else
 echo 'AUTO STOP: SD update.conf missing. Console only.' >/run/emmc-auto.log
fi
while :; do
 if [ -c /dev/ttyGS0 ]; then
  $bb stty -F /dev/ttyGS0 sane icrnl echo opost onlcr -ixon -ixoff
  echo 'RAM UPDATER: SD-selected automatic update. Status: cat /run/emmc-auto.log' >/dev/ttyGS0
  /bin/console-shell </dev/ttyGS0 >/dev/ttyGS0 2>&1
 fi
 $bb sleep 2; $bb mdev -s
done
