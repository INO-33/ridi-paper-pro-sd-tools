# RIDI PAPER PRO E70Q10 hardware manifest

## Physical package and panel markings

These identifiers were reported from a disassembled unit on 2026-07-22.

| Function | Marking |
| --- | --- |
| SoC | Freescale `MCIMX6L8DVN10AB` (i.MX6 SoloLite, Cortex-A9, 1 GHz) |
| RAM | Nanya `NT6TL256T32BQ-G0` (1 GiB LPDDR2) |
| eMMC | Samsung `KLM8G1GEME-B041` (8 GB) |
| System PMIC | RICOH `RC5T619` (`1010 7309QG`) |
| E Ink PMIC | Texas Instruments `TPS65185` (`T1 7AI AHVZ G4`) |
| Wi-Fi | Realtek `RTL8189FTV` (`H4102G1 GH15B`) |
| E Ink panel | E Ink `ED078KH3 U2-ZA` |
| Battery | 3.7 V Li-polymer, 1200 mAh, approximately 1.7 x 80 x 98 mm |

## Correlation with extracted stock data

- hwcfg PCB: `E70Q10`, revision `0x10`, level A
- CPU: `mx6sl`; RAM: 1024 MB LPDDR2; internal flash: eMMC
- Display: 7.8-inch bottom EPD, 1872x1404, 16-bit bus
- Display controller: MX6SL + TPS65185; system PMIC/RTC: RC5T619
- Wi-Fi: RTL8189; extracted stock module: `8189fs.ko`
- Touch: CYTT21X family; runtime device is CYTTSP5 at I2C1 address 0x24
- Front light: LM3630

## Physical buttons

The mapping below was verified on the running stock 4.4.2 kernel through
`debugfs` GPIO labels, IRQ names and `/dev/input/event0`.

| Function | i.MX6SL GPIO | Global GPIO | Stock Linux event |
| --- | --- | ---: | --- |
| Right quick button (`TP_ON`) | `GPIO3_IO24` | 88 | `KEY_F1` (59) |
| Page right 1 | `GPIO3_IO26` | 90 | stock page key |
| Page left 1 | `GPIO3_IO30` | 94 | stock page key |
| Page right 2 | `GPIO4_IO00` | 96 | stock page key |
| Page left 2 | `GPIO4_IO02` | 98 | stock page key |
| Power | `GPIO5_IO08` | 136 | `KEY_POWER` (116) |

The Android 8 device tree retains `KEY_F1` for the quick button, matching the
stock kernel ABI. Its device keylayout maps key 59 to Android `BACK`; the
DOWN/UP duration remains available for a future long-press quick-settings
policy. Page-button mappings are intentionally unchanged.

The public Netronix/Tolino kernel does not name ED078KH3 separately. For hwcfg
resolution code 8 (1872x1404), it selects `panel_modes[9]`, whose software name
is `ED078KH1`. This timing profile is therefore retained as the compatibility
name while the physical panel is documented as ED078KH3 U2-ZA.
