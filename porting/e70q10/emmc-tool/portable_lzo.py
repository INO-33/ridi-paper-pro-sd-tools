"""Bounded pure Python LZO1X/lzop decoder; no DLL, WSL or executable needed.
LZO1X state machine adapted from the BSP Linux lzo1x_decompress_safe.c,
Copyright 1996-2012 Markus F.X.J. Oberhumer; GPL-2.0, see vendor/lzo/LICENSE.
"""
import struct,zlib

def lzo1x(data,expected):
    ip=0;out=bytearray();state=0
    def byte():
        nonlocal ip
        if ip>=len(data):raise ValueError('잘린 LZO 데이터')
        v=data[ip];ip+=1;return v
    def word():return byte()|(byte()<<8)
    def extend(base):
        t=base;b=byte()
        while b==0:
            t+=255
            if t>expected:raise ValueError('LZO 길이 초과')
            b=byte()
        return t+b
    def literal(n):
        nonlocal ip
        if ip+n>len(data) or len(out)+n>expected:raise ValueError('LZO literal 범위 초과')
        out.extend(data[ip:ip+n]);ip+=n
    def match(dist,n):
        if dist<=0 or dist>len(out) or len(out)+n>expected:raise ValueError('LZO match 범위 초과')
        start=len(out)-dist
        if n<=dist:out.extend(out[start:start+n])
        else:
            pattern=bytes(out[start:]);out.extend(pattern*(n//dist)+pattern[:n%dist])
    if len(data)<3:raise ValueError('잘린 LZO 헤더')
    if data[0]>17:
        n=byte()-17;literal(n);state=n if n<4 else 4
    while True:
        t=byte()
        if t<16:
            if state==0:
                if t==0:t=extend(15)
                literal(t+3);state=4;continue
            nxt=t&3
            if state!=4:dist=1+(t>>2)+(byte()<<2);n=2
            else:dist=2049+(t>>2)+(byte()<<2);n=3
        elif t>=64:
            nxt=t&3;dist=1+((t>>2)&7)+(byte()<<3);n=(t>>5)+1
        elif t>=32:
            n=(t&31)+2
            if n==2:n+=extend(31)
            v=word();dist=1+(v>>2);nxt=v&3
        else:
            dist=(t&8)<<11;n=(t&7)+2
            if n==2:n+=extend(7)
            v=word();dist+=v>>2;nxt=v&3
            if dist==0:
                if n!=3 or ip!=len(data) or len(out)!=expected:raise ValueError('LZO 종료/크기 오류')
                return bytes(out)
            dist+=0x4000
        match(dist,n);literal(nxt);state=nxt

def lzop(data,limit=128<<20):
    if data[:9]!=bytes.fromhex('894c5a4f000d0a1a0a'):raise ValueError('잘못된 lzop 헤더')
    at=9;start=at
    def take(n):
        nonlocal at
        if at+n>len(data):raise ValueError('잘린 lzop 파일')
        b=data[at:at+n];at+=n;return b
    def u32():return struct.unpack('>I',take(4))[0]
    version,library,needed=struct.unpack('>HHH',take(6));method,level=take(2)
    if version<0x940 or needed>0x1040 or method not in (1,2,3):raise ValueError('지원하지 않는 lzop 버전')
    flags=u32()
    if flags&0x840:raise ValueError('lzop filter/extra header는 지원하지 않습니다')
    take(4);take(4);take(4);take(take(1)[0]);end=at
    check=u32();actual=zlib.crc32(data[start:end]) if flags&0x1000 else zlib.adler32(data[start:end])
    if check!=(actual&0xffffffff):raise ValueError('lzop 헤더 체크섬 불일치')
    out=bytearray()
    while True:
        raw=u32()
        if not raw:return bytes(out)
        comp=u32()
        if not 0<comp<=raw<=16<<20 or len(out)+raw>limit:raise ValueError('lzop 블록 크기 초과')
        ad=u32() if flags&1 else None;cd=u32() if flags&0x100 else None
        ac=u32() if comp<raw and flags&2 else None;cc=u32() if comp<raw and flags&0x200 else None
        block=take(comp)
        if ac is not None and (zlib.adler32(block)&0xffffffff)!=ac:raise ValueError('lzop 압축 체크섬 오류')
        if cc is not None and (zlib.crc32(block)&0xffffffff)!=cc:raise ValueError('lzop 압축 CRC 오류')
        decoded=block if comp==raw else lzo1x(block,raw)
        if ad is not None and (zlib.adler32(decoded)&0xffffffff)!=ad:raise ValueError('lzop 원본 체크섬 오류')
        if cd is not None and (zlib.crc32(decoded)&0xffffffff)!=cd:raise ValueError('lzop 원본 CRC 오류')
        out.extend(decoded)
