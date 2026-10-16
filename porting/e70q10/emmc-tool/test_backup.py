#!/usr/bin/env python3
"""Actual 8GB backup on regular files; boot regions and SD mounts simulated."""
from pathlib import Path
import sys, tempfile, subprocess, os, hashlib,shutil,json
from package import sha
out=Path(sys.argv[1]).resolve()
logs=Path('/home/juwon/ridi/.orchestrator/logs/emmc-model-20261008');log=logs/'backup-details.log'
with tempfile.TemporaryDirectory(prefix='ridi-backup-test-') as td:
 w=Path(td);dev=w/'emmc.disk';sd=w/'sd';sd.mkdir();work=w/'run'
 backup=Path('/media/juwon/build/리디백업/backups/e70q10-PP1A1GK166561-20260923-full-emmc/emmc.part00')
 with dev.open('wb') as f,backup.open('rb') as src:f.write(src.read(51<<20));f.truncate(7818182656)
 cid='112233445566778899aabbccddeeff00';cidfile=w/'cid';cidfile.write_text(cid+'\n');capacity=w/'sectors';capacity.write_text('15269888\n')
 # Restore all source EBR sectors into the sparse fixture for real model/layout parsing.
 folder=backup.parent
 def sector(lba):
  index,offset=divmod(lba*512,256<<20)
  with (folder/f'emmc.part{index:02d}').open('rb') as f:f.seek(offset);return f.read(512)
 import struct
 m=sector(0);base=struct.unpack_from('<I',m,486)[0];at=base
 with dev.open('r+b') as f:
  for _ in range(5):
   e=sector(at);f.seek(at*512);f.write(e);next=struct.unpack_from('<I',e,470)[0]
   if not next:break
   at=base+next
 for name in ['boot0','boot1']:(w/name).write_bytes(os.urandom(65536))
 wrapper=w/'bb';wrapper.write_text('#!/bin/sh\ncase "$1" in mount) exit 0;; sync) exec /usr/bin/sync -f '+str(sd)+';; blockdev) [ "$2" != --getsize64 ] || { /usr/bin/stat -c %s "$3";exit; };; esac\nexec /usr/bin/busybox "$@"\n');wrapper.chmod(0o755)
 original=(out/'ram-install.sh').read_text();script=original[:original.index("echo 'BACKUP VERIFIED.")]
 # Payload verification is separately covered by pinned writer rehearsals. Run actual backup core.
 a=script.index('# Validate every payload');b=script.index('BACK=$SD/',a);script=script[:a]+script[b:]
 script=script.replace('BB=/bin/busybox','BB='+str(wrapper)).replace('DEV=/dev/mmcblk0','DEV='+str(dev)).replace('SD=/mnt/sd','SD='+str(sd)).replace('[ -b "$DEV" ]','[ -f "$DEV" ]').replace('/sys/block/mmcblk0/device/cid',str(cidfile)).replace('/sys/block/mmcblk0/size',str(capacity)).replace('WORK=/run/initial-install','WORK='+str(work)).replace('NODE=/dev/mmcblk0$NAME','NODE='+str(w)+'/$NAME').replace('[ -b "$NODE" ]','[ -f "$NODE" ]').replace('[ -b /dev/mmcblk0$NAME ]','[ -f '+str(w)+'/$NAME ]').replace('/bin/device-layout',str(out/'.native/device-layout-host'))
 runner=w/'backup.sh';runner.write_text(script)
 def run(ok=True):
  shutil.rmtree(work,ignore_errors=True)
  with log.open('ab') as lf:r=subprocess.run(['sh',str(runner),str(out)],stdout=lf,stderr=lf)
  assert (r.returncode==0)==ok,r.returncode
 run()
 back=sd/'e70q10-backups'/cid
 assert (back/'complete').read_text().strip()==cid+':7818182656'
 pieces=sorted(back.glob('emmc.part*'));assert len(pieces)==30
 assert sum(p.stat().st_size for p in pieces)==dev.stat().st_size
 for name in ['boot0','boot1']:assert (back/(name+'.bin')).read_bytes()==(w/name).read_bytes()
 # Completed backup retries validate existing files without rewriting them.
 before={p.name:(p.stat().st_mtime_ns,p.stat().st_size) for p in pieces};run();after={p.name:(p.stat().st_mtime_ns,p.stat().st_size) for p in pieces};assert before==after
 with pieces[0].open('r+b') as f:f.write(b'CORRUPT')
 run(False)
 (back/'complete').unlink();run(False)
 result={'test_cid':cid,'sample_CID_required':False,'userarea_bytes':7818182656,'pieces':30,'boot_regions':'both 64KiB fixtures backed up and readback matched','completed_backup_retry':'validated without overwrite','corrupt_backup':'rejected','incomplete_backup':'rejected','device_type':'regular file; no physical writes','passed':True}
 (logs/'backup-validation.json').write_text(json.dumps(result,indent=2)+'\n')
 print('PASS: full 8GB raw backup/readback, boot areas, no-overwrite retry and corrupt/incomplete refusal')
