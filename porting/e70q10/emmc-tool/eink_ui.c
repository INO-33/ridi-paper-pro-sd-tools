/* RAM-only framebuffer observer. Never opens eMMC/SD; framebuffer failures do
 * not affect installer. Manual EPDC updates, cropped to changed pixels. */
#ifdef HOST
#define _FILE_OFFSET_BITS 64
#include <unistd.h>
#include <fcntl.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <linux/fb.h>
#include <time.h>
static long op(const char*p,int f){return open(p,f,0600);}
static long rd(int f,void*p,unsigned n){return read(f,p,n);}
static long wr(int f,const void*p,unsigned n){return write(f,p,n);}
static void cl(int f){close(f);}
#ifdef UI_TEST
int test_io(int,unsigned,void*);
static int io(int f,unsigned n,void*p){return test_io(f,n,p);}
#else
static int io(int f,unsigned n,void*p){return ioctl(f,n,p);}
#endif
static unsigned char*map(int f,unsigned n){return mmap(0,n,3,1,f,0);}
static void nap(){struct timespec t={1,0};nanosleep(&t,0);}
#else
void *memset(void*p,int value,unsigned n){volatile unsigned char*q=p;for(unsigned i=0;i<n;i++)q[i]=value;return p;}
static int sys(int n,unsigned a,unsigned b,unsigned c,unsigned d,unsigned e,unsigned f){
 register unsigned r0 __asm__("r0")=a,r1 __asm__("r1")=b,r2 __asm__("r2")=c,r3 __asm__("r3")=d,r4 __asm__("r4")=e,r5 __asm__("r5")=f,r7 __asm__("r7")=n;
 __asm__ volatile("svc 0":"+r"(r0):"r"(r1),"r"(r2),"r"(r3),"r"(r4),"r"(r5),"r"(r7):"memory");return (int)r0;
}
static long op(const char*p,int f){return sys(5,(unsigned)p,f,0600,0,0,0);}
static long rd(int f,void*p,unsigned n){return sys(3,f,(unsigned)p,n,0,0,0);}
static long wr(int f,const void*p,unsigned n){return sys(4,f,(unsigned)p,n,0,0,0);}
static void cl(int f){sys(6,f,0,0,0,0,0);}
static int io(int f,unsigned n,void*p){return sys(54,f,n,(unsigned)p,0,0,0);}
static unsigned char*map(int f,unsigned n){return (void*)sys(192,0,n,3,1,f,0);}
static void nap(){unsigned t[2]={1,0};sys(162,(unsigned)t,0,0,0,0,0);}
#endif
#define W 700
#define H 900
#define ASSETS (700*180+23*600*70+95*20*32)
static unsigned char assets[ASSETS],canvas[W*H],previous[W*H];
static unsigned len(const char*s){unsigned n=0;while(s[n])n++;return n;}
static int eq(const char*a,const char*b){while(*a&&*a==*b){a++;b++;}return *a==*b;}
static unsigned long long num(const char*s){unsigned long long n=0;while(*s>='0'&&*s<='9'){n=n*10+*s++-'0';if(n>17179869184ull)return 0;}return n;}
static void cp(char*d,const char*s,unsigned max){unsigned i=0;while(s[i]&&i+1<max){d[i]=s[i];i++;}d[i]=0;}
static unsigned number(char*d,unsigned n){char rev[16];unsigned a=0,b=0;do{rev[a++]='0'+n%10;n/=10;}while(n);while(a)d[b++]=rev[--a];d[b]=0;return b;}
static int error(const char*s){wr(2,s,len(s));wr(2,"\n",1);return 1;}
static int readfile(const char*p,char*b,unsigned cap){int fd=op(p,0);if(fd<0)return 0;unsigned at=0;while(at+1<cap){long n=rd(fd,b+at,cap-1-at);if(n<=0)break;at+=n;}cl(fd);b[at]=0;return at;}
static int load(const char*p){int fd=op(p,0);if(fd<0)return 0;unsigned at=0;while(at<ASSETS){long n=rd(fd,assets+at,ASSETS-at);if(n<=0){cl(fd);return 0;}at+=n;}cl(fd);return 1;}
static void blit(const unsigned char*p,unsigned w,unsigned h,unsigned x,unsigned y){for(unsigned j=0;j<h&&y+j<H;j++)for(unsigned i=0;i<w&&x+i<W;i++)canvas[(y+j)*W+x+i]=p[j*w+i];}
static void label(unsigned n,unsigned y){blit(assets+700*180+n*600*70,600,70,50,y);}
static void text(const char*s,unsigned x,unsigned y,unsigned scale){for(unsigned k=0;s[k]&&k<60;k++){unsigned ch=(unsigned char)s[k];if(ch<32||ch>126)ch='?';if(x+20*scale>W-30){x=50;y+=36*scale;}if(y+32*scale>H)break;
 const unsigned char*g=assets+700*180+23*600*70+(ch-32)*20*32;for(unsigned j=0;j<32*scale;j++)for(unsigned i=0;i<20*scale;i++)canvas[(y+j)*W+x+i]=g[(j/scale)*20+i/scale];x+=20*scale;}}
