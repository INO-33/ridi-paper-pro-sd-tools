#!/usr/bin/env python3
from pathlib import Path
import sys,tempfile,subprocess,json
from package import validate,plan,fields
OUT=Path(sys.argv[1]).resolve();report=validate(OUT.with_suffix('.tar'));proof=[]
with tempfile.TemporaryDirectory() as td:
 root=Path(td)
 for name,op,kind,rc,completed,invalid in [('factory-stock','install','stock',0,False,False),('factory-on-android8','install','unified',0,False,False),('preserve-android8','install-test','unified',0,False,False),('preserve-on-stock','install-test','stock',0,False,False),('test-backup-failure','install-test','unified',1,False,False),('update','update','unified',0,False,False),('repeat-complete','install-test','unified',0,True,False),('invalid-data-policy','install-test','unified',0,False,True),('missing-ram-asset','install-test','unified',0,False,False)]:
  w=root/name;w.mkdir();sd=w/'sd';sd.mkdir();pkg=sd/'e70q10-update';pkg.mkdir();config=plan(report,op,'all')['metadata']['update.conf'];values=fields(config);job=values['job']
  if invalid:config=config.replace(b'userdata=preserve',b'userdata=create')
  (pkg/'update.conf').write_bytes(config);cid='112233445566778899aabbccddeeff00';cidfile=w/'cid';cidfile.write_text(cid);sector=w/'sectors';sector.write_text('15269888')
  trace=w/'trace';model=w/'model';model.write_text('#!/bin/sh\necho CURRENT_KIND='+kind+'\n');model.chmod(0o755)
  bb=w/'bb';bb.write_text('#!/bin/sh\ncase "$1" in mount|sync) exit 0;; reboot) echo reboot >>'+str(trace)+';exit 0;; esac\nexec /usr/bin/busybox "$@"\n');bb.chmod(0o755)
  status=sd/'e70q10-update-status';status.mkdir()
  if completed:(status/'completed').write_text(f'{cid}:{job}-{op}-{report["manifest"]}-system,vendor,boot'+('-backup-'+values['backup'] if values['format']=='5' else '')+'\n')
  text=(OUT/'ram-auto.sh').read_text().replace('BB=/bin/busybox','BB='+str(bb)).replace('SD=/mnt/sd','SD='+str(sd)).replace('/sys/block/mmcblk0/device/cid',str(cidfile)).replace('/sys/block/mmcblk0/size',str(sector)).replace('/bin/device-layout',str(model)).replace('/run/device.env',str(w/'device.env')).replace('WORK=/run/selected-package','WORK='+str(w/'selected')).replace('/run/emmc-auto.log',str(w/'ram.log')).replace('/run/preservation.result',str(w/'preservation.result'))
  for command,action in [('/bin/initial-install','factory-format'),('/bin/install-test','preserving-test'),('/bin/updater','update')]:
   fake=w/action;fake.write_text('#!/bin/sh\necho '+action+' >>'+str(trace)+'\nexit '+str(rc)+'\n');fake.chmod(0o755);text=text.replace(command,str(fake))
  # Model the RAM asset preflight independently of storage command mocks.
  for asset in ['/bin/backup-copy','/bin/stream-write','/system/bin/linker','/system/bin/make_ext4fs','/system/bin/e2fsck','/system/lib/libc.so','/etc/file_contexts']:
   target=w/asset.lstrip('/');target.parent.mkdir(parents=True,exist_ok=True)
   if name!='missing-ram-asset' or asset!='/system/lib/libc.so':
    target.write_text('#!/bin/sh\nexit 0\n');target.chmod(0o755)
   text=text.replace(asset,str(target))
  script=w/'run.sh';script.write_text(text)
  with (w/'ram.log').open('wb') as f:r=subprocess.run(['sh',str(script),str(pkg)],stdout=f,stderr=f)
  actions=trace.read_text().splitlines() if trace.exists() else []
  allow=name!='missing-ram-asset' and not invalid and not completed and ((op=='install' and kind=='stock') or (op!='install' and kind=='unified'))
  assert bool([x for x in actions if x!='reboot'])==allow,(name,actions)
  assert ('reboot' in actions)==(allow and rc==0),(name,actions)
  if op=='install-test':assert 'factory-format' not in actions
  proof.append({'case':name,'actions':actions,'passed':True})
 logs=Path(sys.argv[2]) if len(sys.argv)>2 else Path('/home/juwon/ridi/.orchestrator/logs/emmc-windows-20261012');logs.mkdir(parents=True,exist_ok=True);(logs/'runtime-policy-validation.json').write_text(json.dumps(proof,indent=2)+'\n')
 print('PASS: stock-only factory install, Android8-only preserving test, failures and job replay safety')
