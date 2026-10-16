#!/bin/sh
# Stage ordinary files on an existing FAT32 SD partition; never format or flash.
set -eu
exec python3 - "$@" <<'PY'
import argparse, hashlib, json, os, pathlib, re, shutil, stat, subprocess, sys, tarfile, tempfile
R=pathlib.Path('/home/juwon/ridi')
ARCHIVE=R/'deliverables/e70q10-emmc-android8-install-20261001.tar'
BACK=pathlib.Path('/media/juwon/build/리디백업/backups/e70q10-PP1A1GK166561-20260923-full-emmc')
LOGROOT=R/'.orchestrator/logs/emmc-install-20261001'
p=argparse.ArgumentParser(prog='prepare_sd.sh',description='기존 FAT32 SD 첫 파티션에 e70q10-install 파일을 준비합니다. 포맷/장치 기록 없음.')
p.add_argument('mountpoint',help='SD 첫 파티션의 마운트 경로; /dev/sdX 같은 장치 경로가 아닙니다')
p.add_argument('--dry-run',action='store_true',help='대상/파일/필요 공간을 검사하고 복사하지 않습니다')
p.add_argument('--install-only',action='store_true',help='설치 파일만 복사합니다. SD에서 순정 복원은 불가능합니다')
a=p.parse_args()
def fail(s): raise RuntimeError(s)
def command(args):return subprocess.check_output(args,text=True,stderr=subprocess.DEVNULL).strip()
def sha(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for b in iter(lambda:f.read(4<<20),b''):h.update(b)
 return h.hexdigest()
def checksums(text):
 result={}
 for line in text.splitlines():
  m=re.fullmatch(r'([0-9a-f]{64})  (.+)',line)
  if not m:fail('잘못된 SHA256 목록')
  name=m[2];x=pathlib.PurePosixPath(name)
  if x.is_absolute() or '..' in x.parts or name in result:fail('잘못된 SHA256 경로')
  result[name]=m[1]
 return result
stage=None;lock=None;log=None
try:
 supplied=pathlib.Path(a.mountpoint).expanduser()
 if str(supplied).startswith('/dev/'):fail('장치 대신 마운트 디렉터리를 지정하세요.')
 mount=supplied.resolve(strict=True)
 info=json.loads(command(['findmnt','-J','-M',str(mount)]))['filesystems'][0]
 if pathlib.Path(info['target']).resolve()!=mount:fail('마운트 지점 자체를 지정하세요.')
 if info['fstype']!='vfat' or 'rw' not in info['options'].split(','):fail('읽기/쓰기 가능한 FAT32 파티션이 필요합니다.')
 device=pathlib.Path(info['source']).resolve(strict=True)
 if not stat.S_ISBLK(device.stat().st_mode):fail('실제 SD 블록 장치가 아닙니다.')
 sysblock=pathlib.Path('/sys/class/block')/device.name
 if (sysblock/'partition').read_text().strip()!='1':fail('RAM 설치기는 SD 첫 파티션만 읽습니다. p1을 지정하세요.')
 if command(['lsblk','-nro','FSVER',str(device)])!='FAT32':fail('FAT32가 아닙니다.')
 parent=command(['lsblk','-nro','PKNAME',str(device)])
 removable=(pathlib.Path('/sys/class/block')/parent/'removable').read_text().strip()
 transport=command(['lsblk','-dnro','TRAN','/dev/'+parent])
 if removable!='1' and transport!='usb':fail('외장 SD/USB 매체로 식별되지 않아 중단합니다.')
 dest=mount/'e70q10-install'
 if os.path.lexists(dest):fail('e70q10-install 폴더가 이미 있습니다. 기존 폴더를 다른 이름으로 옮긴 후 실행하세요.')
 if not os.access(mount,os.W_OK):fail('마운트 디렉터리에 쓰기 권한이 없습니다.')
 # Verify the archive before trusting any internal path or manifest.
 expected=checksums(ARCHIVE.with_suffix('.tar.sha256').read_text())[ARCHIVE.name]
 if sha(ARCHIVE)!=expected:fail('배포 tar SHA256이 다릅니다.')
 with tarfile.open(ARCHIVE) as tar:
  members=tar.getmembers();files={}
  for m in members:
   path=pathlib.PurePosixPath(m.name)
   if path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0]!='e70q10-install':fail('tar 경로가 잘못되었습니다.')
   if not (m.isfile() or m.isdir()) or (m.isfile() and m.size>=4294967296):fail('FAT32에 복사할 수 없는 tar 항목입니다.')
   if m.isfile():
    relative=str(pathlib.PurePosixPath(*path.parts[1:]))
    if relative in files:fail('중복 tar 파일')
    files[relative]=m
  package_hashes=checksums(tar.extractfile(files['SHA256SUMS']).read().decode())
  if set(package_hashes)!=set(files)-{'SHA256SUMS'}:fail('배포 파일과 해시 목록이 다릅니다.')
  backup_hashes=checksums(tar.extractfile(files['backup.sha256']).read().decode())
  if set(backup_hashes)!={f'emmc.part{i:02d}' for i in range(30)}:fail('백업 30개 목록이 다릅니다.')
  backup_bytes=0
  if not a.install_only:
   for name in sorted(backup_hashes):
    f=BACK/name
    if not f.is_file() or f.is_symlink():fail('백업 파일이 없거나 일반 파일이 아닙니다: '+name)
    expected_size=(256<<20) if name!='emmc.part29' else 7818182656-29*(256<<20)
    if f.stat().st_size!=expected_size:fail('백업 크기 불일치: '+name)
    backup_bytes+=expected_size
  payload_bytes=sum(m.size for m in files.values())+backup_bytes
  required=payload_bytes+(64<<20)
  free=shutil.disk_usage(mount).free
  print(f'대상: {device} → {mount} (FAT32 p1)',flush=True)
  print(f'복사 {payload_bytes:,} bytes / 여유 포함 필요 {required:,} bytes / 사용 가능 {free:,} bytes',flush=True)
  if free<required:fail('SD 첫 파티션의 여유 공간이 부족합니다. 포맷/확장은 이 스크립트가 수행하지 않습니다.')
  if a.dry_run:
   print('점검 완료. --dry-run을 빼면 설치 파일'+('만' if a.install_only else '과 복원 백업 30개')+'을 복사합니다.')
   sys.exit(0)
  LOGROOT.mkdir(parents=True,exist_ok=True)
  logpath=LOGROOT/('sd-prepare-'+__import__('datetime').datetime.now().strftime('%Y%m%d-%H%M%S')+'.log')
  log=open(logpath,'x')
  log.write(json.dumps({'mountpoint':str(mount),'device':str(device),'archive_sha256':expected,'restore_included':not a.install_only,'payload_bytes':payload_bytes},ensure_ascii=False)+'\n');log.flush()
  candidate_lock=mount/'.e70q10-prepare.lock';candidate_lock.mkdir();lock=candidate_lock
  stage=pathlib.Path(tempfile.mkdtemp(prefix='.e70q10-stage-',dir=mount))
  for name,m in files.items():
   target=stage/name;target.parent.mkdir(parents=True,exist_ok=True)
   with tar.extractfile(m) as src,open(target,'xb') as dst:shutil.copyfileobj(src,dst,4<<20)
  for name,expected_hash in package_hashes.items():
   if sha(stage/name)!=expected_hash:fail('SD 설치 파일 검증 실패: '+name)
  print('설치 파일 복사·SHA256 검증 완료.',flush=True)
  if not a.install_only:
   (stage/'backup').mkdir()
   for i,(name,expected_hash) in enumerate(sorted(backup_hashes.items()),1):
    h=hashlib.sha256();target=stage/'backup'/name
    with open(BACK/name,'rb') as src,open(target,'xb') as dst:
     for block in iter(lambda:src.read(4<<20),b''):h.update(block);dst.write(block)
    if h.hexdigest()!=expected_hash:fail('원본 백업 SHA256 불일치: '+name)
    log.write(name+' copied\n');log.flush()
    print(f'복원 백업 복사 {i}/30',flush=True)
  # Complete buffered writes before verifying the copied backup.
  os.sync()
  if not a.install_only:
   print('SD 복원 백업 30개 SHA256 검증 중…',flush=True)
   for name,expected_hash in sorted(backup_hashes.items()):
    if sha(stage/'backup'/name)!=expected_hash:fail('SD 백업 SHA256 불일치: '+name)
    log.write(name+' SHA256 OK\n');log.flush()
  if os.path.lexists(dest):fail('복사 중 대상 폴더가 만들어졌습니다. 덮어쓰지 않습니다.')
  stage.rename(dest);stage=None;os.sync()
  log.write('READY '+str(dest)+'\n');log.flush()
  print('SD 준비 완료: '+str(dest),flush=True)
  print('호스트 로그: '+str(logpath),flush=True)
  print('SD를 정상적으로 분리한 뒤 기기에 넣으세요. RAM 콘솔 명령: installer check /mnt/sd/e70q10-install')
except (RuntimeError,OSError,KeyError,ValueError,subprocess.CalledProcessError,tarfile.TarError) as e:
 print('중단: '+str(e),file=sys.stderr)
 if log:log.write('ERROR '+str(e)+'\n');log.flush()
 sys.exit(1)
finally:
 if stage is not None:shutil.rmtree(stage,ignore_errors=True)
 if lock is not None:
  try:lock.rmdir()
  except OSError:pass
 if log:log.close()
PY
