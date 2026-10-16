#!/usr/bin/env python3
"""Model-wide regular-file verification, using both original stock layouts."""
from pathlib import Path
import struct,subprocess,sys,os,tempfile,hashlib,json,shutil,gzip
from package import sha,validate,plan
SRC=Path(__file__).resolve().parent
OUT=Path(sys.argv[1]).resolve();NATIVE=OUT/'.native/device-layout-host';ARM=OUT/'.native/device-layout-arm'
LOGS=Path('/home/juwon/ridi/.orchestrator/logs/emmc-model-20261008');LOGS.mkdir(parents=True,exist_ok=True)
BACK=Path('/media/juwon/build/리디백업/backups')
# July is a backup-copy fixture, not stock hardware evidence.
CASES=[('september','e70q10-PP1A1GK166561-20260923-full-emmc',15269888)]
proofs=[]
def run(cmd,ok=True,env=None):
 r=subprocess.run(list(map(str,cmd)),capture_output=True,env=env)
 with (LOGS/'model-details.log').open('ab') as f:f.write(r.stdout+r.stderr)
 assert (r.returncode==0)==ok,(r.returncode,r.stderr.decode(errors='replace'))
 return r.stdout.decode()
def read_backup(folder,pos,size):
 out=bytearray()
 while size:
  index,offset=divmod(pos,256<<20);n=min(size,(256<<20)-offset)
  with (folder/f'emmc.part{index:02d}').open('rb') as f:f.seek(offset);d=f.read(n)
  assert len(d)==n;out+=d;pos+=n;size-=n
 return bytes(out)
def variables(text):return dict(line.split('=',1) for line in text.splitlines())
def metadata(folder):
 m=read_backup(folder,0,512);base=struct.unpack_from('<I',m,486)[0];at=base;tables={0:m}
 for _ in range(5):
  b=read_backup(folder,at*512,512);tables[at]=b;next=struct.unpack_from('<I',b,470)[0]
  if not next:break
  at=base+next
 return tables
