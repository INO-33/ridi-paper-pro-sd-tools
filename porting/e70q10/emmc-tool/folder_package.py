"""Portable image-folder package builder. No compiler/Linux executables needed."""
from pathlib import Path
import zipfile,tarfile,tempfile,hashlib,json,gzip,shutil,struct,uuid
from package import sha,sums,safe_name,validate,ORDER,RANGES
from portable_boot import prepare,entries,pack_entries
from portable_images import Image,Ext4

FILES={'ram-updater.img','toolkit.json','build-report.json','compatibility-baseline.json','licenses/sha256-OpenSSL.txt'}

def runtime_seed(path):
 path=Path(path)
 if Path(str(path)+'.sha256').read_text().split()!=[sha(path),path.name]:raise ValueError('RAM 런타임 배포 파일 해시 오류')
 with zipfile.ZipFile(path) as z:
  names=z.namelist()
  if len(names)!=len(set(names)) or set(names)!=FILES|{'SHA256SUMS'}:raise ValueError('RAM 런타임 파일 목록 오류')
  for n in names:safe_name(n)
  if any(z.getinfo(n).file_size>32<<20 for n in names):raise ValueError('RAM 런타임 파일 크기 오류')
  data={n:z.read(n) for n in names};checks=sums(data.pop('SHA256SUMS'))
  if set(checks)!=FILES or any(hashlib.sha256(data[n]).hexdigest()!=checks[n] for n in checks):raise ValueError('RAM 런타임 내부 해시 오류')
 return data

