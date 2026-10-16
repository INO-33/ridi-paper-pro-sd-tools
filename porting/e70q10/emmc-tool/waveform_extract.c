/* RAM-only preparation of this device's own NTX waveform. eMMC opened read-only. */
#ifdef HOST
#define _FILE_OFFSET_BITS 64
#include <unistd.h>
#include <fcntl.h>
#include <sys/types.h>
#include <errno.h>
static long op(const char*p,int flags){return open(p,flags,0600);}
static long rd(int fd,void*p,unsigned n){long r=read(fd,p,n);return r<0?-errno:r;}
static long wr(int fd,const void*p,unsigned n){long r=write(fd,p,n);return r<0?-errno:r;}
static int sk(int fd,unsigned long long o){return lseek(fd,(off_t)o,SEEK_SET)<0?-1:0;}
static int flush(int fd){return fsync(fd);}
static int discard(int fd){return posix_fadvise(fd,0,0,POSIX_FADV_DONTNEED);}
static void cl(int fd){close(fd);}
#else
static int call(int nr,unsigned a,unsigned b,unsigned c,unsigned d,unsigned e,unsigned f){
 register unsigned r0 __asm__("r0")=a,r1 __asm__("r1")=b,r2 __asm__("r2")=c,r3 __asm__("r3")=d,r4 __asm__("r4")=e,r5 __asm__("r5")=f,r7 __asm__("r7")=nr;
 __asm__ volatile("svc 0":"+r"(r0):"r"(r1),"r"(r2),"r"(r3),"r"(r4),"r"(r5),"r"(r7):"memory");return (int)r0;
}
static long op(const char*p,int flags){return call(5,(unsigned)p,flags,0600,0,0,0);}
static long rd(int fd,void*p,unsigned n){return call(3,fd,(unsigned)p,n,0,0,0);}
static long wr(int fd,const void*p,unsigned n){return call(4,fd,(unsigned)p,n,0,0,0);}
static int sk(int fd,unsigned long long o){unsigned long long r;return call(140,fd,o>>32,(unsigned)o,(unsigned)&r,0,0);}
static int flush(int fd){return call(118,fd,0,0,0,0,0);}
/* ARM syscall signature: fd, advice, offset(lo,hi), len(lo,hi). */
static int discard(int fd){return call(270,fd,4,0,0,0,0);}
static void cl(int fd){call(6,fd,0,0,0,0,0);}
#endif

static int bad(const char*s){unsigned n=0;while(s[n])n++;wr(2,s,n);wr(2,"\n",1);return 1;}
static int readat(int fd,unsigned long long offset,void*p,unsigned n){if(sk(fd,offset)<0)return 0;unsigned at=0;while(at<n){long r=rd(fd,(unsigned char*)p+at,n-at);if(r==-4)continue;if(r<=0)return 0;at+=r;}return 1;}
static unsigned get(const unsigned char*p){return p[0]|(unsigned)p[1]<<8|(unsigned)p[2]<<16|(unsigned)p[3]<<24;}
static unsigned char buffer[4194304];
static int mainwork(int argc,char**argv){
 const char*source="/dev/mmcblk0",*target="/lib/firmware/imx/epdc/epdc_ED078KH1.fw";
#ifdef HOST
 if(argc!=3)return bad("waveform-extract SOURCE RAM_OUTPUT");source=argv[1];target=argv[2];
#else
 if(argc!=1)return bad("waveform-extract: no arguments allowed");
#endif
 int fd=op(source,0);if(fd<0)return bad("waveform source unavailable");
 unsigned char hw[110],header[512];
 if(!readat(fd,524288,hw,110)||!readat(fd,14335ull*512,header,512)){cl(fd);return bad("waveform metadata read failed");}
 const char*magic="HW CONFIG ";for(unsigned i=0;i<10;i++)if(hw[i]!=(unsigned char)magic[i]){cl(fd);return bad("not Paper Pro hwcfg");}
 if(hw[16]!=67||hw[29]!=31||hw[43]!=5||hw[47]!=8){cl(fd);return bad("unsupported Paper Pro hardware");}
 if(header[496]!=0xff||header[497]!=0xf5||header[498]!=0xaf||header[499]!=0xff){cl(fd);return bad("NTX waveform header absent");}
 unsigned size=get(header+504);if(size<1024||size>10u*1024*1024){cl(fd);return bad("invalid NTX waveform length");}
 int out=op(target,1|64|128);if(out<0){cl(fd);return bad("RAM waveform target unavailable or exists");}
 unsigned at=0;while(at<size){unsigned take=size-at;if(take>sizeof(buffer))take=sizeof(buffer);
  if(!readat(fd,14336ull*512+at,buffer,take)){cl(fd);cl(out);return bad("short waveform source");}
  unsigned done=0;while(done<take){long n=wr(out,buffer+done,take-done);if(n==-4)continue;if(n<=0){cl(fd);cl(out);return bad("RAM waveform write failed");}done+=n;}at+=take;
 }
 cl(fd);cl(out);wr(1,"OWN DEVICE WAVEFORM READY\n",26);return 0;
}
#ifdef HOST
int main(int argc,char**argv){return mainwork(argc,argv);}
#else
void start(int argc,char**argv){int rc=mainwork(argc,argv);call(1,rc,0,0,0,0,0);__builtin_unreachable();}
__attribute__((naked,noreturn)) void _start(void){__asm__ volatile("ldr r0, [sp]\nadd r1, sp, #4\nb start");}
#endif
