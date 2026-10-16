#!/bin/bash
set -euo pipefail
ROOT=/home/juwon/ridi
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [[ $# -lt 1 || $1 == --help ]]; then
 echo "병렬 작업: SD_COPY_JOBS=8 (1..32)"
 echo "사용법: $0 <FAT32-p1 마운트 경로> [업데이트.tar] [--targets boot|system|vendor|조합] [--manual] [--no-reboot]";exit 0
fi
exec python3 - "$SCRIPT_DIR" "$@" <<'PY'
import argparse,sys,pathlib as P,subprocess as S,json,os,stat,tarfile,shutil,tempfile,datetime,time,concurrent.futures as F,hashlib
sys.path.insert(0,sys.argv[1]);from validate_package import validate,digest
from selection import sd_plan
root=P.Path('/home/juwon/ridi')
parser=argparse.ArgumentParser();parser.add_argument('mount');parser.add_argument('archive',nargs='?',default=str(root/'deliverables/e70q10-update-20261006-auto.tar'));parser.add_argument('--targets');parser.add_argument('--manual',action='store_true');parser.add_argument('--no-reboot',action='store_true');args=parser.parse_args(sys.argv[2:])
mount=P.Path(args.mount).resolve(strict=True);archive=P.Path(args.archive)
stage=lock=None
jobs=int(os.environ.get("SD_COPY_JOBS","8"))
if not 1<=jobs<=32:raise SystemExit("SD_COPY_JOBS must be 1..32")
started=time.monotonic()
try:
 info=json.loads(S.check_output(['findmnt','-J','-M',str(mount)],text=True))['filesystems'][0]
 if P.Path(info['target']).resolve()!=mount or info['fstype']!='vfat' or 'rw' not in info['options'].split(','):raise ValueError('RW FAT32 mountpoint required')
 device=P.Path(info['source']).resolve(strict=True)
 if not stat.S_ISBLK(device.stat().st_mode) or (P.Path('/sys/class/block')/device.name/'partition').read_text().strip()!='1':raise ValueError('SD p1 required')
 if S.check_output(['lsblk','-nro','FSVER',str(device)],text=True).strip()!='FAT32':raise ValueError('FAT32 required')
 parent=S.check_output(['lsblk','-nro','PKNAME',str(device)],text=True).strip()
 removable=(P.Path('/sys/class/block')/parent/'removable').read_text().strip();transport=S.check_output(['lsblk','-dnro','TRAN','/dev/'+parent],text=True).strip()
 if removable!='1' and transport!='usb':raise ValueError('External removable/USB media required')
 package=validate(archive);plan=sd_plan(package,args)
 if shutil.disk_usage(mount).free<plan['required_bytes']:raise ValueError('Not enough space on SD p1')
 dest=mount/'e70q10-update'
 if os.path.lexists(dest):raise ValueError('e70q10-update exists; rename it before staging new release')
 candidate=mount/'.e70q10-update-prepare.lock';candidate.mkdir();lock=candidate
 stage=P.Path(tempfile.mkdtemp(prefix='.e70q10-update-',dir=mount))
 # The package was already fully verified. Each worker reads independent tar
 # offsets, avoiding shared tar seek state and another archive hashing pass.
 with tarfile.open(archive) as tar:
  members=[m for m in tar.getmembers() if m.isfile()]
 work=[]
 for m in members:
  name=str(P.PurePosixPath(*P.PurePosixPath(m.name).parts[1:]))
  if name not in package['checksums']:raise ValueError('Archive entries changed after validation')
  if name not in plan['names'] or name in plan['metadata']:continue
  target=stage/name
  target.parent.mkdir(parents=True,exist_ok=True)
  work.append((name,target,m.offset_data,m.size))
 print('COPY: targets={} workers={} automatic={} reboot={}'.format(','.join(plan['targets']),jobs,int(plan['automatic']),int(plan['reboot'])),flush=True)
 def copy_one(item):
  name,target,offset,left=item;h=hashlib.sha256()
  with archive.open('rb',buffering=0) as source,target.open('xb',buffering=0) as dst:
   source.seek(offset)
   while left:
    chunk=source.read(min(left,8<<20))
    if not chunk:raise ValueError('Truncated archive: '+name)
    # FileIO writes may be short, so complete every buffer explicitly.
    view=memoryview(chunk)
    while view:
     n=dst.write(view)
     if not n:raise ValueError('SD write failed: '+name)
     view=view[n:]
    h.update(chunk);left-=len(chunk)
   os.fsync(dst.fileno())
  if h.hexdigest()!=package['checksums'][name]:raise ValueError('Archive changed during copy: '+name)
 with F.ThreadPoolExecutor(max_workers=jobs) as pool:list(pool.map(copy_one,work))
 for name,data in plan['metadata'].items():
  target=stage/name
  with target.open('xb',buffering=0) as dst:
   view=memoryview(data)
   while view:
    n=dst.write(view)
    if not n:raise ValueError('SD metadata write failed')
    view=view[n:]
   os.fsync(dst.fileno())
  work.append((name,target,0,len(data)))
 # Flush only this filesystem; avoid waiting for unrelated Android build disks.
 S.run(['sync','-f',str(mount)],check=True)
 print(f'READBACK: {jobs} workers',flush=True)
 def check_one(item):
  name,target,_,_=item
  with target.open('rb') as f:
   if hasattr(os,'posix_fadvise'):os.posix_fadvise(f.fileno(),0,0,os.POSIX_FADV_DONTNEED)
   if digest(f)!=plan['checksums'][name]:raise ValueError('SD readback mismatch: '+name)
 with F.ThreadPoolExecutor(max_workers=jobs) as pool:list(pool.map(check_one,work))
 if os.path.lexists(dest):raise ValueError('Destination appeared during copy; no overwrite')
 stage.rename(dest);stage=None;S.run(['sync','-f',str(mount)],check=True)
 logdir=root/'.orchestrator/logs/emmc-update-20261001';logdir.mkdir(parents=True,exist_ok=True)
 (logdir/('sd-ready-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S')+'.json')).write_text(json.dumps({'destination':str(dest),'device':str(device),'archive_sha256':package['archive_sha256'],'file_bytes':plan['file_bytes'],'targets':plan['targets'],'automatic':plan['automatic'],'reboot':plan['reboot'],'readback':'all passed','workers':jobs,'elapsed_seconds':round(time.monotonic()-started,2)},indent=2)+'\n')
 print('UPDATE SD READY: '+str(dest))
 print('RAM boot behavior: automatic selected update and reboot' if plan['automatic'] and plan['reboot'] else 'RAM boot behavior: see update.conf (manual or reboot disabled)')
except Exception as e:
 print('STOP: '+str(e),file=sys.stderr);sys.exit(1)
finally:
 if stage is not None:shutil.rmtree(stage,ignore_errors=True)
 if lock is not None:
  try:lock.rmdir()
  except OSError:pass
PY
