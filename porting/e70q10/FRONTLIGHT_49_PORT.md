# E70Q10 LM3630A front-light port

## Hardware and stock interface

- Controller: TI LM3630A
- Linux bus/address: I2C2 at `0x38` (stock calls the controller `imx-i2c.1`)
- Channel A stock full-scale current: `4`
- Channel B stock full-scale current: `7`
- Combined backlight: `/sys/class/backlight/lm3630a_led`
- Brightness: `0..100`
- Colour mix: `color`, `0..10`
- Stock register values while off:
  - configuration `0x18`
  - boost `0x63`
  - filter strength `0x03`
  - current, brightness, and control registers `0`

## Linux 4.9 implementation

The NXP LM3630A driver was extended instead of copying the complete Tolino
driver.  The latter depends on Netronix runtime hardware configuration and
firmware-table globals which do not exist in the NXP 4.9 tree.

The 4.9 implementation adds:

- DT matching for `ti,lm3630a`;
- safe, light-off probe and shutdown;
- the stock current limits and register setup;
- `lm3630a_led` with 0..100 brightness;
- `color` and read-only `max_color` attributes;
- the public Tolino channel-A brightness curve;
- suspend/resume handling through the backlight core.

The initial colour mixing is safe but not yet optically calibrated.  After the
basic hardware test succeeds, the complete Tolino/RIDI 11-by-100 two-channel
table can replace the small mixer without changing the userspace interface.

## RAM-only test order

Never write this test kernel to eMMC.

1. Boot the 4.9 image in RAM with the external-SD watchdog/logging setup.
2. Confirm probe:

   ```sh
   dmesg | grep -i lm3630
   ls -l /sys/class/backlight/lm3630a_led
   ```

3. Test the lowest brightness on channel A:

   ```sh
   echo 0 > /sys/class/backlight/lm3630a_led/color
   echo 1 > /sys/class/backlight/lm3630a_led/brightness
   ```

4. Turn it off before changing colour:

   ```sh
   echo 0 > /sys/class/backlight/lm3630a_led/brightness
   ```

5. Test channel B and then the midpoint, always starting at brightness 1:

   ```sh
   echo 10 > /sys/class/backlight/lm3630a_led/color
   echo 1 > /sys/class/backlight/lm3630a_led/brightness
   echo 0 > /sys/class/backlight/lm3630a_led/brightness
   echo 5 > /sys/class/backlight/lm3630a_led/color
   echo 1 > /sys/class/backlight/lm3630a_led/brightness
   ```

Do not begin with brightness 100.  Increase in small steps only after both
channels turn off cleanly.

## Android 8 follow-up

The kernel interface is independent of the Android version.  Android 8 still
needs:

- `hw.backlight.dev=lm3630a_led`;
- system ownership and mode `0660` for `brightness` and `color`;
- an SELinux label/allow rule for the backlight sysfs nodes;
- the i.MX lights HAL fix that permits brightness `0` (the current HAL clamps
  every value below 1 to 1).

## Hardware validation (2026-07-29)

The Linux 4.9 RAM boot probed `lm3630a_led` with brightness range `0..100` and
colour range `0..10`. Channel A was tested at brightness 1 and 16, then returned
to brightness 0. Probe, brightness writes, and shutdown to zero all succeeded.

Those Android files should be changed after the currently running system/vendor
build finishes, so an in-progress build does not consume a mixed source state.
