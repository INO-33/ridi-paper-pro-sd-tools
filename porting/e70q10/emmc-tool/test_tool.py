#!/usr/bin/env python3
"""Offline release checks; no physical disk formatting, USB commands, or reboot."""
from pathlib import Path
import sys,tempfile,subprocess,os,hashlib,json,struct,shutil,tarfile,types
from unittest.mock import patch
from package import validate,plan,stage,sha,targets,safe_name
from ridi_emmc import select_serial
SRC=Path(__file__).resolve().parent
archive=Path(sys.argv[1]).resolve();out=archive.with_suffix('');report=validate(archive)
logdir=Path('/home/juwon/ridi/.orchestrator/logs/emmc-model-20261008');logdir.mkdir(parents=True,exist_ok=True)
log=logdir/'offline-details.log'
proofs=[]
def passed(s):proofs.append(s)
def rejected(fn):
 try:fn()
 except (ValueError,RuntimeError,OSError):return
 raise AssertionError('expected refusal')
for name in ['../bad','a\\..\\b','C:/bad','a:stream','CON','a/NUL.txt','a.','a/../b']:
 rejected(lambda:safe_name(name))
rejected(lambda:targets('boot,boot'));rejected(lambda:select_serial(['other'],None,['PP1A1GK166561']))
rejected(lambda:select_serial(['a','b'],None,['a','b']))
assert select_serial(['OTHER-PAPER-PRO'],None,None)=='OTHER-PAPER-PRO'
rejected(lambda:plan(report,'install','boot'))
passed('unsafe Windows/Linux paths, duplicate targets, unsupported/multiple devices, partial install rejected')
with tempfile.TemporaryDirectory(prefix='ridi-tool-test-') as td:
 w=Path(td);mount=w/'sd';mount.mkdir();(mount/'keep.txt').write_text('unchanged')
 selection=plan(report,'update','boot')
 dest=stage(report,selection,mount,8,verify_mount=False)
 assert not (dest/'system.raw.gz').exists() and not (dest/'vendor.raw.gz').exists()
 assert (dest/'boot.raw.gz').exists() and (mount/'keep.txt').read_text()=='unchanged'
 assert 'operation=update' in (dest/'update.conf').read_text() and 'targets=boot' in (dest/'update.conf').read_text()
 for n,h in selection['checksums'].items():assert sha(dest/n)==h,n
 rejected(lambda:stage(report,selection,mount,verify_mount=False))
 assert not list(mount.glob('.e70q10-*'))
 passed('selected SD copy/fsync/readback, v2 metadata, existing files retained and overwrite refused')
 # Parse v2 strictly in the actual shell helper, including injection and install constraints.
 control=(SRC/'ram-control.sh').read_text().replace('@MANIFEST@',report['manifest'])
 config=w/'config';config.mkdir();file=config/'update.conf'
 runner=w/'control.sh';runner.write_text(control+'\nread_control "$1"\n')
 valid=plan(report,'install','all')['metadata']['update.conf'];file.write_bytes(valid)
 assert subprocess.run(['sh',str(runner),str(config)],capture_output=True).returncode==0
 for bad in [valid+b'operation=update\n',valid.replace(b'targets=system,vendor,boot',b'targets=boot'),valid.replace(b'backup=required',b'backup=none'),valid.replace(b'reboot=1',b'reboot=$(reboot)'),valid.replace(report['manifest'].encode(),b'0'*64)]:
  file.write_bytes(bad);assert subprocess.run(['sh',str(runner),str(config)],capture_output=True).returncode!=0
 passed('RAM control malformed/duplicate/injected/mismatched manifest and unsafe install selection rejected')
 # Actual Android ARM formatter/checker through QEMU, not a host-format substitute.
 root=out/'.ram-tools';qemu='/usr/bin/qemu-arm-static'
 arm_result='actual Android ARM formatter/checker passed under QEMU in isolated PID namespace'
 with log.open('ab') as lf:
  for role,size in [('cache',67108864),('data',6311378944)]:
   img=w/(role+'.ext4')
   env=os.environ|{'LD_LIBRARY_PATH':'/system/lib'}
   prefix=['unshare','--user','--map-root-user','--pid','--fork',qemu,'-L',str(root)]
   subprocess.run(prefix+[str(root/'system/bin/make_ext4fs'),'-l',str(size),'-a',role,'-S',str(root/'etc/file_contexts'),str(img)],check=True,env=env,stdout=lf,stderr=lf)
   subprocess.run(prefix+[str(root/'system/bin/e2fsck'),'-fn',str(img)],check=True,env=env,stdout=lf,stderr=lf)
   assert img.stat().st_size==size
   img.unlink()
 passed('actual Android ARM make_ext4fs/e2fsck checked 64MiB cache and 6019MiB userdata including SELinux contexts')
 # Reuse guard must require every backup chunk and boot-region checksum entry.
 shape=w/'backup-shape';shape.mkdir();cid='15010038474d45345201bbd3fe618400'
 sums=[]
 for n in range(30):
  name=f'emmc.part{n:02d}'
  with (shape/name).open('wb') as f:f.truncate(268435456 if n<29 else 33554432)
  sums.append('0'*64+'  '+name)
 (shape/'device.txt').write_text('cid='+cid+'\nuserarea_bytes=7818182656\nchunk_bytes=268435456\n');sums.append('0'*64+'  device.txt')
 for n in ['boot0','boot1']:
  (w/n).write_bytes(bytes(512));(shape/(n+'.bin')).write_bytes(bytes(512));sums.append('0'*64+'  '+n+'.bin')
 (shape/'SHA256SUMS').write_text('\n'.join(sums)+'\n')
 text=(out/'ram-install.sh').read_text();a=text.index('check_backup_shape()');b=text.index('$BB mount -o remount,rw',a)
 helper=text[a:b].replace('[ -b /dev/mmcblk0$NAME ]','[ -f '+str(w)+'/$NAME ]')
 checkfile=w/'shape.sh';checkfile.write_text('BB=/usr/bin/busybox\nCID='+cid+'\nBYTES=7818182656\nBACK='+str(shape)+'\nfail() { exit 1; }\n'+helper+'\ncheck_backup_shape\n')
 assert subprocess.run(['sh',str(checkfile)]).returncode==0
 (shape/'SHA256SUMS').write_text('\n'.join(sums[1:])+'\n')
 assert subprocess.run(['sh',str(checkfile)]).returncode!=0
 (shape/'SHA256SUMS').write_text('\n'.join(sums)+'\n');(shape/'emmc.part29').write_bytes(b'short')
 assert subprocess.run(['sh',str(checkfile)]).returncode!=0
 passed('completed backup reuse rejects missing checksum entries or short chunks')
 # Generic misc extraction supports any source sector, including a split boundary.
 text=(out/'ram-install.sh').read_text();a=text.index('MISC_OFFSET=');b=text.index('. "$WORK/layout.env"',a);fragment=text[a:b]
 for current_start in [7643891,15196160,524000]:
  case=w/str(current_start);case.mkdir();back=case/'backup';back.mkdir();run=case/'run';run.mkdir();data=os.urandom(4186112);pos=current_start*512;left=len(data);used=0
  while left:
   index,offset=divmod(pos,268435456);take=min(left,268435456-offset)
   with (back/f'emmc.part{index:02d}').open('wb') as f:f.seek(offset);f.write(data[used:used+take])
   pos+=take;used+=take;left-=take
  script=case/'misc.sh';script.write_text('BB=/usr/bin/busybox\nBACK='+str(back)+'\nWORK='+str(run)+'\nCURRENT_MISC_START='+str(current_start)+'\nCURRENT_MISC_SECTORS=8176\nfail() { exit 1; }\n'+fragment)
  assert subprocess.run(['sh',str(script)]).returncode==0
  assert (run/'misc').read_bytes()==data
 passed('generic snapshot misc extraction at both source positions and across a 256MiB split boundary')
 # New auto runner dispatches both operations. Stub only effects; real control and decisions run.
 for name,operation,rc,auto,reboot,completed,mount_ok in [('install-success','install',0,1,1,False,True),('update-success','update',0,1,1,False,True),('install-failure','install',1,1,1,False,True),('manual','install',0,0,1,False,True),('no-reboot','update',0,1,0,False,True),('repeat-install','install',0,1,1,True,True),('status-failure','update',0,1,1,False,False)]:
  case=w/name;case.mkdir();sd=case/'sd';sd.mkdir();pkg=sd/'e70q10-update';pkg.mkdir();conf=plan(report,operation,'all')['metadata']['update.conf'].replace(b'autostart=1',f'autostart={auto}'.encode()).replace(b'reboot=1',f'reboot={reboot}'.encode());(pkg/'update.conf').write_bytes(conf)
  trace=case/'trace';ramlog=case/'ram.log';cid='112233445566778899aabbccddeeff00';cidfile=case/'cid';cidfile.write_text(cid+'\n')
  sectorsfile=case/'sectors';sectorsfile.write_text('15273600\n')
  model=case/'model';model.write_text('#!/bin/sh\nexit 0\n');model.chmod(0o755)
  status=sd/'e70q10-update-status';status.mkdir()
  if completed:(status/'completed').write_text(f'{cid}:{operation}-{report["manifest"]}-system,vendor,boot\n')
  bb=case/'bb';bb.write_text('#!/bin/sh\ncase "$1" in mount) exit '+('0' if mount_ok else '1')+';; sync) exit 0;; reboot) echo reboot >>'+str(trace)+';exit 0;; esac\nexec /usr/bin/busybox "$@"\n');bb.chmod(0o755)
  script=(out/'ram-auto.sh').read_text().replace('BB=/bin/busybox','BB='+str(bb)).replace('SD=/mnt/sd','SD='+str(sd)).replace('/sys/block/mmcblk0/device/cid',str(cidfile)).replace('/sys/block/mmcblk0/size',str(sectorsfile)).replace('/bin/device-layout',str(model)).replace('/run/device.env',str(case/'device.env')).replace('WORK=/run/selected-package','WORK='+str(case/'selected')).replace('/run/emmc-auto.log',str(ramlog))
  for command,action in [('/bin/initial-install','install'),('/bin/updater','update')]:
   fake=case/action;fake.write_text('#!/bin/sh\necho '+action+' >>'+str(trace)+'\nexit '+str(rc)+'\n');fake.chmod(0o755);script=script.replace(command,str(fake))
  runfile=case/'auto.sh';runfile.write_text(script)
  with ramlog.open('wb') as lf:result=subprocess.run(['sh',str(runfile),str(pkg)],stdout=lf,stderr=lf)
  actions=trace.read_text().splitlines() if trace.exists() else []
  assert (operation in actions)==(auto==1 and not completed and mount_ok),(name,actions)
  assert ('reboot' in actions)==(auto==1 and not completed and mount_ok and rc==0 and reboot==1),(name,actions)
  if auto and not completed and mount_ok:assert 'exit='+str(rc) in (status/'last.result').read_text()
 passed('auto install/update dispatch, failure/manual/no-reboot/status failure and one-shot install replay protection')
 # Windows destructive adapter contract. No PowerShell/physical disk calls.
 import devices
 d={'id':'3','identity':'card-id','serial':'sdserial','bytes':15931539456,'sector':512,'transport':'USB','system':False,'readonly':False,'name':'test card'}
 rejected_system=dict(d,system=True)
 with patch.object(devices,'os',types.SimpleNamespace(name='nt')),patch.object(devices,'inventory',return_value=[rejected_system]):rejected(lambda:devices.checked_disk('3'))
 with patch.object(devices,'os',types.SimpleNamespace(name='nt')),patch.object(devices,'inventory',return_value=[d]),patch.object(devices,'ps',return_value='true'):rejected(lambda:devices.checked_disk('3'))
 with patch.object(devices,'os',types.SimpleNamespace(name='nt')),patch.object(devices,'checked_disk',return_value=dict(d,identity='changed')):rejected(lambda:devices.format_disk('3',devices.fingerprint(d),'archive.tar'))
 passed('Windows system/pagefile disk and changed identity rejected without mutations')
 from pathlib import PureWindowsPath
 calls=[]
 def fake_ps(code):
  calls.append(code)
  return '0' if code.startswith('Get-Partition -DriveLetter') else 'F'
 fake_ctypes=types.SimpleNamespace(windll=types.SimpleNamespace(shell32=types.SimpleNamespace(IsUserAnAdmin=lambda:True)))
 with patch.object(devices,'os',types.SimpleNamespace(name='nt')),patch.object(devices,'Path',PureWindowsPath),patch.object(devices,'ctypes',fake_ctypes),patch.object(devices,'checked_disk',return_value=d),patch.object(devices,'ps',side_effect=fake_ps),patch.object(devices,'check_mount'):
  mount=devices.format_disk('3',devices.fingerprint(d),'C:\\release.tar')
  assert str(mount)=='F:\\'
 assert len(calls)==2 and 'Clear-Disk' in calls[-1] and 'Format-Volume -FileSystem FAT32' in calls[-1]
 assert calls[-1].index("throw 'protected or changed disk'")<calls[-1].index('Clear-Disk')
 assert 'UniqueId -ne' in calls[-1] and 'SerialNumber -ne' in calls[-1]
 calls=[]
 def source_on_sd(code):calls.append(code);return '3'
 with patch.object(devices,'os',types.SimpleNamespace(name='nt')),patch.object(devices,'Path',PureWindowsPath),patch.object(devices,'ctypes',fake_ctypes),patch.object(devices,'checked_disk',return_value=d),patch.object(devices,'ps',side_effect=source_on_sd):
  rejected(lambda:devices.format_disk('3',devices.fingerprint(d),'E:\\release.tar'))
 assert not any('Clear-Disk' in c for c in calls)
 passed('Windows format adapter command construction/recheck and archive-on-SD refusal tested with all effects mocked')
