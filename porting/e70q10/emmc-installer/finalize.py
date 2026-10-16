#!/usr/bin/env python3
from pathlib import Path
import json,hashlib,tarfile,shutil
root=Path('/home/juwon/ridi');out=root/'deliverables/e70q10-emmc-android8-20261001'
report=json.loads((out/'build-report.json').read_text())
assert report['offline_validation'].startswith('passed:')
arm=json.loads((out/'arm-stream-validation.json').read_text());assert arm['arm_busybox_gzip']=='passed'
report.update({'software_ready':True,'physical_flash_ready':False,'physical_validation':'pending','filesystem_checks':'system/vendor/cache/userdata: e2fsck -fn passed','arm_userdata_stream_validation':arm,'note':'No device or SD writes. Physical independent fastboot entry and RAM boot/check remain mandatory before initial flashing.'})
(out/'build-report.json').write_text(json.dumps(report,indent=2)+'\n')
source=out/'source';source.mkdir(exist_ok=True)
for p in (root/'porting/e70q10/emmc-installer').iterdir():
 if p.is_file():shutil.copyfile(p,source/p.name)
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(4<<20),b''):h.update(b)
 return h.hexdigest()
files=sorted(p for p in out.rglob('*') if p.is_file() and not any(x.startswith('.') for x in p.relative_to(out).parts) and p.name!='SHA256SUMS')
(out/'SHA256SUMS').write_text(''.join(sha(p)+'  '+str(p.relative_to(out))+'\n' for p in files))
archive=root/'deliverables/e70q10-emmc-android8-install-20261001.tar'
with tarfile.open(archive,'w') as tar:
 for p in sorted(out.iterdir()):
  if not p.name.startswith('.'):tar.add(p,arcname='e70q10-install/'+p.name)
(archive.with_suffix('.tar.sha256')).write_text(sha(archive)+'  '+archive.name+'\n')
table=root/'deliverables/emmc-20261001-final-partition-table/manifest.json';v=json.loads(table.read_text());v.update({'installation_package_ready':True,'offline_package_validation':'passed','installation_package':'/home/juwon/ridi/deliverables/e70q10-emmc-android8-install-20261001.tar','physical_validation':'pending'});table.write_text(json.dumps(v,indent=2)+'\n')
packet=root/'.orchestrator/EMMC_INSTALLER_BUILD_PACKET.md'
packet.write_text('''# eMMC installer preparation — 2026-10-01

Independent storage preparation; no physical flashing or graphics checkpoint promotion.

- Device PP1A1GK166561, CID 15010038474d45345201bbd3fe618400, 7,818,182,656 bytes.
- Frozen latest Android boot/system/vendor hashes: deliverables/e70q10-emmc-android8-20261001/build-report.json.
- Artifacts: deliverables/e70q10-emmc-android8-install-20261001.tar and matching .tar.sha256.
- RAM boot image contains static ARM BusyBox, pinned installer, standalone Linux ARM32 byte counter with 64-bit totals.
- Expanded filesystem images: system 1GiB, vendor 256MiB, cache 64MiB, userdata 6019MiB. e2fsck -fn passed.
- Android boot kernel has appended DTB, second_size=0. eMMC fstab and RAM early logs are embedded.
- Full-capacity regular-file installation and per-payload readback passed; EBR/MBR decoded, recovery MBR entry and [512,51MiB) preserved.
- Modified manifest, corrupt gzip input and wrong capacity rejected before writing.
- Full 30-part September restore passed with full-device SHA256 7783c8529e3b89df29a076f2fb8ac7e4216e7e8bca864db50ae872be1e3baf6f.
- Actual ARM BusyBox under QEMU expanded 6,311,378,944-byte userdata with matching SHA256; ARM byte counter and >4GiB dd seek checked.
- 32-bit BusyBox wc overflow found during first rehearsal; replaced by the bundled 64-bit counter. Android ext4 bitmap/resize metadata repaired on package copies only.
- No clean build. No modifications to the source BSP or unrelated working-tree changes.
- No device, SD, boot0/boot1 or RPMB writes.
- Software package ready. Hardware fastboot entry independent of Android, RAM boot/USB console/check and first new Android boot remain pending.
- Required before flashing: confirmed independent fastboot entry, read-only FAT32 SD p1 with adequate free space, check passes in RAM, stable external power.
- Logs: .orchestrator/logs/emmc-install-20261001/ (first failed attempt retained alongside successful run).
''')
print('READY:',archive,'bytes=',archive.stat().st_size)
