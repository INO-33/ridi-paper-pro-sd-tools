"""UI-independent jobs; all disk writes go through existing protected adapters."""
from pathlib import Path
from dataclasses import dataclass
import os,tempfile,zipfile,tarfile,shutil,json,hashlib,subprocess,time
import devices
from package import validate,plan,stage,sha,safe_name,fields
from folder_package import build_folder,adapt_ready
from ridi_emmc import platform_tool,connected,select_serial

class Cancelled(Exception):pass

@dataclass(frozen=True)
class Request:
 folder:Path
 runtime:Path
 disk:str
 operation:str
 selected:tuple
 format_sd:bool=True
 jobs:int=8
 backup_before:bool=False

LABELS={'install':'Android 8 업그레이드','update':'증분 업데이트','backup':'전체 eMMC 백업','restore':'백업으로 롤백'}

def candidates(adapter=devices):
 rows=adapter.inventory()
 return [r for r in rows if r['bytes']>=15_000_000_000 and r['sector']==512 and not r.get('system') and not r.get('readonly') and (r.get('removable') or str(r.get('transport','')).lower() in ('usb','sd','mmc'))]

def mounted_volume(d,adapter=devices):
 if os.name=='nt':
  n=int(d['id']);letter=adapter.ps(f"$p=Get-Partition -DiskNumber {n} -PartitionNumber 1; if(-not $p.DriveLetter){{throw 'SD drive letter absent'}}; [string]$p.DriveLetter").splitlines()[-1].strip()
  if len(letter)!=1 or not letter.isalpha():raise ValueError('SD 드라이브 문자가 없습니다')
  return Path(letter+':\\')
 parts=d.get('row',{}).get('children',[])
 if len(parts)!=1:raise ValueError('기존 SD 사용은 FAT32 파티션 하나가 필요합니다. 포맷 옵션을 사용하세요.')
 mounts=[m for m in parts[0].get('mountpoints',[]) or [] if m]
 if not mounts:
  adapter.run(['udisksctl','mount','-b',parts[0]['name']]);d=adapter.checked_disk(d['id']);mounts=[m for m in d['row']['children'][0].get('mountpoints',[]) or [] if m]
 if len(mounts)!=1:raise ValueError('SD 마운트 위치를 찾지 못했습니다')
 return Path(mounts[0])

def package_from_folder(req,workspace,progress):
 folder=Path(req.folder).resolve(strict=True)
 if not folder.is_dir():raise ValueError('이미지 폴더를 선택하세요')
 raw=any((folder/(r+'.img')).is_file() for r in ('boot','system','vendor'))
 if raw or req.operation=='backup':return build_folder(folder,req.runtime,workspace/'generated',req.operation,req.selected,progress,backup_before=req.backup_before)
 archives=sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in ('.tar','.zip') and p.name!='runtime.zip')
 if len(archives)!=1:raise ValueError('폴더에 선택한 .img 파일 또는 검증된 배포 TAR/ZIP 하나를 넣으세요')
 archive=archives[0]
 if archive.suffix.lower()=='.zip':
  if Path(str(archive)+'.sha256').read_text().split()!=[sha(archive),archive.name]:raise ValueError('배포 ZIP 해시가 일치하지 않습니다')
  with zipfile.ZipFile(archive) as z:
   names=[n for n in z.namelist() if n.endswith('.tar')]
   if len(names)!=1:raise ValueError('배포 ZIP에 TAR 하나가 필요합니다')
   n=names[0];safe_name(n)
   if '/' in n or z.getinfo(n).file_size>2<<30:raise ValueError('지원하지 않는 TAR 경로/크기')
   for name in (n,n+'.sha256'):
    with z.open(name) as f,(workspace/name).open('xb') as o:shutil.copyfileobj(f,o,4<<20)
  archive=workspace/n
 progress('validate',0,0);return adapt_ready(validate(archive),req.runtime,workspace/'adapted')