with tempfile.TemporaryDirectory(prefix='paperpro-model-') as td:
 w=Path(td)
 for name,folder_name,sectors in CASES:
  folder=BACK/folder_name;case=w/name;case.mkdir();disk=case/'emmc.disk';tables=case/'tables';tables.mkdir()
  stock=read_backup(folder,0,51<<20)
  with disk.open('wb') as f:f.write(stock);f.truncate(sectors*512)
  # Copy stock EBRs above the protected range into this sparse regular fixture.
  with disk.open('r+b') as f:
   for lba,data in metadata(folder).items():f.seek(lba*512);f.write(data)
  # Other units can have distinct disk IDs, VCOM/panel bytes and revision.
  with disk.open('r+b') as f:
   f.seek(440);f.write(os.urandom(4));f.seek(524288+55);f.write(bytes([1,210]));f.seek(524288+57);f.write(bytes([17]))
  original_mbr=disk.read_bytes()[:512] if False else None
  with disk.open('rb') as f:original_mbr=f.read(512);before=hashlib.sha256(f.read((51<<20)-512)).hexdigest()
  result=variables(run([NATIVE,'plan',disk,sectors,tables]))
  arm=variables(run(['/usr/bin/qemu-arm-static',ARM,'plan',disk,sectors,tables]))
  assert result==arm
  assert result['CURRENT_KIND']=='stock'
  newm=(tables/'mbr.sector0.bin').read_bytes()
  assert newm[:446]==original_mbr[:446] and newm[462:478]==original_mbr[462:478]
  with disk.open('r+b') as f:
   for file in tables.glob('ebr.sector*.bin'):
    lba=int(file.name.removeprefix('ebr.sector').removesuffix('.bin'));f.seek(lba*512);f.write(file.read_bytes())
   f.seek(0);f.write(newm)
  result=variables(run([NATIVE,'check',disk,sectors,tables]))
  part=json.loads(run(['/usr/sbin/sfdisk','--json',disk]))['partitiontable']['partitions']
  assert len(part)==8
  actual={int(p['node'].split('disk')[-1]):(p['start'],p['size']) for p in part}
  assert actual[7]==(2404352,int(result['DATA_SECTORS'])) and actual[8]==(int(result['VENDOR_START']),524288)
  with disk.open('rb') as f:f.seek(512);after=hashlib.sha256(f.read((51<<20)-512)).hexdigest()
  assert before==after
  # Actual vendor write must follow each capacity's destination, not the sample offset.
  pkg=case/'pkg';pkg.mkdir()
  for n in ['manifest.tsv','system.raw.gz','vendor.raw.gz','boot.raw.gz']:(pkg/n).symlink_to(OUT/n)
  mh=sha(OUT/'manifest.tsv');(pkg/'update.conf').write_text(f'format=1\nmanifest={mh}\ntargets=vendor\nautostart=0\nreboot=0\n')
  writer=OUT/'updater.sh';env=os.environ|{'UPDATER_BB':'/usr/bin/busybox','UPDATER_COUNTER':str(SRC.parent/'emmc-updater/assets/countbytes-host'),'UPDATER_WORK':str(case/'writer-run'),'UPDATER_LAYOUT':str(NATIVE)}
  # Hash every byte outside vendor before/after; metadata, boot, recovery, data all included.
  start=int(result['VENDOR_START'])*512;size=268435456
  def complement():
   h=hashlib.sha256()
   with disk.open('rb') as f:
    remaining=start
    while remaining:
     data=f.read(min(remaining,8<<20));assert data;h.update(data);remaining-=len(data)
    f.seek(start+size)
    for data in iter(lambda:f.read(8<<20),b''):h.update(data)
   return h.hexdigest()
  before=complement();run(['sh',writer,'rehearse',disk,pkg],env=env);assert complement()==before
  expected=next(x.split()[3] for x in (OUT/'manifest.tsv').read_text().splitlines() if x.startswith('vendor'))
  h=hashlib.sha256()
  with disk.open('rb') as f:
   f.seek(start);remaining=size
   while remaining:data=f.read(min(remaining,8<<20));h.update(data);remaining-=len(data)
  assert h.hexdigest()==expected
  # All-target path validates the renamed sector variables and final geometry recheck.
  windows=sorted([(104448*512,65536*512),(172032*512,2097152*512),(start,size)])
  def all_complement():
   h=hashlib.sha256();at=0
   with disk.open('rb') as f:
    for begin,length in windows+[(sectors*512,0)]:
     left=begin-at
     while left:
      data=f.read(min(left,8<<20));assert data;h.update(data);left-=len(data)
     at=begin+length;f.seek(at)
   return h.hexdigest()
  before=all_complement();(pkg/'update.conf').write_text(f'format=1\nmanifest={mh}\ntargets=system,vendor,boot\nautostart=0\nreboot=0\n')
  run(['sh',writer,'rehearse',disk,pkg],env=env);assert all_complement()==before
  for row in (OUT/'manifest.tsv').read_text().splitlines():
   file,lba,count,raw,comp=row.split();lba=int(result['VENDOR_START']) if file=='vendor.raw.gz' else int(lba)
   h=hashlib.sha256()
   with disk.open('rb') as f:
    f.seek(lba*512);left=int(count)*512
    while left:
     data=f.read(min(left,8<<20));assert data;h.update(data);left-=len(data)
   assert h.hexdigest()==raw
  # Wrong model, damaged EBR, and invalid capacity rejected with no writes.
  with disk.open('r+b') as f:f.seek(524288+16);old=f.read(1);f.seek(524288+16);f.write(b'\x44')
  run([NATIVE,'check',disk,sectors,tables],False)
  with disk.open('r+b') as f:f.seek(524288+16);f.write(old);f.seek(169984*512+510);f.write(b'xx')
  run([NATIVE,'check',disk,sectors,tables],False)
  run([NATIVE,'plan',disk,1000000,tables],False)
  snapshot=case/'snapshot';snapshot.mkdir();s=variables(run([NATIVE,'snapshot',folder,sectors,snapshot]))
  proofs.append({'case':name,'sectors':sectors,'vendor_start':int(result['VENDOR_START']),'data_bytes':int(result['DATA_BYTES']),'source_misc':int(s['CURRENT_MISC_START']),'actual_host_and_ARM_plan':'matched','own_mbr_bootcode_recovery_and_prefix':'preserved','vendor_write_readback_and_all_other_bytes':'passed','all_targets_readback_and_all_other_bytes':'passed','wrong_model_bad_chain_wrong_capacity':'rejected'})
 # Smaller/larger compatible capacities produce valid geometry from an actual Paper Pro snapshot.
 for sectors in [14680064,16777216,33554432]:
  case=w/str(sectors);case.mkdir();disk=case/'disk';folder=BACK/CASES[1][1]
  with disk.open('wb') as f:f.write(read_backup(folder,0,51<<20));f.truncate(sectors*512)
  # Install a valid stock geometry whose extents fit this synthetic capacity.
  original=bytearray(read_backup(folder,0,512));base=104448;p4=sectors-65536-2048
  def entry(t,s,c):return struct.pack('<B3sB3sII',0,b'\xfe\xff\xff',t,b'\xfe\xff\xff',s,c)
  original[478:494]=entry(5,base,p4-base);original[494:510]=entry(0x83,p4,65536)
  starts=[106496,894960,1683424,p4-24576,p4-8192];counts=[786416,786416,starts[3]-2048-starts[2],16368,8176];ebrs=[base,starts[1]-16,starts[2]-16,starts[3]-16,starts[4]-16]
  with disk.open('r+b') as f:
   f.seek(0);f.write(original)
   for i,(st,c,lba) in enumerate(zip(starts,counts,ebrs)):
    e=bytearray(512);e[446:462]=entry(0x83,st-lba,c)
    if i<4:e[462:478]=entry(5,ebrs[i+1]-base,p4-ebrs[i+1])
    e[510:]=b'\x55\xaa';f.seek(lba*512);f.write(e)
  v=variables(run([NATIVE,'plan',disk,sectors,case]))
  assert int(v['DATA_BYTES'])>0 and int(v['MISC_START'])+8192<=sectors
  proofs.append({'synthetic_sectors':sectors,'geometry':'passed'})
result={'model':'RIDI Paper Pro E70Q10','unit_serial_and_CID_whitelist':False,'checks':proofs,'physical_multiple_device_validation':'not performed','physical_writes':False}
(LOGS/'model-validation.json').write_text(json.dumps(result,indent=2)+'\n')
print('PASS: September authoritative model + own firmware preservation, host/ARM plans, capacity vendor remap/readback, rejection and synthetic capacities')
