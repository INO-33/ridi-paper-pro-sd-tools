# E70Q10 최종 배치 기록 방식과 MBR/EBR 변경 절차

기준: `EMMC_ANDROID8_FINAL_LAYOUT.json`, 대상 `PP1A1GK166561`, CID
`15010038474d45345201bbd3fe618400`, 내부 eMMC 15,269,888섹터.
이 문서는 설치 절차 설계이다. 실제 eMMC 기록은 수행하지 않았다.

## 설치 환경과 패키지

전용 Linux initramfs를 `fastboot boot`로 RAM에 띄운다. Android의 system,
vendor, data를 실행 환경으로 쓰지 않으며 eMMC 파티션을 마운트하지 않는다.
입력 패키지는 외장 SD의 충분한 공간이 있는 분할에 두고 USB CDC 콘솔로
설치기를 제어한다. OS가 실패해도 USB/키로 Fastboot에 재진입할 수 있는지
첫 기록 전에 검증한다. `adb reboot fastboot` 성공만으로 복구 경로가 확보된
것으로 보지 않는다.

패키지의 모든 입력 해시·길이와 장치 CID·총 섹터 수를 먼저 검사한다.
eMMC writer는 시작/길이의 허용 목록을 검사하며 ARM의 32비트 정수에
바이트 주소가 잘리지 않도록 **64비트 파일/블록 오프셋**을 사용한다.
first 51 MiB 원본 보존과 같은 장치 식별을 쓰기 조건으로 둔다.

최초 설치는 cache/data까지 host에서 미리 만든 빈 Android용 ext4 이미지로
준비한다. system 1 GiB, cache 64 MiB, data 6,019 MiB, vendor 256 MiB와
boot 32 MiB의 raw 범위·내용을 오프라인에서 확정한다. boot는 실제 Android
boot image에 32 MiB까지 0 padding을 붙인다. Android sparse는 host에서 raw로
변환하고 cache는 오래된 U-Boot ext4 검사와 호환되는 기능으로 생성한다.

큰 빈 raw 이미지는 gzip 등으로 압축하거나 분할해 SD에 넣을 수 있다.
압축 데이터의 해시뿐 아니라 **펼친 raw 길이와 SHA-256**도 manifest에 둔다.
RAM 설치기는 작은 버퍼로 풀어 쓰며 예상 길이를 초과하는 입력을 거부한다.
userdata를 6 GiB RAM에 올리는 방식이 아니다. 이 방식이면 새 파티션 노드가
생기기 전에 모든 이미지를 절대 주소로 기록할 수 있고 설치 중 mkfs로
현재/새 파티션을 혼동할 위험도 줄어든다. cache/data 생성 도구와 설치기
writer 자체는 아직 구현·검증해야 하는 대상이다.

## MBR은 원본 섹터 0의 파티션 항목만 수정

백업의 `emmc.part00`에서 첫 512 B를 읽어 원본 MBR로 삼았다. 아래 범위를
유지한다. `parted mklabel`이나 자동 wipe 동작으로 첫 영역을 새로 초기화하지
않는다.

- 바이트 **0~445**: 기존 boot code, disk signature, 예약 바이트 그대로
- 바이트 **462~477**: p2의 원래 16 B 항목 그대로
- 바이트 **510~511**: `55 aa` 서명 그대로

바뀌는 MBR 항목은 다음 세 개이다. 번호는 슬롯 번호이므로 물리 순서와 달라도
p1/p2 번호가 바뀌지 않는다.

| 슬롯 | 항목 바이트 | 최종 type | 시작 LBA | 섹터 수 | 처리 |
|---|---:|---|---:|---:|---|
| p1 | 446~461 | 83 | 104,448 | 65,536 | boot를 51~83 MiB로 이동 |
| p2 | 462~477 | 83 | 38,912 | 65,536 | 원본 항목 그대로 |
| p3 | 478~493 | 05 | 169,984 | 15,099,904 | extended를 83 MiB~장치 끝으로 |
| p4 | 494~509 | 00 | 0 | 0 | 기존 FAT 항목 삭제, 16 B를 0으로 |

실제 저장은 생성한 **512 B MBR 파일 한 개를 LBA 0에 기록**하는 것이다.
U-Boot가 시작하는 `0x400`이나 첫 1 MiB 전체를 기록하는 것이 아니다.
새 MBR 및 원본 MBR 비교에서 위 보존 바이트가 일치하는 것을 확인했다.

## p5~p9는 EBR 다섯 개도 갱신

MBR만 바꾸면 기존 논리 파티션은 원하는 배치가 되지 않는다. 새 p3 안에
아래 EBR 체인을 만든다. EBR의 첫 항목은 해당 EBR에 대한 상대 주소로
파일시스템을 지정하고, 두 번째 항목은 p3 시작에 대한 상대 주소로 다음
EBR을 연결한다. 마지막 EBR의 다음 항목은 비운다. 각 서명은 `55 aa`이다.

| EBR LBA | 첫 항목 | 논리 파티션 시작 | 섹터 수 | 다음 EBR LBA |
|---:|---|---:|---:|---:|
| 169,984 | p5 system | 172,032 | 2,097,152 | 2,269,184 |
| 2,269,184 | p6 cache | 2,271,232 | 131,072 | 2,402,304 |
| 2,402,304 | p7 data | 2,404,352 | 12,326,912 | 14,731,264 |
| 14,731,264 | p8 vendor | 14,733,312 | 524,288 | 15,257,600 |
| 15,257,600 | p9 misc | 15,259,648 | 8,192 | 없음 |

