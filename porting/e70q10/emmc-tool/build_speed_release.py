#!/usr/bin/env python3
"""Build a matched Windows/Linux ZIP from source runtime and completed Android images.
A checksum-verified previous ZIP supplies only the trusted RAM kernel/root seed.
--reuse-images reuses verified seed payloads for RAM/host-only revisions.
All unpack/conversion files are temporary; only the ZIP + SHA256 are retained.
"""
from pathlib import Path
import argparse,tempfile,zipfile,tarfile,io,subprocess,sys,hashlib,json
SRC=Path(__file__).resolve().parent
sys.path.insert(0,str(SRC));from package import sha,validate
p=argparse.ArgumentParser();p.add_argument('--seed',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--product',type=Path,default=Path('/media/juwon/build/android-out/e70q10_reference_agl_stockpath/target/product/e70q10'));p.add_argument('--reuse-images',action='store_true',help='reuse frozen seed OS payloads for a runtime-only revision');a=p.parse_args()
if a.out.exists() or Path(str(a.out)+'.sha256').exists():raise SystemExit('Choose a new ZIP path')
expected=Path(str(a.seed)+'.sha256').read_text().split()
if expected!=[sha(a.seed),a.seed.name]:raise SystemExit('Seed ZIP checksum mismatch')
with tempfile.TemporaryDirectory(prefix='ridi-speed-release-') as td:
 w=Path(td);base=w/'base';base.mkdir()
 with zipfile.ZipFile(a.seed) as z:
  name=next(n for n in z.namelist() if n.endswith('.tar'))
  with tarfile.open(fileobj=io.BytesIO(z.read(name))) as t:
   # Import regular data only. Never execute scripts or extract arbitrary paths.
   for m in t:
    if not m.isfile():continue
    n=m.name.removeprefix('e70q10-update/')
    if '/' in n or n not in {'system.raw.gz','vendor.raw.gz','boot.raw.gz','boot-emmc.img','manifest.tsv','updater.sh','ram-updater.img','updater-ramdisk.cpio.gz','compatibility-baseline.json','build-report.json'}:continue
    (base/n).write_bytes(t.extractfile(m).read())
 if not a.reuse_images:subprocess.run([sys.executable,str(SRC/'freeze_images.py'),str(base),'--product',str(a.product)],check=True)
 out=w/'release'
 subprocess.run([sys.executable,str(SRC/'build_unified.py'),str(base),'--out',str(out),'--product',str(a.product),'--operation','update'],check=True)
 report=validate(out.with_suffix('.tar'))
 tarname=a.out.stem+'.tar';tarbytes=out.with_suffix('.tar').read_bytes();side=hashlib.sha256(tarbytes).hexdigest()+'  '+tarname+'\n'
 launch=lambda cmd:('@echo off\r\ncd /d "%~dp0"\r\npy -3 ridi_emmc.py '+cmd+'\r\npause\r\n').encode()
 a.out.parent.mkdir(parents=True,exist_ok=True)
 # Payloads are already gzip-compressed: STORE avoids a redundant ZIP compression pass.
 with zipfile.ZipFile(a.out,'w',compression=zipfile.ZIP_STORED) as z:
  z.writestr(tarname,tarbytes);z.writestr(tarname+'.sha256',side)
  for n in ['ridi_emmc.py','package.py','devices.py','README.md']:z.write(SRC/n,n)
  z.write(SRC/'vendor/sha256/LICENSE','licenses/sha256-OpenSSL.txt')
  z.write(SRC/'vendor/sha256/README.md','licenses/sha256-source.md')
  z.writestr('disks.cmd',launch('disks'))
  z.writestr('prepare-update.cmd',launch('prepare "'+tarname+'" --disk %1 --operation update --targets all --jobs 8'))
  z.writestr('prepare-backup.cmd',launch('prepare "'+tarname+'" --disk %1 --operation backup --jobs 8'))
  z.writestr('boot.cmd',launch('boot "'+tarname+'"'))
  z.writestr('release-validation.json',json.dumps({'manifest':report['manifest'],'pc_image_validation':report['pc_image_validation'],'reused_seed_payloads':a.reuse_images,'physical_speed_test':'pending','image_policy':'PC prevalidation; device exact bounded write then readback'},indent=2)+'\n')
 with zipfile.ZipFile(a.out) as z:assert z.testzip() is None
 Path(str(a.out)+'.sha256').write_text(sha(a.out)+'  '+a.out.name+'\n')
print('BUILT SPEED ZIP',a.out)
