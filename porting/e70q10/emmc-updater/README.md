# E70Q10 선택 파티션 자동 업데이트

대상은 Android 8 설치와 파티션 재배치가 완료된 PP1A1GK166561입니다. boot/system/vendor를 각각 또는 조합으로 업데이트합니다. SD의 `update.conf`를 RAM 업데이터가 데이터로 읽어 선택한 파일을 검사하고 기록·읽기 검증한 뒤 자동 재부팅합니다. USB 콘솔 연결은 필요하지 않습니다.

## 바로 사용하기

아래 전체 패키지에는 세 이미지가 있습니다. `/dev/sdX`는 실제 SD 전체 장치로 바꾸세요. 실행 직후 경고 한 번을 확인하면 SD를 포맷하고 **선택한 이미지 파일만** 복사합니다.

```sh
UPDATE_DIR=/home/juwon/ridi/deliverables/e70q10-update-20261006-auto
sudo env SD_COPY_JOBS=8 /home/juwon/ridi/porting/e70q10/emmc-updater/format_prepare_update_sd.sh \
  /dev/sdX "$UPDATE_DIR.tar" --targets boot
```

`--targets` 값은 `boot`, `system`, `vendor`, `system,vendor`, `system,boot`, `vendor,boot`, `all`입니다. 생략하면 패키지 기본 선택을 사용합니다. 부트 전용 패키지는 `/home/juwon/ridi/deliverables/e70q10-update-20261006-boot-auto.tar`이며 boot만 선택할 수 있습니다.

SD를 기기에 넣고 fastboot에 진입한 뒤:

```sh
CONFIRM_RAM_BOOT=E70Q10 /home/juwon/ridi/porting/e70q10/emmc-updater/boot_ram_updater.sh \
  "$UPDATE_DIR/ram-updater.img" --from-fastboot
```

Android 실행 중이면 `--from-fastboot`를 생략합니다. **RAM 부팅 후 SD 설정에 따라 eMMC 기록이 자동 시작됩니다.** 성공하면 자동 재부팅합니다. 실패하면 재부팅하지 않고 RAM 환경에 머뭅니다. 결과는 SD의 `e70q10-update-status/last.log`, `last.result`에 남습니다.

기존 FAT32 p1에 포맷 없이 폴더만 추가할 때:

```sh
/home/juwon/ridi/porting/e70q10/emmc-updater/prepare_update_sd.sh \
  /media/juwon/SD이름 "$UPDATE_DIR.tar" --targets boot
```

기존 `e70q10-update` 폴더는 덮어쓰지 않습니다. 복사·읽기 검증은 기본 8개 작업이며 `SD_COPY_JOBS=1..32`로 조절합니다.

## 선택과 수동 실행

SD 준비 시 `--manual`을 추가하면 자동 기록을 끕니다. `--no-reboot`는 성공 후 RAM에 머물게 합니다. 패키지가 이미 수동/재부팅 비활성으로 생성됐다면 그 설정도 유지합니다.

`update.conf`의 정확한 항목은 `format=1`, `manifest=<manifest SHA256>`, `targets=<선택>`, `autostart=0 또는 1`, `reboot=0 또는 1`입니다. 셸 명령으로 실행하지 않으며 누락·중복·잘못된 값은 거부합니다. manifest와 RAM 이미지는 같은 릴리즈여야 합니다. 다른 릴리즈나 옛 SD와 새 RAM을 섞으면 자동 적용을 거부합니다.

수동 모드의 USB 콘솔에서는:

```sh
updater check /mnt/sd/e70q10-update
updater apply /mnt/sd/e70q10-update UPDATE-SELECTED-PP1A1GK166561
/bin/busybox reboot -f
```

수동 apply도 SD에서 선택한 파티션만 기록합니다. 자동 동작 확인은 `cat /run/emmc-auto.log`입니다. 위 토큰은 새 업데이터용이며 구형 업데이터는 전체 세 파티션을 쓰는 별도 방식입니다.

## 새 빌드로 패키지 만들기

완료된 빌드 산출물을 입력합니다. 클린 빌드는 필요하지 않습니다.

```sh
python3 /home/juwon/ridi/porting/e70q10/emmc-updater/build_update.py \
  --boot /path/to/boot.img --system /path/to/system.img --vendor /path/to/vendor.img \
  --targets all --out /home/juwon/ridi/deliverables/e70q10-update-release-N
python3 /home/juwon/ridi/porting/e70q10/emmc-updater/test_and_package.py \
  /home/juwon/ridi/deliverables/e70q10-update-release-N
```

`--targets boot` 등으로 개별 패키지를 만들 수 있습니다. boot 입력은 다른 대상만 선택해도 커널 호환성 기준으로 필요합니다. 선택하지 않은 system/vendor 파일은 변환하지 않습니다. `--manual`, `--no-reboot`도 빌드 시 지정할 수 있습니다. 출력 디렉터리는 비어 있어야 합니다. 검사 후 `.tar`, `.tar.sha256`를 생성합니다.

boot는 DTB를 커널 뒤에 붙이고 second_size를 0으로 변환하며 eMMC용 fstab/init을 반영합니다. 외장 SD는 Android의 보조 저장소로 등록합니다. system/vendor는 고정 파티션 크기의 ext4로 검사·변환합니다. 선택된 vendor의 모듈 vermagic은 입력 boot와 검사합니다. **부분 업데이트는 기존 나머지 파티션과 호환되어야 합니다. 커널 ABI가 바뀌면 일치하는 vendor도 함께 선택하세요.** 이 검사는 실기기 기능 검증을 대신하지 않습니다.

## 기록 범위와 실패 처리

| 대상 | 시작 섹터(512B) | 크기 |
|---|---:|---:|
| p5 system | 172032 | 1GiB |
| p8 vendor | 14733312 | 256MiB |
| p1 boot | 104448 | 32MiB |

선택한 파티션을 위 순서로 기록하며 boot가 마지막입니다. 기기 CID·용량·파티션 표·보호 영역·선택 파일의 압축/원본 해시와 크기를 기록 전에 검사합니다. 각 기록을 다시 읽어 검사하고 보호 영역과 파티션 표를 재확인합니다. recovery, userdata, cache, misc, U-Boot, waveform, logo와 선택하지 않은 파티션은 유지합니다.

A/B 슬롯이 없어 전원 중단 시 일부만 갱신될 수 있습니다. 전원을 유지하고, 중단되면 같은 릴리즈 RAM/SD로 재적용합니다. SD 설정 오류·손상 파일은 기록 전에 중단하며, 기록/검증/SD 로그 저장 실패 시 자동 재부팅하지 않습니다. 이전 boot 해시를 강제하지 않아 반복 업데이트도 가능합니다.

## 검증과 자산

전체 용량의 파일 기반 eMMC 리허설에서 개별/조합 기록, 전체 비선택 바이트 보존, 손상 파일·표·설정 거부를 검사합니다. 자동 성공/실패·수동·재부팅 비활성·로그 저장 실패 흐름, ARM RAM 구성과 FAT32도 검사합니다. 새 자동 흐름은 아직 실기기에 적용하지 않았습니다. 검증 로그는 `.orchestrator/logs/emmc-auto-20261006/`에 있습니다.

RAM 커널·헤더·ARM 도구·기준 파티션 표는 소스의 `assets/`에 보관하며 해시를 검사합니다. 삭제된 과거 deliverables에 의존하지 않습니다. 9월 원본 eMMC 백업은 변경하지 않습니다.
