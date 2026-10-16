/* One-pass, bounded stream writer. No image hashing before/during writes.
 * Opens an existing target, writes exactly SECTORS*512 at START*512,
 * rejects short/long input and flushes before readback. Never writes overflow. */
#ifdef HOST
#define _FILE_OFFSET_BITS 64
#include <unistd.h>
#include <fcntl.h>
#include <sys/types.h>
#include <errno.h>
static long op(const char *p){return open(p,O_WRONLY);}
static long rd(void *p,unsigned n){long r=read(0,p,n);return r<0?-errno:r;}
static long wr(int fd,const void *p,unsigned n){long r=write(fd,p,n);return r<0?-errno:r;}
static int sk(int fd,unsigned long long o){return lseek(fd,(off_t)o,SEEK_SET)<0?-1:0;}
static int flush(int fd){return fsync(fd);}
static void cl(int fd){close(fd);}
#else
static int call(int nr,unsigned a,unsigned b,unsigned c,unsigned d,unsigned e){
 register unsigned r0 __asm__("r0")=a,r1 __asm__("r1")=b,r2 __asm__("r2")=c,r3 __asm__("r3")=d,r4 __asm__("r4")=e,r7 __asm__("r7")=nr;
 __asm__ volatile("svc 0":"+r"(r0):"r"(r1),"r"(r2),"r"(r3),"r"(r4),"r"(r7):"memory");return (int)r0;
}
static long op(const char*p){return call(5,(unsigned)p,1,0,0,0);}
static long rd(void*p,unsigned n){return call(3,0,(unsigned)p,n,0,0);}
static long wr(int fd,const void*p,unsigned n){return call(4,fd,(unsigned)p,n,0,0);}
static int sk(int fd,unsigned long long o){unsigned long long result;return call(140,fd,o>>32,(unsigned)o,(unsigned)&result,0);}
static int flush(int fd){return call(118,fd,0,0,0,0);}
static void cl(int fd){call(6,fd,0,0,0,0);}
#endif
static int err(const char*s){unsigned n=0;while(s[n])n++;
#ifdef HOST
 if(write(2,s,n)<0)return 1;
#else
 call(4,2,(unsigned)s,n,0,0);
#endif
 return 1;
}
static int parse(const char*s,unsigned*out){unsigned long long n=0;if(!*s)return 0;for(;*s;s++){if(*s<'0'||*s>'9')return 0;n=n*10+*s-'0';if(n>0xffffffffu)return 0;}*out=(unsigned)n;return 1;}
#include "ui_progress.h"
static unsigned char buf[4194304];
static int mainwork(int argc,char**argv){
 unsigned start,count;
 if(argc!=4||!parse(argv[2],&start)||!parse(argv[3],&count)||!count||count>2097152u||(unsigned long long)start+count>33554432u)return err("STOP: invalid stream-write range\n");
 int fd=op(argv[1]);if(fd<0)return err("STOP: stream target open failed\n");
 if(sk(fd,(unsigned long long)start*512)<0){cl(fd);return err("STOP: stream target seek failed\n");}
 unsigned long long left=(unsigned long long)count*512,total=left;ui_progress(0,total);
 while(left){
  unsigned need=left>sizeof(buf)?sizeof(buf):(unsigned)left,have=0;
  while(have<need){long r=rd(buf+have,need-have);if(r==-4)continue;if(r<=0){cl(fd);return err("STOP: short or unreadable image stream\n");}have+=r;}
  unsigned at=0;while(at<have){long r=wr(fd,buf+at,have-at);if(r==-4)continue;if(r<=0){cl(fd);return err("STOP: image write failed\n");}at+=r;}
  left-=have;ui_progress(total-left,total);
 }
 long r;do{r=rd(buf,1);}while(r==-4);
 if(r!=0){cl(fd);return err("STOP: image stream exceeds partition or cannot reach EOF\n");}
 if(flush(fd)<0){cl(fd);return err("STOP: image flush failed\n");}cl(fd);return 0;
}
#ifdef HOST
int main(int argc,char**argv){return mainwork(argc,argv);}
#else
void start(int argc,char**argv){int rc=mainwork(argc,argv);call(1,rc,0,0,0,0);__builtin_unreachable();}
__attribute__((naked,noreturn)) void _start(void){__asm__ volatile("ldr r0, [sp]\nadd r1, sp, #4\nb start");}
#endif
