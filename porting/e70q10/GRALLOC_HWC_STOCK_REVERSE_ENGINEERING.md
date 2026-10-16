# RIDI Paper Pro stock gralloc/HWC reverse engineering and Oreo proposal

## Scope

This report covers the two stock Android 4.4.2 HALs requested for the Android
8.0 port:

- `files/system/lib/hw/gralloc.imx6.so`
- `files/system/lib/hw/hwcomposer.imx6.so`

There is no separate `framebuffer.imx6.so` in the stock image. The framebuffer
HAL is the `GRALLOC_HARDWARE_FB0` device implemented inside
`gralloc.imx6.so`. `hwcomposer_fsl.imx6.so` is used below only to identify the
subordinate compositor selected by the `hwcomposer.imx6.so` wrapper.

Analyzed stock SHA-256 values:

| Binary | SHA-256 |
| --- | --- |
| `gralloc.imx6.so` | `34dde84ae00f147878e6c8e0cd89d751361ed3f39325ebf3a839db3f954382db` |
| `hwcomposer.imx6.so` | `c32f102acfe442bccab96c6c768f29e9cf9a99cf7c88cf5cd70f8f00a0007d37` |
| `hwcomposer_fsl.imx6.so` | `e2df65b0b3d6f500ffa40729ab6c3871f00aaa75fa6e54ecce8f4453a789f70c` |

## Conclusion

The stock design has a clear division of responsibility:

1. SurfaceFlinger produces the final RGB565 framebuffer target and the E Ink
   rectangle/policy metadata.
2. `hwcomposer.imx6.so` selects the final framebuffer-target layer and calls
   the framebuffer device's `post()` on every presentation. It does not decide
   the waveform and does not suppress a frame because a handle was reused.
3. The framebuffer half of `gralloc.imx6.so` page-flips or copies the final
   target, consumes the rectangle list, groups compatible overlapping regions,
   translates the packed policy to EPDC fields, and issues the update ioctls.
4. Android VSYNC is a separate logical scheduling signal. It is not EPDC
   update completion.

The best Oreo baseline is therefore a minimal HWC 1.5 framebuffer-target
bridge plus an E Ink-aware framebuffer/gralloc presentation backend. Porting
the FSL G2D composition heuristics into the primary path would add work without
matching stock behavior.

## Recovered stock gralloc/framebuffer behavior

### One binary implements both HAL roles

The dynamic symbols include allocator/mapper entry points as well as
`fb_device_open()` and `mapFrameBufferLocked()`. The module allocates generic
buffers through ION, but maps fb0 directly for framebuffer buffers. It imports
no userspace cache-flush API.

The normal stock display is 1872x1404 RGB565 with a kernel stride of 1888
pixels and three 1404-line pages. A framebuffer-backed target therefore uses
page flipping without a full-screen userspace copy.

### `fb_post()` always presents the supplied target

Disassembly of the stock post path shows two branches:

- A handle carrying the framebuffer flag is locked/mapped if required, its
  page is selected with `FBIOPAN_DISPLAY` (`0x4606`), and the EPDC update path
  is called.
- A generic handle is locked, copied into the mapped framebuffer, and sent to
  the same EPDC path.

There is no framebuffer-diff pass and no same-handle early return in stock
`fb_post()`. Reusing a BufferQueue slot is not evidence that its pixels are
unchanged.

### EPDC initialization

During framebuffer initialization stock selects:

- `AUTO_UPDATE_MODE_REGION_MODE` with ioctl `0x4004462d`;
- `UPDATE_SCHEME_QUEUE_AND_MERGE` with ioctl `0x40044632`.

This means userspace explicitly submits update regions while the kernel is
allowed to queue and merge compatible work.

### Rectangle-list semantics

The input is a linked list of 24-byte records:

```text
int left;
int top;
int right;
int bottom;
uint32_t packed_policy;
node *next;
```

Stock clamps the coordinates to the physical display. Compatible rectangles
are merged when they overlap and have the same packed policy. A policy change
or a disjoint rectangle flushes the accumulated region before processing the
next record. Every consumed node is freed.

