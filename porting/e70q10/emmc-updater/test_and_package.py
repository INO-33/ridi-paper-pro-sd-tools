#!/usr/bin/env python3
"""Regular-file selected-write rehearsal, auto flow mocks, and package export."""
import argparse,pathlib as P,subprocess as S,gzip,hashlib,json,os,shutil,struct,tarfile,sys,shlex
from runtime_assets import verify_assets
from selection import roles,parse_control,control,targets,RANGES,ORDER
ROOT=P.Path(os.environ.get('RIDI_WORKSPACE', P.Path(__file__).resolve().parents[3]));SRC=ROOT/'porting/e70q10/emmc-updater';ASSETS=SRC/'assets';TABLE=ASSETS/'tables';BACK=P.Path('/media/juwon/build/리디백업/backups/e70q10-PP1A1GK166561-20260923-full-emmc')
verify_assets(ASSETS)
p=argparse.ArgumentParser();p.add_argument('directory',type=P.Path);a=p.parse_args();OUT=a.directory.resolve();W=OUT/'.rehearsal';W.mkdir(exist_ok=True)
LOGDIR=ROOT/'.orchestrator/logs/emmc-auto-20261006';LOGDIR.mkdir(parents=True,exist_ok=True);LOG=LOGDIR/(OUT.name+'-rehearsal.log');disk=W/'emmc.disk';env=os.environ|{'UPDATER_BB':'/usr/bin/busybox','UPDATER_COUNTER':str(OUT/'countbytes-host'),'UPDATER_WORK':str(W/'run')}
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(4<<20),b''):h.update(b)
 return h.hexdigest()
manifest=(OUT/'manifest.tsv').read_text();mh=sha(OUT/'manifest.tsv');available=roles([x.split() for x in manifest.splitlines()]);default,automatic,reboot=parse_control((OUT/'update.conf').read_bytes(),mh,available)
def command(script,package,ok=True):
 with LOG.open('ab') as log:r=S.run(['sh',str(script),'rehearse',str(disk),str(package)],env=env,stdout=log,stderr=log)
 assert (r.returncode==0)==ok,(r.returncode,package)
with disk.open('wb') as f,open(BACK/'emmc.part00','rb') as source:f.write(source.read(51<<20));f.truncate(7818182656)
with disk.open('r+b') as f:
 for sector in [0,169984,2269184,2402304,14731264,15257600]:
  name='mbr.sector0.bin' if sector==0 else f'ebr.sector{sector}.bin';f.seek(sector*512);f.write((TABLE/name).read_bytes())
 for sector in [104448,169970,170100,172032,2269170,2271232,2404352,2404500,4000000,8000000,12000000,14730000,14732000,14733312,15257590,15259648,15267000,15268000]:
  f.seek(sector*512);f.write(hashlib.sha256(str(sector).encode()).digest()*128)
def complement(selected):
 windows=sorted((RANGES[n][1]*512,(RANGES[n][1]+RANGES[n][2])*512) for n in selected);keep=[];at=0
 for begin,end in windows:
  if begin>at:keep.append((at,begin))
  at=end
 if at<7818182656:keep.append((at,7818182656))
 h=hashlib.sha256()
 with disk.open('rb') as f:
  for begin,end in keep:
   f.seek(begin);left=end-begin
   while left:
    b=f.read(min(left,4<<20));assert b;h.update(b);left-=len(b)
 return h.hexdigest()
# Negative cases must preserve every byte, including all candidate payload ranges.
before_all=complement(())
with disk.open('r+b') as f:f.seek(0);f.write((TABLE/'original-mbr.sector0.bin').read_bytes())
command(OUT/'updater.sh',OUT,False)
with disk.open('r+b') as f:f.seek(0);f.write((TABLE/'mbr.sector0.bin').read_bytes())
bad=W/'bad';bad.mkdir(exist_ok=True)
for name in ['manifest.tsv','update.conf']+[RANGES[n][0] for n in available]:
 target=bad/name
 if os.path.lexists(target):target.unlink()
 target.symlink_to(OUT/name)
