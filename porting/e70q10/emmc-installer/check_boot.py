#!/usr/bin/env python3
from pathlib import Path
import gzip,struct,hashlib,json
p=Path('/home/juwon/ridi/deliverables/e70q10-emmc-android8-20261001');results={}
for name in ['boot-emmc.img','ram-installer.img']:
 b=(p/name).read_bytes();ks,ka,rs,ra,ss,sa,tags,page=struct.unpack_from('<8I',b,8)
 assert ss==0
 pos=page;h=hashlib.sha1();chunks=[]
 for n in [ks,rs,ss]:
  data=b[pos:pos+n];assert len(data)==n;chunks.append(data);h.update(data);h.update(struct.pack('<I',n));pos+=(n+page-1)//page*page
 assert b[576:596]==h.digest()
 start,end=struct.unpack_from('<II',chunks[0],40);size=end-start
 assert chunks[0][size:size+4]==bytes.fromhex('d00dfeed')
 entries={};raw=gzip.decompress(chunks[1]);at=0
 while at<len(raw):
  assert raw[at:at+6]==b'070701'
  fields=[int(raw[at+6+i*8:at+14+i*8],16) for i in range(13)]
  mode=fields[1];n=fields[6];namesize=fields[11];nm=raw[at+110:at+110+namesize-1].decode();at=(at+110+namesize+3)&~3;data=raw[at:at+n];at=(at+n+3)&~3
  if nm=='TRAILER!!!':break
  entries[nm.removeprefix('./')]=(mode,data)
 if name=='ram-installer.img':
  assert entries['bin/installer'][1]==(p/'installer.sh').read_bytes()
  assert entries['bin/countbytes'][1]==(p/'countbytes-arm').read_bytes()
  assert entries['init'][0]&0o111
 else:
  assert b'/dev/block/mmcblk1' not in entries['fstab.E70Q10'][1]
  assert entries['fstab.E70Q10'][1].count(b'voldmanaged=extsd:auto')==1
  assert b'/devices/*/2194000.usdhc/mmc_host/mmc*/*/block/mmcblk*' in entries['fstab.E70Q10'][1]
  assert b'mmcblk1' not in entries['init.E70Q10.rc'][1]
 results[name]={'header_sha1':'valid','kernel_addr':hex(ka),'ramdisk_addr':hex(ra),'dtb_appended':True,'second_size':ss,'ramdisk_entries':len(entries)}
(p/'boot-validation.json').write_text(json.dumps(results,indent=2)+'\n')
print('PASS: boot headers, appended DTB, embedded installer and eMMC fstab')
