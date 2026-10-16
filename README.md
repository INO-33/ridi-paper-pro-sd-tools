# RIDI PAPER PRO · SD/eMMC 빌드·배포 도구

RIDI PAPER PRO의 SD 준비, eMMC 업데이트·업그레이드, 백업과 Windows GUI 배포판
생성을 담당하는 저장소입니다. Android/Chromium 컴파일 환경과 분리해 관리합니다.

**전체 프로젝트:** [메인 manifest 저장소](https://github.com/INO-33/ridi-paper-pro)
 · **Android 빌드 환경:** [빌드 도구 저장소](https://github.com/INO-33/ridi-paper-pro-dev-tools)

## 구성

| 경로 | 내용 |
|---|---|
| `porting/e70q10/emmc-tool/` | 현재 SD/eMMC CLI·GUI, RAM 도구, Windows 배포 빌더 |
| `porting/e70q10/emmc-tool/runtime.zip` | 보존한 GUI 실행용 RAM 런타임 입력 |
| `porting/e70q10/emmc-updater/` | 선택 파티션 업데이터와 검증된 필수 자산 |
| `porting/e70q10/emmc-installer/` | 초기 설치 도구의 과거 소스 |
| `verify_assets.py`, `ASSET_SHA256SUMS` | 런타임·소스·필수 자산의 무결성 검사 |

OS 이미지와 전체 기기 백업은 별도 산출물입니다. 이 저장소에는 소스와 동작에
필요한 고정 런타임·라이선스·해시를 보관합니다.

## GUI 소스 실행

Python 3.10 이상과 Tk가 필요합니다. GUI의 실제 fastboot 동작에는 해당 OS용
platform-tools와 기기 드라이버가 필요합니다.

```sh
python3 verify_assets.py
python3 porting/e70q10/emmc-tool/ridi_gui.py
```

이미지 입력과 모드/백업 옵션은
[`GUI_README.md`](porting/e70q10/emmc-tool/GUI_README.md)를 확인합니다.
SD 준비 작업은 선택한 SD를 포맷하므로 대상 디스크를 확인해야 합니다.
업데이트와 초기 업그레이드는 기록 범위 및 userdata 처리 방식이 다릅니다.

## Windows 실행파일과 GUI 패키지 만들기

실행용 GUI 폴더를 만드는 `build_gui_bundle.py`는 검증된 seed ZIP과 SHA256을
입력으로 받습니다. 그 폴더의 `runtime.zip`, 라이선스와 GUI 소스를 사용해
Windows에서 실행파일을 만듭니다.

```powershell
py -3 .\porting\e70q10\emmc-tool\build_windows.py --app-dir C:\PaperProGUI --platform-tools C:\platform-tools --output C:\PaperProRelease
```

Windows 빌드는 Windows에서 실행합니다. 자세한 준비 조건과 배포 파일 구성은
[`WINDOWS_BUILD.md`](porting/e70q10/emmc-tool/WINDOWS_BUILD.md)에 있습니다.
CLI 및 RAM 실행 결과 확인은
[`emmc-tool/README.md`](porting/e70q10/emmc-tool/README.md), 선택 파티션 업데이터는
[`emmc-updater/README.md`](porting/e70q10/emmc-updater/README.md)를 참고합니다.

## Android 소스와 함께 사용

메인 manifest는 이 저장소를 Android 소스의 `ridi-sd-tools`에 배치합니다.
환경 설정은 `$RIDI_WORKSPACE/porting`을 이 저장소의 `porting/`에 연결해 기존
도구 경로를 유지합니다. Android 이미지 컴파일은 빌드 도구 저장소가 담당합니다.

체크포인트: **2026-10-16**. 이번 업로드는 소스·자산 보존과 구조/무결성 검사이며,
SD 기록·기기 플래시·Windows 실기기 검증을 실행한 작업은 아닙니다. 과거 진단과
초기 설치 스크립트에는 원래 백업/출력 경로가 남아 있을 수 있습니다.
