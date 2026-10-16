# Paper Pro Windows SD 플래시 도구 (UI 없는 Python 실행판)

현재 기기에서 시험할 때는 **install-test**를 사용합니다. 최신 boot/system/vendor를 올리면서 현재 userdata와 파티션 표를 보존하고, 그 전에 현재 eMMC 전체를 새 작업별로 백업합니다. 백업 뒤 cache(64MiB)는 실제로 생성·검사하며, userdata는 보존합니다. 실제 Android 4.4 설치는 별도의 install 작업입니다.

## Windows에서 이번 시험

Python 3.10 이상을 설치하고 ZIP을 PC 디스크의 한 폴더에 풉니다. Python 프로그램·OS tar·tar.sha256를 모두 PC에 두세요. 포맷할 SD에 두면 실행을 거부합니다. 16GB 이상 SD카드를 연결하고 **관리자 PowerShell**을 엽니다.

```powershell
cd C:\PaperPro
py -3 .\ridi_emmc.py disks
```

출력에서 SD 디스크 번호를 확인합니다. 아래 `3`은 예시입니다.

```powershell
py -3 .\ridi_emmc.py prepare .\paperpro-eink-4m-20261013-r2.tar --disk 3 --operation install-test --targets all --jobs 8
```

SD 전체 삭제 경고를 한 번 확인하면 MBR/FAT32 포맷 → 파일 복사 → 동기화 → 해시 읽기 검증을 수행합니다. SD 준비가 완료된 다음 안전하게 제거하고 기기에 넣습니다. **이번에는 install을 선택하지 마세요.** install-test는 재파티션과 userdata 포맷을 실행하지 않습니다. 이번 버전은 cache만 포맷합니다.

Windows Android platform-tools와 해당 fastboot 드라이버가 준비돼 있고 기기가 fastboot 상태라면:

```powershell
py -3 .\ridi_emmc.py boot .\paperpro-eink-4m-20261013-r2.tar --platform-tools .\platform-tools
```

platform-tools는 ZIP에 동봉하지 않습니다. 기기가 여러 대면 --serial로 한 대를 선택합니다. Android에서 ADB로 fastboot 진입까지 수행하려면 --from-adb를 추가합니다. Windows에서는 SD만 준비하고 RAM 부팅은 Linux에서 같은 tar로 진행해도 됩니다.

작업이 완료될 때까지 전원과 SD를 유지합니다. 전체 eMMC 백업과 userdata 전후 전체 읽기 검증이 있어 일반 업데이트보다 오래 걸립니다. 성공하면 자동 재부팅합니다. 실패하면 RAM 상태에 머뭅니다. --no-reboot는 성공 후에도 RAM 상태를 유지합니다. --manual은 자동 실행을 끄는 진단 모드입니다.

## 결과 확인

SD를 다시 PC에 연결하고 예를 들어 E: 드라이브라면:

```powershell
py -3 .\ridi_emmc.py status E:\
Get-Content E:\e70q10-update-status\preservation.result
```

현재 job/manifest/작업과 일치하는 last.result의 exit=0, preservation.result의 userdata=preserved / partitioning=preserved / cache=created / cache_fsck=passed가 이번 시험 성공의 기준입니다. SD의 e70q10-update-status/last.log에는 단계별 상세 결과가 있습니다. RAM 로그는 /run/emmc-auto.log입니다.

**원본 백업:** `e70q10-backups/<실제 CID>/<job ID>/` 아래 256MiB emmc.partNN, device.txt, SHA256SUMS, complete, 지원되는 경우 boot0/boot1.bin이 저장됩니다. userdata도 전체 백업에 포함됩니다. 백업은 실제 현재 상태이며 기존 Android4 백업으로 대체하거나 옛 CID별 스냅샷을 재사용하지 않습니다. 새 SD 준비마다 job이 바뀝니다. 같은 job의 중단 후 재시도만 완료 백업을 검증해 재사용합니다. 불완전·손상 백업은 덮어쓰지 않고 중단합니다.

백업을 PC로 복사해서 보관한 뒤 SD를 재포맷하세요. 같은 16GB SD에 여러 전체 백업을 동시에 보관할 공간이 없을 수 있습니다. 공간 부족이나 백업 검증 실패 시 OS 기록을 시작하지 않습니다.

