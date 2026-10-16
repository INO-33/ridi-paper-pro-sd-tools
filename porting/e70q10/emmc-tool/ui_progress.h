/* Best-effort RAM-only progress; errors never alter copy/verification results. */
#ifdef HOST
#include <stdio.h>
#include <stdlib.h>
static int ui_open(const char*p){return open(p,O_WRONLY|O_CREAT|O_TRUNC,0600);}
static long ui_write(int f,const void*p,unsigned n){return write(f,p,n);}
static void ui_close(int f){close(f);}
static void ui_rename(const char*a,const char*b){rename(a,b);}
#else
static int ui_sys(int nr,unsigned a,unsigned b,unsigned c,unsigned d,unsigned e,unsigned f){
 register unsigned r0 __asm__("r0")=a,r1 __asm__("r1")=b,r2 __asm__("r2")=c,r3 __asm__("r3")=d,r4 __asm__("r4")=e,r5 __asm__("r5")=f,r7 __asm__("r7")=nr;
 __asm__ volatile("svc 0":"+r"(r0):"r"(r1),"r"(r2),"r"(r3),"r"(r4),"r"(r5),"r"(r7):"memory");return (int)r0;
}
static int ui_open(const char*p){return ui_sys(5,(unsigned)p,1|64|512,0600,0,0,0);}
static long ui_write(int f,const void*p,unsigned n){return ui_sys(4,f,(unsigned)p,n,0,0,0);}
static void ui_close(int f){ui_sys(6,f,0,0,0,0,0);}
static void ui_rename(const char*a,const char*b){ui_sys(38,(unsigned)a,(unsigned)b,0,0,0,0);}
#endif
static unsigned ui_num(char*p,unsigned long long n){char rev[24];unsigned a=0,b=0;do{rev[a++]='0'+n%10;n/=10;}while(n);while(a)p[b++]=rev[--a];return b;}
static void ui_progress(unsigned long long done,unsigned long long total){
#ifdef UI_NO_PROGRESS
 return; /* Isolated benchmark must not change the active installer UI state. */
#endif
 static unsigned previous=~0u;unsigned pct=total?(unsigned)(done*100/total):0;
 if(pct==previous&&done!=total)return;previous=pct;
 const char*path="/run/updater-ui.progress";
#ifdef HOST
 const char*override=getenv("UPDATER_PROGRESS");if(override)path=override;
#endif
 char tmp[512],data[64];unsigned i=0;while(path[i]&&i<480){tmp[i]=path[i];i++;}tmp[i++]='.';tmp[i++]='t';tmp[i++]='m';tmp[i++]='p';tmp[i]=0;
 unsigned n=ui_num(data,done);data[n++]=' ';n+=ui_num(data+n,total);data[n++]='\n';int fd=ui_open(tmp);if(fd<0)return;
 long wrote=ui_write(fd,data,n);ui_close(fd);if(wrote==(long)n)ui_rename(tmp,path);
}