When the list pointer is null, stock submits a full-display fallback using its
default automatic policy. It does not interpret null metadata as "the buffer
is unchanged".

### Exact update ABI

The update routine builds a 64-byte `mxcfb_update_data` and uses:

| Operation | ioctl |
| --- | --- |
| Send region | `MXCFB_SEND_UPDATE`, `0x4040462e` |
| Wait for marker | `MXCFB_WAIT_FOR_UPDATE_COMPLETE`, `0xc008462f` |

It sets `temp = TEMP_USE_AMBIENT` (`0x1000`). A NOWAIT request uses marker
zero. A WAIT request allocates a monotonically increasing nonzero marker and
then waits for that marker. A failed send sleeps 300 ms and retries; the stock
binary has no useful retry bound.

The final gralloc-side packed-policy decoding recovered from instructions is:

| Packed field | Stock action |
| --- | --- |
| Waveform low nibble `1,2,3,4,6,7` | pass that waveform index |
| Waveform low nibble `5` | pass `WAVEFORM_MODE_AUTO` (`0x101`) |
| Bit `0x20` | `UPDATE_MODE_FULL`; otherwise partial |
| Bit `0x40` | allocate marker and wait |
| Bit `0x200` | `EPDC_FLAG_ENABLE_INVERSION` (`0x1`) |
| Bit `0x400` | `EPDC_FLAG_FORCE_MONOCHROME` (`0x2`) |
| Bit `0x100` with waveform 1 or 4 | dithering flag `0x2000` |
| Bit `0x100` with another waveform | dithering flag `0x4000` |

These are the values arriving at stock gralloc, after the stock framework's
application-facing View mode has been translated. The Oreo compatibility API
has more application enum values (ANIM, A2, GL16, REAGL and REAGLD), so it
must retain one explicit application-mode-to-kernel-waveform translation and
must not pass all View low nibbles to the kernel verbatim.

## Recovered stock HWC behavior

### `hwcomposer.imx6.so` is a wrapper

The wrapper first tries `hwcomposer_viv` and falls back to `hwcomposer_fsl`.
On i.MX6 SoloLite the FSL path is the expected subordinate implementation.
The wrapper owns display discovery, blanking, hotplug state and the VSYNC
thread.

The subordinate `hwcomposer_fsl.imx6.so` contains G2D helpers such as
`hwc_composite()`, `hwc_updateSwapRect()` and `hwc_hasSameContent()`. Those
helpers do not change the recovered primary presentation boundary: the wrapper
selects the last `HWC_FRAMEBUFFER_TARGET`, transfers the pending E Ink list to
gralloc, clears its local list pointer, and calls the framebuffer device's
`post()` callback.

Consequently, `hwc_hasSameContent()` is not a valid reason for Oreo's final
presentation path to skip `fb_post()`. At most it is a subordinate composition
optimization.

### VSYNC is independent from EPDC completion

The wrapper contains both timer and framebuffer implementations:

- `performFakeVSync()` calculates the next absolute deadline, sleeps with
  `clock_nanosleep()`, and invokes SurfaceFlinger's VSYNC callback.
- `performVSync()` calls ioctl `0x80084620`, receives a 64-bit timestamp and
  invokes the same callback.

The Netronix stock kernel defines this command as
`_IOR('F', 0x20, unsigned long long)`. Its EPDC implementation delays at a
logical 15 Hz cadence and returns a timestamp. This ABI differs from the NXP
Oreo header's `_IOW(..., uint32_t)` command (`0x40044620`). The commands are
not interchangeable.

The stock kernel implementation uses a blocking delay rather than a physical
EPDC scanout interrupt. Oreo should therefore use a userspace timer and should
not forward-port the stock kernel's busy-wait implementation. The stock
wrapper's invalid-refresh fallback is 15 Hz.

## Audit of the current Android 8 implementation

The existing Oreo work already has the correct major pieces:

- HWC 1.5 is advertised so standard damage metadata is available.
- application layers are returned as `HWC_FRAMEBUFFER` in the stock path;
- the final framebuffer target is RGB565, framebuffer-backed and posted on
  every `set()`;
- the target acquire fence is waited and closed;
- EPDC policy and update submission live at the framebuffer/gralloc boundary;
- timer-backed VSYNC avoids the incompatible EPDC VSYNC ioctl;
- the framebuffer-target dirty region is already captured inside
  SurfaceFlinger before display composition.

The following differences should be addressed before adding more compositor
optimizations.

### P0: use framebuffer-target damage in the stock path

`SurfaceFlinger_hwc1.cpp` already passes its authoritative display dirty
region to `setFramebufferTargetDamage()`. That region contains newly exposed
pixels when a layer moves, closes or stops covering an area.

However, the current stock branch of `set_epdc_damage()` ignores that target
region and recomputes one bounding rectangle from per-layer producer damage.
Producer damage cannot describe a layer that disappeared from the current
list, and geometry-change-to-full-screen is unnecessarily expensive.

Change the stock path to use `collect_target_damage()` first:

- `TARGET_DAMAGE_VALID`: submit exactly those screen-space rectangles;
- `TARGET_DAMAGE_NONE`: submit no EPDC update;
- `TARGET_DAMAGE_UNKNOWN`: conservative full screen, normally only for the
  first/forced frame;
- `TARGET_DAMAGE_ABSENT`: fall back to transformed per-layer damage only as a
  compatibility path.

Do not transform framebuffer-target damage a second time. It is already in
physical display coordinates.

### P0: distinguish no damage from missing/unknown damage

The current framebuffer stock policy treats `missing_damage` as a quality
cleanup and may convert it to full-screen GC16 plus a synchronous wait. If HWC
leaves the one-shot rectangle unset for an idle frame, this turns the absence
of work into the most expensive panel operation.

Carry a three-state value to the framebuffer backend:

```text
UNKNOWN  -> one conservative full refresh
NONE     -> no MXCFB_SEND_UPDATE
REGIONS  -> submit the provided regions
```

Stock's null-list full fallback is useful as a corruption-safety fallback, but
it must not also be the encoding for HWC 1.5's explicit empty damage.

### P0: preserve a region list instead of one union rectangle

The current `setUpdateRect()` transport collapses all work into one bounding
box. Two small dirty areas at opposite corners can therefore energize almost
the whole panel. Stock preserves multiple records and only merges compatible,
overlapping regions.

Add a private, versioned HWC-to-framebuffer operation such as
`setUpdateRegions(regions, count, policy, damage_state)`. Store a bounded copy
inside `fb_context_t` and consume it exactly once in the matching `post()`.
Keep `setUpdateRect()` as the single-region compatibility fallback.

The backend should:

1. clip and align each region;
2. discard empty regions;
3. merge only overlapping/adjacent regions with compatible policy;
4. cap the list size and union the cheapest pair when the cap is exceeded;
5. submit each remaining region with the same frame policy.

### P0: do not silently lose damage when the EPDC queue is full

Stock retries forever, which is unsafe, while the current port has a finite
retry count but ultimately allows `fb_post()` to return success after the
refresh helper has failed. That can leave the new framebuffer page selected
without the corresponding panel update.

Use bounded backpressure without dropping semantic damage:

- retry only `EBUSY`, `ENOMEM` and `EAGAIN` with a short bounded delay;
- return permanent errors immediately;
- on exhaustion, union the failed regions into a pending-damage accumulator;
- include pending damage in the next successful submission;
- after repeated failures, force one full GC16 recovery and expose a rate-
  limited error counter in `dumpsys`/logs.

### P1: keep the direct RGB565 path, but retain a diagnostic copy fallback

Rejecting non-framebuffer targets is useful for detecting a broken production
configuration. Stock nevertheless has a generic lock-and-copy fallback. Keep
that fallback behind a debug/bring-up property so a BufferQueue allocation
regression produces a slow visible frame and a clear error rather than a black
screen. It must not become the normal path.

