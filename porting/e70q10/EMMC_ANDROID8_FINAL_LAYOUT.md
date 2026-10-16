# E70Q10 Android 8 eMMC 최종 파티션 배치

실제 기록 순서와 MBR/EBR 바이트 변경 방식은
[`EMMC_ANDROID8_FLASH_SEQUENCE.md`](EMMC_ANDROID8_FLASH_SEQUENCE.md)에 있다.
검증된 테이블 파일 6개와 기록 LBA·해시는
[`테이블 manifest`](../../deliverables/emmc-20261001-final-partition-table/manifest.json)에
준비했다. OS 이미지와 RAM 설치기는 아직 완성하지 않았다.

확정일: 2026-10-01. 대상 시리얼 `PP1A1GK166561`, CID
`15010038474d45345201bbd3fe618400`, eMMC 이름 `8GME4R`.
사용자가 misc를 마지막에 두고 system/vendor/userdata 크기를 확정하도록
지정한 결과이다. **파티션 배치는 확정했으며, 이미지 제작·실기기 쓰기와
부팅 검증은 아직 별도 단계이다.**

## 실제 용량: 내부 eMMC 8 GB급, 외장 SD 16 GB급

9월 23일 대상 기기의 기록과 원본 백업을 다시 대조했다.

| 근거 | 내부 eMMC | 외장 SD |
|---|---:|---:|
| Linux 장치 | `mmcblk0` | `mmcblk1` |
| `/proc/partitions`의 1 KiB 블록 수 | 7,634,944 | 15,558,144 |
| 전체 바이트 수 | 7,818,182,656 | 15,931,539,456 |
| 용량 분류 | **8 GB급** | **16 GB급** |

`emmc-sysfs.txt`의 `/sys/block/mmcblk0/size`는 15,269,888섹터이다.
`ext_csd.bin`을 hex에서 512 B 레지스터로 디코딩한 `SEC_COUNT[212:215]`도
15,269,888이다. `emmc.part00..29`의 파일 크기 합계 역시 정확히
7,818,182,656 B이다. 서로 독립적인 세 기록이 일치한다. 내부 eMMC의 user
area는 **7,456 MiB = 7.28125 GiB = 약 7.818 GB**이다. 이것을 16 GB로
가정한 설치 이미지를 만들면 장치 끝을 초과한다.

근거 파일은
`/media/juwon/build/리디백업/backups/e70q10-PP1A1GK166561-20260923-full-emmc/`의
`emmc-sysfs.txt`, `ext_csd.bin`, `runtime-layout.txt`, 30개 분할 파일이다.
공식 지원 문서 검색도 수행했으나 검색된 저장소 용량 표시 안내에는 전체
GB 사양 수치가 없어 실제 장치 레지스터와 백업을 용량 판단 기준으로 삼았다.

## 확정 배치

크기는 이진 단위 MiB/GiB이고 끝 섹터는 포함값이다. 파티션은 DOS/MBR이며
섹터 크기는 512 B이다. p3은 컨테이너이므로 다른 파티션과 용량을 중복
합산하지 않는다.

| 번호 | 용도 | 크기 | 시작 섹터 | 끝 섹터 | 내용 |
|---|---|---:|---:|---:|---|
| p1 | boot | **32 MiB** | 104,448 | 169,983 | 새 Android 8 boot image |
| p2 | recovery | **32 MiB** | 38,912 | 104,447 | 순정 이미지·위치 유지 |
| p3 | extended | 7,373 MiB | 169,984 | 15,269,887 | p5~p9와 EBR의 컨테이너 |
| p4 | — | — | — | — | MBR 슬롯을 비움, 기존 FAT 삭제 |
| p5 | system | **1,024 MiB / 1 GiB** | 172,032 | 2,269,183 | `/system`, ext4 |
| p6 | cache | **64 MiB** | 2,271,232 | 2,402,303 | `/cache`, 새 ext4 |
| p7 | userdata | **6,019 MiB / 약 5.878 GiB** | 2,404,352 | 14,731,263 | `/data`, 새 ext4; 책/앱 저장소 포함 |
| p8 | vendor | **256 MiB** | 14,733,312 | 15,257,599 | `/vendor`, ext4 |
| p9 | misc | **4 MiB** | 15,259,648 | 15,267,839 | 기존 raw 내용 이전 |

EBR 위치: `169984`, `2269184`, `2402304`, `14731264`, `15257600`.
각 EBR부터 해당 논리 파티션 시작까지 1 MiB를 배정해 실제 파일시스템은
모두 1 MiB 경계에 맞춘다. 장치 마지막 1 MiB는 예약한다.

물리 순서는 다음과 같다.

```text
0~19 MiB      MBR + U-Boot/hwcfg/firmware/waveform/logo + 이전 boot 잔여 영역
19~51 MiB     p2 recovery (원본 유지)
51~83 MiB     p1 새 boot
83~84 MiB     첫 EBR/정렬 공간
84~1108 MiB   p5 system 1024 MiB
1108~1109     EBR/정렬 공간
1109~1173     p6 cache 64 MiB
1173~1174     EBR/정렬 공간
1174~7193     p7 userdata 6019 MiB
7193~7194     EBR/정렬 공간
7194~7450     p8 vendor 256 MiB
7450~7451     EBR/정렬 공간
7451~7455     p9 misc 4 MiB
7455~7456     끝 예약 1 MiB
```

