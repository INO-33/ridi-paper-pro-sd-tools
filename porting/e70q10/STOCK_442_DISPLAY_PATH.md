# RIDI Paper Pro stock 4.4.2 display path

This note records the display architecture recovered from the extracted stock
4.4.2 binaries and the public Tolino Epos/Netronix kernel source. It is the
baseline for the Android 8 port; new display changes should be made only where
the Oreo path first differs from this baseline.

## Evidence

Stock binaries:

- `files/system/lib/libsurfaceflinger.so`
- `files/system/lib/hw/hwcomposer.imx6.so`
- `files/system/lib/hw/gralloc.imx6.so`

Reference kernel:

- `reference-sources/tolino-epos/kernel_imx/drivers/video/mxc/mxc_epdc_fb.c`

The stock HWC device version word is `0x01030001` (HWC 1.3). Its `set()`
implementation selects the final `HWC_FRAMEBUFFER_TARGET` layer and calls the
framebuffer device's `post()` callback with that layer's buffer handle. It does
not import EGL swap functions and it does not CPU-compose application layers.

The stock gralloc `fb_post()` has two paths:

1. A framebuffer-backed handle is page-flipped with `FBIOPAN_DISPLAY`, then
   submitted to the EPDC update routine without a userspace copy.
2. A non-framebuffer handle is locked, copied into the mapped framebuffer with
   `memcpy()`, and then submitted to the same EPDC update routine.

The EPDC routine merges/clamps dirty rectangles, builds `mxcfb_update_data`,
submits `MXCFB_SEND_UPDATE` (`0x4040462e`), and retries a temporarily rejected
submission after a delay. When a synchronous update was requested, it assigns
a nonzero monotonically increasing marker and waits with
`MXCFB_WAIT_FOR_UPDATE_COMPLETE` (`0xc008462f`).

### Dirty rectangles are explicit metadata, not framebuffer diffs

Further disassembly recovered the source of those rectangles. Stock does not
compare the posted framebuffer against a userspace shadow buffer.

- `libgui.so` exports `Surface::addEpdc(hwc_epdc_llist*)` and
  `Surface::freeEpdcList()`.
- `Surface::queueBuffer()` attaches the complete linked list to the
  `QueueBufferInput`.
- `GLConsumer` stores the list and `GLConsumer::getEpdc()` transfers ownership
  to SurfaceFlinger.
- SurfaceFlinger transforms every rectangle through the layer/display
  transform, joins it to the pending display list and clones a final
  24-byte-per-node list for presentation.
- Stock gralloc consumes that list in `fb_post()`. Rectangles with compatible
  mode values are merged; incompatible entries are submitted separately.
- A node contains four rectangle coordinates, a packed update-policy word and
  a `next` pointer. The packed word selects waveform in its low nibble and has
  separate full/partial, synchronous-wait, inversion, monochrome and EPDC flag
  bits.
- If no EPDC list was supplied, stock gralloc submits a full-screen update with
  its default policy. It does not silently skip the frame.

There is also a public `SurfaceComposerClient::einkChangeUpdateMode(unsigned)`
call, backed by a vendor SurfaceFlinger binder method, for changing the global
E Ink update policy.

This explains why a moving clock hand is erased correctly on stock: the
producer supplies damage covering both the old and new drawing bounds, and
SurfaceFlinger transforms that damage into physical display coordinates before
gralloc submits it. Inferring components from the already rotated framebuffer
loses this semantic boundary and is not the stock design.

There is no imported userspace cache-maintenance function in stock gralloc.
The Tolino/Netronix EPDC driver allocates framebuffer memory with
`dma_alloc_writecombine()` and maps it with `pgprot_writecombine()`. Therefore
the stock direct framebuffer path relies on write-combined framebuffer mapping,
not `DMA_BUF_IOCTL_SYNC` or an explicit userspace cache flush.

The HWC stores the callback table registered by SurfaceFlinger. Static
references use callback offset 4 for vsync and offset 8 for HDMI hotplug.
There is no primary-frame `invalidate()` callback from `set()`, `fb_post()`, or
EPDC completion.

