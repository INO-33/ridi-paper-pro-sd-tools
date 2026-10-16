#!/usr/bin/env python3
"""Bounded writer + corrupt-image PC gates + real regular-file writer speed comparison.
No physical storage writes. All disks/archives/staged files removed at exit.
"""
from pathlib import Path
import sys,tempfile,subprocess,zipfile,tarfile,io,hashlib,gzip,time,json,os,struct,shutil
SRC=Path(__file__).resolve().parent;ROOT=SRC.parents[2];LOG=Path(sys.argv[3]) if len(sys.argv)>3 else ROOT/'.orchestrator/logs/emmc-speed-20261013';LOG.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(SRC));from package import verify_image,validate,plan,stage
seed=Path(sys.argv[1]);candidate=Path(sys.argv[2]);proof={'physical_writes':False,'cases':[]}
cc='/opt/st/stm32cubeclt_1.18.0/gnu-tools-for-stm32/14.3.1+st.2/bin/arm-none-eabi-gcc'
with tempfile.TemporaryDirectory(prefix='ridi-speed-tests-') as td:
 w=Path(td);host=w/'stream-host';arm=w/'stream-arm';native=w/'layout-host'
 subprocess.run(['gcc','-DHOST','-O2',str(SRC/'stream_write.c'),'-o',str(host)],check=True)
 subprocess.run([cc,'-O2','-marm','-march=armv7-a','-ffreestanding','-fno-builtin','-nostdlib','-static','-Wl,-e,_start,-Ttext=0x10000',str(SRC/'stream_write.c'),'-lgcc','-o',str(arm)],check=True)
 reader=w/'backup-reader';subprocess.run(['gcc','-DHOST','-O2',str(SRC/'backup_copy.c'),'-o',str(reader)],check=True)
 subprocess.run(['gcc','-DHOST','-O2',str(SRC/'device_layout.c'),'-o',str(native)],check=True)
 # Test exact, short and oversized input on BOTH the deployed ARM binary and host build.
 for mode,cmd in [('host',[str(host)]),('arm',['qemu-arm-static',str(arm)])]:
  for name,n,ok in [('exact',2048,True),('short',2047,False),('oversized',2049,False)]:
   dest=w/'bounded';sentinel=b'Z'*8192;dest.write_bytes(sentinel);data=b'A'*n
   r=subprocess.run(cmd+[str(dest),'4','4'],input=data,capture_output=True)
   assert (r.returncode==0)==ok,(mode,name,r.stderr)
   out=dest.read_bytes();assert out[:2048]==sentinel[:2048] and out[4096:]==sentinel[4096:]
   if ok:assert out[2048:4096]==data
   proof['cases'].append(mode+'-'+name+'-bounded')
  # 64-bit destination offset regression without allocating a large disk.
  dest=w/'large-offset';offset=1<<32
  with dest.open('wb') as f:f.truncate(offset+4096)
  r=subprocess.run(cmd+[str(dest),str(offset//512),'4'],input=b'B'*2048,capture_output=True);assert r.returncode==0,r.stderr
  with dest.open('rb') as f:f.seek(offset);assert f.read(4096)==b'B'*2048+bytes(2048)
  dest.unlink();proof['cases'].append(mode+'-64bit-offset')
 raw=b'hello'*1000;compressed=gzip.compress(raw,mtime=0)
 for name,data,expected_size,expected_hash,ok in [
  ('valid',compressed,len(raw),hashlib.sha256(raw).hexdigest(),True),
  ('wrong-raw-hash',compressed,len(raw),'0'*64,False),
  ('oversize',compressed,len(raw)-1,hashlib.sha256(raw).hexdigest(),False),
  ('short-raw',compressed,len(raw)+1,hashlib.sha256(raw).hexdigest(),False),
  ('gzip-crc',compressed[:-5]+bytes([compressed[-5]^1])+compressed[-4:],len(raw),hashlib.sha256(raw).hexdigest(),False),
  ('truncated',compressed[:-3],len(raw),hashlib.sha256(raw).hexdigest(),False)]:
  p=w/'image';p.write_bytes(data);m=tarfile.TarInfo(name);m.offset_data=0;m.size=len(data)
  try:verify_image(p,m,expected_size,expected_hash,hashlib.sha256(data).hexdigest());passed=True
  except ValueError:passed=False
  assert passed==ok,name;proof['cases'].append('pc-'+name)
 out=w/'release';out.mkdir();old_writer=w/'old-writer.sh'
 for zpath,current in [(seed,False),(candidate,True)]:
  with zipfile.ZipFile(zpath) as z:
   tn=next(n for n in z.namelist() if n.endswith('.tar'));data=z.read(tn)
   if current:
    archive=out.with_suffix('.tar');archive.write_bytes(data);Path(str(archive)+'.sha256').write_bytes(z.read(tn+'.sha256').replace(tn.encode(),archive.name.encode()))
   with tarfile.open(fileobj=io.BytesIO(data)) as t:
    if not current:old_writer.write_bytes(t.extractfile('e70q10-update/updater.sh').read());continue
    for n in ['system.raw.gz','vendor.raw.gz','boot.raw.gz','manifest.tsv','updater.sh','ram-auto.sh']:(out/n).write_bytes(t.extractfile('e70q10-update/'+n).read())
 report=validate(archive);proof['pc_image_validation']=report['pc_image_validation']
 subprocess.run([sys.executable,str(SRC/'test_runtime_policy.py'),str(out),str(LOG)],check=True)
 # Same pinned manifest in baseline and optimized package isolates runtime differences.
 base=Path('/media/juwon/build/리디백업/backups/e70q10-PP1A1GK166561-20260923-full-emmc');dev=w/'emmc.disk';tables=w/'tables';tables.mkdir()
 with dev.open('wb') as f,(base/'emmc.part00').open('rb') as b:f.write(b.read(51<<20));f.truncate(7818182656)
 def source(lba):
  i,o=divmod(lba*512,256<<20)
  with (base/f'emmc.part{i:02d}').open('rb') as f:f.seek(o);return f.read(512)
 m=source(0);ext=struct.unpack_from('<I',m,486)[0];at=ext
 with dev.open('r+b') as f:
  for _ in range(5):
   e=source(at);f.seek(at*512);f.write(e);n=struct.unpack_from('<I',e,470)[0]
   if not n:break
   at=ext+n
 subprocess.run([str(native),'plan',str(dev),'15269888',str(tables)],stdout=subprocess.DEVNULL,check=True)
 with dev.open('r+b') as f:
  for p in tables.glob('ebr.sector*.bin'):f.seek(int(p.name[10:-4])*512);f.write(p.read_bytes())
  f.seek(0);f.write((tables/'mbr.sector0.bin').read_bytes())
  # Sentinel bytes in every unselected region and each boundary.
  protected=[(0,512),(2271232*512,4096),(2404352*512,4096),(15259648*512,4096),(15268864*512,4096)]
  for offset,size in protected[1:]:f.seek(offset);f.write(os.urandom(size))
 def capture():
  with dev.open('rb') as f:
   result=[]
   for offset,size in protected:f.seek(offset);result.append(f.read(size))
   return result
 before=capture();mh=report['manifest'];(out/'update.conf').write_text(f'format=1\nmanifest={mh}\ntargets=system,vendor,boot\nautostart=0\nreboot=0\n')
 times={}
 for name,writer in [('baseline',old_writer),('optimized',out/'updater.sh')]:
  env=os.environ|{'UPDATER_BB':'/usr/bin/busybox','UPDATER_COUNTER':str(SRC.parent/'emmc-updater/assets/countbytes-host'),'UPDATER_STREAM':str(host),'UPDATER_READER':str(reader),'UPDATER_LAYOUT':str(native),'UPDATER_WORK':str(w/(name+'-work'))}
  started=time.monotonic()
  with (LOG/(name+'-writer.log')).open('wb') as lf:r=subprocess.run(['sh',str(writer),'rehearse',str(dev),str(out)],env=env,stdout=lf,stderr=lf)
  assert r.returncode==0,(name,r.returncode);times[name]=round(time.monotonic()-started,3);assert capture()==before
  log=(LOG/(name+'-writer.log')).read_text();assert log.count('READBACK PASSED')==3
  if name=='optimized':assert 'VERIFY compressed hash' not in log and 'VERIFY expanded' not in log
 proof['writer_wall_seconds']=times;proof['speedup_host_rehearsal']=round(times['baseline']/times['optimized'],2)
 proof['all_image_readbacks']='passed; cache/userdata/misc/table sentinels unchanged'
 # SD stage exercises parallel copy and subsequent independent reads on a temporary directory.
 mount=w/'sd';mount.mkdir();stage(report,plan(report,'update','all'),mount,8,verify_mount=False)
 proof['parallel_stage_readback']='passed on temporary folder, physical SD speed not measured'
 (LOG/'speed-validation.json').write_text(json.dumps(proof,indent=2)+'\n')
print('PASS: host/ARM bounded writes, corrupt-image PC gates, all OS readbacks, parallel stage and guards')