first=RANGES[default[0]][0];(bad/first).unlink();(bad/first).write_bytes(b'corrupt gzip');command(OUT/'updater.sh',bad,False);(bad/first).unlink();(bad/first).symlink_to(OUT/first)
(bad/'manifest.tsv').unlink();(bad/'manifest.tsv').write_text('bad\n');command(OUT/'updater.sh',bad,False)
row=manifest.splitlines()[0].split();old=' '.join(row[:3]);row[1]='38912' if row[0]=='boot.raw.gz' else '2404352';wrong=manifest.replace(old,' '.join(row[:3]));(bad/'manifest.tsv').write_text(wrong);newhash=sha(bad/'manifest.tsv');guard=W/'range-guard.sh';guard.write_text((OUT/'updater.sh').read_text().replace(mh,newhash));(bad/'update.conf').unlink();(bad/'update.conf').write_bytes(control(newhash,default));command(guard,bad,False)
(bad/'manifest.tsv').write_text(manifest);(bad/'update.conf').write_bytes(control(mh,default)+b'targets=boot\n');command(OUT/'updater.sh',bad,False)
(bad/'update.conf').write_bytes(control(mh,default).replace(b'targets='+','.join(default).encode(),b'targets=$(touch /run/SHOULD_NOT_EXIST)'));command(OUT/'updater.sh',bad,False)
assert complement(())==before_all,'Invalid inputs wrote device bytes'
# Test each singleton and package default. Mark all other allowed partitions with
# differing data so accidental extra writes cannot hide behind identical images.
selections=list(dict.fromkeys([default]+[(n,) for n in available]))
if set(available)==set(ORDER):selections.append(('system','vendor'))
proofs=[]
for selected in selections:
 case=W/('selected-'+'-'.join(selected));case.mkdir(exist_ok=True)
 (case/'manifest.tsv').write_text(manifest);(case/'update.conf').write_bytes(control(mh,selected))
 for role in selected:
  file=case/RANGES[role][0]
  if not os.path.lexists(file):file.symlink_to(OUT/file.name)
 with disk.open('r+b') as f:
  for role in ORDER:f.seek(RANGES[role][1]*512);f.write(hashlib.sha256(('case'+','.join(selected)+role).encode()).digest())
 before=complement(selected);command(OUT/'updater.sh',case);after=complement(selected);assert before==after,'Unselected bytes changed: '+str(selected)
 with disk.open('rb') as f:
  for line in manifest.splitlines():
   name,start,sectors,expected,comp=line.split()
   if name.removesuffix('.raw.gz') not in selected:continue
   f.seek(int(start)*512);left=int(sectors)*512;h=hashlib.sha256()
   while left:b=f.read(min(left,4<<20));assert b;h.update(b);left-=len(b)
   assert h.hexdigest()==expected
 proofs.append({'targets':selected,'non_target_before':before,'non_target_after':after,'readback':'passed'})
# ARM boot formats and actual packed executable tools.
from boot_image import unpack,entries
if 'boot' in available:
 k,rd,_=unpack((OUT/'boot-emmc.img').read_bytes());es=entries(rd);assert b'/dev/block/mmcblk1' not in es['fstab.E70Q10'][1] and b'mmcblk1' not in es['init.E70Q10.rc'][1]
b=(OUT/'ram-updater.img').read_bytes();ks,ka,rs,ra,ss,sa,tags,page=struct.unpack_from('<8I',b,8);assert ss==0 and ka==0x82808000 and ra==0x84000000;at=page;h=hashlib.sha1();chunks=[]
for size in [ks,rs,ss]:
 data=b[at:at+size];chunks.append(data);h.update(data);h.update(struct.pack('<I',size));at+=(size+page-1)//page*page
