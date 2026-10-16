#!/usr/bin/env python3
"""Freeze boot/system/vendor, check target boot/module compatibility, make a pinned RAM updater."""
from boot_image import prepare
from selection import targets,control
import argparse,gzip,hashlib,json,os,pathlib as P,shutil,struct,subprocess as S
ROOT=P.Path(os.environ.get('RIDI_WORKSPACE', P.Path(__file__).resolve().parents[3]));SRC=ROOT/'porting/e70q10/emmc-updater';ASSETS=SRC/'assets';TABLE=ASSETS/'tables'
PRODUCT=P.Path(os.environ.get('RIDI_PRODUCT_OUT', ROOT/'android-out/e70q10/target/product/e70q10'));HOST=PRODUCT.parents[2]/'host/linux-x86/bin'
p=argparse.ArgumentParser();p.add_argument('--targets',default='all');p.add_argument('--manual',action='store_true');p.add_argument('--no-reboot',action='store_true');p.add_argument('--boot',type=P.Path,default=PRODUCT/'boot.img');p.add_argument('--system',type=P.Path,default=PRODUCT/'system.img');p.add_argument('--vendor',type=P.Path,default=PRODUCT/'vendor.img');p.add_argument('--out',type=P.Path,default=ROOT/'deliverables/e70q10-emmc-update-20261001-boot');a=p.parse_args()
from runtime_assets import verify_assets
verify_assets(ASSETS)
selected=targets(a.targets)
OUT=a.out.resolve()
if OUT.exists() and any(OUT.iterdir()):raise SystemExit('Output exists: choose a new --out directory.')
OUT.mkdir(parents=True,exist_ok=True);WORK=OUT/'.build';WORK.mkdir()
baseline=json.loads((SRC/'compatibility-baseline.json').read_text())
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(4<<20),b''):h.update(b)
 return h.hexdigest()
def run(args,**kw):return S.run(list(map(str,args)),check=True,**kw)
def fsck(raw):
 rc=S.run(['e2fsck','-fy',str(raw)],stdout=S.DEVNULL).returncode
 assert rc in (0,1),f'Filesystem error {raw}: {rc}'
 assert S.run(['e2fsck','-fn',str(raw)],stdout=S.DEVNULL).returncode==0
sources={};rows=[];compat={}
frozen=WORK/'boot.input';h=sha(a.boot);shutil.copyfile(a.boot,frozen);assert sha(a.boot)==sha(frozen)==h,'Boot source changed during copy'
sources['boot']={'path':str(a.boot.resolve()),'sha256':h,'bytes':frozen.stat().st_size}
boot,release=prepare(frozen.read_bytes());assert len(boot)<=33554432,'Boot exceeds p1'
if 'boot' in selected:(OUT/'boot-emmc.img').write_bytes(boot)
(WORK/'boot.raw').write_bytes(boot+bytes(33554432-len(boot)))
compat['boot']={'kernel_release':release,'dtb_appended':True,'second_size':0,'emmc_fstab':True}

