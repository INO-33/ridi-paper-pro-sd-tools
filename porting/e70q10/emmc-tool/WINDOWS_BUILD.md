# Windows EXE 빌드

Windows 10/11 x64에서 공식 Python 3.10 이상 x64(설치 시 Tcl/Tk 포함)로 실행합니다.
PyInstaller는 별도 가상환경에 고정 버전 6.22.3으로 설치합니다. 첫 실행에는 인터넷이 필요합니다.
Linux에서 Windows EXE를 생성하는 스크립트가 아닙니다.

## 빌드

1. 최신 GUI ZIP을 풀고 해당 폴더에서 PowerShell을 엽니다.
2. Windows용 Android platform-tools의 `fastboot.exe`, `AdbWinApi.dll`,
   `AdbWinUsbApi.dll`, 가능하면 `NOTICE.txt`를 `platform-tools` 폴더에 넣습니다.
3. 실행합니다.

```powershell
.\build_windows.cmd
```

다른 위치에 있는 platform-tools를 사용할 수도 있습니다.

```powershell
.\build_windows.cmd --platform-tools 'C:\Android\platform-tools'
```

OS 이미지 세 개도 포함하려면:

```powershell
.\build_windows.cmd --platform-tools 'C:\Android\platform-tools' --images 'D:\PaperPro-images'
```

fastboot를 배포본에 포함하지 않으려면 `--without-fastboot`를 지정합니다.
이 경우 사용자가 GUI에서 fastboot 폴더를 선택해야 합니다.
`images` 폴더에 나중에 이미지를 넣거나 GUI에서 다른 이미지 폴더를 선택해도 됩니다.
이미지 포함 빌드는 파일 존재만 확인하며 이미지 내용 검증은 SD 준비 시 수행합니다.

출력:

- `windows-release\PaperProSD\PaperProSD.exe`
- `windows-release\PaperProSD-windows-x64.zip`
- ZIP의 SHA256 파일

배포 시 폴더 전체를 ZIP으로 전달합니다. EXE 하나만 복사하면 실행되지 않습니다.
수신자는 Python을 설치할 필요가 없습니다. 실행 시 관리자 권한을 요청합니다.

기존 출력은 덮어쓰지 않습니다. 다시 빌드하려면 새 출력 경로를 지정하세요.

```powershell
.\build_windows.cmd --output '.\windows-release-r2'
```

소스 디렉터리에서 빌드 스크립트를 실행할 경우 `--app-dir`로 `runtime.zip`이
들어 있는 GUI 배포 폴더를 지정합니다. `.venv-pyinstaller`는 다음 빌드에 재사용하며
PyInstaller 임시 작업 파일은 작업 종료 시 제거합니다.

## 검증 범위

Linux에서 Python 구문, frozen EXE의 경로/인자 처리와 빌드 구성 모의 검사를 수행했습니다.
Windows 네이티브 빌드 및 실제 SD 기록 시험은 Windows에서 별도로 수행해야 합니다.

[PyInstaller 공식 실행 옵션](https://www.pyinstaller.org/en/stable/usage.html)
