#!/usr/bin/env python3
"""Portable image/UI job contracts; all disk fixtures are temporary regular files."""
from pathlib import Path
import sys,tempfile,subprocess,struct,os,hashlib,json,zlib,ctypes,tarfile
from unittest.mock import patch
from portable_images import Image,Ext4
from portable_lzo import lzop
from portable_boot import prepare,entries
from folder_package import build_folder
from package import plan,sha
import gui_backend as backend,devices
SRC=Path(__file__).resolve().parent;ROOT=SRC.parents[2];LOG=ROOT/'.orchestrator/logs/emmc-gui-20261014';LOG.mkdir(parents=True,exist_ok=True)
seed=Path(sys.argv[1]);product=Path(sys.argv[2]);proof=[]
with tempfile.TemporaryDirectory(prefix='gui-portable-tests-') as td:
 w=Path(td)
 # LZO independently agrees with native lzop for literal/match/overlap patterns.
 for i,data in enumerate([b'',b'a',os.urandom(65537),b'abcde'*100000]):
  packed=subprocess.run(['lzop','-c'],input=data,capture_output=True,check=True).stdout;assert lzop(packed)==data
  corrupt=bytearray(packed);corrupt[15]^=1
  try:lzop(corrupt);raise AssertionError('corrupt lzop accepted')
  except ValueError:pass
 proof.append('pure Python LZO/native lzop identical; header corruption refused')
 # Sparse types and cumulative CRC, malformed/truncated refusal.
 raw=b'A'*4096+b'1234'*1024+bytes(4096);crc=zlib.crc32(raw)&0xffffffff
 sparse=struct.pack('<IHHHHIIII',0xed26ff3a,1,0,28,12,4096,3,4,crc)+struct.pack('<HHII',0xcac1,0,1,4108)+b'A'*4096+struct.pack('<HHII',0xcac2,0,1,16)+b'1234'+struct.pack('<HHII',0xcac3,0,1,12)+struct.pack('<HHII',0xcac4,0,0,16)+struct.pack('<I',crc)
 f=w/'sparse';f.write_bytes(sparse);im=Image(f,1<<20);assert b''.join(im.chunks())==raw and im.read(4097,31)==raw[4097:4128];im.close()
 for data in [sparse[:-1],sparse[:-4]+bytes(4),sparse+b'extra']:
  f.write_bytes(data)
  try:
   im=Image(f,1<<20)
   try:b''.join(im.chunks())
   finally:im.close()
   raise AssertionError('corrupt sparse accepted')
  except ValueError:pass
 proof.append('RAW/FILL/DONTCARE/CRC, unaligned reads, corrupt/truncated sparse refusal')
 # Real OS inputs; package construction may not execute external host tools.
 with patch.object(subprocess,'run',side_effect=AssertionError('portable builder invoked external tool')):
  report=build_folder(product,seed,w/'all','install')
 proof.append('actual boot/system/vendor package built without Linux tools/compiler')
 with tarfile.open(report['path']) as tar:
  for role in ('system','vendor'):
   rawfile=w/(role+'.raw')
   import gzip,shutil
   with gzip.GzipFile(fileobj=tar.extractfile('e70q10-update/'+role+'.raw.gz')) as src,rawfile.open('wb') as out:shutil.copyfileobj(src,out,4<<20)
   # Optional Linux oracle, never invoked by the Windows portable builder.
   r=subprocess.run(['e2fsck','-fn',str(rawfile)],capture_output=True);assert r.returncode==0,r.stderr
   rawfile.unlink()
  es=entries(tar.extractfile('e70q10-update/updater-ramdisk.cpio.gz').read());mh=report['manifest'].encode()
  assert all(mh in es[n][1] for n in ('bin/updater','bin/auto-update','bin/backup-current'))
  hashes=json.loads(es['etc/runtime-sha256.json'][1]);assert all(hashlib.sha256(es[n][1]).hexdigest()==h for n,h in hashes.items())
 proof.append('padded ext4 passes Linux fsck oracle; matched RAM manifest and runtime hashes')
 # Existing Windows Storage adapter contracts and normal policy remain valid.
 with (LOG/'windows-contract.log').open('wb') as f:subprocess.run([sys.executable,str(SRC/'test_windows_logic.py'),str(w/'all')],stdout=f,stderr=f,check=True)
 proof.append('Windows storage contract: Unicode/source-on-SD/system/pagefile/identity/FAT32 guards')
 empty=w/'images-empty';empty.mkdir();backup=build_folder(empty,seed,w/'backup','backup',());assert backup['available']==() and not any(n.endswith('.raw.gz') for n in backup['members'])
 # Real shared backend stage/readback on temp SD, no format or physical mount.
 mount=w/'sd';mount.mkdir();cache=w/'cache';calls=[]
 class Adapter:
  def checked_disk(self,identifier):return {'id':identifier,'identity':'test','serial':'test','bytes':16_000_000_000,'sector':512,'name':'TEST ONLY'}
  def fingerprint(self,d):return devices.fingerprint(d)
  def check_mount(self,m):assert m==mount
  def flush_volume(self,m):assert m==mount
  def format_disk(self,*a):raise AssertionError('physical formatting attempted')
 req=backend.Request(empty,seed,'TEST','backup',(),False)
 with patch.object(backend,'mounted_volume',return_value=mount):
  state=backend.prepare(req,cache,lambda s:(calls.append(s) or True),adapter=Adapter())
 assert len(calls)==1 and state['config']['targets']=='none' and state['config']['reboot']=='0' and (mount/'e70q10-update/ram-updater.img').is_file()
 assert not list((mount/'e70q10-update').glob('*.raw.gz'))
 before={p.name:p.stat().st_mtime_ns for p in (mount/'e70q10-update').iterdir()}
 with patch.object(backend,'mounted_volume',return_value=mount):
  try:backend.prepare(req,cache,lambda s:False,adapter=Adapter());raise AssertionError('cancel accepted')
  except backend.Cancelled:pass
 assert before=={p.name:p.stat().st_mtime_ns for p in (mount/'e70q10-update').iterdir()}
 proof.append('shared backend backup stage/readback, one consent, no OS images, cancel leaves SD untouched')
 # Windows no-buffering ABI: alignment, tail sizes, EOF failure and handle closure.
 class Fn:
  def __init__(self,f):self.f=f
  def __call__(self,*a):return self.f(*a)
 for size in (0,1,511,512,65535,65536,(4<<20)+137):
  payload=os.urandom(size);path=w/'winfile';path.write_bytes(payload);pos=[0];closed=[]
  def create(path,access,share,sec,creation,flags,temp):assert access==0x80000000 and flags&0x20000000;return 123
  def read(handle,address,count,got,over):
   assert address.value%65536==0 and count%65536==0;b=payload[pos[0]:pos[0]+count];ctypes.memmove(address.value,b,len(b));ctypes.cast(got,ctypes.POINTER(ctypes.c_uint32))[0]=len(b);pos[0]+=len(b);return 1
  class Kernel:pass
  kernel=Kernel();kernel.CreateFileW=Fn(create);kernel.ReadFile=Fn(read);kernel.CloseHandle=Fn(lambda h:closed.append(h))
  assert devices.windows_readback_sha(path,kernel)==hashlib.sha256(payload).hexdigest() and closed==[123]
 path.write_bytes(b'one');kernel.ReadFile=Fn(lambda h,a,n,got,o:1)
 try:devices.windows_readback_sha(path,kernel);raise AssertionError('short read accepted')
 except ValueError:pass
 assert len(closed)==2
 proof.append('Windows unbuffered ABI: 64KiB aligned buffers/reads, all tail sizes, empty/EOF failure, close handles')
 (LOG/'portable-validation.json').write_text(json.dumps({'cases':proof,'manifest':report['manifest'],'Windows_physical_test':False,'physical_SD_writes':False},indent=2))
print('PASS portable image conversion, Linux fsck oracle, RAM pairing, Windows adapters/readback and shared SD jobs')