각 첫 항목의 상대 시작은 모두 2,048섹터(1 MiB)이다. 준비한 테이블 파일은
[`emmc-20261001-final-partition-table`](../../deliverables/emmc-20261001-final-partition-table/manifest.json)
묶음이며 MBR 512 B + EBR 512 B × 5 = 총 3,072 B이다. manifest에는 각
파일의 기록 LBA·길이·해시와 원본 MBR 해시를 적었다. 테이블 파일만 준비된
것이며 완성된 설치 패키지는 아니다.

## 실제 기록 순서

1. **입력/대상 확인.** 모든 패키지 파일 해시, raw 길이, CID, eMMC 크기,
   마운트 상태, 첫 51 MiB의 보호 범위를 확인한다. 복구 파일과 외부 재진입
   경로가 준비된 상태여야 한다. 원본 MBR과 원본 misc를 패키지/SD에 저장하고
   misc는 적어도 RAM에도 읽어 검증한다. 새 data가 원래 misc 위치까지
   덮으므로 이 사본 확보는 data 기록보다 먼저 한다.
2. **새 payload 기록.** system을 84 MiB, cache를 1,109 MiB, data를
   1,174 MiB, vendor를 7,194 MiB에 기록한다. misc는 원본 4,186,112 B에
   8,192 B zero padding을 붙여 7,451 MiB에 기록한다. 각 기록은 새 시작
   LBA와 크기를 사용하는 전체 eMMC의 절대 범위로 수행하고, 해당 범위를
   다시 읽어 raw 해시를 비교한다. 아직 이전 테이블인 `/dev/mmcblk0p5`
   등의 파티션 장치를 목표 위치로 사용하지 않는다. 새 vendor 첫 512 B가
   0인 것도 검사한다.
3. **boot 기록.** 검증된 eMMC ramdisk와 appended DTB를 갖는 새 boot
   32 MiB 범위를 51 MiB에 기록하고 읽기 해시를 확인한다. 원래 p2 recovery
   19~51 MiB는 기록하지 않는다. 첫 51 MiB의 섹터 0 외 부분이 원본과
   동일한지 확인한다.
4. **테이블 반영.** 준비한 EBR 다섯 개를 각 LBA에 기록하고 읽기 해시를
   검사한다. 모든 payload와 EBR이 검증된 뒤 **MBR 512 B를 마지막에
   기록**한다. MBR을 다시 읽어 보존 바이트와 최종 항목을 비교한다.
5. **표/내용 검증.** fsync/블록 캐시 flush를 수행한다. 마운트가 없는 상태에서
   커널에 partition table reread를 요청하고 각 p1/p2/p5~p9의 sysfs
   start/size가 최종 JSON과 일치하는지 확인한다. 재읽기가 실패하면 RAM
   설치 환경에서 작업을 멈추고 외부 재진입으로 검증을 계속한다. ext4 검사,
   boot header, p2 원본 해시, U-Boot/hidden 영역 보존도 확인한다.
6. **정상 부팅 확인.** 모든 검증을 통과한 뒤 SD를 제거하고 전원 부팅한다.
   `/system`, `/vendor`, `/data`가 실제 eMMC p5/p8/p7인지 확인하고 별도로
   recovery 진입을 확인한다. 순정 recovery의 초기화/업데이트 작업은 Android 8
   호환성을 확인하기 전 자동 실행하지 않는다.

MBR 마지막 기록은 전체 설치를 원자적으로 만들거나 옛 OS의 중간 부팅을
보장하지 않는다. 새 payload가 원래 system/data/EBR까지 덮으므로 중간
전원 차단 시 정상 OS가 부팅되지 않을 수 있다. U-Boot/원래 recovery의
payload는 남아 있지만 복구 환경의 정상 마운트까지 보장하는 것은 아니다.
이 때문에 Android와 독립적인 Fastboot RAM 설치기 재진입을 선행 검증한다.

## 실패 시 복원

외부 Fastboot RAM 환경에서 9월 원본의 51 MiB 이후 범위를 복원하고
원본 EBR/내용을 확인한 뒤 원본 MBR을 마지막에 반영한다. 보존 범위
`[512 B, 51 MiB)`가 계속 원본과 동일하다면 U-Boot/waveform/logo/recovery를
다시 기록할 필요가 없다. 전체 user area 읽기 SHA-256을 9월 원본
`7783c8529e3b89df29a076f2fb8ac7e4216e7e8bca864db50ae872be1e3baf6f`와
대조한다. 이 대상에 맞는 범위 복원기는 별도 구현하며 7월 다른 기기용
스크립트를 사용하지 않는다.

## 준비 상태

최종 JSON에서 생성한 실제 MBR/EBR 파일을 일반 임시 이미지에 넣어 Linux
`sfdisk`와 `partx`의 주소/번호가 일치하는 것을 확인했다. 생성 코드와 로그는
`.orchestrator/logs/emmc-review-20261001/build_final_partition_table.py`,
`final-table-build.log`에 있다. 지금 준비된 것은 **테이블 파일과 설치 설계**다.
eMMC 제품 이미지, 압축 패키지, RAM writer/복원기 및 실기기 검증은 남아 있다.
