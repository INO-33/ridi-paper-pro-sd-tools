#!/usr/bin/env python3
"""Build a small Python/Tk desktop app; no OS payloads included."""
from pathlib import Path
import argparse,tempfile,zipfile,tarfile,io,hashlib,json,shutil,sys
SRC=Path(__file__).resolve().parent
from package import validate,sha
from folder_package import FILES,repack_ram
p=argparse.ArgumentParser();p.add_argument('--seed',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
if a.out.exists():raise SystemExit('Choose a new output directory')
if Path(str(a.seed)+'.sha256').read_text().split()!=[sha(a.seed),a.seed.name]:raise SystemExit('Seed checksum mismatch')
with tempfile.TemporaryDirectory(prefix='gui-runtime-seed-') as d:
 w=Path(d)
 with zipfile.ZipFile(a.seed) as z:
  n=next(n for n in z.namelist() if n.endswith('.tar'))
  (w/n).write_bytes(z.read(n));(w/(n+'.sha256')).write_bytes(z.read(n+'.sha256'))
 validate(w/n)
 with tarfile.open(w/n) as t:assets={f:t.extractfile('e70q10-update/'+f).read() for f in FILES}
 report=json.loads(assets['build-report.json']);mh=report['manifest_sha256']
 control=(SRC/'ram-control.sh').read_text().replace('@MANIFEST@',mh)
 replacements={
  'bin/auto-update':(SRC/'ram-auto.sh').read_text().replace('@CONTROL@',control).encode(),
  'bin/initial-install':(SRC/'ram-install.sh').read_text().replace('@MANIFEST@',mh).encode(),
  'bin/backup-current':(SRC/'ram-backup.sh').read_text().replace('@MANIFEST@',mh).encode(),
 }
 ram,rd,hashes=repack_ram(assets['ram-updater.img'],mh,replacements)
 assets['ram-updater.img']=ram;report['runtime_sha256']=hashes;assets['build-report.json']=json.dumps(report).encode()
 toolkit=json.loads(assets['toolkit.json']);toolkit['schema']=5;toolkit['backup_option']='before-install-or-update';assets['toolkit.json']=json.dumps(toolkit).encode()
 a.out.mkdir(parents=True)
 with zipfile.ZipFile(a.out/'runtime.zip','w',compression=zipfile.ZIP_STORED) as z:
  for n,b in assets.items():z.writestr(n,b)
  z.writestr('SHA256SUMS',''.join(hashlib.sha256(assets[n]).hexdigest()+'  '+n+'\n' for n in sorted(assets)))
 (a.out/'runtime.zip.sha256').write_text(sha(a.out/'runtime.zip')+'  runtime.zip\n')
 for name in ['ridi_gui.py','gui_backend.py','folder_package.py','portable_images.py','portable_boot.py','portable_lzo.py','ridi_emmc.py','package.py','devices.py','GUI_README.md','build_windows.py','build_windows.cmd','WINDOWS_BUILD.md','rollback.py','ram-restore.sh','ROLLBACK.md']:shutil.copy2(SRC/name,a.out/name)
 (a.out/'images').mkdir();(a.out/'images/이미지_넣는_곳.txt').write_text('이 폴더에 boot.img / system.img / vendor.img를 넣으세요.\n백업 작업에는 이미지가 필요 없습니다.\n',encoding='utf-8')
 (a.out/'platform-tools').mkdir();(a.out/'platform-tools/README.txt').write_text('Windows Android platform-tools의 fastboot.exe 및 필요한 DLL을 이 폴더에 넣으세요.\nLinux는 fastboot 실행파일 또는 PATH의 fastboot를 사용합니다.\n',encoding='utf-8')
 (a.out/'licenses').mkdir();shutil.copy2(SRC/'vendor/lzo/LICENSE',a.out/'licenses/LZO-GPL-2.0.txt');shutil.copy2(SRC/'vendor/sha256/LICENSE',a.out/'licenses/sha256-OpenSSL.txt')
 (a.out/'start.cmd').write_bytes(b'@echo off\r\ncd /d "%~dp0"\r\npy -3 ridi_gui.py\r\nif errorlevel 1 pause\r\n')
 (a.out/'start.sh').write_text('#!/bin/sh\ncd "$(dirname "$0")"\nexec python3 ridi_gui.py\n');(a.out/'start.sh').chmod(0o755)
print('GUI DIRECTORY',a.out)
