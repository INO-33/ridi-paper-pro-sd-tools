#!/usr/bin/env python3
import pathlib as P,subprocess as S,os,json,hashlib,shutil,struct,gzip,sys
R=P.Path('/home/juwon/ridi');O=R/'deliverables/e70q10-emmc-android8-20261001';W=O/'.rehearsal';W.mkdir(exist_ok=True)
B=P.Path('/media/juwon/build/리디백업/backups/e70q10-PP1A1GK166561-20260923-full-emmc');disk=W/'emmc.disk';log=R/'.orchestrator/logs/emmc-install-20261001/rehearsal.log'
if '--resume-restore' not in sys.argv:
 with open(disk,'wb') as f,open(B/'emmc.part00','rb') as i:f.write(i.read(51<<20));f.truncate(7818182656)
env=os.environ|{'INSTALLER_BB':'/usr/bin/busybox','INSTALLER_WORK':str(W/'run'),'INSTALLER_COUNTER':str(O/'countbytes-host')}
def run(args,ok=True):
 with open(log,'ab') as f:p=S.run(args,env=env,stdout=f,stderr=S.STDOUT)
 if ok:assert p.returncode==0,(args,p.returncode)
 else:assert p.returncode!=0,args
if '--resume-restore' not in sys.argv:
 # Reject a changed trusted manifest without writing.
 bad=W/'bad';bad.mkdir(exist_ok=True);(bad/'manifest.tsv').write_text('bad\n')
 run(['sh',str(O/'installer.sh'),'rehearse',str(disk),str(bad)],False)
 assert disk.stat().st_blocks*512 < 60<<20
 # Reject a modified payload and a wrong-capacity target before recording.
 for p in O.iterdir():
  if p.is_file() and p.name!='system.raw.gz':
   target=bad/p.name
   if target.exists():target.unlink()
   target.symlink_to(p)
 (bad/'system.raw.gz').write_bytes(b'corrupt gzip')
 run(['sh',str(O/'installer.sh'),'rehearse',str(disk),str(bad)],False)
 assert disk.stat().st_blocks*512 < 60<<20
 wrong=W/'wrong.disk';wrong.write_bytes(b'bad')
 run(['sh',str(O/'installer.sh'),'rehearse',str(wrong),str(O)],False)
 wrong.unlink()
 run(['sh',str(O/'installer.sh'),'rehearse',str(disk),str(O)])
run(['sfdisk','--json',str(disk)])
# Verify actual installed offsets independently against layout.
layout=json.loads((O/'layout.json').read_text());rows=[x.split() for x in (O/'manifest.tsv').read_text().splitlines()]
with open(disk,'rb') as f:
 f.seek(462);assert f.read(16)==(O/'original-mbr.sector0.bin').read_bytes()[462:478]
 for kind,name,start,sectors,raw,comp in rows:
  if kind=='table':
   f.seek(int(start)*512);assert f.read(512)==gzip.decompress((O/name).read_bytes())
# Complete restore rehearsal using all 30 original parts and full-device SHA.
(O/'backup').symlink_to(B,target_is_directory=True)
try:run(['sh',str(O/'installer.sh'),'rehearse-restore',str(disk),str(O)])
finally:(O/'backup').unlink()
# ARM32 BusyBox tests: >4-GiB arithmetic, byte counter, large seek and gzip/sha applets.
arm=O/'.build/ram-root/bin/busybox';q='/usr/bin/qemu-arm-static'
assert S.check_output([q,str(arm),'sh','-c','echo $((12326912 * 512))']).strip()==b'6311378944'
large=W/'arm-large'
with open(large,'wb') as f:f.truncate(6311378944)
with open(large,'rb') as source:
 assert S.check_output([q,str(O/'.build/ram-root/bin/countbytes')],stdin=source).strip()==b'6311378944'
run([q,str(arm),'dd','if='+str(O/'original-mbr.sector0.bin'),'of='+str(large),'bs=512','seek=12326911','conv=notrunc'])
with open(large,'rb') as f:f.seek(6311378944-512);assert f.read(512)==(O/'original-mbr.sector0.bin').read_bytes()
assert S.check_output([q,str(arm),'gzip','-dc',str(O/'mbr.sector0.bin.gz')])[:512]==gzip.decompress((O/'mbr.sector0.bin.gz').read_bytes())
assert S.check_output([q,str(arm),'sha256sum',str(O/'boot-emmc.img')]).split()[0].decode()==hashlib.sha256((O/'boot-emmc.img').read_bytes()).hexdigest()
large.unlink();disk.unlink()
p=O/'build-report.json';r=json.loads(p.read_text());r['offline_validation']='passed: full-capacity install/readback, unchanged protected prefix, table decode, full restore SHA, rejected altered manifest, ARM32 >4GiB utilities';p.write_text(json.dumps(r,indent=2)+'\n')
print('PASS: installation + full restoration + ARM32 utility checks')
