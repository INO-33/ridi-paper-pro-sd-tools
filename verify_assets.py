#!/usr/bin/env python3
"""Read-only validation of preserved SD producer/runtime input assets."""
import hashlib
from pathlib import Path
import sys
root = Path(__file__).resolve().parent
for line in (root / 'ASSET_SHA256SUMS').read_text().splitlines():
    digest, relative = line.split('  ', 1)
    if hashlib.sha256((root / relative).read_bytes()).hexdigest() != digest:
        raise SystemExit('Asset mismatch: ' + relative)
sys.path.insert(0, str(root / 'porting/e70q10/emmc-updater'))
from runtime_assets import verify_assets
verify_assets(root / 'porting/e70q10/emmc-updater/assets')
sys.path.insert(0, str(root / 'porting/e70q10/emmc-tool'))
from folder_package import runtime_seed
runtime_seed(root / 'porting/e70q10/emmc-tool/runtime.zip')
print('SD source assets, updater input and GUI runtime verified')