static int stage(const char*p){const char*keys[]={"starting","checking","backup","backup-check","layout","format","write","verify","success","failed","completed","idle"};for(int i=0;i<12;i++)if(eq(p,keys[i]))return i;return 11;}
static void render(const char*phase,const char*role,unsigned long long done,unsigned long long total,const char*detail){
 for(unsigned i=0;i<W*H;i++)canvas[i]=255;blit(assets,700,180,0,85);int s=stage(phase);label(s,340);
 if(eq(role,"system"))label(12,430);else if(eq(role,"vendor"))label(13,430);else if(eq(role,"boot"))label(14,430);else if(eq(role,"userdata"))label(19,430);else if(eq(role,"cache"))label(20,430);else if(s==2||s==3)label(eq(role,"boot0")||eq(role,"boot1")?21:18,430);else text(role,50,445,1);
 unsigned pct=total?(unsigned)((done>total?total:done)*100/total):0;
 for(unsigned y=555;y<595;y++)for(unsigned x=55;x<645;x++){int edge=x<58||x>=642||y<558||y>=592;canvas[y*W+x]=(edge||(total&&x<58+pct*584/100))?0:255;}
 char p[16];if(total){unsigned n=number(p,pct);p[n++]='%';p[n]=0;}else cp(p,"...",sizeof(p));text(p,(W-len(p)*40)/2,630,2);
 text(detail,50,735,1);label(s==8?16:(s==9?17:(s==10?22:15)),825);
}
static unsigned packgray(unsigned gray,unsigned*v){if(v[6]==8)return v[7]==2?255-gray:gray;unsigned px=0;for(unsigned i=8;i<=14;i+=3){unsigned shift=v[i],bits=v[i+1];if(bits&&bits<=8&&shift+bits<=32)px|=((gray*((1u<<bits)-1)+127)/255)<<shift;}if(v[17]<32&&v[18]&&v[18]<=8&&v[17]+v[18]<=32)px|=((1u<<v[18])-1)<<v[17];return px;}
static int draw(int fd,unsigned char*fb,unsigned*v,unsigned stride,int first,int terminal){
 unsigned width=v[0],height=v[1];unsigned dw=width,dh=width*H/W;if(dh>height){dh=height;dw=height*W/H;}unsigned ox=(width-dw)/2,oy=(height-dh)/2,bpp=v[6]/8;
 unsigned left=width,top=height,right=0,bottom=0;int changed=0;
 unsigned xbegin=0,xend=width,ybegin=0,yend=height;
 if(!first){
  unsigned a=W,b=H,c=0,d=0;int diff=0;
  for(unsigned y=0;y<H;y++)for(unsigned x=0;x<W;x++)if(canvas[y*W+x]!=previous[y*W+x]){if(x<a)a=x;if(y<b)b=y;if(x>c)c=x;if(y>d)d=y;diff=1;}
  if(!diff)return 0;
  xbegin=ox+a*dw/W;ybegin=oy+b*dh/H;xend=ox+((c+1)*dw+W-1)/W;yend=oy+((d+1)*dh+H-1)/H;
 }
 for(unsigned y=ybegin;y<yend;y++)for(unsigned x=xbegin;x<xend;x++){
  int inside=x>=ox&&x<ox+dw&&y>=oy&&y<oy+dh;unsigned at=inside?((y-oy)*H/dh)*W+(x-ox)*W/dw:0;unsigned gray=inside?canvas[at]:255;
  if(!first&&(!inside||gray==previous[at]))continue;
  unsigned px=packgray(gray,v);unsigned char*dest=fb+(y+v[5])*stride+(x+v[4])*bpp;for(unsigned i=0;i<bpp;i++)dest[i]=px>>(8*i);
  if(x<left)left=x;if(y<top)top=y;if(x>right)right=x;if(y>bottom)bottom=y;changed=1;
 }
 if(!changed)return 0;
 unsigned update[18]={0};update[0]=first||terminal?0:top;update[1]=first||terminal?0:left;update[2]=first||terminal?width:right-left+1;update[3]=first||terminal?height:bottom-top+1;update[4]=257;update[5]=first||terminal?1:0;update[7]=0x1000;
 int submit_rc=io(fd,0x4048462e,update);
 if(submit_rc<0){char code[24];unsigned n=number(code,(unsigned)(-submit_rc));wr(2,"EPDC errno=",11);wr(2,code,n);wr(2,"\n",1);return -1;}
 for(unsigned i=0;i<W*H;i++)previous[i]=canvas[i];return 1;
}
static int mainwork(int argc,char**argv){
 if(argc==9&&eq(argv[1],"--preview")){if(!load(argv[2]))return error("UI assets missing");render(argv[3],argv[4],num(argv[5]),num(argv[6]),argv[7]);int out=op(argv[8],1|64|512);if(out<0)return 1;wr(out,"P5\n700 900\n255\n",15);unsigned at=0;while(at<W*H){long n=wr(out,canvas+at,W*H-at);if(n<=0)return 1;at+=n;}cl(out);return 0;}
 if(argc!=1)return error("eink-ui: invalid arguments");if(!load("/etc/updater-ui.bin"))return error("UI assets missing; USB logs remain available");
 int fd=op("/dev/fb0",2);if(fd<0)return error("Framebuffer unavailable; USB logs remain available");unsigned v[40]={0},stride,bytes;
 if(io(fd,0x4600,v)<0)return error("Framebuffer geometry unavailable");
 /* Firmware is prepared in RAM before launch; force set_par to retry init. */
 v[21]|=128;int mode_rc=io(fd,0x4601,v);if(mode_rc<0)wr(2,"Framebuffer init retry rejected\n",32);
 if(io(fd,0x4600,v)<0)return error("Framebuffer geometry reread failed");
#ifdef HOST
 struct fb_fix_screeninfo fix;if(io(fd,0x4602,&fix)<0)return 1;stride=fix.line_length;bytes=fix.smem_len;
#else
 unsigned char fix[80]={0};if(io(fd,0x4602,fix)<0)return 1;stride=*(unsigned*)(fix+44);bytes=*(unsigned*)(fix+20);
#endif
 if(v[0]<320||v[1]<400||v[0]>4096||v[1]>4096||(v[6]!=8&&v[6]!=16&&v[6]!=32)||v[4]+v[0]>v[2]||v[5]+v[1]>v[3]||(v[4]+v[0])*(v[6]/8)>stride||(unsigned long long)(v[5]+v[1])*stride>bytes||bytes>134217728)return error("Unsupported framebuffer geometry; USB logs remain available");
 unsigned char*fb=map(fd,bytes);if((unsigned long)fb>=(unsigned long)-4095)return error("Framebuffer mmap failed");io(fd,0x4611,0);
 int first=1;unsigned tick=0,lastpct=~0u;char lastphase[64]="",lastrole[128]="",lastdetail[256]="";
 for(;;){char state[1024],progress[128],*lines[5];unsigned n=0;
  if(!readfile("/run/updater-ui.state",state,sizeof(state)))cp(state,"starting\n\n0\n0\n",sizeof(state));lines[n++]=state;for(unsigned i=0;state[i]&&n<5;i++)if(state[i]=='\n'){state[i]=0;lines[n++]=state+i+1;}while(n<5)lines[n++]="";
  for(unsigned i=0;lines[4][i];i++)if(lines[4][i]=='\n'){lines[4][i]=0;break;}
  unsigned long long done=num(lines[2]),total=num(lines[3]);
  if(readfile("/run/updater-ui.progress",progress,sizeof(progress))){unsigned i=0;while(progress[i]&&progress[i]!=' ')i++;if(progress[i]==' '){progress[i]=0;unsigned long long local=num(progress),localtotal=num(progress+i+1);if((eq(lines[0],"backup")||eq(lines[0],"backup-check"))&&local<=localtotal)done+=local;else if(localtotal==total&&local<=total)done=local;}}
  int terminal=eq(lines[0],"success")||eq(lines[0],"failed")||eq(lines[0],"completed");
  unsigned pct=total?(unsigned)(done*100/total):0;
  int visible_change=!eq(lastphase,lines[0])||!eq(lastrole,lines[1])||!eq(lastdetail,lines[4])||pct!=lastpct;
  if(first||(visible_change&&(terminal||!eq(lastphase,lines[0])||tick%2==0))){render(lines[0],lines[1],done,total,lines[4]);int result=draw(fd,fb,v,stride,first,terminal&&!eq(lastphase,lines[0]));if(result>=0){first=0;lastpct=pct;cp(lastphase,lines[0],sizeof(lastphase));cp(lastrole,lines[1],sizeof(lastrole));cp(lastdetail,lines[4],sizeof(lastdetail));}else if(result<0&&tick%10==0){
   wr(2,"EPDC submit retry\n",18);
   /* Early asynchronous firmware fallback can outlive our first set_par.
    * Retry only while submits fail; normal display updates stay unchanged. */
   if(io(fd,0x4600,v)==0){v[21]|=128;io(fd,0x4601,v);}
  }}
  tick++;nap();
 }
}
#ifdef HOST
int main(int argc,char**argv){return mainwork(argc,argv);}
#else
void start(int argc,char**argv){int rc=mainwork(argc,argv);sys(1,rc,0,0,0,0,0);__builtin_unreachable();}
__attribute__((naked,noreturn)) void _start(void){__asm__ volatile("ldr r0, [sp]\nadd r1, sp, #4\nb start");}
#endif
