/* Read each source byte once; copy to a NEW backup file and stream identical
 * bytes to stdout for concurrent SHA256. fsync + discard clean file cache
 * before the caller performs its independent SD readback hash. */
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
static int bad(const char*s){unsigned n=0;while(s[n])n++;wr(2,s,n);return 1;}
static int parse(const char*s,unsigned long long*out){unsigned long long n=0;if(!*s)return 0;for(;*s;s++){if(*s<'0'||*s>'9'||n>17179869184ull/10)return 0;n=n*10+*s-'0';if(n>17179869184ull)return 0;}*out=n;return 1;}
#include "ui_progress.h"
#include "sha256_fast.h"
static unsigned char buf[4194304];
static int writeall(int fd,unsigned n){unsigned at=0;while(at<n){long r=wr(fd,buf+at,n-at);if(r==-4)continue;if(r<=0)return 0;at+=r;}return 1;}
static int isread(const char*s){return s[0]=='-'&&s[1]=='-'&&s[2]=='r'&&s[3]=='e'&&s[4]=='a'&&s[5]=='d'&&!s[6];}
static int equal(const char*a,const char*b){while(*a&&*a==*b){a++;b++;}return *a==*b;}
static int mainwork(int argc,char**argv){
 int hash_only=argc==5&&equal(argv[1],"--hash");
 int copy_hash=argc==6&&equal(argv[1],"--copy-hash");
 int read_only=hash_only||(argc==5&&isread(argv[1]));
 unsigned long long offset,left;
 const char*src=copy_hash?argv[2]:(read_only?argv[2]:argc>1?argv[1]:"");
 const char*dst=copy_hash?argv[3]:argc>2?argv[2]:"";
 if((argc!=5&&!copy_hash)||!parse(argv[copy_hash?4:3],&offset)||!parse(argv[copy_hash?5:4],&left)||(!left&&!hash_only)||(!read_only&&left>268435456ull)||offset+left>17179869184ull)return bad("STOP: invalid backup-copy range\n");
 int source=op(src,0);if(source<0)return bad("STOP: backup source open failed\n");
 if(sk(source,offset)<0){cl(source);return bad("STOP: backup source seek failed\n");}
 int dest=read_only?-1:op(dst,1|64|128);
 if(!read_only&&dest<0){cl(source);return bad("STOP: backup target exists or cannot be created\n");}
 FastSHA hash;sha_cpu_init();sha_init(&hash);
 unsigned long long total=left;ui_progress(0,total);
 while(left){
  unsigned need=left>sizeof(buf)?sizeof(buf):(unsigned)left,have=0;
  while(have<need){long r=rd(source,buf+have,need-have);if(r==-4)continue;if(r<=0){cl(source);if(dest>=0)cl(dest);return bad("STOP: backup source short read\n");}have+=r;}
  if(hash_only||copy_hash)sha_add(&hash,buf,have);
  if((!read_only&&!writeall(dest,have))||(!(hash_only||copy_hash)&&!writeall(1,have))){cl(source);if(dest>=0)cl(dest);return bad("STOP: backup output/hash stream failed\n");}
  left-=have;ui_progress(total-left,total);
 }
 cl(source);
 if(!read_only){
  if(flush(dest)<0){cl(dest);return bad("STOP: backup flush failed\n");}
  if(discard(dest)!=0){cl(dest);return bad("STOP: backup cache discard failed\n");}
  cl(dest);
 }
 if(hash_only||copy_hash){char hex[65];sha_hex(&hash,hex);long n=wr(1,hex,65);if(n!=65)return bad("STOP: hash output failed\n");}
 return 0;
}
#ifdef HOST
int main(int argc,char**argv){return mainwork(argc,argv);}
#else
void start(int argc,char**argv){int rc=mainwork(argc,argv);call(1,rc,0,0,0,0,0);__builtin_unreachable();}
__attribute__((naked,noreturn)) void _start(void){__asm__ volatile("ldr r0, [sp]\nadd r1, sp, #4\nb start");}
#endif
