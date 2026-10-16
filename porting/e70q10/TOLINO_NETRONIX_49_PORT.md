# E70Q10: Tolino/Netronix semantics on the NXP 4.9 kernel

The NXP Oreo kernel remains the API and SoC framework base, but the E70Q10
board behaviour is taken from the published Tolino Epos/Netronix 3.0.35 tree
and the stock RIDI hardware configuration.  The old board file is a hardware
reference, not a file that can be compiled unchanged against Linux 4.9.

## Verified identity

- Netronix PCB 67 family (`E70Q1X`), RIDI model `E70Q10`
- i.MX6 SoloLite, 1 GiB RAM with the top 6 MiB reserved by stock U-Boot
- Physical panel label: E Ink `ED078KH3 U2-ZA`, 1872 x 1404, 16-bit EPDC bus
- Netronix software timing profile: `ED078KH1` (the public tree maps hwcfg
  resolution code 8, including this 7.8-inch bottom-panel configuration, to
  the profile at `panel_modes[9]`)
- TPS65185 E Ink PMIC at I2C address 0x68
- RC5T619 system PMIC at I2C address 0x32
- Stock waveform SHA-256:
  `3b9558e462b71d82c56763852fc3421e93b445edc22700200f92dd9b39b31089`

## Port matrix

| Netronix behaviour | NXP 4.9 before port | E70Q10 state |
| --- | --- | --- |
| Netronix 1872x1404 (`ED078KH1`) timings and EPDC offsets | No panel entry | Ported exactly; used by physical ED078KH3 |
| Stock `0x19` mode map | Generic modes | Ported (INIT/DU/GC16/GL16/REAGL/REAGLD/A2/GC4) |
| Waveform `luts=0x04` means P5N | Hard-coded P4N | Ported and hardware-verified |
| P5N PxP quantisation | Missing | Ported as `PXP_LUT_AA` |
| P5N histogram thresholds | Missing | Ported |
| 16-LUT restriction in P5N | Present in NXP 4.9 | Retained |
| FIFO priority 200/255/254 | Generic 100/200/100 | Ported |
| 100 us EPDC reset settling | Missing | Ported |
| VCD/ACD/XWI appended sections | Copied into waveform DMA data | Safely parsed and split |
| TRT upper sentinel byte | Allocated one byte short | Corrected |
| EPDC pad electrical control | Inherited from U-Boot | Netronix `0x110b0`, EPD_LV clear |
| TCE display bus | Generic 8-bit / 4 pixels per SDCLK | E70Q10 16-bit / 8 pixels per SDCLK |
| EPDC reset order | Generic reset release | Netronix clock-domain-safe order and delays |
| TPS65185 rails and up/down sequence | Generic/missing initially | Ported and hardware-verified |
| RC5T619 regulators | Missing initially | Ported and hardware-verified |
| Manual update mode deferred-I/O | Uninitialised work exposed | Corrected |

## Stock waveform structure verified on hardware

The E70Q10 file has `mode_version=0x19`, `luts=0x04`, `awv=3`, eight waveform
modes and fourteen temperature ranges.  The 4.9 driver reports:

```
core=4639320 VCD=1792 ACD=802 XWI=31
```

These sizes exactly match the offsets encoded in the stock binary.  GC16 at
the room-temperature range has a zero VCOM delta, so dynamic VCD VCOM
adjustment is not required for the current basic full-refresh validation.
The VCD is retained for the future Android display update path.

## Hardware result: 2026-07-22

The second Tolino/Netronix RAM-boot test produced a uniform full-white panel.
The successful kernel reported `16-bit SDDO`, `8 pixels/SDCLK`, TCE control
`0x00040007`, a completed update with no collision, and clean automatic panel
power-down.  There were no EPDC underrun messages or kernel warnings.  This
confirms the basic panel timings, EPDC bus width, stock waveform parsing, PMIC
sequence and reset ordering without writing any internal eMMC partition.

A small black square remained at the physical upper-right corner.  The same
artifact was present in earlier stripe tests, all of which ended with the same
logical `(0,0)` 1x1 partial update.  Because EPDC/PxP updates are alignment-
expanded and the display is rotated, this is provisionally treated as a test
artifact.  The grayscale test deliberately uses only a full-screen update to
distinguish it from a persistent panel defect.

The next bounded hardware check is a single full-screen GC16 update containing
16 vertical grayscale bars.  The rightmost bar is completely white so the
upper-right artifact can be checked without a deliberate corner mark.  It
validates pixel packing, data-lane order and grayscale conversion before
Android SurfaceFlinger/HAL integration.

The v3 hardware test completed on 2026-07-22 and displayed all sixteen bands
cleanly with a smooth black-to-white progression.  The former upper-right black
square was absent after stock boot and the full-screen test; it was residue from
the aligned/rotated 1x1 diagnostic update, not physical panel damage.  EPDC bus
lane order, RGB565 conversion, PxP P5N processing and the stock GC16 waveform
are therefore hardware-verified.

The final v3 RAM-boot image has SHA-256
`efa5ae021ab56786a556e7fd16ee191b39d58db3cedaef733e4497564cb2652d`.

## Remaining integration work

- Integrate the final kernel/DTB and stock waveform into the Android 8 boot
  and vendor images.
- Forward-port the E70Q10 touch, frontlight and Wi-Fi integration required by
  Android userspace.
- Implement the Android 8 E Ink update HAL/ioctl policy, including Regal mode
  selection.  The proprietary Regal image-processing implementation is not
  present in the public Tolino source; its public stubs return `-1`.
- Add suspend/resume validation and only then consider a flashable image.

All current device tests use `fastboot boot` only.  No kernel or partition has
been flashed to internal eMMC.
