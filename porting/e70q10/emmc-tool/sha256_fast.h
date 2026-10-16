/* SHA-256 streaming wrapper. ARM compression is the vendored OpenSSL assembly.
 * Host reference intentionally uses portable C for independent cross checks. */
typedef struct { unsigned h[8]; unsigned long long bytes; unsigned used; unsigned char tail[64]; } FastSHA;
#ifndef HOST
extern void sha256_block_data_order(unsigned*,const void*,unsigned);
extern void sha256_block_data_order_neon(unsigned*,const void*,unsigned);
static int fast_neon;
static void sha_cpu_init(void){
#ifdef SHA_TEST_SCALAR
 return;
#endif
 unsigned aux[128];int f=op("/proc/self/auxv",0);if(f<0)return;
 long n=rd(f,aux,sizeof(aux));cl(f);
 for(unsigned i=0;n>0&&i+1<(unsigned)n/4;i+=2)if(aux[i]==16){fast_neon=(aux[i+1]&4096)!=0;break;}
}
static void sha_blocks(unsigned*h,const unsigned char*p,unsigned n){if(fast_neon)sha256_block_data_order_neon(h,p,n);else sha256_block_data_order(h,p,n);}
#else
static void sha_cpu_init(void){}
static unsigned ror(unsigned x,unsigned n){return (x>>n)|(x<<(32-n));}
static void sha_blocks(unsigned*h,const unsigned char*p,unsigned blocks){
 static const unsigned k[64]={0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2};
 while(blocks--){unsigned w[64];for(unsigned i=0;i<16;i++)w[i]=((unsigned)p[4*i]<<24)|((unsigned)p[4*i+1]<<16)|((unsigned)p[4*i+2]<<8)|p[4*i+3];for(unsigned i=16;i<64;i++)w[i]=w[i-16]+(ror(w[i-15],7)^ror(w[i-15],18)^(w[i-15]>>3))+w[i-7]+(ror(w[i-2],17)^ror(w[i-2],19)^(w[i-2]>>10));
 unsigned a=h[0],b=h[1],c=h[2],d=h[3],e=h[4],f=h[5],g=h[6],v=h[7];
 for(unsigned i=0;i<64;i++){unsigned t=v+(ror(e,6)^ror(e,11)^ror(e,25))+((e&f)^(~e&g))+k[i]+w[i];unsigned z=(ror(a,2)^ror(a,13)^ror(a,22))+((a&b)^(a&c)^(b&c));v=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+z;}
 h[0]+=a;h[1]+=b;h[2]+=c;h[3]+=d;h[4]+=e;h[5]+=f;h[6]+=g;h[7]+=v;p+=64;
 }
}
#endif
static void sha_init(FastSHA*s){static const unsigned iv[8]={0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19};for(unsigned i=0;i<8;i++)s->h[i]=iv[i];s->bytes=0;s->used=0;}
static void sha_add(FastSHA*s,const unsigned char*p,unsigned n){
 s->bytes+=n;if(s->used){while(n&&s->used<64){s->tail[s->used++]=*p++;n--;}if(s->used==64){sha_blocks(s->h,s->tail,1);s->used=0;}}
 if(n>=64){unsigned blocks=n/64;sha_blocks(s->h,p,blocks);p+=blocks*64;n-=blocks*64;}
 while(n--){s->tail[s->used++]=*p++;}
}
static void sha_hex(FastSHA*s,char*out){unsigned long long bits=s->bytes*8;unsigned at=s->used;s->tail[at++]=128;if(at>56){while(at<64)s->tail[at++]=0;sha_blocks(s->h,s->tail,1);at=0;}while(at<56)s->tail[at++]=0;for(unsigned i=0;i<8;i++)s->tail[56+i]=(unsigned char)(bits>>(56-8*i));sha_blocks(s->h,s->tail,1);const char*x="0123456789abcdef";for(unsigned i=0;i<32;i++){unsigned v=(s->h[i/4]>>(24-8*(i%4)))&255;out[2*i]=x[v>>4];out[2*i+1]=x[v&15];}out[64]='\n';}
