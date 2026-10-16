"""Portable package validation and SD selection; no host-specific commands."""
from pathlib import Path, PurePosixPath
import hashlib, json, tarfile, re, shutil, os, tempfile, uuid, gzip, time, logging, threading
from concurrent.futures import ThreadPoolExecutor
ORDER = ('system', 'vendor', 'boot')
RANGES = {'system': ('system.raw.gz',172032,2097152), 'vendor': ('vendor.raw.gz',14733312,524288), 'boot': ('boot.raw.gz',104448,65536)}
PREFIX = 'e70q10-update'
MIN_SD = 15_000_000_000
BACKUP_BYTES = 7_818_182_656

def digest(stream):
    h=hashlib.sha256()
    for chunk in iter(lambda:stream.read(8<<20), b''): h.update(chunk)
    return h.hexdigest()

def sha(path):
    with Path(path).open('rb') as f: return digest(f)

def targets(value):
    parts=list(ORDER) if value=='all' else value.split(',')
    if not parts or len(set(parts))!=len(parts) or any(p not in ORDER for p in parts):
        raise ValueError('대상은 boot/system/vendor/all 또는 쉼표 조합입니다.')
    return tuple(p for p in ORDER if p in parts)

def safe_name(name):
    p=PurePosixPath(name)
    # Windows traversal/ADS/device names are rejected on every host.
    if not name or name.startswith('/') or '\\' in name or ':' in name or any(x in ('','.', '..') for x in name.split('/')):
        raise ValueError('안전하지 않은 패키지 경로: '+name)
    for part in p.parts:
        stem=part.split('.')[0].upper()
        if part.endswith((' ','.')) or stem in {'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))}:
            raise ValueError('Windows에서 사용할 수 없는 경로: '+name)
    return p

def sums(data):
    out={}
    for line in data.decode('ascii').splitlines():
        m=re.fullmatch(r'([0-9a-f]{64})  (.+)',line)
        if not m or m[2] in out: raise ValueError('해시 목록 오류')
        safe_name(m[2]);out[m[2]]=m[1]
    return out

def fields(data):
    out={}
    for line in data.decode('ascii').splitlines():
        k,sep,v=line.partition('=')
        if not sep or k in out: raise ValueError('설정 항목 누락/중복')
        out[k]=v
    return out

class ImageReader:
    """One bounded compressed pass: gzip CRC, compressed/raw hashes and raw size."""
    def __init__(self, stream, count):
        self.stream=stream;self.left=count;self.hash=hashlib.sha256()
    def read(self, size=-1):
        size=self.left if size<0 else min(size,self.left)
        data=self.stream.read(size)
        if size and not data:raise ValueError('압축 이미지가 검증 중 잘렸습니다.')
        self.left-=len(data);self.hash.update(data);return data

def verify_image(path, member, raw_bytes, raw_hash, compressed_hash):
    started=time.monotonic();h=hashlib.sha256();total=0
    try:
        with Path(path).open('rb') as f:
            f.seek(member.offset_data);reader=ImageReader(f,member.size)
            with gzip.GzipFile(fileobj=reader,mode='rb') as raw:
                for chunk in iter(lambda:raw.read(4<<20),b''):
                    total+=len(chunk)
                    if total>raw_bytes:raise ValueError('이미지 해제 크기가 파티션보다 큽니다: '+member.name)
                    h.update(chunk)
            if reader.left or reader.hash.hexdigest()!=compressed_hash:raise ValueError('압축 이미지 해시 불일치: '+member.name)
    except (EOFError,gzip.BadGzipFile) as e:
        raise ValueError('압축 이미지가 손상되었습니다: '+member.name) from e
    if total!=raw_bytes or h.hexdigest()!=raw_hash:raise ValueError('이미지 해제 크기/해시 불일치: '+member.name)
    return {'file':member.name,'raw_bytes':total,'seconds':round(time.monotonic()-started,3)}

def validate(path):
    path=Path(path).resolve(strict=True)
    expected=sums(Path(str(path)+'.sha256').read_bytes())
    if set(expected)!={path.name} or sha(path)!=expected[path.name]: raise ValueError('배포 파일 해시 불일치')
    with tarfile.open(path,'r:') as tar:
        members={};seen=set();case_seen=set()
        for m in tar.getmembers():
            safe_name(m.name.rstrip('/') if m.isdir() else m.name)
            p=PurePosixPath(m.name)
            if p.parts[0]!=PREFIX or len(p.parts)<1 or not (m.isdir() or m.isfile()): raise ValueError('패키지 항목 오류')
            if m.name in seen or m.name.casefold() in case_seen: raise ValueError('중복 패키지 경로')
            seen.add(m.name);case_seen.add(m.name.casefold())
            if m.isfile():
                name=str(PurePosixPath(*p.parts[1:]));safe_name(name)
                if m.size >= 4<<30: raise ValueError('FAT32 파일 크기 초과')
                members[name]=m
        def read(n): return tar.extractfile(members[n]).read()
        checks=sums(read('SHA256SUMS'))
        if set(checks)!=set(members)-{'SHA256SUMS'}:raise ValueError('패키지 해시 범위 오류')
        for n,h in checks.items():
            if n not in {v[0] for v in RANGES.values()} and digest(tar.extractfile(members[n]))!=h:raise ValueError('파일 해시 불일치: '+n)
        manifest=read('manifest.tsv');mh=hashlib.sha256(manifest).hexdigest();rows=[l.split() for l in manifest.decode('ascii').splitlines()]
        available=[];image_work=[]
        for row in rows:
            if len(row)!=5: raise ValueError('이미지 목록 오류')
            roles=[r for r in ORDER if row[:3]==list(map(str,RANGES[r]))]
            if len(roles)!=1 or not re.fullmatch('[a-f0-9]{64}',row[3]) or checks.get(row[0])!=row[4]: raise ValueError('허용하지 않는 파티션/이미지')
            available+=roles
            image_work.append((path,members[row[0]],int(row[2])*512,row[3],row[4]))
        if (not available and fields(read('update.conf')).get('operation')!='backup') or tuple(available)!=tuple(r for r in ORDER if r in available):raise ValueError('중복/순서 오류')
        conf=fields(read('update.conf'));version=conf.get('format')
        keys={'format','manifest','targets','autostart','reboot'}
        toolkit=json.loads(read('toolkit.json')) if 'toolkit.json' in members else None
        if version in ('2','3','4','5'):
            keys|={'operation','backup'}
            if version in ('3','4','5'):keys|={'job','userdata','partitioning'}
            if version in ('4','5'):keys|={'cache'}
            if not toolkit or toolkit.get('schema')!=int(version):raise ValueError('통합 RAM 설치기가 없는 패키지')
        elif version!='1':raise ValueError('지원하지 않는 설정 버전')
        if set(conf)!=keys or conf['manifest']!=mh or conf['autostart'] not in ('0','1') or conf['reboot'] not in ('0','1'):raise ValueError('설정 오류')
        chosen=() if conf.get('operation')=='backup' and conf['targets']=='none' else targets(conf['targets'])
        if (','.join(chosen) if chosen else 'none')!=conf['targets'] or not set(chosen)<=set(available):raise ValueError('선택 이미지 없음')
        if version in ('2','3','4','5'):
            operations=('install','update','install-test','backup') if version in ('4','5') else ('install','update','install-test') if version=='3' else ('install','update')
            backup_expected='required' if conf['operation'] in ('install','install-test','backup') else 'none'
            optional=version=='5' and conf['operation'] in ('install','update')
            if conf['operation'] not in operations or conf['backup'] not in (('none','required') if optional else (backup_expected,)):raise ValueError('설치/백업 작업 설정 오류')
        if version in ('2','3','4','5') and conf['operation'] in ('install','install-test') and chosen!=ORDER:raise ValueError('초기 설치는 세 이미지 모두 필요')
        if version in ('3','4','5'):
            if not re.fullmatch('[0-9a-f]{32}',conf['job']):raise ValueError('작업 ID 오류')
            preservation='create' if conf['operation']=='install' else 'preserve'
            if conf['userdata']!=preservation or conf['partitioning']!=preservation:raise ValueError('userdata/파티션 보존 정책 오류')
        if version in ('4','5') and conf['cache']!=('preserve' if conf['operation'] in ('update','backup') else 'create'):raise ValueError('cache 생성 정책 오류')
        if conf.get('operation')=='backup' and (conf['targets']!='none' or conf['reboot']!='0'):raise ValueError('백업은 기록 대상 없이 RAM에 남아야 합니다.')
        for n in ('userdata.raw.gz','cache.raw.gz'):
            if n in members:raise ValueError('RAM 생성 파일시스템 이미지는 배포하지 않습니다.')
        if {n for n in members if n in {v[0] for v in RANGES.values()}}!={row[0] for row in rows}:raise ValueError('이미지 검증 범위 오류')
        with ThreadPoolExecutor(max_workers=3) as pool:
            image_proof=list(pool.map(lambda args:verify_image(*args),image_work))
        checks['SHA256SUMS']=hashlib.sha256(read('SHA256SUMS')).hexdigest()
        return {'path':path,'archive_sha256':expected[path.name],'members':members,'checksums':checks,'available':tuple(available),'manifest':mh,'config':conf,'toolkit':toolkit,'pc_image_validation':image_proof}

def plan(report,operation='update',selected=None,manual=False,no_reboot=False,backup_before=None):
    if operation=='backup':
        if selected not in (None,'none'):raise ValueError('백업 모드는 --targets를 지정하지 않습니다.')
        if report['config']['format'] not in ('4','5') or not report['toolkit'] or 'backup' not in report['toolkit']['operations']:raise ValueError('백업 전용 RAM 모드를 지원하지 않는 패키지입니다.')
        chosen=()
    else:chosen=targets(selected) if selected else targets(report['config']['targets'])
    if not set(chosen)<=set(report['available']):raise ValueError('패키지에 선택 이미지가 없습니다.')
    if operation not in ('install','update','install-test','backup'):raise ValueError('지원하지 않는 작업')
    if operation in ('install','install-test'):
        if not report['toolkit'] or operation not in report['toolkit']['operations']:raise ValueError('이 패키지는 초기 설치를 지원하지 않습니다. 통합 패키지를 만드세요.')
        if chosen!=ORDER:raise ValueError('초기 설치에는 --targets all이 필요합니다.')
    conf=dict(report['config']);conf['targets']=','.join(chosen) if chosen else 'none'
    conf['autostart']=str(int(conf['autostart']=='1' and not manual));conf['reboot']=str(int(conf['reboot']=='1' and not no_reboot and operation!='backup'))
    if conf['format'] in ('2','3','4','5'):conf.update(operation=operation,backup='required' if operation in ('install','install-test','backup') else 'none')
    if conf['format'] in ('3','4','5'):
        conf.update(job=uuid.uuid4().hex,userdata='create' if operation=='install' else 'preserve',partitioning='create' if operation=='install' else 'preserve')
    if conf['format'] in ('4','5'):conf['cache']='preserve' if operation in ('update','backup') else 'create'
    if backup_before is not None:
        requested='required' if backup_before else 'none'
        if operation in ('backup','install-test') and requested!='required':raise ValueError('이 시험 작업은 전체 백업이 필요합니다.')
        if conf['format']!='5' and requested!=conf.get('backup'):raise ValueError('백업 옵션은 format=5 RAM 런타임이 필요합니다.')
        conf['backup']=requested
    data=(''.join(k+'='+v+'\n' for k,v in conf.items())).encode('ascii')
    skipped={RANGES[r][0] for r in ORDER if r not in chosen}
    if 'boot' not in chosen:skipped.add('boot-emmc.img')
    names=set(report['members'])-skipped
    checks={n:report['checksums'][n] for n in names if n!='SHA256SUMS'};checks['update.conf']=hashlib.sha256(data).hexdigest()
    checkdata=''.join(checks[n]+'  '+n+'\n' for n in sorted(checks)).encode('ascii')
    checks['SHA256SUMS']=hashlib.sha256(checkdata).hexdigest()
    metadata={'update.conf':data,'SHA256SUMS':checkdata}
    size=sum(report['members'][n].size for n in names if n not in metadata)+sum(map(len,metadata.values()))
    return {'names':names,'metadata':metadata,'checksums':checks,'targets':chosen,'operation':operation,'file_bytes':size,'required_bytes':size+(BACKUP_BYTES+(64<<20) if conf.get('backup')=='required' else 0)+(128<<20)}

def stage(report,selection,mount,jobs=8,verify_mount=True,progress=None):
    mount=Path(mount).resolve(strict=True)
    if not 1<=jobs<=32:raise ValueError('병렬 작업은 1..32입니다.')
    if verify_mount:
        from devices import check_mount
        check_mount(mount)
    if shutil.disk_usage(mount).free<selection['required_bytes']:raise ValueError('SD의 설치/백업 여유 공간이 부족합니다.')
    dest=mount/PREFIX
    if os.path.lexists(dest):raise ValueError('기존 e70q10-update 폴더를 먼저 다른 이름으로 옮기세요.')
    lock=mount/'.e70q10-prepare.lock';lock.mkdir();tmp=None
    try:
        tmp=Path(tempfile.mkdtemp(prefix='.e70q10-stage-',dir=mount))
        work=[(n,report['members'][n]) for n in sorted(selection['names']) if n not in selection['metadata']]
        counters={'copy':0,'verify':0};counter_lock=threading.Lock()
        def advance(phase,n):
            if progress:
                with counter_lock:
                    counters[phase]+=n;progress(phase,counters[phase],selection['file_bytes'])
        def copy(item):
            name,m=item;target=tmp/name;target.parent.mkdir(parents=True,exist_ok=True)
            with report['path'].open('rb') as f,target.open('xb') as out:
                f.seek(m.offset_data);left=m.size;h=hashlib.sha256()
                while left:
                    chunk=f.read(min(left,8<<20))
                    if not chunk:raise ValueError('배포 파일이 복사 중 잘렸습니다.')
                    out.write(chunk);h.update(chunk);left-=len(chunk);advance('copy',len(chunk))
                out.flush();os.fsync(out.fileno())
            if h.hexdigest()!=report['checksums'][name]:raise ValueError('복사 중 원본 변경: '+name)
        copy_started=time.monotonic()
        print('선택 파일 복사:',','.join(selection['targets']),flush=True)
        with ThreadPoolExecutor(max_workers=jobs) as pool:list(pool.map(copy,work))
        for name,data in selection['metadata'].items():
            with (tmp/name).open('xb') as out:out.write(data);out.flush();os.fsync(out.fileno())
            advance('copy',len(data))
        from devices import flush_volume
        if progress:progress('flush',0,0)
        flush_volume(mount)
        copy_seconds=time.monotonic()-copy_started
        logging.info('SD copy+flush: %.3fs, jobs=%d, bytes=%d',copy_seconds,jobs,selection['file_bytes'])
        verify_started=time.monotonic()
        print('SD 읽기 검증',flush=True)
        def check(name):
            if os.name=='nt':
                from devices import windows_readback_sha
                actual=windows_readback_sha(tmp/name)
            else:
                with (tmp/name).open('rb') as f:
                    if hasattr(os,'posix_fadvise'):os.posix_fadvise(f.fileno(),0,0,os.POSIX_FADV_DONTNEED)
                    actual=digest(f)
            if actual!=selection['checksums'][name]:raise ValueError('SD 검증 실패: '+name)
            advance('verify',(tmp/name).stat().st_size)
        with ThreadPoolExecutor(max_workers=jobs) as pool:list(pool.map(check,selection['names']))
        if os.path.lexists(dest):raise ValueError('복사 중 대상 폴더가 생겼습니다.')
        verify_seconds=time.monotonic()-verify_started
        logging.info('SD readback: %.3fs',verify_seconds)
        print(f'SD 복사 {copy_seconds:.1f}초 / 읽기 검증 {verify_seconds:.1f}초',flush=True)
        tmp.rename(dest);tmp=None;flush_volume(mount)
        return dest
    finally:
        if tmp is not None:shutil.rmtree(tmp,ignore_errors=True)
        lock.rmdir()