assert h.digest()==b[576:596];start,end=struct.unpack_from('<II',chunks[0],40);assert chunks[0][end-start:end-start+4]==bytes.fromhex('d00dfeed');es=entries(chunks[1])
for name,file in [('bin/updater','updater.sh'),('bin/auto-update','auto-update.sh')]:assert es[name][1]==(OUT/file).read_bytes() and es[name][0][1]&0o111
assert es['bin/countbytes'][1]==(ASSETS/'countbytes-arm').read_bytes() and es['bin/countbytes'][0][1]&0o111
assert es['bin/console-shell'][0][1]&0o111 and b'/bin/auto-update' in es['init'][1]
assert S.check_output(['/usr/bin/qemu-arm-static',str(OUT/'.build/ram-root/bin/busybox'),'sha256sum',str(OUT/'manifest.tsv')]).split()[0].decode()==mh
# Automatic flow with mount/reboot mocked. Never invokes a device or real reboot.
auto_proofs=[]
for name,rc,auto,do_reboot,mount_ok,valid in [('success',0,True,True,True,True),('apply-failure',1,True,True,True,True),('manual',0,False,True,True,True),('no-reboot',0,True,False,True,True),('log-failure',0,True,True,False,True),('invalid-config',0,True,True,True,False)]:
 case=W/('auto-'+name);case.mkdir(exist_ok=True);sd=case/'sd';sd.mkdir(exist_ok=True);pkg=sd/'e70q10-update';pkg.mkdir(exist_ok=True);trace=case/'trace';log=case/'auto.log'
 (pkg/'update.conf').write_bytes(control(mh,default,auto,do_reboot) if valid else b'format=1\ntargets=$(reboot)\n')
 bb=case/'bb';bb.write_text('#!/bin/sh\ncase "$1" in mount) echo mount >>'+shlex.quote(str(trace))+';exit '+('0' if mount_ok else '1')+';;reboot) echo reboot >>'+shlex.quote(str(trace))+';exit 0;;sync) exit 0;;esac\nexec /usr/bin/busybox "$@"\n');bb.chmod(0o755)
 update=case/'update';update.write_text('#!/bin/sh\necho apply >>'+shlex.quote(str(trace))+'\necho "UPDATE VERIFIED MOCK"\nexit '+str(rc)+'\n');update.chmod(0o755)
 script=(OUT/'auto-update.sh').read_text().replace('BB=/bin/busybox','BB='+shlex.quote(str(bb))).replace('SD=/mnt/sd','SD='+shlex.quote(str(sd))).replace('/bin/updater apply',shlex.quote(str(update))+' apply').replace('/run/emmc-auto.log',str(log))
 test=case/'run.sh';test.write_text(script)
 with log.open('wb') as f:r=S.run(['sh',str(test),str(pkg)],stdout=f,stderr=f)
 actions=trace.read_text().splitlines() if trace.exists() else []
 expect_reboot=valid and auto and rc==0 and mount_ok and do_reboot
 assert ('reboot' in actions)==expect_reboot,(name,actions)
 assert ('apply' in actions)==(valid and auto),(name,actions)
 assert (r.returncode==0)==(valid and (not auto or (rc==0 and mount_ok))),name
 if valid and auto and mount_ok:assert (sd/'e70q10-update-status/last.result').is_file() and 'exit='+str(rc) in (sd/'e70q10-update-status/last.result').read_text()
 auto_proofs.append({'case':name,'actions':actions,'passed':True})
fat=W/'fat.img'
with fat.open('wb') as f:f.truncate(128<<20)
with LOG.open('ab') as log:S.run(['mkfs.vfat','-F','32','-S','512','-n','RIDI_UPD',str(fat)],check=True,stdout=log,stderr=log)
props=S.check_output(['blkid','-p','-o','export',str(fat)],text=True);assert 'LABEL=RIDI_UPD' in props and 'VERSION=FAT32' in props;fat.unlink();disk.unlink()
source=OUT/'source';source.mkdir(exist_ok=True)
for src in SRC.iterdir():
 if src.is_file():shutil.copy2(src,source/src.name)
for name in ['README.md','boot_ram_updater.sh','prepare_update_sd.sh','format_prepare_update_sd.sh','validate_package.py','selection.py']:shutil.copy2(SRC/name,OUT/name)
report=json.loads((OUT/'build-report.json').read_text());report.update({'offline_validation':'passed','selected_write_rehearsals':proofs,'negative_cases':'invalid table, gzip, manifest, pinned forbidden range, duplicate config and config injection rejected; every byte retained','auto_flow_mock_tests':auto_proofs,'ram_image_validation':'header/DTB, updater/auto worker, counter/console executable modes verified','physical_update_validation':'not performed','fat_label_validation':'actual FAT32 mkfs/blkid on regular file passed'})
(OUT/'build-report.json').write_text(json.dumps(report,indent=2)+'\n')
files=sorted(x for x in OUT.rglob('*') if x.is_file() and not any(part.startswith('.') for part in x.relative_to(OUT).parts) and x.name!='SHA256SUMS');(OUT/'SHA256SUMS').write_text(''.join(sha(x)+'  '+str(x.relative_to(OUT))+'\n' for x in files));archive=OUT.with_suffix('.tar')
with tarfile.open(archive,'w') as tar:
 for x in sorted(OUT.iterdir()):
  if not x.name.startswith('.'):tar.add(x,arcname='e70q10-update/'+x.name)
archive.with_suffix('.tar.sha256').write_text(sha(archive)+'  '+archive.name+'\n')
from validate_package import validate
validate(archive)
print('PASS: selected writes/readback and all other byte preservation, auto success/failure/reboot flow, RAM/ARM/FAT32 and archive checks')
print('PACKAGE',archive,archive.stat().st_size,'bytes')
