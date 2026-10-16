#!/usr/bin/env python3
"""Windows/Linux installer CLI. Package creation remains a release-side job."""
from pathlib import Path
import argparse, json, os, shutil, subprocess, sys, tarfile, tempfile, time, logging
from package import validate, plan, stage, fields
from devices import inventory, checked_disk, fingerprint, format_disk, flush_volume

def platform_tool(name,directory):
    exe=name+('.exe' if os.name=='nt' else '')
    if directory:
        p=Path(directory)/exe
        if p.is_file():return str(p.resolve())
        raise ValueError('platform-tools에 '+exe+'가 없습니다.')
    appdir=Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent
    candidates=[appdir/'platform-tools'/exe]
    if os.name!='nt':candidates.append(Path('/home/juwon/ridi/host-tools/android-platform-tools/platform-tools')/exe)
    for p in candidates:
        if p.is_file():return str(p)
    found=shutil.which(exe)
    if found:return found
    raise ValueError('Android platform-tools 경로를 --platform-tools로 지정하세요.')

def connected(exe,adb=False):
    r=subprocess.run([exe,'devices'],capture_output=True,text=True,errors='replace',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0) if os.name=='nt' else 0)
    if r.returncode:raise RuntimeError(r.stderr.strip())
    return [p[0] for line in r.stdout.splitlines() if len(p:=line.split())>=2 and (p[1]=='device' if adb else p[-1]=='fastboot')]

def boot(report,tools=None,serial=None,from_adb=False):
    fastboot=platform_tool('fastboot',tools)
    baseline_name='compatibility-baseline.json'
    with tarfile.open(report['path'],'r:') as tar:
        baseline=json.loads(tar.extractfile(report['members'][baseline_name]).read())
    supported=None if report['toolkit'] and report['toolkit'].get('device_selection')=='model-checked-in-ram' else report['toolkit']['supported_serials'] if report['toolkit'] else [baseline['device_serial']]
    if from_adb:
        adb=platform_tool('adb',tools);ids=connected(adb,True)
        serial=select_serial(ids,serial,supported)
        subprocess.run([adb,'-s',serial,'reboot','fastboot'],check=True)
    deadline=time.monotonic()+45
    while True:
        ids=connected(fastboot)
        if (serial and serial in ids) or (not serial and ids):break
        if time.monotonic()>deadline:raise RuntimeError('fastboot 기기가 보이지 않습니다. 진입 상태와 Windows 드라이버를 확인하세요.')
        time.sleep(1)
    serial=select_serial(ids,serial,supported)
    with tempfile.TemporaryDirectory(prefix='ridi-ram-') as td:
        image=Path(td)/'ram-updater.img'
        with tarfile.open(report['path'],'r:') as tar,image.open('wb') as f:shutil.copyfileobj(tar.extractfile(report['members']['ram-updater.img']),f)
        from package import sha
        if sha(image)!=report['checksums']['ram-updater.img']:raise ValueError('RAM 이미지 검증 실패')
        print('RAM 부팅 후 SD 설정에 따라 설치/업데이트가 자동 시작됩니다.',flush=True)
        args=[fastboot,'boot',str(image)] if len(ids)==1 else [fastboot,'-s',serial,'boot',str(image)]
        try:result=subprocess.run(args,capture_output=True,text=True,errors='replace',timeout=45)
        except subprocess.TimeoutExpired as e:
            logging.error('fastboot timeout: %r %r',e.stdout,e.stderr)
            raise RuntimeError('fastboot가 45초 동안 응답하지 않습니다. 기기를 재시작해 fastboot로 다시 진입하고 USB를 재연결하세요.') from e
        logging.info('fastboot: %s %s',result.stdout,result.stderr)
        if result.returncode:raise RuntimeError(result.stderr.strip() or 'RAM 부팅 실패')
    print('RAM 부팅 전송 완료. 설치 완료 여부는 SD 결과 로그로 확인하세요.')

def select_serial(ids,serial,supported):
    if serial:
        if serial not in ids:raise ValueError('선택 기기가 연결되지 않았습니다.')
    elif len(ids)==1:serial=ids[0]
    else:raise ValueError('기기가 여러 대입니다. --serial로 선택하세요.')
    if supported is not None and serial not in supported:raise ValueError('아직 검증되지 않은 기기입니다. 지원 프로필을 추가한 릴리즈가 필요합니다.')
    return serial