## 크기를 이렇게 정한 이유

- **system 1 GiB:** 현재 Android system image는 펼친 크기 768 MiB이다.
  256 MiB의 파티션 여유를 두어 이미지 증가에 대응한다. 기존 768 MiB
  파일시스템을 그대로 기록하면 그 파일시스템의 크기도 768 MiB이며,
  1 GiB 전체 사용은 eMMC 제품의 image size 설정을 반영한 빌드로 한다.
- **vendor 256 MiB:** 현재 제품 설정과 raw image 크기가 256 MiB이다.
  최신 sparse 파일은 약 16.6 MB지만 설치 범위는 펼친 256 MiB를 기준으로
  한다. 추가로 ext4 superblock을 읽어 실제 사용량을 확인했다. 65,536개
  4 KiB 블록 중 60,956개가 비어 있다. 파일시스템 메타데이터까지 포함한
  사용량은 **17.890625 MiB**, 여유는 **238.109375 MiB(약 93%)**다.
  현재 vendor 파일은 60개, 합계 약 9.55 MiB이며 큰 항목은 패널 waveform
  4,642,008 B, Wi-Fi 모듈 1,826,576 B, wpa_supplicant 1,456,124 B이다.
  현재 구성에서는 256 MiB를 유지한다. 512 MiB로 늘리는 선택은 가능하며
  그 경우 userdata는 6,019 MiB에서 5,763 MiB(약 5.63 GiB)로 감소한다.
  조사 수치는 `.orchestrator/logs/emmc-review-20261001/vendor-capacity.json`에 있다.
- **cache 64 MiB:** 현재 제품 설정과 일치하며 작은 관리·복구 파일용으로
  남긴다. system을 통째로 다운로드해 보관하는 업데이트 방식을 전제로 하지
  않는다. 기존 `/recovery/command`를 복원하지 않는다.
- **userdata 나머지 6,019 MiB:** 기존 FAT와 순정 사용자 데이터는 보존할
  필요가 없다는 지시에 따라 `/data` 한곳으로 통합한다. `/data/media`의
  책과 앱 데이터가 이 공간을 공유한다. 파일시스템 메타데이터 등으로 실제
  표시되는 빈 공간은 파티션 용량보다 작다.
- **boot/recovery 각각 32 MiB:** 새 부트 이미지 약 11.8 MB를 수용하며
  순정 recovery를 그대로 둔다. U-Boot는 각각 p1/p2의 MBR 시작 주소를 읽는다.
- **misc 4 MiB:** 원본 p9의 4,186,112 B를 새 영역으로 이전하고 나머지
  8,192 B만 0으로 채운다. Android 및 순정 recovery의 p9 경로를 유지한다.

## 이미지 및 설치 계약

기계 판독용 배치는 `EMMC_ANDROID8_FINAL_LAYOUT.json`에 고정한다. eMMC용
제품의 이미지 크기는 아래와 일치해야 한다. 기존 SD용 BSP 설정에 적용하거나
빌드를 수행한 상태는 아니며, eMMC 제품 구현 시 이 값을 사용한다.

```make
BOARD_BOOTIMAGE_PARTITION_SIZE := 33554432
BOARD_SYSTEMIMAGE_PARTITION_SIZE := 1073741824
BOARD_VENDORIMAGE_PARTITION_SIZE := 268435456
BOARD_CACHEIMAGE_PARTITION_SIZE := 67108864
BOARD_USERDATAIMAGE_PARTITION_SIZE := 6311378944
```

fstab의 필수 경로는 `/system=mmcblk0p5`, `/cache=mmcblk0p6`,
`/data=mmcblk0p7`, `/vendor=mmcblk0p8`이고 raw misc는 p9이다. 부트 이미지에는
최신 kernel+appended DTB 및 eMMC ramdisk를 넣고 필수 외장 SD 대기를 제거한다.
system/vendor는 같은 빌드 세트를 새 raw로 변환한다. 기존 `system.raw.img`는
최신 sparse와 불일치했으므로 재사용하지 않는다.

기록 방식은 전용 `fastboot boot` RAM 설치기가 외장 SD의 패키지를 읽어
새 절대 범위로 기록하고 해시를 검증하는 것이다. `[512 B, 51 MiB)`는
원본 그대로 보존하고, MBR은 기존 boot code/서명을 보존한 파티션 항목
수정으로만 적용한다. 별도 boot0/boot1 및 RPMB는 변경하지 않는다.

일반 임시 파일에서 이 배치의 경계·중첩·EBR 및 파티션 번호를 검증했고
참조 U-Boot DOS 조회 규칙과 util-linux `sfdisk`/`partx`에서도 같은 주소가
나왔다. **확정은 파티션 설계에 대한 것이며 실제 기록 준비 완료를 뜻하지
않는다.** 이동한 boot의 실기기 부팅과 순정 recovery의 Android 8 마운트/
초기화 호환성은 남은 검증이다. system/cache 사이에서 발견한 미확정 약
1 MiB는 별도 사본과 전체 원본 백업으로 보관한다.