userdata의 바이트 보존은 RAM 업데이트 종료 시점까지 검증합니다. 이후 Android가 정상 부팅하며 설정·앱 데이터를 기록하는 것은 일반적인 OS 동작입니다. 파일 보존과 새 OS의 모든 앱 호환성은 별개입니다.

## 작업 종류

| 작업 | 허용되는 현재 배치 | 백업 | 파티션 / userdata |
|---|---|---|---|
| install | 순정 배치 | 새 작업의 전체 백업 필수 | 재배치, userdata/cache 생성 |
| install-test | 기존 Android8 배치 | 새 작업의 전체 백업 필수 | 배치/userdata 보존, cache 생성 후 OS 갱신 |
| update | 기존 Android8 배치 | 이 모드에서는 생략 | 선택한 boot/system/vendor만 기록 |

실제 Android4.4 기기에서는 위 준비 명령의 --operation을 install로 지정합니다. install은 기존 userdata를 초기화하므로 원본은 SD 백업에 보관됩니다. 현재 Android8 기기에서는 install 작업을 기록 전에 거부합니다. 이번 시험은 4.4 설치의 공용 모델 검사·백업·cache 생성/검사·파일 검사·OS 기록 경로를 사용하지만, **이번 기기에서의 빈 userdata 생성/실제 4.4에서 최초 부팅을 시험한 것으로 간주하지 않습니다.**

Android8 설치 여부는 RAM이 실제 eMMC 파티션 구조를 읽어 판정합니다. OS 버전을 임의로 4.4처럼 위장하거나 현재 userdata를 초기화해서 시험하지 않습니다.

## Linux에서 동일 도구

```sh
TOOL=/home/juwon/ridi/porting/e70q10/emmc-tool/ridi_emmc.py
PACKAGE=/home/juwon/ridi/deliverables/paperpro-eink-4m-20261013-r2.tar
sudo python3 "$TOOL" prepare "$PACKAGE" --disk /dev/sdX --operation install-test --targets all
python3 "$TOOL" boot "$PACKAGE"
```

이미 포맷된 FAT32 SD를 유지하려면 --disk 대신 --mount <SD루트>를 사용합니다. 기존 e70q10-update 폴더는 덮어쓰지 않습니다. 백업 용량도 포함해 여유 공간을 검사합니다. --jobs는 1..32이며 기본값은 8입니다.

## 모델·순정 기준과 기록 범위

지원 대상은 RIDI Paper Pro E70Q10입니다. 특정 serial/CID 허용 목록은 없고 실제 Netronix hwcfg/CPU/RAM/디스플레이/터치/Wi-Fi, i.MX 부트 헤더와 파티션 체인을 검사합니다. 다른 모델·손상된 표·미지원 임의 배치는 거부합니다. 실제 eMMC 용량으로 userdata와 vendor/misc 위치를 계산합니다.

**순정 배치의 기준은 온전한 9월 23일 백업입니다. 7월 자료는 백업 카피 배치이며, 순정 배치의 증거나 다른 실제 기기의 검증 자료로 취급하지 않습니다.** 이전 문서의 두 순정 배치 표현은 폐기합니다. 구조 파서의 파일 기반 시험 자료와 실제 출고 배치의 근거를 구분합니다.

초기 설치에서도 해당 기기의 MBR boot code/disk ID와 recovery 항목을 유지하고 [512B, 51MiB)의 U-Boot/hwcfg/waveform/logo/recovery를 기록하지 않습니다. 원본 misc는 그 기기 백업의 실제 EBR 위치에서 추출합니다. 배포용 userdata/cache 이미지 없이 Android ARM 포맷 도구와 SELinux 컨텍스트로 생성합니다.

## Windows 구현과 검증 범위

Windows Storage API의 Clear-Disk/Initialize-Disk/New-Partition/Format-Volume로 MBR + FAT32 p1을 만듭니다. BusType을 문자열로 처리하고 PowerShell 출력은 UTF8로 고정합니다. 디스크의 식별/크기/섹터/시스템·페이지파일 여부를 삭제 직전에 재확인하며, 원본 tar가 저장된 실제 볼륨이 대상 SD면 거부합니다. 복사 파일과 설정을 fsync한 후 볼륨 FlushFileBuffers와 해시 검사를 수행합니다. 32GB보다 큰 SD는 최대 약 32GB 파티션을 사용합니다.

