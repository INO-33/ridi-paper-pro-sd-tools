#!/usr/bin/env python3
"""Release-side Linux builder: extend a frozen updater directory with install runtime."""
from pathlib import Path
import argparse,sys,json,shutil,subprocess,re,struct,hashlib,gzip,tarfile,stat,uuid
SRC=Path(__file__).resolve().parent
UPDATER=SRC.parent/'emmc-updater'
sys.path.insert(0,str(UPDATER))
from boot_image import entries,pack_entries
from runtime_assets import verify_assets
p=argparse.ArgumentParser();p.add_argument('base',type=Path);p.add_argument('--out',type=Path,required=True);p.add_argument('--operation',choices=['install','install-test','update','backup'],default='install-test');p.add_argument('--product',type=Path,default=Path('/media/juwon/build/android-out/e70q10_reference_agl_stockpath/target/product/e70q10'));a=p.parse_args()
sys.path.remove(str(UPDATER));sys.path.insert(0,str(SRC));from package import sha,validate,ORDER
verify_assets(UPDATER/'assets')
base=a.base.resolve();out=a.out.resolve()
if out.exists():raise SystemExit('Choose a new output directory')
rows=[r.split() for r in (base/'manifest.tsv').read_text().splitlines()]
if [r[0] for r in rows]!=['system.raw.gz','vendor.raw.gz','boot.raw.gz']:raise SystemExit('Full base package required')
# Verify all frozen payloads; source changes cannot be hidden by rebuilding sums.
for row in rows:
 if sha(base/row[0])!=row[4]:raise SystemExit('Base payload changed')
for n in ['ram-updater.img','updater-ramdisk.cpio.gz','updater.sh','manifest.tsv','compatibility-baseline.json','build-report.json']:
 if not (base/n).is_file():raise SystemExit('Missing base runtime: '+n)
