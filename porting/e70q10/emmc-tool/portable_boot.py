"""Validate Android v0 boot and convert the known E70Q10 SD ramdisk to eMMC."""
import gzip,hashlib,pathlib,struct,re,zlib,lzma

def unpack(b):
 assert b[:8]==b'ANDROID!' and len(b)>=608,'Invalid Android boot header'
 ks,ka,rs,ra,ss,sa,tags,page=struct.unpack_from('<8I',b,8)
 assert page==2048 and ka==0x82808000 and ra==0x83800000 and tags==0x82800100,'Unsupported E70Q10 load addresses/page'
 assert struct.unpack_from('<I',b,40)[0]==0,'Only boot header v0 supported'
 pos=page;chunks=[];h=hashlib.sha1()
 for n in [ks,rs,ss]:
  data=b[pos:pos+n];assert len(data)==n;chunks.append(data);h.update(data);h.update(struct.pack('<I',n));pos+=(n+page-1)//page*page
 assert b[576:596]==h.digest(),'Invalid boot header SHA1'
 k,rd,dtb=chunks;start,end=struct.unpack_from('<II',k,40);zend=end-start
 assert struct.unpack_from('<I',k,36)[0]==0x016f2818 and 48<zend<=len(k),'Invalid ARM zImage'
 if ss:
  assert len(k)==zend and dtb[:4]==bytes.fromhex('d00dfeed'),'Invalid separate DTB'
  k+=dtb
 else:dtb=k[zend:]
 assert dtb[:4]==bytes.fromhex('d00dfeed') and struct.unpack_from('>I',dtb,4)[0]==len(dtb),'Invalid appended DTB'
 assert b'E70Q10' in dtb or b'e70q10' in dtb,'Wrong DTB board'
 return k,rd,b[:page]

def entries(rd):
 raw=gzip.decompress(rd);at=0;out={}
 while at<len(raw):
  assert raw[at:at+6]==b'070701','Expected newc ramdisk'
  fields=[int(raw[at+6+i*8:at+14+i*8],16) for i in range(13)];size=fields[6];ns=fields[11]
  name=raw[at+110:at+110+ns-1].decode();at=(at+110+ns+3)&~3;data=raw[at:at+size];at=(at+size+3)&~3
  assert len(data)==size
  if name=='TRAILER!!!':break
  name=name.removeprefix('./');p=pathlib.PurePosixPath(name)
  assert not p.is_absolute() and '..' not in p.parts and name not in out,'Unsafe ramdisk entry'
  out[name]=(fields,data)
 return out

def pack_entries(es):
 raw=bytearray()
 for name,(old,data) in list(es.items())+[('TRAILER!!!',([0]*13,b''))]:
  f=old.copy();nm=name.encode()+b'\0';f[6]=len(data);f[11]=len(nm);f[12]=0
  raw+=b'070701'+''.join(f'{v:08x}' for v in f).encode()+nm;raw+=bytes((-len(raw))%4);raw+=data;raw+=bytes((-len(raw))%4)
 raw+=bytes((-len(raw))%512)
 return gzip.compress(raw,compresslevel=9,mtime=0)

def kernel_release(k):
 from portable_lzo import lzop
 images=[k]
 at=k.find(bytes.fromhex('894c5a4f000d0a1a0a'))
 if at>=0:images.append(lzop(k[at:]))
 at=k.find(b'\xfd7zXZ\0')
 if at>=0:
  decoder=lzma.LZMADecompressor();raw=decoder.decompress(k[at:],max_length=128<<20)
  if not decoder.eof:raise ValueError('Kernel XZ too large or truncated')
  images.append(raw)
 for m in re.finditer(b'\x1f\x8b\x08',k):
  try:
   decoder=zlib.decompressobj(31);raw=decoder.decompress(k[m.start():],128<<20)
   if decoder.eof:images.append(raw)
  except zlib.error:pass
 for raw in images:
  m=re.search(rb'Linux version ([^\s\x00]+)',raw)
  if m:return m[1].decode()
 raise ValueError('Unable to identify boot kernel release')

