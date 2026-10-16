"""OS adapters. Mutations recheck the selected external disk identity."""
from pathlib import Path
import subprocess, json, os, base64, time, ctypes
from package import MIN_SD

def run(args):
    result=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',errors='replace',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0) if os.name=='nt' else 0)
    if result.returncode:raise RuntimeError(result.stderr.strip() or result.stdout.strip() or '장치 명령 실패')
    return result.stdout.strip()

def ps(code):
    encoded=base64.b64encode(("$ErrorActionPreference='Stop'; [Console]::OutputEncoding=New-Object System.Text.UTF8Encoding($false); $OutputEncoding=[Console]::OutputEncoding; "+code).encode('utf-16le')).decode('ascii')
    return run(['powershell.exe','-NoProfile','-NonInteractive','-EncodedCommand',encoded])

def linux_inventory():
    return json.loads(run(['lsblk','-Jbpo','NAME,TYPE,SIZE,RM,TRAN,SERIAL,MODEL,MOUNTPOINTS,LOG-SEC']))['blockdevices']

def inventory():
    if os.name=='nt':
        data=ps("@(Get-Disk | Select-Object Number,FriendlyName,SerialNumber,UniqueId,Size,@{Name='BusType';Expression={[string]$_.BusType}},IsBoot,IsSystem,IsReadOnly,LogicalSectorSize) | ConvertTo-Json -Depth 4 -Compress")
        rows=json.loads(data or '[]');rows=rows if isinstance(rows,list) else [rows]
        return [{'id':str(r['Number']),'name':r['FriendlyName'],'serial':r['SerialNumber'],'identity':r['UniqueId'],'bytes':int(r['Size']),'transport':str(r['BusType']),'system':r['IsBoot'] or r['IsSystem'],'readonly':r['IsReadOnly'],'sector':r['LogicalSectorSize']} for r in rows]
    return [{'id':r['name'],'name':r.get('model'),'serial':r.get('serial'),'identity':str(Path(r['name']).resolve()),'bytes':int(r['size']),'transport':r.get('tran'),'removable':r['rm'],'sector':r['log-sec'],'row':r} for r in linux_inventory() if r['type']=='disk']

def checked_disk(identifier):
    rows=[r for r in inventory() if r['id']==identifier]
    if len(rows)!=1:raise ValueError('선택한 전체 디스크를 찾을 수 없습니다.')
    d=rows[0]
    if d['bytes']<MIN_SD:raise ValueError('16GB 이상 SD카드를 준비하세요.')
    if d['sector']!=512 or d['bytes']>2_199_023_255_552:raise ValueError('지원하지 않는 섹터/디스크 크기')
    if os.name=='nt':
        if d['system'] or d['readonly'] or d['transport'] not in ('USB','SD','MMC'):raise ValueError('쓰기 가능한 외장 SD/USB 디스크만 허용합니다.')
        n=int(d['id'])
        # Pagefile and system volumes must never be erased.
        blocked=ps(f"$parts=@(Get-Partition -DiskNumber {n} -ErrorAction SilentlyContinue); $blocked=$false; foreach($p in $parts){{ if($p.IsBoot -or $p.IsSystem){{$blocked=$true}}; if($p.DriveLetter){{$letter=[string]$p.DriveLetter; if(($letter+':') -eq $env:SystemDrive){{$blocked=$true}}; foreach($f in @(Get-CimInstance Win32_PageFileUsage)){{if($f.Name.StartsWith($letter+':',[System.StringComparison]::OrdinalIgnoreCase)){{$blocked=$true}}}} }} }}; $blocked | ConvertTo-Json")
        if json.loads(blocked):raise ValueError('시스템 또는 페이지 파일 디스크입니다.')
    else:
        if not d.get('removable') and d['transport']!='usb':raise ValueError('외장 SD/USB 디스크만 허용합니다.')
        def visit(row):
            if row['type'] not in ('disk','part'):raise ValueError('활성 RAID/장치 매퍼가 있습니다.')
            for mp in row.get('mountpoints',[]) or []:
                if mp and not mp.startswith(('/media/','/mnt/','/run/media/')):raise ValueError('시스템/비표준 마운트가 있습니다: '+mp)
            block=Path('/sys/class/block')/Path(row['name']).name
            if list((block/'holders').iterdir()):raise ValueError('활성 block holder가 있습니다.')
            for c in row.get('children',[]):visit(c)
        visit(d['row'])
    return d

def fingerprint(d):return tuple(d[k] for k in ('id','identity','serial','bytes','sector'))

