#!/usr/bin/env python3
"""End-to-end backup + real image writer on a regular eMMC file; no physical device."""
from pathlib import Path
import tempfile,subprocess,sys,os,struct,json,hashlib,shutil
SRC=Path(__file__).resolve().parent;OUT=Path(sys.argv[1]).resolve();LOG=SRC.parents[2]/'.orchestrator/logs/emmc-windows-20261012';LOG.mkdir(parents=True,exist_ok=True)
from package import sha
native=OUT/'.native/device-layout-host';base=Path('/media/juwon/build/리디백업/backups/e70q10-PP1A1GK166561-20260923-full-emmc')
def source(lba):
 i,o=divmod(lba*512,256<<20)
 with (base/f'emmc.part{i:02d}').open('rb') as f:f.seek(o);return f.read(512)
with tempfile.TemporaryDirectory(prefix='preserve-emmc-') as td:
 w=Path(td);dev=w/'emmc.disk';sd=w/'sd';sd.mkdir();plan=w/'plan';plan.mkdir()
 with dev.open('wb') as f,(base/'emmc.part00').open('rb') as src:f.write(src.read(51<<20));f.truncate(7818182656)
 m=source(0);ext=struct.unpack_from('<I',m,486)[0];at=ext
 with dev.open('r+b') as f:
  for _ in range(5):
   e=source(at);f.seek(at*512);f.write(e);n=struct.unpack_from('<I',e,470)[0]
   if not n:break
   at=ext+n
 result=subprocess.check_output([str(native),'plan',str(dev),'15269888',str(plan)],text=True)
 with dev.open('r+b') as f:
  for file in plan.glob('ebr.sector*.bin'):
   f.seek(int(file.name[10:-4])*512);f.write(file.read_bytes())
  f.seek(0);f.write((plan/'mbr.sector0.bin').read_bytes())
  for sector in [2404352,8000000,14730000,2271232,15259648]:f.seek(sector*512);f.write(os.urandom(4096))
 cid='112233445566778899aabbccddeeff00';cidfile=w/'cid';cidfile.write_text(cid+'\n');size=w/'sectors';size.write_text('15269888\n');job='a'*32
 old=sd/'e70q10-backups'/cid/('b'*32);old.mkdir(parents=True);(old/'complete').write_text('prior snapshot must remain')
 pkg=w/'pkg';pkg.mkdir()
 for name in ['manifest.tsv','boot.raw.gz','system.raw.gz','vendor.raw.gz']:(pkg/name).symlink_to(OUT/name)
 mh=sha(OUT/'manifest.tsv');(pkg/'update.conf').write_text(f'format=1\nmanifest={mh}\ntargets=system,vendor,boot\nautostart=0\nreboot=0\n')
 bb=w/'bb';bb.write_text('#!/bin/sh\ncase "$1" in mount) exit 0;; sync) exec /usr/bin/sync -f '+str(sd)+';; esac\nexec /usr/bin/busybox "$@"\n');bb.chmod(0o755)
 common=(OUT/'ram-backup.sh').read_text().replace('BB=/bin/busybox','BB='+str(bb)).replace('DEV=/dev/mmcblk0','DEV='+str(dev)).replace('SD=/mnt/sd','SD='+str(sd)).replace('/sys/block/mmcblk0/device/cid',str(cidfile)).replace('/sys/block/mmcblk0/size',str(size)).replace('[ -b "$DEV" ]','[ -f "$DEV" ]').replace('/bin/device-layout',str(native)).replace('/bin/backup-copy',str(OUT/'.native/backup-copy-host')).replace('WORK=/run/backup-operation','WORK='+str(w/'backup-run')).replace('/bin/countbytes',str(SRC.parent/'emmc-updater/assets/countbytes-host'))
 backup=w/'backup.sh';backup.write_text(common);backup.chmod(0o755)
 # Map the simulated kernel cache node to a real 64MiB ARM-formatted file,
 # then copy it into the actual cache range of the regular eMMC fixture.
 cache=w/'cache.node'
 with dev.open('rb') as f: f.seek(2271232*512);cache.write_bytes(f.read(67108864))
 cache_start=w/'cache.start';cache_start.write_text('2271232')
 formatter=w/'format-cache.py'
 formatter.write_text("#!/usr/bin/python3\nimport subprocess,os,sys\nfrom pathlib import Path\nroot=Path("+repr(str(OUT/'.ram-tools'))+")\nnode=Path("+repr(str(cache))+")\nprefix=['unshare','--user','--map-root-user','--pid','--fork','/usr/bin/qemu-arm-static','-L',str(root)]\nsubprocess.run(prefix+[str(root/'system/bin/make_ext4fs'),'-l','67108864','-a','cache','-S',str(root/'etc/file_contexts'),str(node)],check=True,env=os.environ|{'LD_LIBRARY_PATH':'/system/lib'})\nwith open("+repr(str(dev))+",'r+b') as f:f.seek(2271232*512);f.write(node.read_bytes());f.flush();os.fsync(f.fileno())\n")
 formatter.chmod(0o755)
 checker=w/'check-cache.py'
 checker.write_text("#!/usr/bin/python3\nimport subprocess,os\nfrom pathlib import Path\nroot=Path("+repr(str(OUT/'.ram-tools'))+")\nsubprocess.run(['unshare','--user','--map-root-user','--pid','--fork','/usr/bin/qemu-arm-static','-L',str(root),str(root/'system/bin/e2fsck'),'-fn',"+repr(str(cache))+"],check=True,env=os.environ|{'LD_LIBRARY_PATH':'/system/lib'})\n")
 checker.chmod(0o755)
 # The genuine kernel ioctl is the only emulated node query.
 bb.write_text(bb.read_text().replace('case "$1" in', 'case "$1" in blockdev) [ "$2" != --getsize64 ] || { /usr/bin/stat -c %s "$3";exit; };;',1))
 writer=w/'writer';writer.write_text('#!/bin/sh\nexec sh '+str(OUT/'updater.sh')+' rehearse '+str(dev)+' "$2"\n');writer.chmod(0o755)
 script=(OUT/'ram-install-test.sh').read_text().replace('BB=/bin/busybox','BB='+str(bb)).replace('DEV=/dev/mmcblk0','DEV='+str(dev)).replace('/sys/block/mmcblk0/size',str(size)).replace('/bin/device-layout',str(native)).replace('/bin/backup-copy',str(OUT/'.native/backup-copy-host')).replace('/bin/backup-current',str(backup)).replace('/bin/updater',str(writer)).replace('/run/test-layout.env',str(w/'test-layout.env')).replace('WORK=/run/install-test','WORK='+str(w/'test-run')).replace('/run/preservation.result',str(w/'preservation.result'))
 script=script.replace('/dev/mmcblk0p6',str(cache)).replace('[ -b '+str(cache)+' ]','[ -f '+str(cache)+' ]').replace('/sys/class/block/mmcblk0p6/start',str(cache_start)).replace('/system/bin/make_ext4fs',str(formatter)).replace('/system/bin/e2fsck',str(checker))
 runner=w/'test.sh';runner.write_text(script)
 env=os.environ|{'UPDATER_BB':'/usr/bin/busybox','UPDATER_LAYOUT':str(native),'UPDATER_STREAM':str(OUT/'.native/stream-write-host'),'UPDATER_WORK':str(w/'writer-run')}
 with (LOG/'preserving-details.log').open('ab') as lf:r=subprocess.run(['sh',str(runner),str(pkg),job],stdout=lf,stderr=lf,env=env)
 assert r.returncode==0,r.returncode
 current=sd/'e70q10-backups'/cid/job
 assert (current/'complete').read_text().strip()==cid+':7818182656'
 assert (old/'complete').read_text()=='prior snapshot must remain'
 assert sum(p.stat().st_size for p in current.glob('emmc.part*'))==7818182656
 assert 'cache=created' in (w/'preservation.result').read_text()
 assert 'userdata=preserved' in (w/'preservation.result').read_text()
 assert source(0)[:446]==dev.open('rb').read(446)
 result={'test_mode':'install-test','backup':'fresh job-scoped 8GB snapshot passed','old_snapshot':'not reused or changed','writes':'actual pinned system/vendor/boot writer on regular file','userdata_misc':'full raw before/after hashes identical','cache':'actual ARM make_ext4fs/e2fsck created 64MiB and copied to fixture cache range; new cache unchanged through OS writes','partitioning':'no repartition; cache-only formatting','physical_device_or_SD_writes':False,'actual_Android4_device':'not tested'}
 (LOG/'preserving-validation.json').write_text(json.dumps(result,indent=2)+'\n')
 print('PASS: fresh 8GB backup + real all-image update; userdata/misc preserved; ARM cache creation/fsck passed')