report=json.loads((base/'build-report.json').read_text())
if sha(base/'manifest.tsv')!=report['manifest_sha256']:raise SystemExit('Base manifest changed')
image=(base/'ram-updater.img').read_bytes();page=struct.unpack_from('<I',image,36)[0];ks=struct.unpack_from('<I',image,8)[0];rs=struct.unpack_from('<I',image,16)[0];off=page+((ks+page-1)//page)*page
rd=image[off:off+rs]
if rd!=(base/'updater-ramdisk.cpio.gz').read_bytes():raise SystemExit('Base RAM ramdisk differs')
es=entries(rd)
if es['bin/updater'][1]!=(base/'updater.sh').read_bytes():raise SystemExit('Base RAM writer differs')
out.mkdir(parents=True)
for n in ['system.raw.gz','vendor.raw.gz','boot.raw.gz','boot-emmc.img','manifest.tsv','updater.sh','compatibility-baseline.json']:
 if (base/n).exists():shutil.copy2(base/n,out/n)
baseline=json.loads((out/'compatibility-baseline.json').read_text());baseline.pop('device_serial',None);baseline.pop('cid',None);baseline['device_model']='RIDI Paper Pro E70Q10';(out/'compatibility-baseline.json').write_text(json.dumps(baseline,indent=2)+'\n')
mh=sha(out/'manifest.tsv')
policy='create' if a.operation=='install' else 'preserve'
backup='none' if a.operation=='update' else 'required'
cache='preserve' if a.operation in ('update','backup') else 'create'
(out/'update.conf').write_text(f'format=4\nmanifest={mh}\ntargets={"none" if a.operation=="backup" else "system,vendor,boot"}\nautostart=1\nreboot={0 if a.operation=="backup" else 1}\noperation={a.operation}\nbackup={backup}\njob={uuid.uuid4().hex}\nuserdata={policy}\npartitioning={policy}\ncache={cache}\n')
toolkit={'schema':4,'operations':['install','install-test','update','backup'],'layout':'e70q10-emmc-capacity-v2','model':'RIDI Paper Pro E70Q10','device_selection':'model-checked-in-ram','capacity_sector_bounds':[14680064,33554432],'backup_space_check':'actual eMMC capacity in RAM','userarea_bytes':7818182656,'minimum_sd_nominal_gb':16,'userdata':'created-in-ram','cache':'created-in-ram','backup':'raw-256MiB-chunks-before-install','community_release_ready':False,'physical_validation':'not performed','stock_layout_authority':'20260923 full-emmc; July copy is not stock-layout evidence','install_test':'fresh full backup then cache creation + image writes; userdata/misc/table byte checks','image_validation':'PC gzip CRC + compressed/raw SHA256 + exact size; device bounded streaming write and readback only'}
(out/'toolkit.json').write_text(json.dumps(toolkit,indent=2)+'\n')
ino=max(f[0] for f,_ in es.values())+1
runtime_hashes={}
def add(name,data,mode=0o100755):
 global ino
 es[name]=([ino,mode,0,0,1,0,len(data),0,0,0,0,len(name)+1,0],data);ino+=1
 runtime_hashes[name]=hashlib.sha256(data).hexdigest()
 for parent in reversed(Path(name).parents):
  s=str(parent)
  if s!='.' and s not in es:
   es[s]=([ino,0o040755,0,0,2,0,0,0,0,0,0,len(s)+1,0],b'');ino+=1
control=(SRC/'ram-control.sh').read_text().replace('@MANIFEST@',mh)
auto=(SRC/'ram-auto.sh').read_text().replace('@CONTROL@',control)
installer=(SRC/'ram-install.sh').read_text().replace('@MANIFEST@',mh)
writer=(SRC/'ram-writer.sh').read_text().replace('@CONFIG_FUNCTIONS@',(UPDATER/'config-functions.sh').read_text()).replace('@MANIFEST@',mh)
assert '@CONFIG_FUNCTIONS@' not in writer and '@MANIFEST@' not in writer
(out/'updater.sh').write_text(writer)
add('bin/updater',writer.encode())
native=out/'.native';native.mkdir()
cc='/opt/st/stm32cubeclt_1.18.0/gnu-tools-for-stm32/14.3.1+st.2/bin/arm-none-eabi-gcc'
subprocess.run([cc,'-Os','-marm','-march=armv7-a','-ffreestanding','-fno-builtin','-nostdlib','-static','-Wl,-e,_start,-Ttext=0x10000',str(SRC/'device_layout.c'),'-lgcc','-o',str(native/'device-layout-arm')],check=True)
subprocess.run(['gcc','-DHOST','-O2',str(SRC/'device_layout.c'),'-o',str(native/'device-layout-host')],check=True)
add('bin/device-layout',(native/'device-layout-arm').read_bytes())
subprocess.run([cc,'-O2','-marm','-march=armv7-a','-ffreestanding','-fno-builtin','-nostdlib','-static','-Wl,-e,_start,-Ttext=0x10000',str(SRC/'stream_write.c'),'-lgcc','-o',str(native/'stream-write-arm')],check=True)
subprocess.run(['gcc','-DHOST','-O2',str(SRC/'stream_write.c'),'-o',str(native/'stream-write-host')],check=True)
add('bin/stream-write',(native/'stream-write-arm').read_bytes())
subprocess.run([cc,'-O2','-marm','-march=armv7-a','-ffreestanding','-fno-builtin','-nostdlib','-static','-Wl,-e,_start,-Ttext=0x10000',str(SRC/'backup_copy.c'),str(SRC/'vendor/sha256/sha256-armv4.S'),'-D__KERNEL__','-D__LINUX_ARM_ARCH__=7','-lgcc','-o',str(native/'backup-copy-arm')],check=True)
subprocess.run(['gcc','-DHOST','-O2',str(SRC/'backup_copy.c'),'-o',str(native/'backup-copy-host')],check=True)
add('bin/backup-copy',(native/'backup-copy-arm').read_bytes())
subprocess.run([cc,'-O2','-marm','-march=armv7-a','-ffreestanding','-fno-builtin','-nostdlib','-static','-Wl,-e,_start,-Ttext=0x10000',str(SRC/'eink_ui.c'),'-lgcc','-o',str(native/'eink-ui-arm')],check=True)
subprocess.run(['gcc','-DHOST','-O2',str(SRC/'eink_ui.c'),'-o',str(native/'eink-ui-host')],check=True)
subprocess.run([sys.executable,str(SRC/'render_ui_assets.py'),str(native/'updater-ui.bin')],check=True)
add('bin/eink-ui',(native/'eink-ui-arm').read_bytes())
subprocess.run([cc,'-O2','-marm','-march=armv7-a','-ffreestanding','-fno-builtin','-nostdlib','-static','-Wl,-e,_start,-Ttext=0x10000',str(SRC/'waveform_extract.c'),'-lgcc','-o',str(native/'waveform-extract-arm')],check=True)
add('bin/waveform-extract',(native/'waveform-extract-arm').read_bytes())
add('bin/ui-status',(SRC/'ui-status.sh').read_bytes())
add('etc/updater-ui.bin',(native/'updater-ui.bin').read_bytes(),0o100644)
# Give each RAM USB gadget its actual eMMC identity, avoiding a shared serial.
init=es['init'][1].decode().replace('echo PP1A1GK166561 >', 'echo "$($bb cat /sys/block/mmcblk0/device/cid)" >')
# Attach the RAM-only display observer before auto-update starts. Never touch Android graphics.
if '/bin/eink-ui' not in init:
 init=init.replace('# The worker logs', "# RAM-only updater screen; failure falls back to USB/SD logs.\nfor V in /sys/class/vtconsole/*; do $bb grep -q 'frame buffer' \"$V/name\" && echo 0 >\"$V/bind\"; done\n/bin/eink-ui >/run/eink-ui.log 2>&1 &\n# The worker logs")
if '/bin/waveform-extract' not in init:
 init=init.replace('/bin/eink-ui >/run/eink-ui.log', '$bb mkdir -p /lib/firmware/imx/epdc\n/bin/waveform-extract >/run/waveform-extract.log 2>&1 || echo \"Waveform unavailable; USB/SD logs remain active\"\n/bin/eink-ui >/run/eink-ui.log')
add('init',init.encode())
for name,text in [('bin/auto-update',auto),('bin/initial-install',installer),('bin/backup-current',(SRC/'ram-backup.sh').read_text().replace('@MANIFEST@',mh)),('bin/install-test',(SRC/'ram-install-test.sh').read_text())]:add(name,text.encode())
# Tables are generated from this device's MBR and capacity by the native verifier.
for name in list(es):
 if name.startswith('etc/layout/'):del es[name]
# Resolve the exact Android ARM formatter and checker dependency closure.
product=a.product.resolve();queue=['system/bin/linker','system/bin/make_ext4fs','system/bin/e2fsck'];seen=set()
while queue:
 name=queue.pop()
 if name in seen:continue
 seen.add(name);path=product/name
 if not path.is_file():raise SystemExit('Missing Android runtime: '+str(path))
 data=path.read_bytes()
 if data[:4]!=b'\x7fELF' or struct.unpack_from('<H',data,18)[0]!=40:raise SystemExit('Non-ARM runtime: '+name)
 add(name,data,0o100755 if name.startswith('system/bin') else 0o100644)
 dynamic=subprocess.check_output(['readelf','-d',str(path)],text=True)
 queue += ['system/lib/'+lib for lib in re.findall(r'Shared library: \[([^\]]+)\]',dynamic)]
contexts=(product/'root/plat_file_contexts').read_bytes()+b'\n'+(product/'root/nonplat_file_contexts').read_bytes()+b'\n'
add('etc/file_contexts',contexts,0o100644)
# Record RAM assets inside the image and export the tools for ARM offline verification.
ramtools=out/'.ram-tools'
for n in seen|{'etc/file_contexts'}:
 target=ramtools/n;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(es[n][1]);target.chmod(0o755)
add('etc/runtime-sha256.json',json.dumps(runtime_hashes,sort_keys=True).encode(),0o100644)
# Kernel initramfs unpacker does not create missing parent directories for files.
es=dict(sorted(es.items(),key=lambda item: (0 if item[1][0][1]&0o170000==0o040000 else 1,item[0].count('/'),item[0])))
created={'.'}
for name,(fields,content) in es.items():
 if name=='.':continue
 assert str(Path(name).parent) in created, 'RAM parent missing before entry: '+name
 if fields[1]&0o170000==0o040000:created.add(name)
rd=pack_entries(es);(out/'updater-ramdisk.cpio.gz').write_bytes(rd)
hdr=bytearray(image[:page]);kernel=image[page:page+ks]
struct.pack_into('<I',hdr,16,len(rd));h=hashlib.sha1()
for data in [kernel,rd,b'']:h.update(data);h.update(struct.pack('<I',len(data)))
hdr[576:608]=h.digest()+bytes(12)
with (out/'ram-updater.img').open('wb') as f:
 f.write(hdr)
 for data in [kernel,rd]:f.write(data);f.write(bytes((-len(data))%page))
(out/'ram-auto.sh').write_text(auto);(out/'ram-install.sh').write_text(installer)
(out/'ram-backup.sh').write_bytes(es['bin/backup-current'][1])
(out/'ram-install-test.sh').write_bytes(es['bin/install-test'][1])
(out/'licenses').mkdir()
shutil.copy2(SRC/'vendor/sha256/LICENSE',out/'licenses/sha256-OpenSSL.txt')
shutil.copy2(SRC/'vendor/sha256/README.md',out/'licenses/sha256-source.md')
(out/'host').mkdir()
for name in ['ridi_emmc.py','package.py','devices.py','README.md']:shutil.copy2(SRC/name,out/'host'/name)
report.update(package_type='unified-install-update',toolkit=toolkit,runtime_sha256=runtime_hashes,offline_validation='pending',physical_update_validation='not performed',model_policy='raw NTX PCB/customer/CPU/RAM/display/touch/WiFi plus i.MX IVT and structural partition validation; no unit whitelist',manifest_offsets='release reference offsets; RAM computes vendor destination from actual capacity')
(out/'build-report.json').write_text(json.dumps(report,indent=2)+'\n')
(out/'README.md').write_text((SRC/'README.md').read_text())
files=sorted(p for p in out.rglob('*') if p.is_file() and not any(s.startswith('.') for s in p.relative_to(out).parts) and p.name!='SHA256SUMS')
(out/'SHA256SUMS').write_text(''.join(sha(p)+'  '+str(p.relative_to(out))+'\n' for p in files))
archive=out.with_suffix('.tar')
with tarfile.open(archive,'w') as t:
 for path in sorted(out.iterdir()):
  if not path.name.startswith('.'):t.add(path,arcname='e70q10-update/'+path.name)
Path(str(archive)+'.sha256').write_text(sha(archive)+'  '+archive.name+'\n')
validate(archive)
print('BUILT UNIFIED',out)