def repack_ram(image,new_manifest,replacements=None):
 page=struct.unpack_from('<I',image,36)[0];ks=struct.unpack_from('<I',image,8)[0];rs=struct.unpack_from('<I',image,16)[0]
 if image[:8]!=b'ANDROID!' or page!=2048:raise ValueError('지원하지 않는 RAM boot 이미지')
 offset=page+((ks+page-1)//page)*page;es=entries(image[offset:offset+rs]);meta=json.loads(es['etc/runtime-sha256.json'][1])
 old=None
 import re
 match=re.search(rb'manifest\) \[ "\$VALUE" = \'([a-f0-9]{64})\'',es['bin/auto-update'][1])
 if match:old=match[1]
 if not old:raise ValueError('RAM 설정 검증기에서 고정 manifest를 찾지 못했습니다')
 for name in ['bin/auto-update','bin/updater','bin/backup-current','bin/initial-install']:
  f,b=es[name];es[name]=(f,b.replace(old,new_manifest.encode()));meta[name]=hashlib.sha256(es[name][1]).hexdigest()
 if replacements:
  for name,b in replacements.items():
   f,_=es[name];es[name]=(f,b);meta[name]=hashlib.sha256(b).hexdigest()
 f,b=es['etc/runtime-sha256.json'];es['etc/runtime-sha256.json']=(f,json.dumps(meta,sort_keys=True).encode())
 # Keep directories before children, matching Linux initramfs unpack rules.
 es=dict(sorted(es.items(),key=lambda x:(0 if x[1][0][1]&0o170000==0o040000 else 1,x[0].count('/'),x[0])))
 rd=pack_entries(es);hdr=bytearray(image[:page]);struct.pack_into('<I',hdr,16,len(rd));kernel=image[page:page+ks];h=hashlib.sha1()
 for data in (kernel,rd,b''):h.update(data);h.update(struct.pack('<I',len(data)))
 hdr[576:608]=h.digest()+bytes(12)
 result=bytes(hdr)+kernel+bytes((-len(kernel))%page)+rd+bytes((-len(rd))%page)
 return result,rd,meta

def build_folder(folder,seed,out,operation='update',selected=ORDER,progress=lambda *a:None,backup_before=None):
 folder=Path(folder).resolve(strict=True);out=Path(out);out.mkdir(parents=True,exist_ok=False)
 data=runtime_seed(seed);baseline=json.loads(data['build-report.json']);rows=[];sources={};filesystems={};inputs={}
 chosen=() if operation=='backup' else tuple(r for r in ORDER if r in selected)
 if operation=='install' and chosen!=ORDER:raise ValueError('업그레이드에는 boot/system/vendor 세 이미지가 필요합니다')
 if operation!='backup' and not chosen:raise ValueError('업데이트할 파티션을 선택하세요')
 for role in chosen:
  f=folder/(role+'.img')
  if not f.is_file():raise ValueError('이미지 폴더에 '+f.name+'가 없습니다')
  st=f.stat();inputs[role]=(f,st.st_size,st.st_mtime_ns)
  sources[role]={'path':str(f),'bytes':st.st_size,'sha256':sha(f)}
 boot=None;release=baseline['compatibility']['boot']['kernel_release']
 if 'boot' in chosen:
  progress('boot-prepare',0,0);boot,release=prepare(inputs['boot'][0].read_bytes())
  if len(boot)>32<<20:raise ValueError('boot 이미지가 32MiB를 초과합니다')
  if 'vendor' not in chosen and release!=baseline['compatibility']['boot']['kernel_release']:raise ValueError('커널 버전이 달라 vendor.img도 함께 선택해야 합니다')
 for role in chosen:
  filename,start,sectors=RANGES[role];size=sectors*512;progress('convert-'+role,0,size);raw_hash=hashlib.sha256();written=0;im=None
  try:
   if role!='boot':
    im=Image(inputs[role][0],size);fs=Ext4(im);filesystems[role]={'filesystem_bytes':fs.bytes,'partition_bytes':size,'clean_ext4':True,'resized':False,'bitmap_padding_normalization':fs.normalize_bitmap_padding()}
    if role=='system':
     props=dict(l.split('=',1) for l in fs.file('/build.prop').decode().splitlines() if '=' in l and not l.startswith('#'))
     if (props.get('ro.build.version.sdk'),props.get('ro.product.device'),props.get('ro.product.cpu.abi'))!=('26','e70q10','armeabi-v7a'):raise ValueError('Paper Pro Android 8 ARM system.img가 아닙니다')
    else:
     if im.read(0,512)!=bytes(512):raise ValueError('vendor 첫 섹터가 legacy BCB와 충돌합니다')
     modules=fs.directory(fs.find('/lib/modules'))
     if '8189fs.ko' not in modules:raise ValueError('vendor Wi-Fi 모듈이 없습니다')
     for n,inode in modules.items():
      if not n.endswith('.ko'):continue
      b=fs.contents(inode)
      if b[:4]!=b'\x7fELF' or len(b)<20 or struct.unpack_from('<H',b,18)[0]!=40:raise ValueError('vendor 모듈은 ARM ELF여야 합니다')
      tag=b.find(b'vermagic=')
      expected=(release+' SMP preempt mod_unload modversions ARMv7 p2v8 ').encode()
      if tag<0 or b[tag+9:].split(b'\0',1)[0]!=expected:raise ValueError('boot/vendor 커널 모듈 ABI가 일치하지 않습니다')
    chunks=im.chunks()
   else:chunks=(boot,)
   with (out/filename).open('wb') as target:
    with gzip.GzipFile(filename='',fileobj=target,mode='wb',compresslevel=1,mtime=0) as gz:
     for chunk in chunks:gz.write(chunk);raw_hash.update(chunk);written+=len(chunk);progress('convert-'+role,written,size)
     while written<size:
      chunk=bytes(min(4<<20,size-written));gz.write(chunk);raw_hash.update(chunk);written+=len(chunk);progress('convert-'+role,written,size)
   rows.append((filename,start,sectors,raw_hash.hexdigest(),sha(out/filename)))
   if role=='boot':(out/'boot-emmc.img').write_bytes(boot)
  finally:
   if im:im.close()
 for role,(f,size,mtime) in inputs.items():
  st=f.stat()
  if (st.st_size,st.st_mtime_ns)!=(size,mtime) or sha(f)!=sources[role]['sha256']:raise ValueError('패키지 준비 중 원본 이미지가 변경됐습니다: '+role)
 manifest=''.join(' '.join(map(str,r))+'\n' for r in rows).encode();mh=hashlib.sha256(manifest).hexdigest();(out/'manifest.tsv').write_bytes(manifest)
 ram,rd,hashes=repack_ram(data['ram-updater.img'],mh);(out/'ram-updater.img').write_bytes(ram);(out/'updater-ramdisk.cpio.gz').write_bytes(rd)
 runtime=entries(rd)
 for n,k in [('updater.sh','bin/updater'),('ram-auto.sh','bin/auto-update'),('ram-backup.sh','bin/backup-current'),('ram-install.sh','bin/initial-install'),('ram-install-test.sh','bin/install-test')]: (out/n).write_bytes(runtime[k][1])
 for n in ('toolkit.json','compatibility-baseline.json','licenses/sha256-OpenSSL.txt'):
  p=out/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data[n])
 baseline.update(source_images=sources,manifest_sha256=mh,runtime_sha256=hashes,portable_filesystems=filesystems,portable_validation='sparse geometry/CRC, clean ext4 metadata, required Android properties, ARM module ABI, boot hashes; no full host fsck',physical_update_validation='pending')
 (out/'build-report.json').write_text(json.dumps(baseline,indent=2)+'\n',encoding='utf-8')
 conf={'format':'5','manifest':mh,'targets':','.join(chosen) or 'none','autostart':'1','reboot':'0' if operation=='backup' else '1','operation':operation,'backup':('required' if (operation in ('backup','install-test') or (backup_before if backup_before is not None else operation=='install')) else 'none'),'job':uuid.uuid4().hex,'userdata':'create' if operation=='install' else 'preserve','partitioning':'create' if operation=='install' else 'preserve','cache':'create' if operation=='install' else 'preserve'}
 (out/'update.conf').write_bytes(''.join(k+'='+v+'\n' for k,v in conf.items()).encode())
 files=sorted(p for p in out.rglob('*') if p.is_file());(out/'SHA256SUMS').write_bytes(''.join(sha(p)+'  '+p.relative_to(out).as_posix()+'\n' for p in files).encode())
 archive=out.with_suffix('.tar')
 with tarfile.open(archive,'w') as t:
  for path in sorted(out.iterdir()):t.add(path,arcname='e70q10-update/'+path.name)
 Path(str(archive)+'.sha256').write_bytes((sha(archive)+'  '+archive.name+'\n').encode())
 progress('validate',0,0);return validate(archive)

