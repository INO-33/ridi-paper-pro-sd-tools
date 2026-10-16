#!/usr/bin/env python3
from pathlib import Path
import subprocess,hashlib,json
out=Path('/home/juwon/ridi/deliverables/e70q10-emmc-android8-20261001')
row=next(x.split() for x in (out/'manifest.tsv').read_text().splitlines() if 'userdata.raw.gz' in x)
p=subprocess.Popen(['/usr/bin/qemu-arm-static',str(out/'.build/ram-root/bin/busybox'),'gzip','-dc',str(out/row[1])],stdout=subprocess.PIPE)
h=hashlib.sha256();count=0
while True:
 b=p.stdout.read(4<<20)
 if not b:break
 count+=len(b);h.update(b)
assert p.wait()==0
assert count==int(row[3])*512==6311378944
assert h.hexdigest()==row[4]
(out/'arm-stream-validation.json').write_text(json.dumps({'arm_busybox_gzip':'passed','expanded_bytes':count,'expanded_sha256':h.hexdigest(),'emulation':'qemu-arm-static; actual bundled ARM BusyBox 1.22.1'},indent=2)+'\n')
print('PASS: ARM gzip expanded 6,311,378,944 bytes with matching SHA256')
