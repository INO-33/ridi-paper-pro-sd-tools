#!/bin/bash
# One confirmation, then format the selected external SD and copy verified files.
set -euo pipefail
ROOT=/home/juwon/ridi
PREP="$ROOT/porting/e70q10/emmc-installer/prepare_sd.sh"
ARCHIVE="$ROOT/deliverables/e70q10-emmc-android8-install-20261001.tar"
BACKUP=/media/juwon/build/리디백업/backups/e70q10-PP1A1GK166561-20260923-full-emmc
if [[ $# != 1 || $1 == --help ]]; then
    echo "사용법: sudo $0 /dev/sdX"
    echo '선택한 SD 전체를 단일 FAT32 p1로 포맷하고 설치 패키지+복원 백업을 넣습니다.'
    exit 0
fi
# This is the only confirmation, and is shown before device inspection or work.
printf '경고: %s의 모든 파티션과 데이터를 삭제하고 설치용 SD로 포맷합니다. 계속할까요? [y/N] ' "$1" >/dev/tty
read -r ANSWER </dev/tty
case "$ANSWER" in y|Y|yes|YES) ;; *) echo '취소했습니다.';exit 0;; esac
fail() { echo "중단: $*" >&2;exit 1; }
[[ $EUID == 0 ]] || fail 'sudo로 실행하세요.'
for tool in lsblk readlink blockdev sfdisk mkfs.vfat udevadm mount umount findmnt sha256sum python3; do
    command -v "$tool" >/dev/null || fail "필요한 도구가 없습니다: $tool"
done
DEV=$(readlink -f -- "$1")
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
LOGDIR="$ROOT/.orchestrator/logs/emmc-install-20261001"
mkdir -p "$LOGDIR"
LOG="$LOGDIR/sd-format-$(date +%Y%m%d-%H%M%S).log"
trap 'rc=$?; printf "중단: SD 준비 작업 실패(종료 코드 %s). 로그: %s\n" "$rc" "$LOG" >&2; exit "$rc"' ERR
[[ -x $PREP && -f $ARCHIVE && -f $ARCHIVE.sha256 ]] || fail '설치 패키지/준비 스크립트가 없습니다.'
printf '포맷 전 설치 패키지와 백업 30개를 검사합니다.\n'
(cd "$(dirname "$ARCHIVE")"; sha256sum -c "$(basename "$ARCHIVE").sha256") >>"$LOG" 2>&1 || fail "패키지 해시가 다릅니다: $LOG"
python3 - "$ARCHIVE" "$BACKUP" "$DEV" >>"$LOG" 2>&1 <<'PY' || fail "포맷 전 원본/용량 검사 실패: $LOG"
import hashlib,pathlib,subprocess,sys,tarfile
archive,back,dev=sys.argv[1:];back=pathlib.Path(back)
with tarfile.open(archive) as t:
 rows=t.extractfile('e70q10-install/backup.sha256').read().decode().splitlines()
 need=sum(m.size for m in t.getmembers() if m.isfile())+7818182656+(128<<20)
 assert int(subprocess.check_output(['blockdev','--getsize64',dev]))>=need,'SD 공간이 부족합니다.'
 assert len(rows)==30
 for i,line in enumerate(rows):
  expected,name=line.split('  ',1);assert name==f'emmc.part{i:02d}'
  f=back/name;assert f.is_file() and not f.is_symlink(),name
  assert f.stat().st_size==((256<<20) if i<29 else 7818182656-29*(256<<20)),name
  h=hashlib.sha256()
  with open(f,'rb') as src:
   for b in iter(lambda:src.read(4<<20),b''):h.update(b)
  assert h.hexdigest()==expected,'원본 백업 해시 불일치: '+name
  print(name+' source SHA256 OK',flush=True)
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
mkfs.vfat -F 32 -S 512 -n RIDI_INST "$PART" >>"$LOG" 2>&1
udevadm settle
MOUNTPOINT=$(mktemp -d /mnt/e70q10-install.XXXXXX)
mount -t vfat -o rw,nosuid,nodev "$PART" "$MOUNTPOINT" >>"$LOG" 2>&1
MOUNTED=1
printf '설치 파일과 복원 백업을 복사하고 SD 해시를 검증합니다.\n'
"$PREP" "$MOUNTPOINT" >>"$LOG" 2>&1 || fail "SD 파일 준비 실패: $LOG"
sync
umount -- "$MOUNTPOINT" >>"$LOG" 2>&1
MOUNTED=0
# Ensure no desktop auto-mount remains when reporting safe removal.
while findmnt -rn -S "$PART" >/dev/null; do umount -- "$PART" >>"$LOG" 2>&1;done
printf 'SD 준비 완료. 카드를 분리해 기기에 넣으세요. 로그: %s\n' "$LOG"
printf 'RAM 콘솔 점검 명령: installer check /mnt/sd/e70q10-install\n'