def adapt_ready(report,seed,out):
 """Pair validated prepared payloads with the current format5 option runtime."""
 out=Path(out);out.mkdir();data=runtime_seed(seed)
 with tarfile.open(report['path']) as t:
  for n in ('system.raw.gz','vendor.raw.gz','boot.raw.gz','boot-emmc.img','manifest.tsv'):
   if n in report['members']:
    with t.extractfile(report['members'][n]) as f,(out/n).open('wb') as o:shutil.copyfileobj(f,o,4<<20)
  old_report=json.loads(t.extractfile(report['members']['build-report.json']).read()) if 'build-report.json' in report['members'] else {}
 mh=report['manifest'];ram,rd,hashes=repack_ram(data['ram-updater.img'],mh);(out/'ram-updater.img').write_bytes(ram);(out/'updater-ramdisk.cpio.gz').write_bytes(rd);es=entries(rd)
 for n,k in [('updater.sh','bin/updater'),('ram-auto.sh','bin/auto-update'),('ram-backup.sh','bin/backup-current'),('ram-install.sh','bin/initial-install'),('ram-install-test.sh','bin/install-test')]: (out/n).write_bytes(es[k][1])
 for n in ('toolkit.json','compatibility-baseline.json','licenses/sha256-OpenSSL.txt'):
  p=out/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data[n])
 old_report.update(manifest_sha256=mh,runtime_sha256=hashes);(out/'build-report.json').write_text(json.dumps(old_report,indent=2),encoding='utf-8')
 conf=dict(report['config']);conf.update(format='5',operation='update',backup='none',job=uuid.uuid4().hex,userdata='preserve',partitioning='preserve',cache='preserve')
 (out/'update.conf').write_bytes(''.join(k+'='+v+'\n' for k,v in conf.items()).encode())
 files=sorted(p for p in out.rglob('*') if p.is_file());(out/'SHA256SUMS').write_bytes(''.join(sha(p)+'  '+p.relative_to(out).as_posix()+'\n' for p in files).encode())
 archive=out.with_suffix('.tar')
 with tarfile.open(archive,'w') as t:
  for p in sorted(out.iterdir()):t.add(p,arcname='e70q10-update/'+p.name)
 Path(str(archive)+'.sha256').write_text(sha(archive)+'  '+archive.name+'\n')
 return validate(archive)