format=4 설정은 작업별 job, userdata, partitioning, cache 정책을 포함합니다. install-test에서 userdata=create, partitioning=create 또는 backup=none 같은 조합은 호스트와 RAM 양쪽에서 거부합니다. 옛 RAM 이미지와 섞으면 설정 버전 검사에서 중단합니다. 백업·테스트 프로그램은 RAM 내부에서 실행하며 SD의 셸 코드를 실행하지 않습니다.

Windows 물리 포맷은 아직 Linux 환경에서 실행할 수 없어 모의 명령 검사만 수행했습니다. SD 실기기 install-test는 2026-10-12 성공했습니다. Windows 디스크 포맷의 직접 실행 로그와 실제 4.4 기기의 재파티션·첫 부팅 검증은 남아 있습니다. 지금 제공본은 그 시험을 위한 최신 이미지와 CLI입니다. UI와 exe 포장은 포함하지 않습니다.

참고: [Microsoft 디스크 초기화/변환](https://learn.microsoft.com/en-us/windows-server/storage/disk-management/change-disk-partition-scheme), [GetVolumePathName](https://devblogs.microsoft.com/oldnewthing/20201020-00/?p=104385), [PowerShell 문자 인코딩](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_character_encoding).

### cache 시험의 의미

cache를 실제 eMMC에서 생성하면 파티션 노드 확인·Android ARM make_ext4fs·SELinux 컨텍스트 입력·e2fsck가 실제 기기에서 동작하는지 확인할 수 있습니다. userdata도 같은 도구를 사용하지만 크기와 mountpoint/권한이 다릅니다. 6019MiB userdata 생성은 이전 ARM/QEMU 파일 기반 시험에서 통과했으며, 이번 기기에서는 userdata를 포맷하지 않습니다. 이전에 성공한 실기기 파티션 재배치 결과도 별도 검증 근거로 유지합니다. cache 시험을 userdata 실기기 포맷 완료로 기록하지 않습니다.

### RAM 로더 수정 r2

libc.so/e2fsck가 상위 디렉터리보다 앞서 저장되어 커널 압축 해제에서 빠지는 순서 오류를 수정했습니다. 현재 ZIP은 paperpro-eink-4m-20261013-r2.zip입니다. boot/system/vendor와 백업 형식은 같고 RAM 압축 항목을 디렉터리 우선으로 정렬합니다. 파일 생성 시 부모 디렉터리를 자동 생성하지 않는 조건에서도 libc.so와 e2fsck 생성이 확인됩니다. 기존 QEMU용 런타임 디렉터리 생성만으로는 이 커널 압축 해제 조건을 검증하지 못했습니다.

### 최종 실기기 결과 (2026-10-12)

SD 결과 exit=0: 전체 eMMC 및 boot0/boot1 백업 검증, 실제 64MiB cache 생성/e2fsck, system/vendor/boot 기록·읽기 검증, userdata/misc 전체 해시 보존 검사가 통과했습니다. 파티션 표도 보존했습니다. 완료 작업은 다시 RAM 부팅해도 자동 실행하지 않습니다. Android 첫 부팅 완료는 이번 SD 로그로 확인할 수 없습니다.

최종 RAM은 필수 linker/formatter/e2fsck/libc/SELinux 파일과 라이브러리 로딩을 백업 전에 확인합니다. 압축 해시·해제 후 해시·크기 검사 단계마다 진행 로그를 출력합니다. 성공/실패 및 재부팅 요청 여부도 SD last.log에 저장합니다. 실패하면 재부팅하지 않습니다.

## 속도 개선 (2026-10-13)

기기에서 boot/system/vendor의 사전 압축 해시·해제 원본 해시·해제 크기 검사를 제거했습니다. PC prepare/inspect/boot가 압축 CRC, 압축 SHA256, 해제 SHA256와 정확한 크기를 검사하며, 세 이미지의 검사를 병렬로 수행합니다. 압축 이미지 하나는 한 번 읽고 한 번 해제하면서 모두 확인합니다. SD 복사 중 원본 변경 검사와 복사 후 SD 읽기 검증은 유지합니다.

RAM은 모델/파티션/manifest 일치 확인 → 선택 이미지 압축 해제 1회 및 기록 → flush → eMMC 읽기 해시 비교 → 결과 저장 → 성공 시 재부팅 순서입니다. 4MiB 버퍼를 쓰는 ARM stream-write가 기록 길이를 파티션 크기로 제한하고 짧거나 긴 입력을 거부합니다. 손상 스트림이나 읽기 검증 실패는 재부팅하지 않습니다. 기기 이미지 사전 검증을 제거했으므로 손상 SD는 일부 기록 후 중단될 수 있습니다.

일반 update는 userdata/cache/misc/파티션 표를 보존하고 전체 백업·cache 재생성·userdata 전체 해시 검사를 실행하지 않습니다. install 및 install-test는 기존 백업/포맷/보존 검사를 유지하지만 이미지 내용 사전 검사는 PC에서 수행합니다. 모델/쓰기 범위 검사 및 manifest 고정 검사는 작은 메타데이터 검사이므로 유지합니다.

### 새 빌드로 패키지 생성 (Linux 릴리즈 제작)

빌드 완료 후 다음을 실행합니다. --reuse-images는 OS 이미지를 그대로 두고 RAM/호스트 로직만 바꾸거나 로직을 시험할 때 사용합니다. 새 Android 이미지가 있는 업데이트 제작에서는 지정하지 않습니다. 출력은 ZIP과 SHA256 두 개이며 변환·압축 해제 중간 파일은 자동 정리됩니다.

```sh
python3 /home/juwon/ridi/porting/e70q10/emmc-tool/build_speed_release.py \
  --seed /home/juwon/ridi/deliverables/paperpro-eink-4m-20261013-r2.zip \
  --product /media/juwon/build/android-out/e70q10_reference_agl_stockpath/target/product/e70q10 \
  --out /home/juwon/ridi/deliverables/paperpro-update-20261013.zip
```

Windows에서는 ZIP 압축을 풀고 기존 CLI의 prepare --operation update --targets all --jobs 8을 사용합니다. 새 prepare-update.cmd도 동일한 작업을 선택합니다. format=4와 RAM은 반드시 동일 ZIP에서 사용해야 합니다. SD 복사/읽기 검증 시간은 화면과 호스트 로그에 남습니다. 실기기에서의 향상 폭은 새 이미지 업데이트 후 비교해야 합니다.

### eMMC 백업 속도 개선 (2026-10-13)

백업 복사는 4MiB 버퍼를 쓰는 ARM backup-copy가 수행합니다. 원본을 읽은 같은 데이터를 SD 파일과 SHA256 계산기로 보내 복사와 해시 계산을 겹칩니다. 각 파일을 fsync한 다음 깨끗한 파일 캐시를 비우고 SD 파일을 다시 읽어 원본 스트림 해시와 비교합니다. 각 256MiB 조각 및 boot0/boot1을 모두 확인한 뒤에만 complete를 기록합니다. 마지막의 중복 전체 SD 재검사와 원본 eMMC 재읽기를 제거했습니다. 큰 데이터 읽기는 eMMC 2회+SD 2회에서 eMMC 1회+SD 1회로 줄었습니다.

새 백업 파일은 O_EXCL로 만들어 기존 파일을 덮어쓰지 않습니다. 복사·해시·flush·SD 비교 중 실패하면 완료 표시를 만들지 않습니다. 같은 job의 이미 완료된 백업을 재사용할 때는 전체 SHA256SUMS 검증을 그대로 수행하며, 미완성/손상 백업은 거부합니다. 최종 SHA256SUMS/complete 메타데이터는 sync하고 SD를 읽기 전용으로 전환합니다. 조각별 복사+해시 및 읽기 검증 시간을 RAM/SD 로그에 출력합니다. 일반 update는 기존과 같이 백업을 새로 만들지 않습니다.

현재 최신 패키지는 paperpro-eink-4m-20261013-r2.zip입니다. 같은 OS 이미지에 새 백업 RAM 로직을 포함했습니다. 이번 일반 업데이트 기기에 새 RAM을 부팅하는 것만으로는 백업을 다시 만들지 않습니다. 백업 개선 경로는 install/install-test에서 적용됩니다. 파일 기반 512MiB+64KiB 시험은 3.042초 → 2.443초(약20% 단축)였고 실제 eMMC+SD 백업 속도는 아직 측정하지 않았습니다.

## RAM 이잉크 진행 화면 (2026-10-13)

RAM 업데이터의 Linux framebuffer/EPDC에 한국어 진행 화면을 표시합니다. 준비·기종 확인·백업·백업 읽기 검증·파티션 배치·파일시스템 생성·OS 기록·기록 후 검증·완료·실패를 표시합니다. 복사와 읽기 검증의 실제 처리 바이트 수로 진행률을 계산합니다. 검사/포맷처럼 바이트 진행률을 알 수 없는 단계는 진행 중 표시를 사용합니다.

화면은 RAM 전용 프로세스가 관찰하며 설치 제어에 관여하지 않습니다. 평소에는 2초 간격으로 달라진 영역만 EPDC 부분 갱신하고 최초/완료/실패 때 전체 갱신합니다. 지원하지 않는 framebuffer/화면 오류는 USB/SD 로그로 대체하며 기록·검증 결과를 바꾸지 않습니다. 실패 시 재부팅하지 않고 오류 안내를 유지합니다. 완료 결과를 SD에 저장하고 화면 표시 시간을 둔 뒤 자동 재부팅합니다. kernel/Android 일반 그래픽 경로는 수정하지 않았습니다.

백업 복사·OS 기록·읽기 검증의 native 버퍼는 4MiB입니다. 백업 파일 분할 단위는 FAT32에 맞춘 기존 256MiB를 유지합니다. 설치/업데이트의 userdata 및 파티션 정책도 기존 format=4를 사용합니다.

한국어 렌더링의 host/ARM 동일 결과, RGB565/8bit/32bit framebuffer 경계·stride·offset·부분 영역·오류 재시도는 파일 기반 시험으로 확인했습니다. 실기기 EPDC 표시·상태 전환은 확인했습니다. 4MiB의 실제 시간 개선은 아직 확인 전입니다.

### 실기기 이잉크 확인 및 기기 고유 파형 준비

2026-10-13 Paper Pro 실기기에서 한국어 진행 화면과 검증75%→모의 실패→완료 전환의 정상 표시를 확인했습니다. 초기 RAM 화면 실패 원인은 /lib/firmware의 EPDC 파형 파일 누락이었습니다. 최종 RAM init은 읽기 전용으로 이 기기의 hwcfg/NTX 파형 헤더를 검사하고 원래 파형을 RAM에 복사한 뒤 framebuffer 재초기화를 요청합니다. 다른 기기의 공통 파형을 넣거나 eMMC 파형을 덮어쓰지 않습니다. 기기별 파형 길이를 검증하고 준비 실패 시 USB/SD 로그를 유지합니다.

실기기 화면 시험은 설치·백업 작업을 비활성화한 RAM으로 수행했습니다. 기기 고유 파형의 ARM 추출 및 해시 일치를 확인했으며, OS/사용자 데이터 기록은 실행하지 않았습니다.

## RAM 백업 성능

- 복사와 SHA-256 계산은 한 프로그램에서 4MiB 블록으로 처리합니다.
- ARM/NEON 최적화를 사용하며 NEON이 없는 CPU는 일반 ARM 경로를 사용합니다.
- SD 백업은 fsync 및 캐시 해제 후 별도로 다시 읽어 SHA-256을 비교합니다.
- OS 기록 후 읽기 검증과 userdata 보존 검사에도 같은 해시 구현을 사용합니다.
- 화면은 표시 내용 또는 정수 퍼센트가 바뀔 때만 그립니다.
- 실기기 64MiB 해시 비교: 기존 8.60초, 개선 2.45초. 진행 중인 백업과 병행한
  측정이며 전체 백업 소요 시간의 개선율은 별도로 측정해야 합니다.

This product includes software developed by the OpenSSL Project for use in the
OpenSSL Toolkit (https://www.openssl.org/). See licenses/sha256-OpenSSL.txt and
licenses/sha256-source.md for licenses and source attribution.

## 백업 전용 시험

`prepare PACKAGE.tar --disk DISK --operation backup` 또는 Windows의
`prepare-backup.cmd DISK`를 사용합니다. SD의 기존 백업은 먼저 PC에 보관하세요.

- `operation=backup`, `targets=none`, `backup=required`, `reboot=0`
- boot/system/vendor 이미지 파일을 SD에 복사하지 않습니다.
- 순정 또는 Android8 배치를 검사한 뒤 eMMC 전체와 boot0/boot1을 백업합니다.
- SD 복사 후 독립 읽기 SHA-256 검증을 유지합니다.
- userdata/misc/cache/파티션 표 및 OS를 기록하거나 포맷하지 않습니다.
- 성공·실패 모두 RAM에 남습니다. 성공 기록은 SD의 상태 폴더에 저장합니다.
