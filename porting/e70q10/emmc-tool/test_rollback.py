#!/usr/bin/env python3
"""Real restore shell + native bounded I/O against disposable regular files only."""
from pathlib import Path
import hashlib,json,os,shutil,subprocess,sys,tempfile,types,struct
from rollback import snapshot,prepare,CHUNK,PROTECTED_END
from gui_backend import Request,Cancelled
from portable_boot import unpack,entries
SRC=Path(__file__).resolve().parent
LOG=SRC.parents[2]/'.orchestrator/logs/emmc-rollback-20261016';LOG.mkdir(parents=True,exist_ok=True)
proof={'physical_writes':False,'cases':[]}
with tempfile.TemporaryDirectory(prefix='ridi-rollback-test-') as td:
 w=Path(td);sd=w/'sd';cid='1'*32;backupjob='2'*32;back=sd/'e70q10-backups'/cid/backupjob;back.mkdir(parents=True)
 size=CHUNK+2*1048576
 for i,n in enumerate((CHUNK,size-CHUNK)):
  p=back/f'emmc.part{i:02d}'
  with p.open('wb') as f:
   f.truncate(n);f.seek(0);f.write(b'SNAPSHOT-MBR' if i==0 else b'TAIL-SNAPSHOT');f.seek(n-1024);f.write(b'last snapshot bytes')
 for n in ('boot0.bin','boot1.bin'):(back/n).write_bytes(b'firmware'+bytes(1048576-8))
 (back/'device.txt').write_text(f'cid={cid}\nuserarea_bytes={size}\nchunk_bytes={CHUNK}\n')
 def checks():
  (back/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in sorted(back.iterdir()) if p.name not in ('SHA256SUMS','complete')))
 checks();(back/'complete').write_text(f'{cid}:{size}\n')
 class Adapter:
  def checked_disk(self,d):return {'id':'fixture','name':'disposable file SD','bytes':16_000_000_000,'row':{'children':[{'mountpoints':[str(sd)]}]}}
  def fingerprint(self,d):return 'fixture'
  def check_mount(self,p):assert p==sd
  def flush_volume(self,p):pass
 adapter=Adapter();req=Request(back,Path(sys.argv[1]),'fixture','restore',(),False)
 cancelled=False
 try:prepare(req,w/'cache',lambda s:False,lambda *x:None,adapter)
 except Cancelled:cancelled=True
 assert cancelled and not (sd/'e70q10-update').exists();proof['cases'].append('cancel leaves SD unchanged')
 state=prepare(req,w/'cache',lambda s:True,lambda *x:None,adapter)
 ram=Path(state['ram']).read_bytes();page=struct.unpack_from('<I',ram,36)[0];ks=struct.unpack_from('<I',ram,8)[0];rs=struct.unpack_from('<I',ram,16)[0];offset=page+((ks+page-1)//page)*page;rd=ram[offset:offset+rs];es=entries(rd);base=es['bin/auto-update'][1].decode();assert '@CID@' not in base
 meta=json.loads(es['etc/runtime-sha256.json'][1]);assert meta['bin/auto-update']==hashlib.sha256(base.encode()).hexdigest()
 assert b'operation=restore' in (sd/'e70q10-update/update.conf').read_bytes()
 proof['cases'].append('PC validated snapshot, paired RAM/config, runtime checksum')
 for source in ('backup_copy.c','stream_write.c'):
  subprocess.run(['gcc','-DHOST','-O2',str(SRC/source),'-o',str(w/source.removesuffix('.c'))],check=True,capture_output=True)
 before_backup={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in back.iterdir()}
 for case in ('success','wrong-cid','wrong-capacity','corrupt-backup','firmware-differs','boot-differs','write-failure','readback-failure','config-mismatch'):
  c=w/case;c.mkdir();dev=c/'emmc';trace=c/'trace';cidfile=c/'cid';cap=c/'capacity';cidfile.write_text(cid if case!='wrong-cid' else '3'*32);cap.write_text(str(size//512 if case!='wrong-capacity' else size//512+128))
  with dev.open('wb') as f, (back/'emmc.part00').open('rb') as src:
   f.truncate(size);f.write(src.read(PROTECTED_END));f.seek(0);f.write(b'CURRENT-MBR');f.seek(PROTECTED_END);f.write(b'CURRENT-USERDATA');f.seek(size-1024);f.write(b'CURRENT-TAIL')
  if case=='firmware-differs':
   with dev.open('r+b') as f:f.seek(4096);f.write(b'bad')
  boots={}
  for n in ('boot0','boot1'):
   p=c/n;shutil.copyfile(back/(n+'.bin'),p);boots[n]=p
  if case=='boot-differs':
   with boots['boot0'].open('r+b') as f:f.write(b'bad')
  mounts=c/'mounts';mounts.write_text('/dev/sd /mnt/sd vfat ro 0 0\n');swaps=c/'swaps';swaps.touch()
  bb=c/'bb';bb.write_text('#!/bin/sh\ncase "$1" in mount|sync|sleep) exit 0;; reboot) echo reboot >>"'+str(trace)+'";exit 0;; blockdev) stat -c %s "$3";exit $?;; esac\nexec /usr/bin/busybox "$@"\n');bb.chmod(0o755)
  writer=c/'writer';writer.write_text('#!/bin/sh\necho "$2 $3" >>"'+str(trace)+'"\n'+('if [ "$2" != 104448 ];then exit 7;fi\n' if case=='write-failure' else '')+'"'+str(w/'stream_write')+'" "$@" || exit $?\n'+('printf x | dd of="$1" bs=1 seek=$(( $2*512 )) conv=notrunc 2>/dev/null\n' if case=='readback-failure' else ''));writer.chmod(0o755)
  script=base.replace('BB=/bin/busybox','BB='+str(bb)).replace('DEV=/dev/mmcblk0','DEV='+str(dev)).replace('SD=/mnt/sd','SD='+str(sd)).replace('WORK=/run/restore-operation','WORK='+str(c/'work')).replace('/sys/block/mmcblk0/device/cid',str(cidfile)).replace('/sys/block/mmcblk0/size',str(cap)).replace('/proc/mounts',str(mounts)).replace('/proc/swaps',str(swaps)).replace('/bin/backup-copy',str(w/'backup_copy')).replace('/bin/stream-write',str(writer)).replace('NODE=/dev/mmcblk0$NAME','NODE='+str(c)+'/$NAME').replace('[ -b ', '[ -f ').replace('/run/emmc-auto.log',str(c/'log'))
  runner=c/'run';runner.write_text(script)
  original=(back/'emmc.part01').read_bytes();conf=(sd/'e70q10-update/update.conf').read_bytes()
  if case=='corrupt-backup':
   with (back/'emmc.part01').open('r+b') as f:f.write(b'bad')
  if case=='config-mismatch':(sd/'e70q10-update/update.conf').write_bytes(conf+b'extra=1\n')
  shutil.rmtree(sd/'e70q10-update-status',ignore_errors=True)
  before=hashlib.sha256(dev.read_bytes()).hexdigest()
  with (c/'log').open('wb') as log:r=subprocess.run(['sh',runner,str(sd/'e70q10-update')],stdout=log,stderr=log,timeout=45)
  actions=trace.read_text().splitlines() if trace.exists() else []
  if case=='success':
   assert r.returncode==0,(c/'log').read_text();assert actions==['104448 419840','524288 4096','0 1','reboot'],actions
   with dev.open('rb') as f:
    for name in ('emmc.part00','emmc.part01'):
     n=(back/name).stat().st_size;assert hashlib.sha256(f.read(n)).hexdigest()==before_backup[name]
   with (c/'log').open('ab') as log:r2=subprocess.run(['sh',runner,str(sd/'e70q10-update')],stdout=log,stderr=log,timeout=45)
   assert r2.returncode==0 and trace.read_text().splitlines()==actions
  else:
   assert r.returncode!=0,(case,(c/'log').read_text());assert 'reboot' not in actions and '0 1' not in actions
   if case not in ('write-failure','readback-failure'):assert hashlib.sha256(dev.read_bytes()).hexdigest()==before and not actions
  (back/'emmc.part01').write_bytes(original);(sd/'e70q10-update/update.conf').write_bytes(conf)
  proof['cases'].append({'case':case,'exit':r.returncode,'actions':actions})
  shutil.copy2(c/'log',LOG/(case+'.log'))
 assert before_backup=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in back.iterdir()}
 # PC rejection gates before any SD change.
 (back/'complete').unlink()
 try:snapshot(back);raise AssertionError('incomplete accepted')
 except FileNotFoundError:pass
 proof['cases'].append('incomplete marker refused; snapshot files preserved')
(LOG/'validation.json').write_text(json.dumps(proof,indent=2))
print('PASS rollback: paired RAM, byte-exact file restore, MBR last, replay guard, 8 failure gates, no physical writes')