def main(argv=None):
    p=argparse.ArgumentParser(description='RIDI Android 8 SD 준비 / fastboot RAM 설치 도구')
    p.add_argument('--log-dir',type=Path,default=Path.home()/'ridi-emmc-logs')
    sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('disks',help='SD 후보와 전체 디스크 목록')
    inspect=sub.add_parser('inspect');inspect.add_argument('archive',type=Path)
    prep=sub.add_parser('prepare',help='패키지 검증 후 SD 준비')
    prep.add_argument('archive',type=Path);group=prep.add_mutually_exclusive_group(required=True);group.add_argument('--disk',help='Linux /dev/sdX 또는 Windows 디스크 번호');group.add_argument('--mount',type=Path,help='이미 포맷한 FAT32 SD 루트')
    prep.add_argument('--operation',choices=['install','install-test','update','backup'],default='install-test');prep.add_argument('--targets');prep.add_argument('--manual',action='store_true');prep.add_argument('--no-reboot',action='store_true');prep.add_argument('--jobs',type=int,default=8)
    b=sub.add_parser('boot',help='패키지와 짝인 RAM 이미지를 fastboot boot')
    b.add_argument('archive',type=Path);b.add_argument('--platform-tools',type=Path);b.add_argument('--serial');b.add_argument('--from-adb',action='store_true')
    status=sub.add_parser('status');status.add_argument('mount',type=Path)
    a=p.parse_args(argv)
    a.log_dir.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(filename=a.log_dir/(time.strftime('%Y%m%d-%H%M%S')+'.log'),level=logging.INFO,encoding='utf-8')
    try:
        if a.command=='disks':
            for d in inventory():print(d['id'],d['name'],round(d['bytes']/1e9,2),'GB',d['transport'],d.get('serial') or '')
        elif a.command=='status':
            result=a.mount/'e70q10-update-status/last.result'
            if not result.is_file():raise ValueError('완료 결과가 없습니다. 아직 작업 중이거나 RAM 로그 확인이 필요합니다.')
            text=result.read_text(encoding='ascii');record=fields(text.encode('ascii'))
            conf=a.mount/'e70q10-update/update.conf'
            current=fields(conf.read_bytes())
            if record.get('manifest')!=current.get('manifest') or record.get('targets')!=current.get('targets') or (current.get('format') in ('2','3','4','5') and record.get('operation')!=current.get('operation')) or (current.get('format') in ('3','4','5') and record.get('job')!=current.get('job')):raise ValueError('현재 SD 작업과 다른 과거 결과입니다. 아직 완료가 확인되지 않았습니다.')
            if current.get('format')=='5' and record.get('backup')!=current.get('backup'):raise ValueError('현재 SD 백업 옵션과 다른 결과입니다.')
            print(text)
        else:
            print('PC 이미지 검증 중 (압축·원본 해시 및 크기)',flush=True);started=time.monotonic();report=validate(a.archive)
            logging.info('PC validation %.3fs: %s',time.monotonic()-started,report['pc_image_validation'])
            print(f'PC 이미지 검증 완료 ({time.monotonic()-started:.1f}초)',flush=True)
            if a.command=='inspect':print(json.dumps({'available':report['available'],'configuration':report['config'],'toolkit':report['toolkit'],'archive_sha256':report['archive_sha256']},ensure_ascii=False,indent=2))
            elif a.command=='boot':boot(report,a.platform_tools,a.serial,a.from_adb)
            elif a.command=='prepare':
                selection=plan(report,a.operation,a.targets,a.manual,a.no_reboot)
                if not 1<=a.jobs<=32:raise ValueError('--jobs는 1..32입니다.')
                mount=a.mount;formatted=False
                if a.disk:
                    d=checked_disk(a.disk);identity=fingerprint(d)
                    answer=input(f'경고: {a.disk} ({d["name"]}, {d["bytes"]/1e9:.2f}GB)의 모든 데이터를 삭제합니다. RAM 부팅 시 {a.operation} 작업이 자동 실행될 수 있습니다. 계속할까요? [y/N] ')
                    if answer.lower() not in ('y','yes'):print('취소했습니다.');return 0
                    mount=format_disk(a.disk,identity,a.archive);formatted=True
                try:dest=stage(report,selection,mount,a.jobs)
                finally:
                    if formatted and os.name!='nt':
                        flush_volume(mount);subprocess.run(['umount',str(mount)],check=True)
                print('SD 준비 완료:',dest,'/ 작업:',a.operation,'/ 대상:',','.join(selection['targets']))
        return 0
    except (ValueError,RuntimeError,OSError,KeyError,subprocess.CalledProcessError) as e:
        logging.exception('operation failed');print('중단:',e,file=sys.stderr);return 1
if __name__=='__main__':sys.exit(main())