# Verify the output RAM image has a valid digest, pinned scripts, and executable formatter.
sys.path.insert(0,str(SRC.parent/'emmc-updater'));from boot_image import entries
image=(out/'ram-updater.img').read_bytes();page=struct.unpack_from('<I',image,36)[0];ks=struct.unpack_from('<I',image,8)[0];rs=struct.unpack_from('<I',image,16)[0];off=page+((ks+page-1)//page)*page;kernel=image[page:page+ks];rd=image[off:off+rs];h=hashlib.sha1()
for data in [kernel,rd,b'']:h.update(data);h.update(struct.pack('<I',len(data)))
assert h.digest()==image[576:596]
es=entries(rd)
for n in ['bin/auto-update','bin/initial-install','bin/device-layout','system/bin/make_ext4fs','system/bin/e2fsck']:assert es[n][0][1]&0o111
assert es['bin/auto-update'][1]==(out/'ram-auto.sh').read_bytes()
assert es['bin/initial-install'][1]==(out/'ram-install.sh').read_bytes()
assert es['bin/updater'][1]==(out/'updater.sh').read_bytes()
passed('RAM image SHA1, pinned original writer, auto/install scripts and ARM executable modes')
result={'passed':proofs,'physical_disk_or_device_writes':False,'arm_formatter_execution':arm_result,'windows_execution':'not tested on Windows; destructive adapter refusal mocked','backup_full_rehearsal':'separate test_backup.py','community_release_ready':False}
(logdir/'python-tool-validation.json').write_text(json.dumps(result,indent=2)+'\n')
print('PASS:',len(proofs),'offline checks; no physical disk/device writes')
