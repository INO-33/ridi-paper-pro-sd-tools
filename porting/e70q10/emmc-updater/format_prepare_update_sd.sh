#!/bin/bash
# One confirmation, then format the selected external SD and copy verified files.
set -euo pipefail
ROOT=/home/juwon/ridi
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PREP="$SCRIPT_DIR/prepare_update_sd.sh"
if [[ $# -lt 1 || $1 == --help ]]; then
    echo "사용법: sudo $0 /dev/sdX [업데이트.tar] [--targets boot|system|vendor|조합] [--manual] [--no-reboot]"
    echo '선택한 SD 전체를 단일 FAT32 p1로 포맷하고 boot/system/vendor 업데이트 파일을 넣습니다.'
    exit 0
fi
DEV_INPUT=$1;shift
ARCHIVE="$ROOT/deliverables/e70q10-update-20261006-auto.tar"
if [[ $# -gt 0 && $1 != --* ]]; then ARCHIVE=$1;shift;fi
PREP_OPTIONS=("$@")
# This is the only confirmation, and is shown before device inspection or work.
printf '경고: %s의 모든 파티션과 데이터를 삭제하고 업데이트용 SD로 포맷합니다. RAM 부팅 시 SD 설정에 따라 선택 파티션을 자동 기록하고 재부팅합니다. 계속할까요? [y/N] ' "$DEV_INPUT" >/dev/tty
read -r ANSWER </dev/tty
case "$ANSWER" in y|Y|yes|YES) ;; *) echo '취소했습니다.';exit 0;; esac
fail() { echo "중단: $*" >&2;exit 1; }
[[ $EUID == 0 ]] || fail 'sudo로 실행하세요.'
[[ ${SD_COPY_JOBS:-8} =~ ^([1-9]|[12][0-9]|3[0-2])$ ]] || fail 'SD_COPY_JOBS는 1..32로 지정하세요.'
for tool in lsblk readlink blockdev sfdisk mkfs.vfat udevadm mount umount findmnt sha256sum python3 sync; do
    command -v "$tool" >/dev/null || fail "필요한 도구가 없습니다: $tool"
done
DEV=$(readlink -f -- "$DEV_INPUT")
[[ -b $DEV ]] || fail '블록 장치가 아닙니다.'
[[ $(lsblk -dnro TYPE "$DEV") == disk ]] || fail '파티션 대신 SD 전체 장치를 지정하세요.'
REMOVABLE=$(lsblk -dnro RM "$DEV")
TRANSPORT=$(lsblk -dnro TRAN "$DEV")
[[ $REMOVABLE == 1 || $TRANSPORT == usb ]] || fail '외장 SD/USB 매체가 아닙니다.'
[[ $(blockdev --getss "$DEV") == 512 ]] || fail '512바이트 논리 섹터 장치만 지원합니다.'
[[ $(blockdev --getsize64 "$DEV") -le 2199023255552 ]] || fail 'DOS 파티션 테이블 용량을 초과합니다.'
# Refuse system mounts, swap, and any active block holder before unmounting.
python3 - "$DEV" <<'PY'
import json,pathlib,subprocess,sys
rows=json.loads(subprocess.check_output(['lsblk','-Jpo','NAME,TYPE,MOUNTPOINTS',sys.argv[1]]))['blockdevices']
def visit(row):
 if row['type'] not in ('disk','part'):raise SystemExit('중단: 장치 매퍼/RAID 등 활성 종속 장치가 있습니다.')
 for mp in row.get('mountpoints',[]) or []:
  if mp and (mp=='[SWAP]' or not mp.startswith(('/media/','/mnt/','/run/media/'))):
   raise SystemExit('중단: 시스템/비표준 마운트가 포함돼 있습니다: '+mp)
 name=pathlib.Path(row['name']).name
 if list((pathlib.Path('/sys/class/block')/name/'holders').iterdir()):
  raise SystemExit('중단: 활성 block holder: '+name)
 for child in row.get('children',[]):visit(child)
for row in rows:visit(row)
PY
LOGDIR="$ROOT/.orchestrator/logs/emmc-update-20261001"
mkdir -p "$LOGDIR"
LOG="$LOGDIR/sd-format-$(date +%Y%m%d-%H%M%S).log"
trap 'rc=$?; printf "중단: SD 준비 작업 실패(종료 코드 %s). 로그: %s\n" "$rc" "$LOG" >&2; exit "$rc"' ERR
[[ -x $PREP && -f $ARCHIVE && -f $ARCHIVE.sha256 ]] || fail '업데이트 패키지/준비 스크립트가 없습니다.'
printf '포맷 전 업데이트 패키지와 boot/system/vendor 전용 구성을 검사합니다.\n'
(cd "$(dirname "$ARCHIVE")"; sha256sum -c "$(basename "$ARCHIVE").sha256") >>"$LOG" 2>&1 || fail "패키지 해시가 다릅니다: $LOG"
python3 - "$SCRIPT_DIR" "$ARCHIVE" "$DEV" "${PREP_OPTIONS[@]}" >>"$LOG" 2>&1 <<'PY' || fail "포맷 전 업데이트/용량 검사 실패: $LOG"
import sys,subprocess
sys.path.insert(0,sys.argv[1]);from validate_package import validate
from selection import sd_options,sd_plan
report=validate(sys.argv[2]);plan=sd_plan(report,sd_options(sys.argv[4:]))
assert int(subprocess.check_output(['blockdev','--getsize64',sys.argv[3]]))>=max(plan['required_bytes']+(64<<20),1073741824),'SD 공간 부족 (FAT32 최소 1GiB)'
print('UPDATE PACKAGE VERIFIED',report['archive_sha256'],plan['file_bytes'],plan['targets'],plan['automatic'],plan['reboot'])
PY
MOUNTPOINT=
MOUNTED=0
cleanup() {
    if [[ $MOUNTED == 1 ]]; then umount -- "$MOUNTPOINT" >>"$LOG" 2>&1 || true;fi
    if [[ -n $MOUNTPOINT ]]; then rmdir -- "$MOUNTPOINT" 2>/dev/null || true;fi
}
trap cleanup EXIT
printf 'SD 파티션 재생성 및 FAT32 포맷: %s\n' "$DEV"
# Unmount only partitions belonging to the explicitly selected disk.
while read -r NODE; do
    while findmnt -rn -S "$NODE" >/dev/null; do
        umount -- "$NODE" >>"$LOG" 2>&1 || fail "SD 마운트를 해제할 수 없습니다: $NODE"
    done
done < <(lsblk -nrpo NAME "$DEV" | tac)
printf 'label: dos\nunit: sectors\n\nstart=2048, type=c\n' | sfdisk --wipe always --wipe-partitions always "$DEV" >>"$LOG" 2>&1
blockdev --rereadpt "$DEV" >>"$LOG" 2>&1
udevadm settle
if [[ $DEV =~ [0-9]$ ]]; then PART=${DEV}p1;else PART=${DEV}1;fi
for ((n=0;n<10;n++)); do [[ -b $PART ]] && break;sleep 1;done
[[ -b $PART ]] || fail '새 SD p1을 찾을 수 없습니다.'
# Remove an automatic desktop mount before formatting the new partition.
while findmnt -rn -S "$PART" >/dev/null; do umount -- "$PART" >>"$LOG" 2>&1;done
mkfs.vfat -F 32 -S 512 -n RIDI_UPD "$PART" >>"$LOG" 2>&1
udevadm settle
MOUNTPOINT=$(mktemp -d /mnt/e70q10-update.XXXXXX)
mount -t vfat -o rw,nosuid,nodev "$PART" "$MOUNTPOINT" >>"$LOG" 2>&1
MOUNTED=1
printf '선택된 업데이트 파일과 update.conf를 복사하고 SD 해시를 검증합니다.\n'
"$PREP" "$MOUNTPOINT" "$ARCHIVE" "${PREP_OPTIONS[@]}" >>"$LOG" 2>&1 || fail "SD 파일 준비 실패: $LOG"
sync -f "$MOUNTPOINT"
umount -- "$MOUNTPOINT" >>"$LOG" 2>&1
MOUNTED=0
# Ensure no desktop auto-mount remains when reporting safe removal.
while findmnt -rn -S "$PART" >/dev/null; do umount -- "$PART" >>"$LOG" 2>&1;done
printf 'SD 준비 완료. 카드를 분리해 기기에 넣으세요. 로그: %s\n' "$LOG"
printf 'RAM 부팅 후 SD의 update.conf에 따라 자동 적용됩니다. 실패하면 재부팅하지 않습니다.\n'