# DT usdhc2 is the removable microSD controller (0x02194000).
# vold matches disk DEVPATH with fnmatch; host/card numbering may vary.
EXTERNAL_SD_ENTRY = (
 '/devices/*/2194000.usdhc/mmc_host/mmc*/*/block/mmcblk* '
 'auto auto defaults voldmanaged=extsd:auto'
)

# Stock E70Q10 ntx_prebooti has a 500-byte stack sprintf buffer; hardware
# arguments plus the command prefix consume about 250 bytes. Leave margin.
NTX_BOOT_CMDLINE_LIMIT = 240

def safe_boot_header(hdr):
 raw = hdr[64:576].split(b'\0', 1)[0]
 if len(raw) <= NTX_BOOT_CMDLINE_LIMIT:
  return hdr
 # Known redundant defaults only: NTX appends mem, kernel console selects
 # ttymxc0 already, and Linux's default console loglevel is 7.
 redundant = {b'androidboot.console=ttymxc0', b'mem=1018M', b'loglevel=7'}
 compact = b' '.join(t for t in raw.split() if t not in redundant)
 if len(compact) > NTX_BOOT_CMDLINE_LIMIT:
  raise ValueError('부팅 인자가 너무 깁니다 (%d바이트, 최대 %d바이트). BOARD_KERNEL_CMDLINE을 줄여주세요.' % (len(compact), NTX_BOOT_CMDLINE_LIMIT))
 fixed = bytearray(hdr)
 fixed[64:576] = compact + bytes(512 - len(compact))
 return bytes(fixed)

def prepare(b):
 k,rd,hdr=unpack(b);hdr=safe_boot_header(hdr);es=entries(rd)
 f,data=es['fstab.E70Q10'];text=data.decode().replace('mmcblk1p2','mmcblk0p5').replace('mmcblk1p3','mmcblk0p8').replace('mmcblk1p4','mmcblk0p7')
 if '/cache' not in text:text+='\n/dev/block/mmcblk0p6 /cache ext4 noatime,nosuid,nodev wait,check\n'
 # Add removable storage only after converting OS mounts to internal eMMC.
 if EXTERNAL_SD_ENTRY not in text:
  text+='\n# Removable microSD managed by Android vold.\n'+EXTERNAL_SD_ENTRY+'\n'
 assert '/dev/block/mmcblk1' not in text
 assert text.splitlines().count(EXTERNAL_SD_ENTRY)==1
 for part,mount in [('mmcblk0p5','/system'),('mmcblk0p8','/vendor'),('mmcblk0p7','/data'),('mmcblk0p6','/cache')]:
  assert any(part in line.split()[0] and line.split()[1]==mount for line in text.splitlines() if line.strip() and not line.lstrip().startswith('#')),'Wrong eMMC fstab'
 es['fstab.E70Q10']=(f,text.encode())
 f,data=es['init.E70Q10.rc'];text=data.decode().replace('    wait /dev/block/mmcblk1p1\n','').replace('    mount vfat /dev/block/mmcblk1p1 /e70log rw noatime nosuid nodev','    mount tmpfs tmpfs /e70log mode=0770,size=8m,nosuid,nodev')
 assert 'mmcblk1' not in text,'SD dependency remains in init'
 es['init.E70Q10.rc']=(f,text.encode());rd=pack_entries(es)
 hdr=bytearray(hdr);struct.pack_into('<I',hdr,8,len(k));struct.pack_into('<I',hdr,16,len(rd));struct.pack_into('<I',hdr,24,0)
 h=hashlib.sha1()
 for data in [k,rd,b'']:h.update(data);h.update(struct.pack('<I',len(data)))
 hdr[576:608]=h.digest()+bytes(12);result=bytes(hdr)
 for data in [k,rd]:result+=data+bytes((-len(data))%2048)
 unpack(result)
 return result,kernel_release(k)