## Recovered pipeline

```text
CPU renderer / SurfaceFlinger
        |
        | HWC_FRAMEBUFFER_TARGET (prefer framebuffer-backed RGB565)
        v
stock HWC set()
        |
        | framebuffer_device.post(target handle)
        v
stock gralloc fb_post()
        |
        +-- framebuffer handle: FBIOPAN_DISPLAY, no memcpy
        |
        +-- generic handle: lock + memcpy to mapped fb
        v
Surface/BufferQueue/SF-provided EPDC rectangle list
        |
        | coordinate transform, merge and waveform selection
        |
        | MXCFB_SEND_UPDATE
        | optional nonzero marker + MXCFB_WAIT_FOR_UPDATE_COMPLETE
        v
i.MX6SL EPDC
```

## Captured stock runtime values

The existing untouched-stock capture already contains the remaining runtime
facts, so another device trace is not required:

- fb0: `mxc_epdc_fb`
- physical mode: `1872x1404`
- bpp: `16`
- kernel stride: `3776` bytes = `1888` RGB565 pixels
- virtual size: `1888x4224` (three 1404-line framebuffer pages)
- SurfaceFlinger display target: `1872x1404`, stride `1888`, format `4`
- `EGL_NATIVE_VISUAL_ID`: `4` (`HAL_PIXEL_FORMAT_RGB_565`)
- renderer: `Android PixelFlinger 1.4 / OpenGL ES-CM 1.0`
- display transform: orientation `3`
- HWC list contains a final `HWC_FRAMEBUFFER_TARGET` with format `4`

This proves that stock SurfaceFlinger renders into page-flippable RGB565 fb0
buffers. The normal path therefore performs neither a 32-bit-to-16-bit
conversion nor a full userspace framebuffer copy.

## Consequence for Android 8

The bring-up HWC must not independently compose every application layer or
infer frame changes from handle/fence identity. The stock-compatible first
implementation should:

1. advertise HWC 1.5 so SurfaceFlinger supplies both a framebuffer target and
   standard per-layer `surfaceDamage`;
2. return unsupported application layers as `HWC_FRAMEBUFFER`;
3. wait and close the target acquire fence;
4. call the framebuffer device's `post()` with the target handle;
5. return synchronous release/retire fences as `-1`;
6. carry compositor damage to the presentation boundary and keep EPDC
   rectangle, waveform and marker policy inside gralloc;
7. never call `invalidate()` merely because an update completed.

For the fast path to match stock, the client target must be framebuffer-backed
and match fb0's RGB565 format and real kernel stride. A Mesa 8-8-8-8 softpipe
target cannot use this direct path without a full CPU conversion, which is both
different from stock and too slow on i.MX6SL. The AGL/PixelFlinger RGB565 path
is therefore the correct baseline; PXP should remain an optional conversion or
rotation fallback, not the primary compositor.

## Next implementation

Use the already-built AGL/PixelFlinger system as the base. Replace the
experimental Oreo HWC with a minimal target-to-`fb_post()` bridge, preserve
RGB565 framebuffer allocation with the 1888-pixel stride, and pass Oreo's
compositor damage to gralloc in physical-display coordinates. Until that path
is working, a missing/invalid damage region must fall back to a full-screen
update. Do not use framebuffer tile diff as the authoritative damage source;
it may remain only as a diagnostic or conservative verification fallback.

## Android 8 implementation

The Oreo HWC now advertises API 1.5 and converts every non-empty producer
damage rectangle from pre-transform buffer coordinates through the layer crop,
rotation and scale into physical EPDC coordinates. Damage from all displayed
layers is unioned and passed to the framebuffer HAL with `setUpdateRect()`
immediately before the corresponding `post()`.

The framebuffer HAL consumes that rectangle exactly once. It submits one
aligned GC16 update and waits for its marker, ensuring that one update contains
both the old and new drawing bounds supplied by the producer. The framebuffer
tile comparison remains only the fallback when no explicit rectangle reaches
the HAL. The first frame and the periodic cleanup threshold still use a
full-screen quality refresh.
