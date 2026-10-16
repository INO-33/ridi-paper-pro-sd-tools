#!/usr/bin/env python3
import pathlib as P, subprocess as S, hashlib as H, json, struct, gzip, shutil, os
ROOT=P.Path('/home/juwon/ridi'); SRC=ROOT/'porting/e70q10/emmc-installer'
OUT=ROOT/'deliverables/e70q10-emmc-android8-20261001'; OUT.mkdir(exist_ok=True)
WORK=OUT/'.build'
if WORK.exists():shutil.rmtree(WORK)
WORK.mkdir()
PRODUCT=P.Path('/media/juwon/build/android-out/e70q10_reference_agl_stockpath/target/product/e70q10')
HOST=PRODUCT.parents[2]/'host/linux-x86/bin'
BACK=P.Path('/media/juwon/build/리디백업/backups/e70q10-PP1A1GK166561-20260923-full-emmc')
TABLE=ROOT/'deliverables/emmc-20261001-final-partition-table'
layout=json.loads((ROOT/'porting/e70q10/EMMC_ANDROID8_FINAL_LAYOUT.json').read_text())
parts={x['role']:x for x in layout['partitions']}
def run(args,**kw): S.run(list(map(str,args)),check=True,**kw)
def sha(p):
 h=H.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(4<<20),b''):h.update(b)
 return h.hexdigest()
def rangehash(off,size):
 h=H.sha256()
 while size:
  i,at=divmod(off,256<<20); n=min(size,(256<<20)-at)
  with open(BACK/f'emmc.part{i:02d}','rb') as f:
   f.seek(at)
   while n:
    b=f.read(min(n,4<<20)); assert b;h.update(b);off+=len(b);size-=len(b);n-=len(b)
 return h.hexdigest()
def packboot(kernel,ramdisk,header,path):
 page=struct.unpack_from('<I',header,36)[0]
 hdr=bytearray(header[:page]);struct.pack_into('<I',hdr,8,len(kernel));struct.pack_into('<I',hdr,16,len(ramdisk));struct.pack_into('<I',hdr,24,0)
 digest=H.sha1()
 for data in (kernel,ramdisk,b''):digest.update(data);digest.update(struct.pack('<I',len(data)))
 hdr[576:608]=digest.digest()+b'\0'*12
 with open(path,'wb') as f:
  f.write(hdr)
  for data in (kernel,ramdisk):f.write(data);f.write(b'\0'*((-len(data))%page))
def cpio(root,out):
 names=sorted(str(p.relative_to(root)) for p in root.rglob('*'))
 proc=S.run(['cpio','-o','-H','newc','--owner=0:0','--null'],cwd=root,input=('\0'.join(['.']+names)+'\0').encode(),stdout=S.PIPE,check=True)
 out.write_bytes(gzip.compress(proc.stdout,compresslevel=9,mtime=0))
sources={}
for name in ('boot.img','system.img','vendor.img'):
 p=PRODUCT/name;before=sha(p);shutil.copyfile(p,WORK/name);assert before==sha(p)==sha(WORK/name);sources[name]={'sha256':before,'mtime':p.stat().st_mtime,'bytes':p.stat().st_size}
