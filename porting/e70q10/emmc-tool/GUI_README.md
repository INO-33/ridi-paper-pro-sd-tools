# Paper Pro Android 8 SD 도구

Python 3.10 이상과 Tkinter로 실행합니다. Windows 공식 Python에는 Tkinter가
포함됩니다. Linux에서는 python3-tk가 필요합니다.

## 사용

1. `images` 폴더에 `boot.img`, `system.img`, `vendor.img`를 넣습니다.
   다른 빌드 출력 폴더를 GUI에서 선택해도 됩니다.
2. Windows: `start.cmd`를 실행하고 OS의 관리자 권한 요청을 허용합니다.
   Linux SD 포맷: `sudo -E python3 ridi_gui.py`로 실행합니다.
   이미 포맷된 SD를 사용할 때는 일반 실행도 가능합니다.
3. 작업과 16GB 이상 SD를 선택합니다. SD 준비 버튼을 누르면 PC에서
   검증·변환하고, 확인 문구 하나를 거쳐 SD를 준비합니다.
4. SD를 안전 제거해 기기에 넣고 USB 연결·fastboot 진입 후
   “준비한 SD 작업 실행 · RAM 부팅”을 누릅니다.
5. 완료 후 SD를 PC에 옮겨 “SD 결과 확인”으로 실제 성공 여부를 확인합니다.

## 작업과 백업 옵션

| 선택 | 동작 |
|---|---|
| Android 8 업그레이드 | 순정 Android 4.4 배치에서 파티션 재구성, userdata/cache 생성 및 세 이미지 기록. 기존 userdata 초기화. 성공 시 재부팅. |
| 증분 업데이트 | 선택한 boot/system/vendor **전체 파티션 이미지**를 기록. 바이너리 차이 패치가 아닙니다. userdata/misc/cache/파티션 표 보존. 성공 시 재부팅. |

**기록 전에 eMMC 전체 백업**은 두 작업에 공통인 체크 옵션입니다.
업그레이드에서는 기본 선택, 업데이트에서는 기본 해제이며 변경할 수 있습니다.
선택하면 eMMC 전체 및 boot0/boot1을 SD에 복사·읽기 검증한 뒤에만 OS를 기록합니다.
백업에 실패하면 OS 기록을 시작하지 않습니다. 해제하면 전체 백업을 생략합니다.
업그레이드의 최소 misc 보존 및 기기 펌웨어 보호 검사는 해제해도 유지합니다.
GUI에는 별도 백업 메뉴가 없습니다. 이전 개발용 백업 전용 CLI 모드는 유지합니다.

실패하면 기기를 자동 재부팅하지 않습니다. Android 8이 이미 설치된 기기에는
업그레이드 모드를 사용하지 않습니다. RAM에서 실제 모델과 배치를 검사합니다.

## 백업으로 롤백

작업에서 **백업으로 롤백**을 선택하고 SD의
`e70q10-backups/CID/작업ID` 폴더를 선택합니다. `device.txt`가 있는 폴더입니다.
SD 포맷은 금지되며 OS·사용자 데이터·파티션 표를 모두 백업 시점으로 되돌립니다.
백업 옵션 체크박스는 기존 업그레이드/업데이트 작업에 그대로 유지됩니다.
실기기 복원은 아직 시험하지 않았습니다. 자세한 조건은 `ROLLBACK.md`를 확인하세요.

## Windows와 이미지 처리

- WSL, Android 빌드 환경, Linux fsck/resize 도구 없이 처리합니다.
- Android sparse를 Python으로 읽고 CRC/크기, clean ext4 geometry,
  Android 8/ARM/Paper Pro 속성, boot 구조/해시, 커널과 vendor 모듈 ABI를 검사합니다.
- Android make_ext4fs의 비트맵 끝 여분 비트를 정규화합니다. 실제 inode/블록
  할당이나 파일 내용은 바꾸지 않습니다. group descriptor 체크섬을 확인하며, metadata_csum 기능은 거부합니다.
- 파일시스템 자체는 재크기 조정하지 않고 파티션 끝까지 0으로 채웁니다.
  예: 768MiB system 파일시스템을 1GiB 파티션에 기록할 수 있습니다.
- 이 검사는 전체 fsck를 대체하지 않습니다. 지원하지 않는 ext4 기능,
  dirty/recovery-needed 이미지, 잘린 이미지와 ABI 불일치는 거부합니다.
- Windows SD 읽기 검증은 FILE_FLAG_NO_BUFFERING과 정렬된 버퍼로
  파일 캐시를 우회합니다. [Microsoft File Buffering](https://learn.microsoft.com/en-us/windows/win32/fileio/file-buffering)
- 파일을 준비하는 동안 원본이 바뀌면 SD 기록 전에 중단합니다.
- 준비된 배포 TAR+SHA 또는 ZIP+SHA 하나가 있는 폴더도 사용할 수 있습니다.

fastboot를 사용하려면 해당 OS용 Android platform-tools의 fastboot와 관련 DLL을
`platform-tools` 폴더에 넣거나 PATH에 설치합니다. 드라이버는 OS에서 별도로
설치해야 합니다. 디스크 목록·SD 포맷은 Windows 기본 PowerShell Storage
명령을 사용하며 시스템/페이지 파일 디스크 및 원본이 있는 SD는 거부합니다.

파일 작업은 별도 스레드에서 실행해 창을 계속 사용할 수 있습니다. 기록 중에는
창을 닫지 못하게 합니다. RAM 전송 성공과 실제 설치 성공은 별도로 표시합니다.
로그 및 준비한 RAM 이미지는 사용자 데이터 폴더 `RidiPaperPro`에 저장합니다.

## 배포/검증 상태

Linux에서 GUI, 원본 sparse/boot 변환, 백업 옵션 ON/OFF와 임시 SD 준비 흐름을 시험합니다.
Windows 실행 경로는 Linux에서 모의 검증하며, Windows 실기기 GUI/SD 작성은
별도 실기기 시험이 필요합니다. 원본 이미지와 실제 SD의 백업 데이터는 자동
정리하지 않습니다. 임시 변환·시험 파일은 작업 종료 시 정리합니다.

LZO decoder: Markus F.X.J. Oberhumer의 Linux LZO1X 상태 기계를 Python으로
옮겼습니다. `licenses/LZO-GPL-2.0.txt`를 확인하세요. OpenSSL ARM SHA 코드는
`licenses/sha256-OpenSSL.txt`에 원문 고지가 있습니다.
