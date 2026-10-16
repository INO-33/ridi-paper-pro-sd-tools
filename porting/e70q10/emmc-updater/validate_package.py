#!/usr/bin/env python3
import argparse,hashlib,pathlib as P,re,tarfile,json
from selection import roles,parse_control
PREFIX='e70q10-update'
def digest(stream):
 h=hashlib.sha256()
 for b in iter(lambda:stream.read(4<<20),b''):h.update(b)
 return h.hexdigest()
def sums(text):
 out={}
 for line in text.splitlines():
  m=re.fullmatch(r'([0-9a-f]{64})  (.+)',line)
  if not m:raise ValueError('Bad checksum list')
  path=P.PurePosixPath(m[2])
  if path.is_absolute() or '..' in path.parts or m[2] in out:raise ValueError('Bad checksum path')
  out[m[2]]=m[1]
 return out
def validate(archive):
 archive=P.Path(archive).resolve(strict=True)
 expected=sums(archive.with_suffix('.tar.sha256').read_text())[archive.name]
 with archive.open('rb') as f:
  if digest(f)!=expected:raise ValueError('Archive SHA256 mismatch')
 with tarfile.open(archive) as tar:
  files={}
  for m in tar.getmembers():
   p=P.PurePosixPath(m.name)
   if p.is_absolute() or '..' in p.parts or p.parts[0]!=PREFIX or not(m.isdir() or m.isfile()):raise ValueError('Unsafe archive entry')
   if m.isfile():
    name=str(P.PurePosixPath(*p.parts[1:]))
    if name in files or m.size>=4294967296:raise ValueError('Duplicate or >=4GiB file')
    files[name]=m
  checksum_data=tar.extractfile(files['SHA256SUMS']).read()
  checks=sums(checksum_data.decode())
  if set(checks)!=set(files)-{'SHA256SUMS'}:raise ValueError('Checksum coverage mismatch')
  for name,h in checks.items():
   if digest(tar.extractfile(files[name]))!=h:raise ValueError('Payload SHA256 mismatch: '+name)
  rows=[line.split() for line in tar.extractfile(files['manifest.tsv']).read().decode().splitlines()]
  available=roles(rows)
  if 'update.conf' not in files:raise ValueError('Legacy package: regenerate to support SD selection and automatic updates')
  manifest_sha=hashlib.sha256(tar.extractfile(files['manifest.tsv']).read()).hexdigest()
  selected,automatic,reboot=parse_control(tar.extractfile(files['update.conf']).read(),manifest_sha,available)
  for row in rows:
   if len(row)!=5 or not re.fullmatch('[0-9a-f]{64}',row[3]) or row[4]!=checks[row[0]]:raise ValueError('Bad payload manifest')
  forbidden=['userdata.raw.gz','cache.raw.gz','misc.raw.gz','mbr.sector0.bin.gz']
  if any(name in files for name in forbidden) or any(name.startswith('backup/') or name.startswith('ebr.') for name in files):raise ValueError('Full-install payload in update archive')
  return {'archive':str(archive),'archive_sha256':expected,'file_bytes':sum(m.size for m in files.values()),'required_bytes':sum(m.size for m in files.values())+(64<<20),'files':sorted(files),'sizes':{name:m.size for name,m in files.items()},'manifest':rows,'manifest_sha256':manifest_sha,'targets':selected,'automatic':automatic,'automatic_reboot':reboot,'checksums':checks|{'SHA256SUMS':hashlib.sha256(checksum_data).hexdigest()}}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('archive');a=p.parse_args()
 print(json.dumps(validate(a.archive),indent=2))