boot=(WORK/'boot.img').read_bytes();assert boot[:8]==b'ANDROID!'
ks,ka,rs,ra,ss,sa,tags,page=struct.unpack_from('<8I',boot,8)
k=boot[page:page+ks];rp=page+((ks+page-1)//page)*page;r=boot[rp:rp+rs];sp=rp+((rs+page-1)//page)*page;dtb=boot[sp:sp+ss]
assert dtb[:4]==b'\xd0\x0d\xfe\xed' and ss>0
kernel=k+dtb
ram=WORK/'android-root';ram.mkdir(exist_ok=True)
run(['cpio','-idmu','--no-absolute-filenames'],cwd=ram,input=gzip.decompress(r),stdout=S.DEVNULL)
fstab=ram/'fstab.E70Q10';text=fstab.read_text();text=text.replace('mmcblk1p2','mmcblk0p5').replace('mmcblk1p3','mmcblk0p8').replace('mmcblk1p4','mmcblk0p7')
text=text.replace('# External SD layout used only by the E70Q10 Android 8 bring-up image.\n# Internal eMMC is /dev/block/mmcblk0 and is intentionally absent.','# Internal eMMC installation layout e70q10-emmc-v1.')
text+='\n/dev/block/mmcblk0p6 /cache ext4 noatime,nosuid,nodev wait,check\n'
# DT usdhc2 is external microSD; never expose the internal eMMC to vold.
sd_entry='/devices/*/2194000.usdhc/mmc_host/mmc*/*/block/mmcblk* auto auto defaults voldmanaged=extsd:auto'
if sd_entry not in text:text+='\n# Removable microSD managed by Android vold.\n'+sd_entry+'\n'
assert '/dev/block/mmcblk1' not in text and text.splitlines().count(sd_entry)==1
fstab.write_text(text)
init=ram/'init.E70Q10.rc';text=init.read_text().replace('    wait /dev/block/mmcblk1p1\n','').replace('    mount vfat /dev/block/mmcblk1p1 /e70log rw noatime nosuid nodev','    mount tmpfs tmpfs /e70log mode=0770,size=8m,nosuid,nodev')
text=text.replace('# Only external SD partitions are present in this fstab.','# Mount the internal eMMC partitions.').replace('# external SD is mounted and skips the default late import.','# eMMC is mounted and skips the default late import.')
text=text.replace('on property:sys.boot_completed=1\n','on property:sys.boot_completed=1\n    mkdir /data/ridi/logs/install-boot 0700 root root\n    copy /e70log/ridi-dev/logs/android8-current/cmdline.txt /data/ridi/logs/install-boot/cmdline.txt\n    copy /proc/mounts /data/ridi/logs/install-boot/mounts.txt\n')
init.write_text(text)
shutil.copyfile(fstab,OUT/'fstab.E70Q10.emmc');shutil.copyfile(init,OUT/'init.E70Q10.emmc.rc')
cpio(ram,WORK/'android-ramdisk.gz');packboot(kernel,(WORK/'android-ramdisk.gz').read_bytes(),boot,OUT/'boot-emmc.img')
shutil.copyfile(OUT/'boot-emmc.img',WORK/'boot.raw')
with open(WORK/'boot.raw','ab') as f:f.truncate(parts['boot']['bytes'])
rows=[]
def add(raw,name,start,kind='image'):
 size=raw.stat().st_size;assert size%512==0
 gz=OUT/(name+'.gz')
 with open(raw,'rb') as i,open(gz,'wb') as o:
  with gzip.GzipFile(filename='',fileobj=o,mode='wb',mtime=0,compresslevel=1) as z:shutil.copyfileobj(i,z,4<<20)
 rows.append((kind,gz.name,start,size//512,sha(raw),sha(gz)))
for name in ('system','vendor'):
 raw=WORK/(name+'.raw');run([HOST/'simg2img',WORK/(name+'.img'),raw])
 if name=='system':
  rc=S.run(['e2fsck','-fy',str(raw)],stdout=S.DEVNULL).returncode
  assert rc in (0,1), f'e2fsck failed: {rc}'
  run(['resize2fs',raw,str(parts[name]['bytes']//4096)],stdout=S.DEVNULL)
 assert raw.stat().st_size==parts[name]['bytes']
 if name=='vendor':assert raw.read_bytes()[:512]==b'\0'*512
 rc=S.run(['e2fsck','-fy',str(raw)],stdout=S.DEVNULL).returncode
 assert rc in (0,1)
 assert S.run(['e2fsck','-fn',str(raw)],stdout=S.DEVNULL).returncode==0
 add(raw,name+'.raw',parts[name]['start'])
for name in ('cache','userdata'):
 raw=WORK/(name+'.raw')
 # Android's own ext4 formatter avoids modern-host ext4 feature incompatibilities.
 run([HOST/'make_ext4fs','-l',str(parts[name]['bytes']),'-a','data' if name=='userdata' else 'cache',raw],stdout=S.DEVNULL)
 rc=S.run(['e2fsck','-fy',str(raw)],stdout=S.DEVNULL).returncode
 assert rc in (0,1)
 assert S.run(['e2fsck','-fn',str(raw)],stdout=S.DEVNULL).returncode==0
 add(raw,name+'.raw',parts[name]['start'])
misc=WORK/'misc.raw'
with open(BACK/'emmc.part14','rb') as i: # original misc crosses the part14/part15 boundary: use general extraction below
 pass
off=7643891*512;size=4186112
with open(misc,'wb') as o:
 while size:
  idx,at=divmod(off,256<<20);n=min(size,(256<<20)-at)
  with open(BACK/f'emmc.part{idx:02d}','rb') as i:i.seek(at);o.write(i.read(n))
  off+=n;size-=n
 o.truncate(parts['misc']['bytes'])
add(misc,'misc.raw',parts['misc']['start']);add(WORK/'boot.raw','boot.raw',parts['boot']['start'])
for sector in layout['ebr_sectors']:add(TABLE/f'ebr.sector{sector}.bin',f'ebr.sector{sector}.bin',sector,'table')
add(TABLE/'mbr.sector0.bin','mbr.sector0.bin',0,'table')
(OUT/'manifest.tsv').write_text(''.join(' '.join(map(str,row))+'\n' for row in rows))
shutil.copyfile(TABLE/'original-mbr.sector0.bin',OUT/'original-mbr.sector0.bin')
shutil.copyfile(BACK/'SHA256SUMS',OUT/'backup.sha256')
installer=(SRC/'installer.sh').read_text()
values={'MANIFEST':sha(OUT/'manifest.tsv'),'PREFIX':rangehash(512,51*1024**2-512),'OLDMBR':sha(OUT/'original-mbr.sector0.bin'),'NEWMBR':sha(TABLE/'mbr.sector0.bin'),'RESTORE':rangehash(51*1024**2,7818182656-51*1024**2),'BACKUP':sha(OUT/'backup.sha256')}
for key,value in values.items():installer=installer.replace('@'+key+'@',value)
assert '@' not in installer
(OUT/'installer.sh').write_text(installer);(OUT/'installer.sh').chmod(0o755)
rr=WORK/'ram-root'
for d in ('bin','dev','proc','sys','run','tmp','mnt/sd','root'): (rr/d).mkdir(parents=True,exist_ok=True)
shutil.copyfile(ROOT/'ridi-paper-pro-stock-4.4.2-20260721/files/system/bin/busybox',rr/'bin/busybox');(rr/'bin/busybox').chmod(0o755)
for name in ('sh','sha256sum','dd','gzip','mkfifo','wc','stat','cut','cat','grep','mkdir','rm','sync','sleep','mount','mdev','ln'):
 (rr/'bin'/name).symlink_to('busybox')
run(['/opt/st/stm32cubeclt_1.18.0/gnu-tools-for-stm32/14.3.1+st.2/bin/arm-none-eabi-gcc','-Os','-marm','-march=armv7-a','-ffreestanding','-fno-builtin','-nostdlib','-static','-Wl,-e,_start,-Ttext=0x10000',SRC/'countbytes.c','-lgcc','-o',rr/'bin/countbytes'])
run(['gcc','-O2','-DHOST',SRC/'countbytes.c','-o',OUT/'countbytes-host'])
shutil.copyfile(OUT/'installer.sh',rr/'bin/installer');(rr/'bin/installer').chmod(0o755)
shutil.copyfile(SRC/'ram-init.sh',rr/'init');(rr/'init').chmod(0o755)
cpio(rr,OUT/'installer-ramdisk.cpio.gz')
header=bytearray(boot);struct.pack_into('<I',header,20,0x84000000)
cmd=b'console=ttymxc0,115200 init=/init loglevel=6 panic=0 androidboot.hardware=E70Q10 mem=1018M'
header[64:576]=cmd+b'\0'*(512-len(cmd));header[608:1632]=b'\0'*1024
packboot(kernel,(OUT/'installer-ramdisk.cpio.gz').read_bytes(),header,OUT/'ram-installer.img')
shutil.copyfile(ROOT/'porting/e70q10/EMMC_ANDROID8_FINAL_LAYOUT.json',OUT/'layout.json')
report={'software_package_built':True,'offline_validation':'pending','physical_validation':'pending','physical_flash_ready':False,'source_images':sources,'pinned_hashes':values,'images':[dict(zip(('kind','file','start_sector','sectors','raw_sha256','compressed_sha256'),row)) for row in rows],'kernel_size':len(kernel),'dtb_appended':True,'second_size':0,'early_logs':'RAM tmpfs /e70log; boot completion snapshot in /data/ridi/logs/install-boot'}
(OUT/'build-report.json').write_text(json.dumps(report,indent=2)+'\n')
(OUT/'SHA256SUMS').write_text(''.join(sha(p)+'  '+p.name+'\n' for p in sorted(OUT.iterdir()) if p.is_file() and p.name!='SHA256SUMS'))
print('PACKAGE BUILT:',OUT)
