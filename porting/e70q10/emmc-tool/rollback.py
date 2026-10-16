"""Same-device, byte-exact snapshot rollback. No firmware-region writes."""
from pathlib import Path
import hashlib,json,os,re,struct,uuid,shutil
from folder_package import runtime_seed,repack_ram
from package import sha,fields

CHUNK=268435456
PROTECTED_END=104448*512

def digest_range(path,offset,size):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  f.seek(offset)
  while size:
   b=f.read(min(size,4<<20))
   if not b:raise ValueError('백업 파일이 잘렸습니다')
   h.update(b);size-=len(b)
 return h.hexdigest()

def snapshot(folder,progress=lambda *a:None):
 root=Path(folder).resolve(strict=True)
 if not root.is_dir():raise ValueError('백업 작업 폴더를 선택하세요')
 for p in root.iterdir():
  if p.is_symlink() or not p.is_file():raise ValueError('백업에 링크나 하위 폴더가 있습니다')
 meta=fields((root/'device.txt').read_bytes())
 if set(meta)!={'cid','userarea_bytes','chunk_bytes'}:raise ValueError('지원하지 않는 백업 메타데이터')
 cid=meta['cid']
 if not re.fullmatch('[0-9a-f]{32}',cid):raise ValueError('백업 CID 오류')
 size=int(meta['userarea_bytes'])
 if meta['chunk_bytes']!=str(CHUNK) or not 64<<20 <= size <= 16<<30 or size%65536:raise ValueError('지원하지 않는 백업 용량')
 if (root/'complete').read_bytes() not in ((cid+':'+str(size)).encode(),(cid+':'+str(size)+'\n').encode()):raise ValueError('미완료 백업입니다')
 rows={}
 for line in (root/'SHA256SUMS').read_text(encoding='ascii').splitlines():
  m=re.fullmatch('([0-9a-f]{64})  ([a-zA-Z0-9.]+)',line)
  if not m or m[2] in rows:raise ValueError('백업 체크섬 목록 오류')
  rows[m[2]]=m[1]
 names=[f'emmc.part{i:02d}' for i in range((size+CHUNK-1)//CHUNK)]
 expected=set(names)|{'boot0.bin','boot1.bin','device.txt'}
 if set(rows)!=expected or {p.name for p in root.iterdir()}!=expected|{'complete','SHA256SUMS'}:raise ValueError('백업 파일 누락 또는 알 수 없는 파일')
 total=0;pieces=[]
 for i,name in enumerate(names):
  n=min(CHUNK,size-i*CHUNK)
  if (root/name).stat().st_size!=n:raise ValueError('백업 조각 크기 오류: '+name)
 for name in ('boot0.bin','boot1.bin'):
  n=(root/name).stat().st_size
  if not 0<n<64<<20 or n%512:raise ValueError('boot 영역 백업 크기 오류')
 for name in sorted(expected):
  p=root/name;before=p.stat()
  progress('validate-backup',total,size)
  if sha(p)!=rows[name]:raise ValueError('백업 해시 불일치: '+name)
  after=p.stat()
  if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise ValueError('검증 중 백업이 변경됐습니다')
  if name in names:total+=after.st_size
 for i,name in enumerate(names):
  skip=PROTECTED_END if i==0 else 0;n=min(CHUNK,size-i*CHUNK)
  pieces.append({'name':name,'bytes':n,'sha256':rows[name],'skip':skip,'start':(i*CHUNK+skip)//512,'count':(n-skip)//512,'write_sha256':digest_range(root/name,skip,n-skip) if skip else rows[name]})
 first=root/names[0]
 return {'cid':cid,'bytes':size,'pieces':pieces,'checks':rows,'sizes':{n:(root/n).stat().st_size for n in expected},'prefix_sha256':digest_range(first,512,PROTECTED_END-512),'mbr_sha256':digest_range(first,0,512),'backup_job':root.name}

def prepare(req,cache,consent,progress,adapter):
 # Rollback never formats or relocates the only backup.
 from gui_backend import mounted_volume,Cancelled
 if req.format_sd:raise ValueError('롤백에서는 SD 포맷을 사용할 수 없습니다')
 d=adapter.checked_disk(req.disk);identity=adapter.fingerprint(d);mount=mounted_volume(d,adapter).resolve();adapter.check_mount(mount)
 root=Path(req.folder).resolve(strict=True)
 if not re.fullmatch('[0-9a-f]{32}',root.name):raise ValueError('백업 작업 ID 폴더를 선택하세요')
 plan=snapshot(root,progress)
 expected=mount/'e70q10-backups'/plan['cid']/root.name
 if root!=expected:raise ValueError('선택한 SD의 e70q10-backups/CID/작업ID 폴더를 선택하세요. PC 백업은 먼저 이 위치로 복사하세요.')
 seed=runtime_seed(req.runtime);job=uuid.uuid4().hex
 manifest=hashlib.sha256(json.dumps(plan,sort_keys=True).encode()).hexdigest()
 conf=f'format=5\noperation=restore\nmanifest={manifest}\ntargets=emmc\nbackup=none\njob={job}\nreboot=1\n'.encode()
 # Template is shipped as source with the desktop bundle, never loaded from SD.
 template=(Path(__file__).resolve().parent/'ram-restore.sh').read_text()
 checks=''.join(f'{h}  {n}\n' for n,h in sorted(plan['checks'].items()))
 pieces=''.join(f"{p['name']} {p['skip']//1048576} {p['start']} {p['count']} {p['write_sha256']}\n" for p in plan['pieces'])
 values={'CID':plan['cid'],'BYTES':str(plan['bytes']),'JOB':job,'BACKUP_JOB':root.name,'MANIFEST':manifest,'CONF_SHA':hashlib.sha256(conf).hexdigest(),'PREFIX_SHA':plan['prefix_sha256'],'MBR_SHA':plan['mbr_sha256'],'CHECKS':checks.rstrip(),'PIECES':pieces.rstrip(),'SIZES':''.join(f'{n} {v}\n' for n,v in sorted(plan['sizes'].items())).rstrip()}
 for k,v in values.items():template=template.replace('@'+k+'@',v)
 if re.search('@[A-Z_]+@',template):raise ValueError('롤백 런타임 템플릿 오류')
 ram,_,_=repack_ram(seed['ram-updater.img'],manifest,{'bin/auto-update':template.encode()})
 summary={'disk':d,'operation':'restore','targets':('emmc',),'format':False,'backup':'none','manifest':manifest,'file_bytes':len(ram),'required_bytes':len(ram),'restore_cid':plan['cid']}
 if not consent(summary):raise Cancelled('롤백 준비를 취소했습니다. SD를 변경하지 않았습니다.')
 if adapter.fingerprint(adapter.checked_disk(req.disk))!=identity:raise ValueError('확인 후 SD가 변경됐습니다')
 # Confirm source metadata did not change during consent; RAM rehashes every byte before writes.
 if fields((root/'device.txt').read_bytes())['cid']!=plan['cid']:raise ValueError('백업이 변경됐습니다')
 old=mount/'e70q10-update';previous=mount/'.e70q10-update.previous';tmp=mount/'.e70q10-restore.new'
 if previous.exists() or tmp.exists():raise ValueError('이전 SD 준비 임시 폴더를 확인하세요')
 if old.exists() and (old.is_symlink() or not old.is_dir()):raise ValueError('잘못된 업데이트 폴더')
 tmp.mkdir()
 try:
  (tmp/'update.conf').write_bytes(conf);(tmp/'ram-updater.img').write_bytes(ram);adapter.flush_volume(mount)
  if os.name=='nt':
   from devices import windows_readback_sha
   conf_hash=windows_readback_sha(tmp/'update.conf');ram_hash=windows_readback_sha(tmp/'ram-updater.img')
  else:conf_hash=sha(tmp/'update.conf');ram_hash=sha(tmp/'ram-updater.img')
  if conf_hash!=hashlib.sha256(conf).hexdigest() or ram_hash!=hashlib.sha256(ram).hexdigest():raise ValueError('롤백 SD 읽기 검증 실패')
  if old.exists():old.rename(previous)
  try:tmp.rename(old)
  except BaseException:
   if previous.exists():previous.rename(old)
   raise
  if previous.exists():shutil.rmtree(previous)
 finally:
  if tmp.exists():shutil.rmtree(tmp)
 cache=Path(cache);cache.mkdir(parents=True,exist_ok=True);temp=cache/'prepared-ram.tmp';temp.write_bytes(ram);os.replace(temp,cache/'prepared-ram.img')
 state={'config':fields(conf),'ram_sha256':hashlib.sha256(ram).hexdigest(),'ram':str(cache/'prepared-ram.img'),'disk':req.disk,'mount':str(mount),'source':str(root),'targets':('emmc',)}
 (cache/'prepared.json').write_text(json.dumps(state,indent=2));adapter.flush_volume(mount)
 return state
