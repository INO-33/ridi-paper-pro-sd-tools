#!/usr/bin/env python3
"""Backup I/O tests only: simulated model/layout with small regular-file device.
Exercises full 256MiB chunks and partial tail, source/SD hashes and retry gates.
Model parsing is tested separately. No physical SD/eMMC writes.
"""
from pathlib import Path
import tempfile,subprocess,sys,os,json,time,hashlib,zipfile,tarfile,io,shutil
SRC=Path(__file__).resolve().parent;ROOT=SRC.parents[2];LOG=ROOT/'.orchestrator/logs/emmc-backup-speed-20261013';LOG.mkdir(parents=True,exist_ok=True)
cc='/opt/st/stm32cubeclt_1.18.0/gnu-tools-for-stm32/14.3.1+st.2/bin/arm-none-eabi-gcc';proof={'physical_writes':False,'model':'mocked only for backup I/O fixture','cases':[]}
with tempfile.TemporaryDirectory(prefix='ridi-backup-speed-') as td:
 w=Path(td);host=w/'backup-host';arm=w/'backup-arm'
 subprocess.run(['gcc','-DHOST','-O2','-Wall','-Wextra',str(SRC/'backup_copy.c'),'-o',str(host)],check=True)
 subprocess.run([cc,'-O2','-marm','-march=armv7-a','-ffreestanding','-fno-builtin','-nostdlib','-static','-Wl,-e,_start,-Ttext=0x10000',str(SRC/'backup_copy.c'),str(SRC/'vendor/sha256/sha256-armv4.S'),'-D__KERNEL__','-D__LINUX_ARM_ARCH__=7','-lgcc','-o',str(arm)],check=True)
 data=os.urandom((1<<20)+137);source=w/'source';source.write_bytes(b'PREFIX'+data+b'TAIL')
 for name,cmd in [('host',[str(host)]),('arm',['qemu-arm-static',str(arm)])]:
  dest=w/('copy-'+name);r=subprocess.run(cmd+[str(source),str(dest),'6',str(len(data))],capture_output=True);assert r.returncode==0,r.stderr;assert r.stdout==data==dest.read_bytes();proof['cases'].append(name+'-copy-stream-exact-fsync-discard')
  before=dest.stat().st_mtime_ns;r=subprocess.run(cmd+[str(source),str(dest),'0','512'],capture_output=True);assert r.returncode!=0 and dest.read_bytes()==data and dest.stat().st_mtime_ns==before;proof['cases'].append(name+'-no-overwrite')
  r=subprocess.run(cmd+[str(source),str(w/('short-'+name)),'0',str(source.stat().st_size+1)],capture_output=True);assert r.returncode!=0;proof['cases'].append(name+'-short-read-rejected')
  large=w/('offset-'+name)
  with large.open('wb') as f:f.seek(1<<32);f.write(data)
  r=subprocess.run(cmd+[str(large),str(w/('offset-dest-'+name)),str(1<<32),str(len(data))],capture_output=True);assert r.returncode==0 and r.stdout==data,r.stderr;large.unlink();proof['cases'].append(name+'-64bit-source-offset')
 # The stream processor exits nonzero when the hash reader fails; no deadlock.
 p=subprocess.Popen([str(host),str(source),str(w/'broken-reader'),'0',str(len(data))],stdout=subprocess.PIPE,stderr=subprocess.PIPE);p.stdout.close();p.wait(timeout=5);assert p.returncode!=0;proof['cases'].append('hash-consumer-failure-stops-copy')
 if Path(sys.argv[1]).suffix=='.sh':baseline=Path(sys.argv[1]).read_text()
 else:
  with zipfile.ZipFile(sys.argv[1]) as z:
   with tarfile.open(fileobj=io.BytesIO(z.read(next(n for n in z.namelist() if n.endswith('.tar'))))) as t:baseline=t.extractfile('e70q10-update/ram-backup.sh').read().decode()
 baseline=baseline.replace('aff449a8879b44f2fcd8d148a563aa511bc916d61e153670ae5f88035010d9dd','@MANIFEST@')
 mh='a'*64;pkg=w/'pkg';pkg.mkdir();manifest=b'system.raw.gz 172032 2097152 '+b'b'*64+b' '+b'c'*64+b'\n';(pkg/'manifest.tsv').write_bytes(manifest);(pkg/'system.raw.gz').touch();mh=hashlib.sha256(manifest).hexdigest()
 for original in (baseline,(SRC/'ram-backup.sh').read_text()):assert 'VERIFY compressed hash' not in original
 cid='112233445566778899aabbccddeeff00';cf=w/'cid';cf.write_text(cid);size=(512<<20)+65536;cap=w/'capacity';cap.write_text(str(size//512));dev=w/'emmc'
 with dev.open('wb') as f:
  f.truncate(size)
  for offset in [0,53<<20,256<<20,512<<20]:f.seek(offset);f.write(os.urandom(4096))
 for n in ['boot0','boot1']:(w/n).write_bytes(os.urandom(65536))
 model=w/'layout';model.write_text('#!/bin/sh\nprintf "BYTES='+str(size)+'\\nSECTORS='+str(size//512)+'\\nCURRENT_KIND=stock\\n"\n');model.chmod(0o755)
 sd=w/'sd';sd.mkdir();bb=w/'bb';bb.write_text('#!/bin/sh\ncase "$1" in mount) exit 0;; sync) exec /usr/bin/sync -f '+str(sd)+';; blockdev) /usr/bin/stat -c %s "$3";exit;; esac\nexec /usr/bin/busybox "$@"\n');bb.chmod(0o755)
 def render(text,work):
  text=text.replace('@MANIFEST@',mh).replace('BB=/bin/busybox','BB='+str(bb)).replace('DEV=/dev/mmcblk0','DEV='+str(dev)).replace('SD=/mnt/sd','SD='+str(sd)).replace('[ -b "$DEV" ]','[ -f "$DEV" ]').replace('/sys/block/mmcblk0/device/cid',str(cf)).replace('/sys/block/mmcblk0/size',str(cap)).replace('WORK=/run/backup-operation','WORK='+str(work)).replace('/bin/device-layout',str(model)).replace('/bin/backup-copy',str(host)).replace('NODE=/dev/mmcblk0$NAME','NODE='+str(w)+'/$NAME').replace('[ -b "$NODE" ]','[ -f "$NODE" ]').replace('[ -b /dev/mmcblk0$NAME ]','[ -f '+str(w)+'/$NAME ]')
  return text
 times={};back=None
 for name,text in [('baseline',baseline),('optimized',(SRC/'ram-backup.sh').read_text())]:
  job=('b' if name=='baseline' else 'c')*32;work=w/(name+'-run');script=w/(name+'.sh');script.write_text(render(text,work));started=time.monotonic()
  with (LOG/(name+'.log')).open('wb') as f:r=subprocess.run(['sh',str(script),str(pkg),job],stdout=f,stderr=f)
  assert r.returncode==0,(name,r.returncode);times[name]=round(time.monotonic()-started,3);back=sd/'e70q10-backups'/cid/job
  pieces=sorted(back.glob('emmc.part*'));assert [p.stat().st_size for p in pieces]==[256<<20,256<<20,65536]
  for i,piece in enumerate(pieces):
   with dev.open('rb') as f:f.seek(i*(256<<20));assert hashlib.file_digest(piece.open('rb'),'sha256').hexdigest()==hashlib.sha256(f.read(piece.stat().st_size)).hexdigest()
  for n in ['boot0','boot1']:assert (back/(n+'.bin')).read_bytes()==(w/n).read_bytes()
  assert (back/'complete').read_text().strip()==cid+':'+str(size)
  if name=='baseline':shutil.rmtree(back)
 proof['times_seconds']=times;proof['speedup_host_fixture']=round(times['baseline']/times['optimized'],2)
 proof['raw_chunks']='two full 256MiB chunks + 64KiB tail, exact source/hash matches; both boot areas matched'
 # Existing completed snapshot is verified, not replaced.
 script=w/'optimized.sh';work=w/'optimized-run';before={p.name:p.stat().st_mtime_ns for p in back.iterdir()};shutil.rmtree(work)
 with (LOG/'retry.log').open('wb') as f:r=subprocess.run(['sh',str(script),str(pkg),'c'*32],stdout=f,stderr=f)
 assert r.returncode==0 and before=={p.name:p.stat().st_mtime_ns for p in back.iterdir()};proof['cases'].append('completed-retry-verified-without-overwrite')
 with (back/'emmc.part00').open('r+b') as f:f.write(b'CORRUPT')
 shutil.rmtree(work)
 with (LOG/'corrupt.log').open('wb') as f:r=subprocess.run(['sh',str(script),str(pkg),'c'*32],stdout=f,stderr=f)
 assert r.returncode!=0;proof['cases'].append('corrupt-completed-backup-rejected')
 (back/'complete').unlink();shutil.rmtree(work)
 with (LOG/'incomplete.log').open('wb') as f:r=subprocess.run(['sh',str(script),str(pkg),'c'*32],stdout=f,stderr=f)
 assert r.returncode!=0 and not (back/'complete').exists();proof['cases'].append('incomplete-backup-not-replaced-or-marked-complete')
 # Corrupt the freshly copied SD file before first readback: marker must not be created.
 wrapper=w/'corrupt-copy';wrapper.write_text('#!/bin/sh\n'+str(host)+' "$@" || exit $?\nif [ "$1" = --copy-hash ]; then printf CORRUPT | dd of="$3" bs=1 conv=notrunc 2>/dev/null; fi\n');wrapper.chmod(0o755)
 badtext=render((SRC/'ram-backup.sh').read_text(),w/'fresh-corrupt-run').replace(str(host),str(wrapper));badscript=w/'fresh-corrupt.sh';badscript.write_text(badtext)
 with (LOG/'fresh-corrupt.log').open('wb') as f:r=subprocess.run(['sh',str(badscript),str(pkg),'d'*32],stdout=f,stderr=f)
 badback=sd/'e70q10-backups'/cid/('d'*32);assert r.returncode!=0 and not (badback/'complete').exists();proof['cases'].append('fresh-SD-readback-mismatch-prevents-completion')
 (LOG/'backup-speed-validation.json').write_text(json.dumps(proof,indent=2)+'\n')
print('PASS: backup single-source-pass, independent SD readback, host/ARM, retries and corruption gates')