def format_disk(identifier,expected,archive_path):
    d=checked_disk(identifier)
    if fingerprint(d)!=expected:raise ValueError('확인 후 장치가 변경되었습니다.')
    if os.name=='nt':
        if not ctypes.windll.shell32.IsUserAnAdmin():raise ValueError('관리자 권한으로 실행하세요.')
        n=int(identifier)
        # Refuse a package hosted by the very disk being erased.
        volume=windows_volume_root(archive_path)
        encoded_path=base64.b64encode(volume.encode('utf-8')).decode('ascii')
        pn=ps(f"$root=[System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{encoded_path}')); @(Get-Partition | Where-Object {{$_.AccessPaths -contains $root}} | Select-Object -ExpandProperty DiskNumber) | ConvertTo-Json -Compress")
        numbers=json.loads(pn or '[]');numbers=numbers if isinstance(numbers,list) else [numbers]
        if n in numbers:raise ValueError('설치 파일이 선택한 SD에 있습니다. PC로 옮기세요.')
        if not numbers and not volume.startswith('\\\\'):raise ValueError('원본 파일의 저장 디스크를 확인할 수 없습니다.')
        size=min(d['bytes']-(8<<20),32_000_000_000);size=size//(1<<20)*(1<<20)
        expected64=base64.b64encode(json.dumps({'identity':d['identity'],'serial':d['serial'],'bytes':d['bytes'],'sector':d['sector']}).encode('utf-8')).decode('ascii')
        code=f"$e=[System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{expected64}')) | ConvertFrom-Json; $d=Get-Disk -Number {n}; if($d.IsBoot -or $d.IsSystem -or $d.IsReadOnly -or ([string]$d.BusType -notin @('USB','SD','MMC')) -or $d.UniqueId -ne $e.identity -or $d.SerialNumber -ne $e.serial -or $d.Size -ne $e.bytes -or $d.LogicalSectorSize -ne $e.sector){{throw 'protected or changed disk'}}; $parts=@(Get-Partition -DiskNumber {n} -ErrorAction SilentlyContinue); foreach($part in $parts){{if($part.IsBoot -or $part.IsSystem){{throw 'system partition'}}; foreach($pf in @(Get-CimInstance Win32_PageFileUsage)){{if($part.DriveLetter -and $pf.Name.StartsWith(([string]$part.DriveLetter+':'),[System.StringComparison]::OrdinalIgnoreCase)){{throw 'pagefile disk'}}}}}}; $d | Clear-Disk -RemoveData -RemoveOEM -Confirm:$false; $d=Get-Disk -Number {n}; if($d.PartitionStyle -eq 'RAW'){{$d | Initialize-Disk -PartitionStyle MBR}}; if((Get-Disk -Number {n}).PartitionStyle -ne 'MBR'){{throw 'MBR initialization failed'}}; $p=New-Partition -DiskNumber {n} -Size {size} -MbrType FAT32 -AssignDriveLetter; $p | Format-Volume -FileSystem FAT32 -NewFileSystemLabel RIDI_UPD -Confirm:$false | Out-Null; [string](Get-Partition -DiskNumber {n} -PartitionNumber 1).DriveLetter"
        result=ps(code).splitlines()[-1].strip()
        if len(result)!=1 or not result.isalpha():raise RuntimeError('SD 드라이브 문자를 확인할 수 없습니다.')
        mount=Path(result+':\\');check_mount(mount);return mount
    if os.geteuid()!=0:raise ValueError('SD 포맷은 sudo로 실행하세요.')
    source=json.loads(run(['findmnt','-J','-T',str(Path(archive_path).resolve())]))['filesystems'][0]['source']
    def nodes(row):return [row['name']]+[n for c in row.get('children',[]) for n in nodes(c)]
    if source.split('[')[0] in nodes(d['row']):raise ValueError('설치 파일이 선택한 SD에 있습니다. PC로 옮기세요.')
    mount=Path('/mnt/ridi-sd-'+Path(identifier).name)
    if subprocess.run(['findmnt','-rn','-M',str(mount)],stdout=subprocess.DEVNULL).returncode==0:raise ValueError('마운트 경로 사용 중')
    for c in reversed(nodes(d['row'])):
        row=next((x for x in d['row'].get('children',[]) if x['name']==c),None)
        if row:
            for mp in row.get('mountpoints',[]) or []:
                if mp:run(['umount',mp])
    d2=checked_disk(identifier)
    if fingerprint(d2)!=expected:raise ValueError('장치가 변경되었습니다.')
    size=min(d['bytes']-(8<<20),32_000_000_000);sectors=size//512
    script=f'label: dos\nunit: sectors\nstart=2048, size={sectors-2048}, type=c\n'
    r=subprocess.run(['sfdisk','--wipe','always',identifier],input=script,text=True,capture_output=True)
    if r.returncode:raise RuntimeError(r.stderr)
    run(['udevadm','settle']);part=identifier+('p1' if identifier[-1].isdigit() else '1')
    for _ in range(30):
        if Path(part).exists():break
        time.sleep(.1)
    run(['mkfs.vfat','-F','32','-S','512','-n','RIDI_UPD',part])
    mount.mkdir(exist_ok=True)
    run(['mount','-t','vfat','-o','rw,nosuid,nodev',part,str(mount)])
    return mount

