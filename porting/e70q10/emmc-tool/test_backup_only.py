#!/usr/bin/env python3
"""Backup-only selection/dispatch guards, and real native backup with NO images.
Temporary regular files only; all fixtures removed after tests."""
from pathlib import Path
import tempfile,zipfile,tarfile,io,sys,subprocess,hashlib,json,os,shutil
SRC=Path(__file__).resolve().parent;ROOT=SRC.parents[2];LOG=ROOT/'.orchestrator/logs/emmc-backup-only-20261013'
from package import validate,plan,fields
proof=[]
with tempfile.TemporaryDirectory(prefix='backup-only-tests-') as d:
 w=Path(d);out=w/'package';out.mkdir()
 with zipfile.ZipFile(sys.argv[1]) as z:
  n=next(n for n in z.namelist() if n.endswith('.tar'))
  for name in (n,n+'.sha256'):(w/name).write_bytes(z.read(name))
 with tarfile.open(w/n) as t:
  for name in ('ram-auto.sh','ram-backup.sh','manifest.tsv'):(out/name).write_bytes(t.extractfile('e70q10-update/'+name).read())
 report=validate(w/n);sel=plan(report,'backup');conf=fields(sel['metadata']['update.conf'])
 assert conf['targets']=='none' and conf['reboot']=='0' and conf['userdata']==conf['partitioning']==conf['cache']=='preserve'
 assert not {'system.raw.gz','vendor.raw.gz','boot.raw.gz','boot-emmc.img'}&sel['names']
 assert sel['required_bytes']>7818182656
 try:plan(report,'backup','all');raise AssertionError('backup selection accepted image targets')
 except ValueError:pass
 for name,kind,patch,rc,completed in [('stock','stock',{},0,False),('unified','unified',{},0,False),('failed','unified',{},1,False),('completed','stock',{},0,True),('reboot','stock',{'reboot':'1'},0,False),('cache','stock',{'cache':'create'},0,False),('userdata','stock',{'userdata':'create'},0,False),('targets','stock',{'targets':'boot'},0,False),('partitioning','stock',{'partitioning':'create'},0,False)]:
  case=w/name;case.mkdir();sd=case/'sd';sd.mkdir();pkg=sd/'e70q10-update';pkg.mkdir();cf=dict(conf);cf.update(patch);(pkg/'update.conf').write_text(''.join(k+'='+v+'\n' for k,v in cf.items()));(pkg/'manifest.tsv').write_bytes((out/'manifest.tsv').read_bytes())
  cid='1'*32;cidf=case/'cid';cidf.write_text(cid);cap=case/'size';cap.write_text('15269888');trace=case/'trace';tool=case/'helper';tool.write_text('unused asset');model=case/'model';model.write_text('#!/bin/sh\necho CURRENT_KIND='+kind+'\n');model.chmod(0o755)
  bb=case/'bb';bb.write_text('#!/bin/sh\ncase "$1" in mount|sync|sleep) exit 0;; reboot) echo reboot >>'+str(trace)+';exit 0;; esac\nexec /usr/bin/busybox "$@"\n');bb.chmod(0o755)
  status=sd/'e70q10-update-status';status.mkdir()
  if completed:(status/'completed').write_text(f'{cid}:{cf["job"]}-backup-{cf["manifest"]}-none\n')
  script=(out/'ram-auto.sh').read_text().replace('BB=/bin/busybox','BB='+str(bb)).replace('SD=/mnt/sd','SD='+str(sd)).replace('/sys/block/mmcblk0/device/cid',str(cidf)).replace('/sys/block/mmcblk0/size',str(cap)).replace('/bin/device-layout',str(model)).replace('/bin/backup-copy',str(tool)).replace('/run/device.env',str(case/'device.env')).replace('WORK=/run/selected-package','WORK='+str(case/'selected')).replace('/run/emmc-auto.log',str(case/'log')).replace('/run/preservation.result',str(case/'preservation'))
  for cmd,action in [('/bin/backup-current','backup'),('/bin/initial-install','INSTALL'),('/bin/install-test','TEST'),('/bin/updater','WRITE')]:
   f=case/action;f.write_text('#!/bin/sh\nprintf "%s\\n" "'+action+' $*" >>'+str(trace)+'\nexit '+str(rc)+'\n');f.chmod(0o755);script=script.replace(cmd,str(f))
  runner=case/'run';runner.write_text(script)
  with (case/'log').open('wb') as f:r=subprocess.run(['sh',str(runner),str(pkg)],stdout=f,stderr=f)
  actions=trace.read_text().splitlines() if trace.exists() else []
  if name in ('stock','unified','failed'):assert len(actions)==1 and actions[0].startswith('backup ') and actions[0].endswith(' backup-only')
  else:assert not actions,(name,actions)
  assert not any('reboot' in x or 'INSTALL' in x or 'TEST' in x or 'WRITE' in x for x in actions)
  if name in ('stock','unified'):assert r.returncode==0 and 'exit=0' in (status/'last.result').read_text()
  if name in ('failed','reboot','cache','userdata','targets','partitioning'):assert r.returncode!=0
  proof.append(name+' dispatch policy passed')
 # Native backup workflow runs without compressed payloads or formatter tools.
 native=w/'native';subprocess.run(['gcc','-DHOST','-O2',str(SRC/'backup_copy.c'),'-o',str(native)],check=True)
 case=w/'real';case.mkdir();sd=case/'sd';sd.mkdir();pkg=case/'pkg';pkg.mkdir();(pkg/'manifest.tsv').write_bytes((out/'manifest.tsv').read_bytes());size=(64<<20)+65536;dev=case/'device'
 with dev.open('wb') as f:f.truncate(size);f.seek(51<<20);f.write(os.urandom(4096))
 before=hashlib.file_digest(dev.open('rb'),'sha256').hexdigest();cid='2'*32;cidf=case/'cid';cidf.write_text(cid);cap=case/'size';cap.write_text(str(size//512))
 model=case/'model';model.write_text('#!/bin/sh\nprintf "BYTES='+str(size)+'\\nSECTORS='+str(size//512)+'\\nCURRENT_KIND=stock\\n"\n');model.chmod(0o755)
 bb=case/'bb';bb.write_text('#!/bin/sh\ncase "$1" in mount|sync) exit 0;; esac\nexec /usr/bin/busybox "$@"\n');bb.chmod(0o755)
 script=(out/'ram-backup.sh').read_text().replace('BB=/bin/busybox','BB='+str(bb)).replace('DEV=/dev/mmcblk0','DEV='+str(dev)).replace('SD=/mnt/sd','SD='+str(sd)).replace('/sys/block/mmcblk0/device/cid',str(cidf)).replace('/sys/block/mmcblk0/size',str(cap)).replace('[ -b "$DEV" ]','[ -f "$DEV" ]').replace('/bin/device-layout',str(model)).replace('/bin/backup-copy',str(native)).replace('WORK=/run/backup-operation','WORK='+str(case/'work'))
 runner=case/'run';runner.write_text(script);job='3'*32
 with (LOG/'real-backup.log').open('wb') as f:r=subprocess.run(['sh',str(runner),str(pkg),job,'backup-only'],stdout=f,stderr=f)
 assert r.returncode==0,(LOG/'real-backup.log').read_text()
 back=sd/'e70q10-backups'/cid/job;assert (back/'complete').read_text().strip()==cid+':'+str(size)
 assert hashlib.file_digest((back/'emmc.part00').open('rb'),'sha256').hexdigest()==before==hashlib.file_digest(dev.open('rb'),'sha256').hexdigest()
 assert not list(pkg.glob('*.gz'));proof.append('real fused backup and independent readback without OS images; source bytes unchanged')
 (LOG/'validation.json').write_text(json.dumps({'cases':proof,'backup_config':conf,'SD_OS_images':False,'physical_writes':False},indent=2))
print('PASS backup-only: stock/unified, no write/format/reboot dispatch, invalid policy refusal, replay and failure guards, real native image-free backup')
