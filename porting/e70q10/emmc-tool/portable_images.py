"""Read Android sparse/ext4 images with Python only on Windows and Linux.
No filesystem editing: clean ext4 filesystems retain their size; image tails
are padded to the fixed eMMC partition. This is validation, not a full fsck.
"""
from pathlib import Path
import struct,bisect,zlib

class Image:
 def __init__(self,path,max_bytes):
  self.path=Path(path);self.f=self.path.open('rb');self.parts=[];self.crcs=[];self.header_crc=0;self.patches=[]
  try:
   size=self.path.stat().st_size;h=self.f.read(28)
   if len(h)>=28 and struct.unpack_from('<I',h)[0]==0xed26ff3a:
    magic,major,minor,fh,ch,block,blocks,count,crc=struct.unpack('<IHHHHIIII',h)
    if major!=1 or not 28<=fh<=4096 or not 12<=ch<=4096 or block not in (1024,2048,4096) or count>1000000:raise ValueError('지원하지 않는 sparse 헤더')
    self.size=block*blocks;self.header_crc=crc
    if not 0<self.size<=max_bytes:raise ValueError('이미지가 파티션보다 큽니다')
    at=fh;out=0
    for _ in range(count):
     if at+ch>size:raise ValueError('잘린 sparse 청크 헤더')
     self.f.seek(at);t,res,n,total=struct.unpack('<HHII',self.f.read(12));n*=block;data_at=at+ch
     if total<ch or at+total>size:raise ValueError('잘린 sparse 청크')
     if t==0xcac1 and total==ch+n:part=(out,out+n,'raw',data_at)
     elif t==0xcac2 and total==ch+4:
      self.f.seek(data_at);part=(out,out+n,'fill',self.f.read(4))
     elif t==0xcac3 and total==ch:part=(out,out+n,'zero',None)
     elif t==0xcac4 and n==0 and total==ch+4:
      self.f.seek(data_at);self.crcs.append((out,struct.unpack('<I',self.f.read(4))[0]));part=None
     else:raise ValueError('지원하지 않거나 손상된 sparse 청크')
     if part:
      if n==0 or out+n>self.size:raise ValueError('sparse 출력 범위 오류')
      self.parts.append(part);out+=n
     at+=total
    if out!=self.size or at!=size:raise ValueError('sparse 전체 크기 불일치')
   else:
    self.size=size
    if not 0<size<=max_bytes:raise ValueError('이미지가 파티션보다 큽니다')
    self.parts=[(0,size,'raw',0)]
   self.starts=[p[0] for p in self.parts]
  except BaseException:self.f.close();raise
 def close(self):self.f.close()
 def read(self,offset,size,patched=True):
  origin=offset
  if offset<0 or size<0 or offset+size>self.size or size>64<<20:raise ValueError('이미지 읽기 범위 오류')
  result=bytearray()
  while size:
   i=bisect.bisect_right(self.starts,offset)-1;a,b,kind,where=self.parts[i];n=min(size,b-offset);delta=offset-a
   if kind=='raw':
    self.f.seek(where+delta);chunk=self.f.read(n)
    if len(chunk)!=n:raise ValueError('이미지가 읽기 중 잘렸습니다')
   elif kind=='fill':shift=delta%4;chunk=(where*((n+shift+3)//4))[shift:shift+n]
   else:chunk=bytes(n)
   result.extend(chunk);size-=n;offset+=n
  return self.apply_patches(origin,bytes(result)) if patched else bytes(result)
 def apply_patches(self,offset,data):
  end=offset+len(data);out=None
  for start,value in self.patches:
   stop=start+len(value);a=max(offset,start);b=min(end,stop)
   if a<b:
    if out is None:out=bytearray(data)
    out[a-offset:b-offset]=value[a-start:b-start]
  return bytes(out) if out is not None else data
 def chunks(self):
  crc=0;at=0;checks={}
  for offset,expected in self.crcs:checks.setdefault(offset,[]).append(expected)
  # Respect all CRC chunk boundaries, including several chunks at one offset.
  boundaries=sorted(set([self.size,*checks]))
  for end in boundaries:
   while at<end:
    b=self.read(at,min(4<<20,end-at),patched=False);crc=zlib.crc32(b,crc);yield self.apply_patches(at,b);at+=len(b)
   if end in checks and any(expected!=(crc&0xffffffff) for expected in checks[end]):raise ValueError('sparse CRC 불일치')
  if self.header_crc and self.header_crc!=(crc&0xffffffff):raise ValueError('sparse 헤더 CRC 불일치')

class Ext4:
 def __init__(self,image):
  self.im=image;sb=image.read(1024,1024);u16=lambda o:struct.unpack_from('<H',sb,o)[0];u32=lambda o:struct.unpack_from('<I',sb,o)[0]
  if u16(56)!=0xef53 or u16(58)!=1:raise ValueError('정상적으로 종료된 ext4 이미지가 필요합니다')
  self.bs=1024<<u32(24);self.ipg=u32(40);self.inode_size=u16(88);self.desc_size=max(32,u16(254));inc=u32(96);ro=u32(100);self.inodes=u32(0);self.bpg=u32(32);self.first=u32(20);self.uuid=sb[104:120];self.gdt_checksum=bool(ro&0x10)
  if ro&~0x7f or inc&~(0x2|0x40|0x80|0x200) or self.bs not in (1024,2048,4096) or not self.ipg or self.inode_size not in (128,256,512) or self.desc_size not in (32,64):raise ValueError('지원하지 않는 ext4 기능/geometry (journal recovery 포함)')
  blocks=u32(4)+(u32(336)<<32 if inc&0x80 else 0);self.bytes=blocks*self.bs;self.blocks=blocks
  if not 0<self.bytes<=image.size:raise ValueError('ext4 크기가 이미지보다 큽니다')
  self.gdt=2*self.bs if self.bs==1024 else self.bs;self.has64=bool(inc&0x80)
 def normalize_bitmap_padding(self):
  # make_ext4fs leaves bitmap padding zero. Only bits OUTSIDE real inode/block
  # domains become one; no real allocations/counts, file contents or geometry change.
  if not self.bpg or self.ipg>self.bs*8 or self.bpg>self.bs*8:raise ValueError('ext4 bitmap geometry 오류')
  groups=(self.blocks-self.first+self.bpg-1)//self.bpg
  if not 0<groups<=4096 or self.inodes>groups*self.ipg:raise ValueError('ext4 group geometry 오류')
  changes=[]
  for group in range(groups):
   gd=self.im.read(self.gdt+group*self.desc_size,self.desc_size)
   if self.gdt_checksum:
    crc=65535
    for value in self.uuid+struct.pack('<I',group)+gd[:30]+gd[32:]:
     crc^=value
     for _ in range(8):crc=(crc>>1)^0xa001 if crc&1 else crc>>1
    if crc!=struct.unpack_from('<H',gd,30)[0]:raise ValueError('ext4 group descriptor checksum 불일치')
   for kind,lo,hi,valid in [('inode',4,36,min(self.ipg,max(0,self.inodes-group*self.ipg))),('block',0,32,min(self.bpg,max(0,self.blocks-self.first-group*self.bpg)))]:
    block=struct.unpack_from('<I',gd,lo)[0]
    if self.has64:block|=struct.unpack_from('<I',gd,hi)[0]<<32
    if not 0<block<self.blocks:raise ValueError('ext4 bitmap 위치 오류')
    start=block*self.bs;old=self.im.read(start,self.bs);new=bytearray(old);byte,bit=divmod(valid,8)
    if bit:new[byte]|=(255<<bit)&255;byte+=1
    new[byte:]=bytes([255])*(self.bs-byte)
    if bytes(new)!=old:
     self.im.patches.append((start,bytes(new)));changes.append({'group':group,'bitmap':kind,'offset':start,'valid_bits':valid})
  return changes
 def inode(self,number):
  if number<1:raise ValueError('ext4 inode 오류')
  group,index=divmod(number-1,self.ipg);gd=self.im.read(self.gdt+group*self.desc_size,self.desc_size);table=struct.unpack_from('<I',gd,8)[0]
  if self.has64:table|=struct.unpack_from('<I',gd,40)[0]<<32
  data=self.im.read(table*self.bs+index*self.inode_size,self.inode_size);size=struct.unpack_from('<I',data,4)[0]|struct.unpack_from('<I',data,108)[0]<<32
  if size>64<<20:raise ValueError('검증 대상 ext4 파일이 너무 큽니다')
  if not struct.unpack_from('<I',data,32)[0]&0x80000:raise ValueError('extents 없는 inode는 지원하지 않습니다')
  return size,data[40:100]
 def extents(self,node,depth=None,seen=None):
  if seen is None:seen=set()
  if len(node)<12:raise ValueError('잘린 ext4 extent')
  magic,n,maximum,d,generation=struct.unpack_from('<HHHHI',node)
  if magic!=0xf30a or n>maximum or 12+n*12>len(node) or d>5 or (depth is not None and d!=depth):raise ValueError('ext4 extent tree 오류')
  result=[]
  for i in range(n):
   item=node[12+i*12:24+i*12];logical=struct.unpack_from('<I',item)[0]
   if d:
    block=struct.unpack_from('<I',item,4)[0]|struct.unpack_from('<H',item,8)[0]<<32
    if block in seen:raise ValueError('ext4 extent cycle')
    seen.add(block);result.extend(self.extents(self.im.read(block*self.bs,self.bs),d-1,seen))
   else:
    length,high,low=struct.unpack_from('<HHI',item,4);uninit=length>32768;count=length-32768 if uninit else length
    if not count:raise ValueError('빈 extent')
    physical=(low|high<<32)*self.bs
    if physical+count*self.bs>self.bytes:raise ValueError('extent가 파일시스템을 벗어납니다')
    result.append((logical*self.bs,count*self.bs,physical,uninit))
  return result
 def contents(self,number):
  size,node=self.inode(number);data=bytearray(size);previous=0
  for logical,count,physical,uninit in self.extents(node):
   if logical<previous:raise ValueError('겹치는 ext4 extent')
   previous=logical+count
   if logical>=size:continue
   n=min(count,size-logical)
   if not uninit:data[logical:logical+n]=self.im.read(physical,n)
  return bytes(data)
 def directory(self,number):
  data=self.contents(number);at=0;out={}
  while at<len(data):
   if at+8>len(data):raise ValueError('잘린 ext4 directory')
   inode,length,n,t=struct.unpack_from('<IHBB',data,at)
   if length<8 or length%4 or at+length>len(data) or n>length-8:raise ValueError('ext4 directory record 오류')
   if inode:
    name=data[at+8:at+8+n].decode('utf-8',errors='strict')
    if name not in ('.','..'):
     if name in out or '/' in name or '\x00' in name:raise ValueError('ext4 directory 이름 오류')
     out[name]=inode
   at+=length
  return out
 def find(self,path):
  number=2
  for part in path.strip('/').split('/'):
   if not part:continue
   try:number=self.directory(number)[part]
   except KeyError:raise ValueError('필수 파일이 없습니다: '+path) from None
  return number
 def file(self,path):return self.contents(self.find(path))
