/* Linux ARM EABI freestanding byte counter: no libc or 32-bit wc counter. */
#ifdef HOST
#include <unistd.h>
#define callread(p,n) read(0,p,n)
#define callwrite(p,n) write(1,p,n)
#define finish(n) return n
int main(void) {
#else
static int syscall3(int nr,int a,void *b,unsigned n) {
 register int r0 __asm__("r0")=a;
 register void *r1 __asm__("r1")=b;
 register unsigned r2 __asm__("r2")=n;
 register int r7 __asm__("r7")=nr;
 __asm__ volatile("svc 0" : "+r"(r0) : "r"(r1),"r"(r2),"r"(r7) : "memory");
 return r0;
}
#define callread(p,n) syscall3(3,0,p,n)
#define callwrite(p,n) syscall3(4,1,p,n)
#define finish(n) do {syscall3(1,n,0,0);__builtin_unreachable();} while(0)
void _start(void) {
#endif
 static unsigned char buf[1048576];
 unsigned long long total=0;
 int n;
 while((n=callread(buf,sizeof(buf)))>0) total+=(unsigned)n;
 if(n<0) finish(1);
 char out[32];int at=31;out[at]='\n';
 do {out[--at]='0'+total%10;total/=10;} while(total);
 int len=32-at;
 if(callwrite(out+at,len)!=len) finish(1);
 finish(0);
}
