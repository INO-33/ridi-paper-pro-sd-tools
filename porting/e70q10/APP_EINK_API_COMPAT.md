# RIDI / MY YES E Ink API compatibility

## Result

The APIs embedded in both APKs can be supported on this Android 8 port. They
must not be implemented as no-ops. MY YES contains a complete Onyx SDK and its
i.MX6 implementation is a reflection adapter for vendor additions to
`android.view.View`; it does not require an Onyx-specific native library.

The following APKs were inspected directly with the Oreo build's `dexdump`:

- `/home/juwon/ridi/apks/myyes.apk`
- `/home/juwon/ridi/ridi-paper-pro-stock-4.4.2-20260721/files/system/priv-app/com.ridi.paper.apk`

MY YES contains both the old and new Onyx namespaces, including:

- `com.onyx.android.sdk.api.device.EpdDeviceManager`
- `com.onyx.android.sdk.api.device.EpdImx6`
- `com.onyx.android.sdk.api.device.epd.EpdController`
- `com.onyx.android.sdk.device.IMX6Device`

`EpdImx6.setUpdateMode(view, mode)` calls
`EpdController.setViewDefaultUpdateMode(view, mode)`. The controller delegates
to `IMX6Device`, which looks up E Ink fields and methods on
`android.view.View` through reflection.

The RIDI APK contains the older
`com.onyx.android.sdk.device.EpdController` enums and the same View-oriented
method names. A framework compatibility surface can therefore serve both
applications.

## RIDI stock framework ABI

The extracted RIDI 4.4.2 `framework.jar` contains the actual Netronix E Ink
framework extension; this is now the primary ABI reference instead of a
generic Onyx implementation. Direct DEX inspection confirms:

- `View.invalidate(int updateMode)`
- `View.invalidate(int left, int top, int right, int bottom, int updateMode)`
- `View.invalidate(Rect dirty, int updateMode)`
- internal `View.invalidate(boolean invalidateCache, int updateMode)`
- `ViewParentEink.invalidateChild(..., int updateMode)`
- `ViewParentEink.invalidateChildInParent(..., int updateMode)`
- `View.AttachInfo.InvalidateInfo.updateMode`

`android.view.View` also publishes packed constants for waveform
INIT/DU/GC16/GC4/GL16/GLR16/GLD16/A2/ANIM/AUTO, FULL/PARTIAL, WAIT/NOWAIT,
regional/automatic, combine, conversion, inversion and dithering. The native
stock libraries additionally export `Surface::addEpdc()`,
`Surface::freeEpdcList()` and
`SurfaceComposerClient::einkChangeUpdateMode(unsigned)`.

This proves that RIDI does not call the framebuffer driver directly. Its
framework carries the packed update policy beside each invalidation rectangle,
then `libgui`, SurfaceFlinger and gralloc deliver it to the EPDC ioctl.
Android 8 must forward-port this small path rather than invent a separate
application service.

## Device detection caveat

The bundled Onyx SDK selects `IMX6Device` only when
`Build.HARDWARE.contains("freescale")`. This port currently uses
`androidboot.hardware=E70Q10`, which is required for its init and HAL filenames,
so changing `ro.hardware` globally would break device startup.

The compatible solution is to add a product-only framework override used by
`Build.HARDWARE`, for example `ro.hardware.app=freescale`, while leaving
`ro.hardware=E70Q10` unchanged. This makes the bundled SDK select its i.MX6
adapter without changing HAL discovery.

## Required pipeline

```text
RIDI / Onyx SDK
    -> reflected android.view.View E Ink method
    -> View default/global/system policy state
    -> invalidation damage (old and new bounds)
    -> SurfaceFlinger HWC1 layer vendor metadata
    -> HWC damage transform to physical coordinates
    -> framebuffer HAL one-shot EPDC policy
    -> MXCFB_SEND_UPDATE
```

The standard HWC 1.5 `surfaceDamage` implemented for E70Q10 already carries the
rectangle, but it does not carry waveform, update mode, wait mode or scope.
A small vendor policy payload must accompany each layer/frame. It should not
be represented by a global property because that races between views and
frames.

For HWC1 on this 32-bit target, the existing reserved bytes in
`hwc_layer_1_t` can carry an E70Q10 policy record populated by the local
SurfaceFlinger adapter and consumed synchronously by the local HWC. This keeps
the policy associated with the same layer and prepare/set cycle as its damage.
The framebuffer HAL then consumes the selected policy exactly once together
with `setUpdateRect()`.

## Policy mapping

The kernel already exposes the required Netronix/i.MX6 EPDC modes:

| App request | Kernel action |
| --- | --- |
| `DU` | waveform table `mode_du` |
| `GC16` / quality default | waveform table `mode_gc16` |
| `GC4` | waveform table `mode_gc4` |
| `A2` / animation | waveform table `mode_a2`, monochrome as requested |
| `REAGL` / `GLR16` | stock E70Q10 waveform index 4 (`mode_aa`) |
| `REAGLD` / `GLD16` | stock E70Q10 waveform index 5 (`mode_aad`) |
| `AUTO` | `WAVEFORM_MODE_AUTO` |
| `FULL` | `UPDATE_MODE_FULL` |
| `PARTIAL` | `UPDATE_MODE_PARTIAL` |
| `WAIT` | nonzero marker plus `MXCFB_WAIT_FOR_UPDATE_COMPLETE` |
| `NOWAIT` | marker zero, subject to collision/queue limits |

Unknown or unsupported mode values must fall back to GC16 quality mode, never
to an unvalidated numeric waveform index.

The E70Q10 stock kernel reports the exact `0x19` waveform map as
DU=1, GC16=2, GL16=3, REAGL=4, REAGLD=5 and A2=6. The separate
`CONFIG_FB_MXC_EINK_REGAL` option is disabled in the captured RIDI stock
configuration, so Android compatibility must not depend on the unused
4.9 `EPDC_FLAG_USE_REGAL` definition. Modes 4 and 5 are selected as waveform
indices, matching the Netronix `mode_aa`/`mode_aad` mapping already ported into
the 4.9 waveform loader. Proprietary Regal preprocessing is therefore not a
prerequisite for reproducing the captured RIDI configuration.

## Implementation order

1. Add the exact Onyx/RIDI constants and reflected method signatures to
   `android.view.View`.
2. Add product-only Onyx i.MX6 device detection without changing
   `ro.hardware`.
3. Store View, application-global and system-default policy with reset
   semantics.
4. Aggregate policy with View invalidation damage in `ViewRootImpl`.
5. Attach the policy to the matching SurfaceFlinger HWC1 layer and frame.
6. Extend the existing HWC-to-framebuffer one-shot call to include waveform,
   full/partial and wait values.
7. Test default GC16, page-turn DU/REAGL, animation A2, explicit FULL and reset
   behavior separately.

The first Android 8 display boot should still validate standard
`surfaceDamage` before enabling app policy overrides. This prevents an app API
bug from being confused with the base coordinate and framebuffer path.
