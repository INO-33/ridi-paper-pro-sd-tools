# Partition constraints and recovery map

The stock internal eMMC has exactly 15,273,600 sectors (512 bytes each), or
7,820,083,200 bytes.  It uses an MBR extended-partition layout.

| Node | Start sector | Sectors | Stock role | Approx. size |
|---|---:|---:|---|---:|
| p1 | 2,048 | 12,224 | boot | 6 MiB |
| p2 | 38,912 | 65,536 | recovery | 32 MiB |
| p3 | 104,448 | extended container | logical p5-p9 | - |
| p4 | 15,204,352 | 65,536 | internal FAT/media | 32 MiB |
| p5 | 106,496 | 786,416 | system | 384 MiB |
| p6 | 892,928 | 786,416 | cache | 384 MiB |
| p7 | 1,679,360 | 13,498,368 | userdata | 6.44 GiB |
| p8 | 15,179,776 | 16,368 | device | 8 MiB |
| p9 | 15,196,160 | 8,176 | misc | 4 MiB |

There is an intentional gap between p1 and p2.  Do not assume p1 can simply be
extended without checking how stock U-Boot locates boot/recovery.

NXP Oreo introduces a vendor partition, while this layout has no usable vendor
space.  A 6 MiB boot partition may also be too small for a Linux 4.9 zImage,
ramdisk and appended DTB, and 384 MiB system is too small for a normal Oreo
product image.  Consequently:

1. Keep the stock partition table until a kernel can be RAM-booted and serial or
   ADB recovery is proven.
2. Make the first kernel/ramdisk as small as possible and test bootloader loading
   behavior without flashing.
3. Measure actual built `boot.img`, `system.img` and `vendor.img` before defining
   a replacement MBR.  Do not guess final sizes.
4. Preserve p9/misc semantics and the raw Netronix regions before sector 2,048.
5. Any repartition operation must be paired with the complete split eMMC backup
   and an independently booted rescue environment.

A likely final direction is boot >=16-32 MiB, recovery 32 MiB, system around
1 GiB, vendor 256-512 MiB, a smaller cache, and userdata using the remainder.
This is a planning range, not a flashable layout.
