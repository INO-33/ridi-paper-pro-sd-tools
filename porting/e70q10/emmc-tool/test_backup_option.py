#!/usr/bin/env python3
"""Actual format5 parser/auto dispatcher: checkbox controls backup before writes."""
from pathlib import Path
import sys,tempfile,subprocess,hashlib,json,tarfile
from package import plan,fields
from folder_package import build_folder
SRC=Path(__file__).resolve().parent;ROOT=SRC.parents[2];LOG=ROOT/'.orchestrator/logs/emmc-gui-20261014'
with tempfile.TemporaryDirectory(prefix='backup-option-test-') as td:
 w=Path(td);empty=w/'empty';empty.mkdir();report=build_folder(empty,Path(sys.argv[1]),w/'backup','backup',())
 # Populate synthetic approved roles to exercise dispatcher only (storage mocked).
 report['available']=('system','vendor','boot');report['members']={};report['checksums']={};report['config'].update(operation='update',targets='system,vendor,boot',reboot='1')
 cases=[]
 with tarfile.open(report['path']) as t:auto=t.extractfile('e70q10-update/ram-auto.sh').read().decode()
 for name,op,enabled,backup_rc,kind in [('update-off','update',False,0,'unified'),('update-on','update',True,0,'unified'),('backup-fails','update',True,7,'unified'),('upgrade-off','install',False,0,'stock'),('upgrade-on','install',True,0,'stock'),('wrong-layout','install',False,0,'unified')]:
  # Real plan, metadata, schema5 parser; zero payloads are enough for dispatch mocks.
  report['members']={'SHA256SUMS':type('M',(),{'size':0})()};selection=plan(report,op,'all',backup_before=enabled);conf=fields(selection['metadata']['update.conf']);case=w/name;case.mkdir();sd=case/'sd';sd.mkdir();pkg=sd/'e70q10-update';pkg.mkdir();(pkg/'update.conf').write_bytes(selection['metadata']['update.conf']);(pkg/'manifest.tsv').touch();cid=case/'cid';cid.write_text('1'*32);cap=case/'size';cap.write_text('15269888');trace=case/'trace'
  bb=case/'bb';bb.write_text('#!/bin/sh\ncase "$1" in mount|sync|sleep) exit 0;; reboot) echo reboot >>'+str(trace)+';exit 0;; esac\nexec /usr/bin/busybox "$@"\n');bb.chmod(0o755)
  model=case/'model';model.write_text('#!/bin/sh\necho CURRENT_KIND='+kind+'\n');model.chmod(0o755)
  text=auto.replace('BB=/bin/busybox','BB='+str(bb)).replace('SD=/mnt/sd','SD='+str(sd)).replace('/sys/block/mmcblk0/device/cid',str(cid)).replace('/sys/block/mmcblk0/size',str(cap)).replace('/bin/device-layout',str(model)).replace('/run/device.env',str(case/'env')).replace('WORK=/run/selected-package','WORK='+str(case/'selected')).replace('/run/emmc-auto.log',str(case/'log')).replace('/run/preservation.result',str(case/'preserved'))
  for asset in ['/bin/backup-copy','/bin/stream-write','/system/bin/linker','/system/bin/make_ext4fs','/system/bin/e2fsck','/system/lib/libc.so','/etc/file_contexts']:
   f=case/asset.lstrip('/');f.parent.mkdir(parents=True,exist_ok=True);f.write_text('#!/bin/sh\nexit 0\n');f.chmod(0o755);text=text.replace(asset,str(f))
  for command,action,rc in [('/bin/backup-current','backup',backup_rc),('/bin/updater','write',0),('/bin/initial-install','install',0)]:
   f=case/action;f.write_text('#!/bin/sh\necho "'+action+' $*" >>'+str(trace)+'\nexit '+str(rc)+'\n');f.chmod(0o755);text=text.replace(command,str(f))
  runner=case/'run';runner.write_text(text)
  with (case/'log').open('wb') as f:r=subprocess.run(['sh',str(runner),str(pkg)],stdout=f,stderr=f)
  if (case/'selected/update.conf').exists():
   actual=(case/'selected/update.conf').read_text()
   assert actual == 'format=1\nmanifest='+conf['manifest']+'\ntargets='+conf['targets']+'\nautostart=0\nreboot=0\n', actual
  actions=trace.read_text().splitlines() if trace.exists() else []
  if name=='update-off':assert [a.split()[0] for a in actions]==['write','reboot']
  elif name=='update-on':assert [a.split()[0] for a in actions]==['backup','write','reboot']
  elif name=='backup-fails':assert [a.split()[0] for a in actions]==['backup'] and r.returncode!=0
  elif name=='upgrade-off':assert actions[0].startswith('install ') and actions[0].endswith(' none')
  elif name=='upgrade-on':assert actions[0].startswith('install ') and actions[0].endswith(' required')
  else:assert not actions and r.returncode!=0
  cases.append({'case':name,'actions':actions,'backup_config':conf['backup']})
 (LOG/'backup-option-validation.json').write_text(json.dumps({'cases':cases,'storage_writes':'mocked; dispatch uses actual format5 RAM script'},indent=2))
print('PASS backup option: update off/on order, failed backup stops writes/reboot, upgrade off/on propagation, wrong-layout refusal')
