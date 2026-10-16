/* Model/geometry verifier and table generator, identical host/ARM implementation.
 * NTX header offsets: reference-sources/tolino-epos/kernel_imx/arch/arm/mach-mx6/ntx_hwconfig.h.
 * No writes to the input device. Outputs only into the supplied RAM directory. */
#ifdef HOST
#define _FILE_OFFSET_BITS 64
#include <unistd.h>
#include <fcntl.h>
#include <sys/types.h>
static long op(const char*p,int flags){return open(p,flags,0600);}
static long rd(int fd,void*p,unsigned n){return read(fd,p,n);}
static long wr(int fd,const void*p,unsigned n){return write(fd,p,n);}
static void cl(int fd){close(fd);}
static long sk(int fd,unsigned long long o){return lseek(fd,(off_t)o,0)<0?-1:0;}
static void quit(int n){_exit(n);}
#else
static int call(int nr,unsigned a,unsigned b,unsigned c,unsigned d,unsigned e){
 register unsigned r0 __asm__("r0")=a,r1 __asm__("r1")=b,r2 __asm__("r2")=c,r3 __asm__("r3")=d,r4 __asm__("r4")=e,r7 __asm__("r7")=nr;
 __asm__ volatile("svc 0":"+r"(r0):"r"(r1),"r"(r2),"r"(r3),"r"(r4),"r"(r7):"memory");return (int)r0;
}
static long op(const char*p,int flags){return call(5,(unsigned)p,flags,0600,0,0);}
static long rd(int fd,void*p,unsigned n){return call(3,fd,(unsigned)p,n,0,0);}
static long wr(int fd,const void*p,unsigned n){return call(4,fd,(unsigned)p,n,0,0);}
static void cl(int fd){call(6,fd,0,0,0,0);}
static long sk(int fd,unsigned long long o){unsigned long long r;return call(140,fd,o>>32,(unsigned)o,(unsigned)&r,0);}
static void quit(int n){call(1,n,0,0,0,0);__builtin_unreachable();}
#endif
static unsigned len(const char*s){unsigned n=0;while(s[n])n++;return n;}
static void print(const char*s){unsigned n=len(s);if(wr(1,s,n)!=(long)n)quit(1);}
static void bad(const char*s){wr(2,"STOP: ",6);wr(2,s,len(s));wr(2,"\n",1);quit(1);}
static int eq(const void*a,const void*b,unsigned n){const unsigned char*x=a,*y=b;while(n--)if(*x++!=*y++)return 0;return 1;}
static void cp(void*a,const void*b,unsigned n){unsigned char*x=a;const unsigned char*y=b;while(n--)*x++=*y++;}
static void zero(void*a,unsigned n){unsigned char*x=a;while(n--)*x++=0;}
static unsigned get(const unsigned char*p){return p[0]|(unsigned)p[1]<<8|(unsigned)p[2]<<16|(unsigned)p[3]<<24;}
static void put(unsigned char*p,unsigned n){p[0]=n;p[1]=n>>8;p[2]=n>>16;p[3]=n>>24;}
static void number(char*out,unsigned long long n){char r[24];unsigned i=0,j=0;do{r[i++]='0'+n%10;n/=10;}while(n);while(i)out[j++]=r[--i];out[j]=0;}
static unsigned parse(const char*s){unsigned long long n=0;if(!*s)bad("capacity absent");for(;*s;s++){if(*s<'0'||*s>'9')bad("invalid capacity");n=n*10+*s-'0';if(n>0xffffffffu)bad("capacity overflow");}return (unsigned)n;}
static void val(const char*k,unsigned long long n){char b[24];print(k);print("=");number(b,n);print(b);print("\n");}
static int fd=-1,split;static const char*source,*directory;static unsigned sectors;
static void readat(unsigned long long pos,void*buf,unsigned size){
 char path[1024],n[24];int f=fd;unsigned off=(unsigned)pos;
 if(pos+size>(unsigned long long)sectors*512)bad("read beyond eMMC");
 if(split){
  unsigned chunk=pos>>28,at=pos&0xfffffff;if(at+size>268435456u)bad("split read crosses chunk");
  if(len(source)>900)bad("backup path too long");cp(path,source,len(source));unsigned i=len(source);path[i++]='/';cp(path+i,"emmc.part",9);i+=9;
  if(chunk<10)path[i++]='0';number(n,chunk);cp(path+i,n,len(n)+1);f=op(path,0);if(f<0)bad("backup chunk absent");off=at;
 }else off=(unsigned)pos;
 if(sk(f,split?off:pos)<0)bad("seek failed");unsigned done=0;while(done<size){long r=rd(f,(unsigned char*)buf+done,size-done);if(r<=0)bad("short device read");done+=r;}
 if(split)cl(f);
}
static void writefile(const char*name,const void*data,unsigned size){
 char path[1024];unsigned n=len(directory);if(n+len(name)+2>sizeof(path))bad("output path too long");cp(path,directory,n);path[n++]='/';cp(path+n,name,len(name)+1);
 int f=op(path,1|64|512);if(f<0)bad("RAM output open failed");unsigned at=0;while(at<size){long r=wr(f,(const unsigned char*)data+at,size-at);if(r<=0)bad("RAM output write failed");at+=r;}cl(f);
}
static void entry(unsigned char*p,unsigned type,unsigned start,unsigned count){zero(p,16);p[1]=p[5]=0xfe;p[2]=p[3]=p[6]=p[7]=0xff;p[4]=type;put(p+8,start);put(p+12,count);}
static void bound(unsigned start,unsigned count){if(!count||(unsigned long long)start+count>sectors)bad("partition outside eMMC");}
static unsigned starts[5],counts[5],ebrs[5];
static int mainwork(int argc,char**argv){
 if(argc!=5)bad("usage: device-layout plan|check|snapshot DEVICE_OR_BACKUP SECTORS RAM_DIRECTORY");
 int check=eq(argv[1],"check",6);split=eq(argv[1],"snapshot",9);
 if(!check&&!split&&!eq(argv[1],"plan",5))bad("unknown command");
 source=argv[2];sectors=parse(argv[3]);directory=argv[4];
 if(sectors<14680064u||sectors>33554432u||sectors%128)bad("unsupported capacity/alignment (7..16GiB)");
 if(!split){fd=op(source,0);if(fd<0)bad("device read open failed");}
 unsigned char hw[110],ivt[4],mbr[512],ebr[512],magic[8];
 readat(524288,hw,110);readat(1024,ivt,4);
 if(!eq(hw,"HW CONFIG ",10)||hw[10]!='v'||hw[15]<48||hw[15]>94||hw[16]!=67||hw[29]!=31||hw[32]!=4||hw[33]!=2||hw[43]!=5||hw[47]!=8)bad("not RIDI Paper Pro E70Q10 hardware");
 if(hw[20]!=8||hw[23]!=14)bad("unsupported Paper Pro Wi-Fi/touch hardware");
 if(ivt[0]!=0xd1||ivt[1]!=0||ivt[2]!=0x20||(ivt[3]!=0x40&&ivt[3]!=0x41))bad("missing i.MX bootloader IVT");
 readat(0,mbr,512);if(mbr[510]!=0x55||mbr[511]!=0xaa)bad("invalid MBR signature");
 unsigned char*p1=mbr+446,*p2=mbr+462,*p3=mbr+478,*p4=mbr+494;
 if(p2[4]!=0x83||get(p2+8)!=38912||get(p2+12)!=65536)bad("unsupported recovery geometry");
 readat((unsigned long long)38912*512,magic,8);if(!eq(magic,"ANDROID!",8))bad("recovery image absent");
 unsigned base=get(p3+8),extent=get(p3+12);if(p3[4]!=5&&p3[4]!=0x0f)bad("extended partition absent");bound(base,extent);
 int stock=p1[4]==0x83&&get(p1+8)==2048&&get(p1+12)>=12224&&get(p1+12)<=12288&&(base==104448||base==104449);
 int unified=p1[4]==0x83&&get(p1+8)==104448&&get(p1+12)==65536&&base==169984;
 if(!stock&&!unified)bad("unknown Paper Pro partition layout");
 if(stock){if(p4[4]!=0x0b&&p4[4]!=0x0c&&p4[4]!=0x83)bad("stock media partition missing");bound(get(p4+8),get(p4+12));if(get(p4+8)<base+extent)bad("overlapping stock media partition");}
 if(unified&&!eq(p4,"\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0",16))bad("unexpected fourth primary partition");
 unsigned at=base,previous=104448;
 for(unsigned i=0;i<5;i++){
  readat((unsigned long long)at*512,ebr,512);
  if(ebr[510]!=0x55||ebr[511]!=0xaa||ebr[450]!=0x83)bad("invalid logical partition");
  unsigned rel=get(ebr+454),count=get(ebr+458);unsigned long long absolute=(unsigned long long)at+rel;
  if(!rel||absolute>0xffffffffu)bad("invalid logical offset");bound((unsigned)absolute,count);
  if(absolute<previous||absolute<base||absolute+count>(unsigned long long)base+extent)bad("overlapping logical partitions");
  starts[i]=(unsigned)absolute;counts[i]=count;ebrs[i]=at;previous=absolute+count;
  unsigned next=get(ebr+470),nc=get(ebr+474);
  if(i==4){if(next||nc||ebr[466])bad("extra logical partitions");}
  else {if(!next||!nc||(ebr[466]!=5&&ebr[466]!=0x0f))bad("logical chain truncated");unsigned long long n=(unsigned long long)base+next;if(n<=at||n<previous||n+nc>(unsigned long long)base+extent)bad("invalid EBR link");at=n;}
 }
 if(stock&&(counts[0]!=786416||counts[1]!=786416||counts[3]!=16368||counts[4]!=8176))bad("unsupported stock logical geometry");
 unsigned end=sectors&~2047u;
 unsigned desired[5]={172032,2271232,2404352,end-536576,end-10240};
 unsigned size[5]={2097152,131072,desired[3]-2048-2404352,524288,8192};
 unsigned positions[5]={169984,2269184,2402304,desired[3]-2048,desired[4]-2048};
 if(unified){
  if(extent!=sectors-base)bad("unified extended size differs");
  for(unsigned i=0;i<5;i++)if(starts[i]!=desired[i]||counts[i]!=size[i]||ebrs[i]!=positions[i])bad("unified geometry differs from capacity");
 }
 if(check&&!unified)bad("initial installation required");
 val("SECTORS",sectors);val("BYTES",(unsigned long long)sectors*512);
 print(stock?"CURRENT_KIND=stock\n":"CURRENT_KIND=unified\n");
 val("CURRENT_MISC_START",starts[4]);val("CURRENT_MISC_SECTORS",counts[4]);
 val("DATA_START",desired[2]);val("DATA_SECTORS",size[2]);val("DATA_BYTES",(unsigned long long)size[2]*512);
 val("VENDOR_START",desired[3]);val("MISC_START",desired[4]);
 print("TABLE_SECTORS="); /* shell-safe comma list */
 for(unsigned i=0;i<5;i++){char n[24];if(i)print(",");number(n,positions[i]);print(n);}print("\n");
 val("PCB_REV",hw[57]);val("VCOM_RAW",((unsigned)hw[55]<<8)|hw[56]);
 if(!check){
  writefile("original-mbr.bin",mbr,512);
  entry(mbr+446,0x83,104448,65536);entry(mbr+478,5,169984,sectors-169984);zero(mbr+494,16);
  writefile("mbr.sector0.bin",mbr,512);
  for(unsigned i=0;i<5;i++){
   zero(ebr,512);entry(ebr+446,0x83,desired[i]-positions[i],size[i]);
   if(i<4)entry(ebr+462,5,positions[i+1]-169984,sectors-positions[i+1]);ebr[510]=0x55;ebr[511]=0xaa;
   char name[64],n[24];cp(name,"ebr.sector",10);number(n,positions[i]);unsigned l=len(n);cp(name+10,n,l);cp(name+10+l,".bin",5);writefile(name,ebr,512);
  }
 }
 if(fd>=0)cl(fd);return 0;
}
#ifdef HOST
int main(int argc,char**argv){return mainwork(argc,argv);}
#else
void start(int argc,char**argv){quit(mainwork(argc,argv));}
__attribute__((naked,noreturn)) void _start(void){__asm__ volatile("ldr r0, [sp]\nadd r1, sp, #4\nb start");}
#endif