### P1: make logical VSYNC E Ink-aware

The current Oreo default is timer-backed 60 Hz. That improves touch cadence
but can wake SurfaceFlinger much more often than a SoloLite E-reader needs.
Start with 30 Hz for usability, allow 15 Hz as the stock/power profile, and
consider 60 Hz only during an active touch/animation burst. Physical EPDC
submission remains damage-driven and independent of this logical cadence.

Never call the stock `0x80084620` command against the unmodified Oreo ioctl
definition, and never treat update-complete as VSYNC.

### P1: keep waveform policy explicit and testable

Maintain one translation table from the application ABI to the actual E70Q10
waveform indices:

| Application mode | E70Q10 kernel waveform |
| --- | --- |
| DU | 1 |
| GC16 | 2 |
| GC4 | 3 (or documented GL16 fallback if the loaded waveform lacks GC4) |
| ANIM | DU or A2, chosen explicitly |
| A2 | 6 |
| GL16 | 3 |
| REAGL/GLR16 | 4 |
| REAGLD/GLD16 | 5 |
| AUTO | 257 |

Do not overload application enum 5 (A2/AUTO compatibility alias) without also
checking the automatic-mode bit. Log both the packed request and resolved
kernel waveform for the first frames and on policy changes.

The stock instruction stream does **not** translate packed combine bit `0x80`
to `EPDC_FLAG_GROUP_UPDATE`; it performs compatible rectangle merging in
userspace. The current Oreo `decode_eink_flags()` does translate it to kernel
flag `0x400`. Remove that translation from the stock-compatible profile unless
panel tests prove that the kernel group-update behavior is required. Likewise,
stock chooses Y1/Y4 dithering from the resolved waveform when packed dither bit
`0x100` is set; it does not consult the Oreo-only `0x800` color selector in the
recovered gralloc routine. Keep these extensions behind an explicit profile
instead of silently changing the stock policy.

### P2: simplify the production HWC

The experimental local PxP/G2D/software composition path is valuable for
diagnosis but should not be the production default. The production HWC should
remain small:

```text
prepare: mark application layers HWC_FRAMEBUFFER
set:     consume fences -> attach policy/damage -> post framebuffer target
vsync:   timer callback only
```

This removes handle/content heuristics from the critical path and keeps all
waveform, marker and queue policy in one backend.

## Proposed implementation sequence

1. Fix the HWC stock path to consume framebuffer-target damage and represent
   NONE separately from UNKNOWN.
2. Replace the one-rectangle private call with a bounded region-list call.
3. Make EPDC submission return status and add pending-damage recovery.
4. Verify direct three-page RGB565 posting and same-handle reposting.
5. Tune logical VSYNC (30 Hz baseline, 15 Hz power mode) independently.
6. Only then tune waveform selection, periodic cleanup and optional smart
   diff/coalescing behavior.

## Verification matrix

Log the page, damage state, region count, resolved waveform, update mode,
marker, retry count and latency for the following cases:

| Test | Required result |
| --- | --- |
| First boot frame | one full GC16 recovery |
| Same handle, changed pixels | update is still submitted |
| Explicit empty damage | no EPDC ioctl |
| Moving clock/dialog | old and new bounds both refreshed |
| Two distant small regions | remain separate, not a full bounding box |
| Page turn REAGL | partial waveform 4, no forced full refresh |
| A2 animation | waveform 6 and requested monochrome/dither flags |
| Explicit WAIT | nonzero marker and matching completion wait |
| Queue saturation | no lost damage; pending region appears next frame |
| Periodic cleanup | full GC16 occurs only at the configured threshold |
| Suspend/resume | one full recovery, then normal partial updates |

Binary patching the stock `.so` files is not recommended. They target the
KitKat HWC/gralloc ABI and the stock kernel's private VSYNC ioctl. The recovered
behavior should be implemented and tested in the existing Oreo source tree.
