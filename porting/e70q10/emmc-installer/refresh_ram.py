#!/usr/bin/env python3
# Repackage RAM image after offline tests, without changing the frozen OS payloads.
import pathlib as P,subprocess as S,struct,gzip,hashlib as H,shutil,json
R=P.Path('/home/juwon/ridi');O=R/'deliverables/e70q10-emmc-android8-20261001';RR=O/'.build/ram-root'
shutil.copyfile(RR/'bin/countbytes',O/'countbytes-arm')
report=json.loads((O/'build-report.json').read_text())
s=(R/'porting/e70q10/emmc-installer/installer.sh').read_text()
for k,v in report['pinned_hashes'].items():s=s.replace('@'+k+'@',v)
assert '@' not in s
(O/'installer.sh').write_text(s);(O/'installer.sh').chmod(0o755);shutil.copyfile(O/'installer.sh',RR/'bin/installer')
names=sorted(str(p.relative_to(RR)) for p in RR.rglob('*'))
cpio=S.run(['cpio','-o','-H','newc','--owner=0:0','--null'],cwd=RR,input=('\0'.join(['.']+names)+'\0').encode(),stdout=S.PIPE,check=True).stdout
rd=gzip.compress(cpio,compresslevel=9,mtime=0);(O/'installer-ramdisk.cpio.gz').write_bytes(rd)
b=(O/'ram-installer.img').read_bytes();ks=struct.unpack_from('<I',b,8)[0];page=struct.unpack_from('<I',b,36)[0];k=b[page:page+ks];header=bytearray(b[:page]);struct.pack_into('<I',header,16,len(rd))
h=H.sha1()
for data in [k,rd,b'']:h.update(data);h.update(struct.pack('<I',len(data)))
header[576:608]=h.digest()+b'\0'*12
with open(O/'ram-installer.img','wb') as f:
 f.write(header)
 for data in [k,rd]:f.write(data);f.write(b'\0'*(-len(data)%page))
print('RAM image refreshed')
