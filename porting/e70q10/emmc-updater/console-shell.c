/* Attach inherited USB tty explicitly; do not guess a UART via cttyhack. */
#ifdef HOST
#include <unistd.h>
#include <sys/ioctl.h>
int main(void) {
 if(setsid()<0 || ioctl(0,TIOCSCTTY,0)<0)return 1;
 char *args[]={"/bin/sh","-i",0};
 char *env[]={"PATH=/bin","HOME=/root","TERM=vt100","PS1=RAM# ",0};
 execve(args[0],args,env);return 1;
}
#else
static int call(int nr,int a,int b,int c) {
 register int r0 __asm__("r0")=a,r1 __asm__("r1")=b,r2 __asm__("r2")=c,r7 __asm__("r7")=nr;
 __asm__ volatile("svc 0" : "+r"(r0):"r"(r1),"r"(r2),"r"(r7):"memory");return r0;
}
void _start(void) {
 static char *args[]={"/bin/sh","-i",0};
 static char *env[]={"PATH=/bin","HOME=/root","TERM=vt100","PS1=RAM# ",0};
 if(call(66,0,0,0)>=0 && call(54,0,0x540E,0)>=0)call(11,(int)args[0],(int)args,(int)env);
 call(4,2,(int)"USB shell attach failed\n",24);call(1,1,0,0);__builtin_unreachable();
}
#endif