def check_mount(mount):
    mount=Path(mount).resolve(strict=True)
    if os.name=='nt':
        letter=mount.drive.rstrip(':')
        if len(letter)!=1 or not letter.isalpha() or mount!=Path(letter+':\\'):raise ValueError('SD 드라이브 루트를 지정하세요.')
        data=json.loads(ps(f"$p=Get-Partition -DriveLetter '{letter}'; $v=$p|Get-Volume; $d=$p|Get-Disk; @{{partition=$p.PartitionNumber;disk=$d.Number;fs=$v.FileSystem;health=[string]$v.HealthStatus}} | ConvertTo-Json -Compress"))
        if data['partition']!=1 or data['fs']!='FAT32' or data['health']!='Healthy':raise ValueError('정상 FAT32 첫 번째 파티션이 필요합니다.')
        checked_disk(str(data['disk']))
    else:
        data=json.loads(run(['findmnt','-J','-M',str(mount)]))['filesystems'][0]
        if Path(data['target']).resolve()!=mount or data['fstype']!='vfat' or 'rw' not in data['options'].split(','):raise ValueError('쓰기 가능한 FAT32 마운트가 필요합니다.')
        dev=str(Path(data['source']).resolve());name=Path(dev).name
        if (Path('/sys/class/block')/name/'partition').read_text().strip()!='1' or run(['lsblk','-nro','FSVER',dev])!='FAT32':raise ValueError('FAT32 첫 번째 파티션이 필요합니다.')
        parent=run(['lsblk','-nro','PKNAME',dev]);checked_disk('/dev/'+parent)

def windows_volume_root(path):
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.GetVolumePathNameW.argtypes=[ctypes.c_wchar_p,ctypes.c_wchar_p,ctypes.c_uint32]
    kernel.GetVolumePathNameW.restype=ctypes.c_int
    buffer=ctypes.create_unicode_buffer(32768)
    if not kernel.GetVolumePathNameW(str(Path(path).resolve()),buffer,len(buffer)):raise ctypes.WinError(ctypes.get_last_error())
    return buffer.value

def flush_volume(mount):
    if os.name=='nt':
        # Flush the volume before readback, including filesystem metadata.
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.CreateFileW.argtypes=[ctypes.c_wchar_p,ctypes.c_uint32,ctypes.c_uint32,ctypes.c_void_p,ctypes.c_uint32,ctypes.c_uint32,ctypes.c_void_p]
        kernel.CreateFileW.restype=ctypes.c_void_p
        kernel.FlushFileBuffers.argtypes=[ctypes.c_void_p];kernel.CloseHandle.argtypes=[ctypes.c_void_p]
        handle=kernel.CreateFileW('\\\\.\\'+Path(mount).drive,0xC0000000,3,None,3,0,None)
        if handle==ctypes.c_void_p(-1).value:raise ctypes.WinError(ctypes.get_last_error())
        try:
            if not kernel.FlushFileBuffers(handle):raise ctypes.WinError(ctypes.get_last_error())
        finally:kernel.CloseHandle(handle)
    else:run(['sync','-f',str(mount)])

def windows_readback_sha(path,kernel=None):
    """Unbuffered, aligned SD file readback (not the Windows file cache).
    See Microsoft File Buffering docs. 64KiB alignment also covers 4KiB sectors.
    """
    import hashlib
    kernel=kernel or ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateFileW.argtypes=[ctypes.c_wchar_p,ctypes.c_uint32,ctypes.c_uint32,ctypes.c_void_p,ctypes.c_uint32,ctypes.c_uint32,ctypes.c_void_p]
    kernel.CreateFileW.restype=ctypes.c_void_p
    kernel.ReadFile.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_uint32,ctypes.POINTER(ctypes.c_uint32),ctypes.c_void_p]
    kernel.ReadFile.restype=ctypes.c_int;kernel.CloseHandle.argtypes=[ctypes.c_void_p]
    handle=kernel.CreateFileW(str(path),0x80000000,3,None,3,0x28000000,None)
    if handle==ctypes.c_void_p(-1).value:raise ctypes.WinError(ctypes.get_last_error())
    block=4<<20;align=65536;buffer=ctypes.create_string_buffer(block+align);address=(ctypes.addressof(buffer)+align-1)&~(align-1)
    left=Path(path).stat().st_size;h=hashlib.sha256()
    try:
        while left:
            count=(min(left,block)+align-1)//align*align;got=ctypes.c_uint32()
            if not kernel.ReadFile(handle,ctypes.c_void_p(address),count,ctypes.byref(got),None):raise ctypes.WinError(ctypes.get_last_error())
            if not got.value or got.value>count:raise ValueError('SD unbuffered readback truncated')
            n=min(left,got.value);h.update(ctypes.string_at(address,n));left-=n
        return h.hexdigest()
    finally:kernel.CloseHandle(handle)
