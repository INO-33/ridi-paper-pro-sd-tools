#!/usr/bin/env python3
from PIL import Image,ImageDraw,ImageFont
from pathlib import Path
import sys
font='/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
f=lambda size:ImageFont.truetype(font,size,index=1)
head=Image.new('L',(700,180),255);d=ImageDraw.Draw(head)
d.text((350,28),'RIDI PAPER PRO',font=f(29),fill=0,anchor='mt')
d.text((350,85),'Android 8 설치 · 업데이트',font=f(38),fill=0,anchor='mt')
labels=['준비 중','기기와 파티션 확인 중','eMMC 백업 중','백업을 읽어 확인 중','파티션 배치 중','파일시스템 생성 중','이미지 기록 중','기록한 이미지 확인 중','완료','실패 · 재부팅하지 않습니다','이미 완료된 작업입니다','대기 중','시스템','벤더','부트','전원을 끄거나 SD를 빼지 마세요','잠시 후 자동으로 재부팅합니다','USB 콘솔 또는 SD 로그를 확인하세요','전체 저장장치','사용자 데이터','캐시','부트로더','기기를 재부팅해도 됩니다']
b=bytearray(head.tobytes())
for s in labels:
 im=Image.new('L',(600,70),255);ImageDraw.Draw(im).text((300,12),s,font=f(29 if len(s)>20 else 34),fill=0,anchor='mt');b+=im.tobytes()
for ch in range(32,127):
 im=Image.new('L',(20,32),255);ImageDraw.Draw(im).text((1,0),chr(ch),font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf',25),fill=0);b+=im.tobytes()
Path(sys.argv[1]).write_bytes(b)