def prepare(req,cache,consent,progress=lambda *a:None,adapter=devices):
 if req.operation not in LABELS:raise ValueError('지원하지 않는 작업입니다')
 if req.operation=='restore':
  from rollback import prepare as restore_prepare
  return restore_prepare(req,cache,consent,progress,adapter)
 if req.operation=='install' and req.selected!=('system','vendor','boot'):raise ValueError('업그레이드는 세 이미지가 필요합니다')
 if req.operation=='update' and not req.selected:raise ValueError('업데이트할 파티션을 선택하세요')
 cache=Path(cache);cache.mkdir(parents=True,exist_ok=True)
 with tempfile.TemporaryDirectory(prefix='ridi-gui-job-') as td:
  report=package_from_folder(req,Path(td),progress);selection=plan(report,req.operation,None if req.operation=='backup' else ','.join(req.selected),backup_before=None if req.operation=='backup' else req.backup_before)
  d=adapter.checked_disk(req.disk);identity=adapter.fingerprint(d)
  if req.format_sd:
   if os.name=='nt':
    if not devices.ctypes.windll.shell32.IsUserAnAdmin():raise ValueError('관리자 권한으로 GUI를 실행하세요')
   elif os.geteuid()!=0:raise ValueError('SD 포맷은 관리자 권한이 필요합니다. sudo -E python3 ridi_gui.py 로 실행하세요')
  summary={'disk':d,'operation':req.operation,'targets':selection['targets'],'format':req.format_sd,'file_bytes':selection['file_bytes'],'required_bytes':selection['required_bytes'],'manifest':report['manifest'],'backup':fields(selection['metadata']['update.conf'])['backup']}
  if not consent(summary):raise Cancelled('취소했습니다. SD를 변경하지 않았습니다.')
  if adapter.fingerprint(adapter.checked_disk(req.disk))!=identity:raise ValueError('확인 후 SD 장치가 변경되었습니다')
  progress('format' if req.format_sd else 'mount',0,0)
  # Guard ORIGINAL image folder as well as our frozen temporary package.
  mount=adapter.format_disk(req.disk,identity,req.folder) if req.format_sd else mounted_volume(d,adapter)
  formatted=req.format_sd;old=mount/'e70q10-update';previous=mount/'.e70q10-update.previous';moved=False
  try:
   adapter.check_mount(mount)
   if not formatted and old.exists():
    if previous.exists():raise ValueError('이전 준비 작업의 임시 폴더가 있습니다. SD를 확인하세요')
    if old.is_symlink() or not old.is_dir():raise ValueError('기존 업데이트 폴더가 정상 디렉터리가 아닙니다')
    old.rename(previous);moved=True
   try:dest=stage(report,selection,mount,req.jobs,verify_mount=False,progress=progress)
   except BaseException:
    if moved and not old.exists():previous.rename(old);moved=False
    raise
   if moved:shutil.rmtree(previous)
   with tarfile.open(report['path']) as t:ram=t.extractfile(report['members']['ram-updater.img']).read()
   if hashlib.sha256(ram).hexdigest()!=report['checksums']['ram-updater.img']:raise ValueError('RAM 이미지 해시 오류')
   conf=fields(selection['metadata']['update.conf']);state={'config':conf,'ram_sha256':hashlib.sha256(ram).hexdigest(),'ram':str(cache/'prepared-ram.img'),'disk':req.disk,'mount':str(mount),'source':str(req.folder),'targets':selection['targets']}
   temp=cache/'prepared-ram.tmp';temp.write_bytes(ram);os.replace(temp,cache/'prepared-ram.img');(cache/'prepared.json').write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
   adapter.flush_volume(mount);return state
  finally:
   if formatted and os.name!='nt':adapter.run(['umount',str(mount)])

def boot(state,tools=None,serial=None):
 ram=Path(state['ram'])
 if sha(ram)!=state['ram_sha256']:raise ValueError('준비한 RAM 이미지가 변경되었습니다')
 fastboot=platform_tool('fastboot',tools);ids=connected(fastboot);chosen=select_serial(ids,serial,None)
 command=[fastboot]+(['-s',chosen] if len(ids)>1 else [])+['boot',str(ram)]
 try:r=subprocess.run(command,capture_output=True,text=True,errors='replace',timeout=45,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0) if os.name=='nt' else 0)
 except subprocess.TimeoutExpired:raise RuntimeError('fastboot 전송에 응답이 없습니다. 기기를 fastboot로 다시 시작하고 USB를 재연결하세요.') from None
 if r.returncode:raise RuntimeError(r.stderr.strip() or r.stdout.strip() or 'RAM 부팅 실패')
 return r.stdout+r.stderr

def status(mount):
 mount=Path(mount);conf=fields((mount/'e70q10-update/update.conf').read_bytes());result=fields((mount/'e70q10-update-status/last.result').read_bytes())
 if any(conf.get(k)!=result.get(k) for k in ('job','operation','manifest','targets')+ (('backup',) if conf.get('format')=='5' else ())):raise ValueError('현재 SD 작업과 다른 과거 결과입니다')
 if result.get('exit') not in ('0','1'):
  if 'exit' not in result:raise ValueError('아직 완료 결과가 없습니다')
 return result