for name,path,start,size in [('system',a.system,172032,1073741824),('vendor',a.vendor,14733312,268435456)]:
 if name not in selected:continue
 frozen=WORK/(name+'.input');h=sha(path);shutil.copyfile(path,frozen);assert sha(path)==sha(frozen)==h,'Source changed during copy'
 sources[name]={'path':str(path.resolve()),'sha256':h,'bytes':frozen.stat().st_size}
 raw=WORK/(name+'.raw')
 with open(frozen,'rb') as f:magic=f.read(4)
 if magic==struct.pack('<I',0xed26ff3a):run([HOST/'simg2img',frozen,raw])
 else:shutil.copyfile(frozen,raw)
 assert raw.stat().st_size<=size,f'{name} exceeds fixed partition size'
 fsck(raw)
 if raw.stat().st_size<size:
  run(['resize2fs',raw,str(size//4096)],stdout=S.DEVNULL);fsck(raw)
 assert raw.stat().st_size==size
 if name=='system':
  prop=S.check_output(['debugfs','-R','cat /build.prop',str(raw)],stderr=S.DEVNULL).decode()
  props=dict(line.split('=',1) for line in prop.splitlines() if '=' in line and not line.startswith('#'))
  assert props.get('ro.build.version.sdk')=='26','Requires Android 8.0/API26'
  assert props.get('ro.product.device')=='e70q10','Wrong device'
  assert props.get('ro.product.cpu.abi')=='armeabi-v7a','Wrong ABI'
  compat['system']={k:props.get(k) for k in ['ro.build.version.release','ro.product.cpu.abi','ro.product.device','ro.build.fingerprint']}
 else:
  with open(raw,'rb') as f:assert f.read(512)==bytes(512),'Vendor legacy BCB sector must be zero'
  listing=S.check_output(['debugfs','-R','ls -p /lib/modules',str(raw)],stderr=S.DEVNULL).decode()
  modules=[line.split('/')[5] for line in listing.splitlines() if line.startswith('/') and len(line.split('/'))>6 and line.split('/')[5].endswith('.ko')]
  assert '8189fs.ko' in modules,'Wi-Fi module missing'
  compat['modules']={}
  for module in modules:
   data=S.check_output(['debugfs','-R','cat /lib/modules/'+module,str(raw)],stderr=S.DEVNULL)
   assert data[:4]==b'\x7fELF' and struct.unpack_from('<H',data,18)[0]==40,'Module must be ARM ELF'
   idx=data.index(b'vermagic=')+9;vermagic=data[idx:].split(b'\0',1)[0].decode()
   assert vermagic==release+' SMP preempt mod_unload modversions ARMv7 p2v8 ',f'Kernel ABI mismatch: {module}: {vermagic}'
   compat['modules'][module]={'vermagic':vermagic,'sha256':hashlib.sha256(data).hexdigest()}
 gz=OUT/(name+'.raw.gz')
 with open(raw,'rb') as f,open(gz,'wb') as o:
  with gzip.GzipFile(filename='',fileobj=o,mode='wb',compresslevel=1,mtime=0) as z:shutil.copyfileobj(f,z,4<<20)
 rows.append((gz.name,start,size//512,sha(raw),sha(gz)))
if 'boot' in selected:
 raw=WORK/'boot.raw';gz=OUT/'boot.raw.gz'
 with raw.open('rb') as f,gz.open('wb') as o:
  with gzip.GzipFile(filename='',fileobj=o,mode='wb',compresslevel=1,mtime=0) as z:shutil.copyfileobj(f,z,4<<20)
 rows.append((gz.name,104448,65536,sha(raw),sha(gz)))
(OUT/'manifest.tsv').write_text(''.join(' '.join(map(str,row))+'\n' for row in rows))
(OUT/'update.conf').write_bytes(control(sha(OUT/'manifest.tsv'),selected,not a.manual,not a.no_reboot))
checks=[]
for name,sector in [('mbr.sector0.bin',0)]+[(f'ebr.sector{x}.bin',x) for x in [169984,2269184,2402304,14731264,15257600]]:
 checks.append(f'    [ "$(rangehash 512 {sector} 1)" = {sha(TABLE/name)} ] || fail "layout mismatch at sector {sector}"')
functions=(SRC/'config-functions.sh').read_text()
script=(SRC/'updater.sh').read_text().replace('@CONFIG_FUNCTIONS@',functions).replace('@MANIFEST@',sha(OUT/'manifest.tsv')).replace('@TABLE_CHECKS@','\n'.join(checks));assert '@' not in script
(OUT/'updater.sh').write_text(script);(OUT/'updater.sh').chmod(0o755)
auto=(SRC/'auto-update.sh').read_text().replace('@CONFIG_FUNCTIONS@',functions).replace('@MANIFEST@',sha(OUT/'manifest.tsv'));assert '@' not in auto
(OUT/'auto-update.sh').write_text(auto);(OUT/'auto-update.sh').chmod(0o755)
ram=WORK/'ram-root'
for d in ['bin','dev','proc','sys','run','tmp','mnt/sd','root']:(ram/d).mkdir(parents=True,exist_ok=True)
run(['/opt/st/stm32cubeclt_1.18.0/gnu-tools-for-stm32/14.3.1+st.2/bin/arm-none-eabi-gcc','-Os','-marm','-march=armv7-a','-ffreestanding','-fno-builtin','-nostdlib','-static','-Wl,-e,_start,-Ttext=0x10000',SRC/'console-shell.c','-o',ram/'bin/console-shell'])
shutil.copy2(ASSETS/'busybox-arm',ram/'bin/busybox');shutil.copy2(ASSETS/'countbytes-arm',ram/'bin/countbytes');shutil.copy2(ASSETS/'countbytes-host',OUT/'countbytes-host')
shutil.copy2(OUT/'auto-update.sh',ram/'bin/auto-update');shutil.copy2(OUT/'updater.sh',ram/'bin/updater');shutil.copy2(SRC/'ram-init.sh',ram/'init');(ram/'bin/countbytes').chmod(0o755);(ram/'init').chmod(0o755)
for applet in ['sh','cat','ls','dd','sha256sum','gzip','cut','stat','wc','mkfifo','mkdir','rmdir','rm','sync','sleep','mount','mdev','ln','ps','stty']:(ram/'bin'/applet).symlink_to('busybox')
names=['.']+sorted(str(x.relative_to(ram)) for x in ram.rglob('*'))
cpio=S.run(['cpio','-o','-H','newc','--owner=0:0','--null'],cwd=ram,input=('\0'.join(names)+'\0').encode(),stdout=S.PIPE,check=True).stdout
rd=gzip.compress(cpio,compresslevel=9,mtime=0);(OUT/'updater-ramdisk.cpio.gz').write_bytes(rd)
kernel=(ASSETS/'ram-kernel.bin').read_bytes();hdr=bytearray((ASSETS/'ram-header.bin').read_bytes());page=struct.unpack_from('<I',hdr,36)[0];struct.pack_into('<I',hdr,8,len(kernel));struct.pack_into('<I',hdr,16,len(rd))
h=hashlib.sha1()
for data in [kernel,rd,b'']:h.update(data);h.update(struct.pack('<I',len(data)))
hdr[576:608]=h.digest()+bytes(12)
with open(OUT/'ram-updater.img','wb') as f:
 f.write(hdr)
 for data in [kernel,rd]:f.write(data);f.write(bytes((-len(data))%page))
shutil.copy2(SRC/'compatibility-baseline.json',OUT/'compatibility-baseline.json')
for name in ['README.md','boot_ram_updater.sh','prepare_update_sd.sh','format_prepare_update_sd.sh','validate_package.py','selection.py']:
 if (SRC/name).exists():shutil.copy2(SRC/name,OUT/name)
report={'package_type':'selected-partition-auto-update','targets':selected,'automatic':not a.manual,'automatic_reboot':not a.no_reboot,'source_images':sources,'compatibility':compat,'target_boot_raw_sha256':sha(WORK/'boot.raw') if 'boot' in selected else None,'manifest_sha256':sha(OUT/'manifest.tsv'),'update_ranges':[{'file':row[0],'start_sector':row[1],'sectors':row[2],'raw_sha256':row[3],'compressed_sha256':row[4]} for row in rows],'ram_kernel_sha256':hashlib.sha256(kernel).hexdigest(),'offline_validation':'pending','physical_update_validation':'not performed','same_source_images_as_initial_install':None,'runtime_assets':'source-owned assets verified before conversion'}
for info in sources.values():assert sha(info['path'])==info['sha256'],'Input changed during package build; regenerate from completed build'
(OUT/'build-report.json').write_text(json.dumps(report,indent=2)+'\n')
print('BUILT',OUT)
