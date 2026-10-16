sha256-armv4.S is copied without modification from the existing Android BSP:
external/boringssl/linux-arm/crypto/fipsmodule/sha256-armv4.S.
Original OpenSSL notices remain in the file; full license is included here.
Build uses __KERNEL__ only to avoid OpenSSL dispatch/header dependencies (this
remains a userspace executable). Dispatch chooses NEON only when Linux auxv
HWCAP reports it, otherwise the ARM integer implementation. No ARMv8 crypto
instruction path is enabled. C streaming/padding wrapper is in sha256_fast.h.
