# E70Q10 Android 8 리더 설정·SystemUI 설계

## 목표

RIDI PAPER PRO 순정 앱의 설정 흐름과 시각 자산을 Android 8의 `Settings` 및
`SystemUI`에 이식한다. 일반 태블릿 UI를 축소하는 방식이 아니라, E Ink에서
불필요한 이동·투명도·실시간 애니메이션을 만들지 않는 정적 리더 UI를 만든다.

기준 해상도는 세로 `1404 x 1872`이며 회전은 잠근다.

## 순정 APK에서 확인한 구조

### RIDI 설정의 5개 탭

`com.ridi.paper.SettingsActivity`와 `SettingsFragmentPaper`는 다음 고정 탭을
사용한다.

1. 기기 설정
2. 뷰어 설정
3. 파일 관리
4. 전원/보안
5. 편의 기능

화면은 상단 제목, 밑줄 탭, 정적인 목록 행으로 구성된다. 새 UI에서도 카드,
리플, 확대/축소, 슬라이드 탭 전환은 사용하지 않는다.

### 실제 설정 항목

| 순정 분류 | 확인된 항목 | Android 8 처리 |
|---|---|---|
| 기기 | 시스템 업데이트 | `기기 정보` 하위로 유지하되 OTA가 준비되기 전에는 숨김 |
| 기기 | 슬립 화면 | `화면 및 전원`에 유지 |
| 기기 | 프론트라이트 켜질 때 밝기 | `프론트라이트`에 통합 |
| 기기 | 최근 읽은 책 | RIDI 전용이므로 제외 |
| 기기 | 날짜 및 시간 | AOSP DateTimeSettings 재사용 |
| 기기 | 기기 정보 | AOSP DeviceInfoSettings 재사용 |
| 뷰어 | 페이지 새로고침 | `화면 갱신`으로 유지 |
| 뷰어 | 읽던 페이지/독서노트 동기화 | RIDI 서비스 전용이므로 제외 |
| 뷰어 | 사용자 글꼴 | 앱별 기능이므로 제외 |
| 파일 | 사용자 파일 추가/다운로드 위치 | RIDI 전용이므로 제외 |
| 파일 | 저장소 | AOSP StorageSettings 재사용 |
| 파일 | 임시 데이터 삭제 | `앱 및 저장소`에서 앱별 데이터 관리로 대체 |
| 전원/보안 | 잠금 설정 | 이 제품 정책상 잠금화면을 제거하므로 제외 |
| 전원/보안 | 배터리 잔량 표시 | 유지 |
| 전원/보안 | 플립 커버 오토 슬립 | Hall 센서 확인 후 조건부 노출 |
| 전원/보안 | 슬립 모드 타이머 | 유지 |
| 전원/보안 | 전원 끄기 타이머 | 유지 |
| 전원/보안 | 기기 초기화 | 유지하되 확인 화면을 2단계로 구성 |
| 편의 | 도움말/사전/위키피디아 | RIDI 전용이므로 제외 |

순정에서 확인된 관련 속성은
`persist.sys.restore_brightness`, `persist.sys.ridi.battery.text`,
`persist.sys.enable_hallsensor`, `persist.sys.shutdowntime`이다. Android 8에서는
가능하면 `Settings.System`/`Settings.Global`과 전용 EPD 서비스로 옮기고,
호환성이 필요한 속성만 함께 기록한다.

## 최종 Settings 정보 구조

설정 첫 화면은 4개 탭만 둔다.

### 화면 및 조명

- 프론트라이트
  - 밝기 0–N 단계
  - 색온도 0–N 단계
  - 켤 때 이전 밝기 복원
- 화면 갱신
  - 기본 모드: 자동/품질 우선/속도 우선
  - 전체 정리 주기: 안 함/5/10/20 페이지
  - 지금 전체 새로고침
- 슬립 화면
- 화면 꺼짐 시간

### 네트워크

- Wi‑Fi 켜기/끄기
- Wi‑Fi 네트워크 선택
- 날짜 및 시간

블루투스, 셀룰러, SIM, VPN, 테더링, NFC, 위치 항목은 노출하지 않는다.

### 앱 및 저장소

- 설치된 앱
- 내부 저장소
- SD 카드
- 알림 설정
- 기본 런처

### 기기

- 배터리 잔량 숫자 표시
- 자동 전원 끄기
- 플립 커버 절전 — 하드웨어 확인 시에만 노출
- 기기 정보
- 재부팅/전원 끄기
- 기기 초기화

## 프론트라이트 화면

순정 `BrightnessActivity`는 두 열로 나뉜다.

- 왼쪽: `밝기 조절`, 최대/최소 밝기, `+`, 단계 막대, `-`
- 오른쪽: `색 온도 조절`, 따뜻한 색/덜 따뜻한 색, `+`, 단계 막대, `-`

이 구조를 그대로 사용한다. 연속 SeekBar 대신 누를 때 한 단계씩 즉시 바뀌는
고정 막대를 쓴다. 누르고 있는 동안 반복 증가시키지 않으며, 상태 변화 영역만
부분 갱신한다.

구현 경로는 다음과 같다.

```text
Settings/SystemUI FrontlightController
    -> android.hardware.light / E70Q10 lights HAL
    -> LM3630A brightness + color-temperature channels
    -> sysfs는 HAL 내부의 최종 fallback으로만 사용
```

순정 앱은 `screen_brightness`, 반사 호출
`PowerManager.setBacklightBrightness(int)`, 그리고
`ACTION.FRONTLIGHT_ON/OFF`를 사용한다. Android 8에서는 이 비공개 앱 호출을
그대로 복제하지 않고 lights HAL을 단일 진실 공급원으로 삼는다.

## SystemUI

### 상태바

- 불투명 흰색 배경
- 분 단위 시계
- Wi‑Fi 상태
- 배터리 아이콘과 선택적 퍼센트
- 알림 개수
- 초, 네트워크 활동 화살표, 충전 애니메이션은 사용하지 않음

### 빠른 패널

드래그되는 Android 알림 shade 대신, 빠른 버튼을 누르면 전체 화면 불투명
패널을 즉시 표시한다.

고정 동작은 순정 `QuickAction`을 기준으로 한다.

| 동작 | 순정 명칭 | 새 동작 |
|---|---|---|
| 전체 새로고침 | 새로고침 | GC16 전체 갱신 |
| 프론트라이트 | 프론트라이트 | 조명 패널 열기 |
| Wi‑Fi | Wi‑Fi | 즉시 토글, 길게 눌러 Wi‑Fi 설정 |
| 뒤로 | 뒤로 가기 | 패널 닫기/뒤로 |
| 터치 잠금 | 터치 잠금 | 선택 기능으로 유지 |
| 넘김 버튼 전환 | 넘김 버튼 전환 | 현재 페이지 버튼을 그대로 쓰므로 제외 |

빠른 패널 하단에는 `알림`, `설정`, `전원` 세 개의 큰 정적 버튼을 둔다.
QS 타일 ripple, 페이지 스와이프, 밝기 슬라이더 드래그, heads-up,
배경 dim은 사용하지 않는다.

### 물리 버튼

- 오른쪽 Quick 버튼 짧게: Back
- 오른쪽 Quick 버튼 길게: 빠른 패널 열기
- 좌우 페이지 버튼: 기존 Page Up/Page Down 매핑 유지
- 볼륨 팝업: 페이지 버튼과 무관하며 완전히 비활성화

## E Ink 갱신 규칙

- 탭/행 선택: 선택 행과 새 본문 영역만 `PARTIAL + GC16`
- 숫자/단계 한 칸 변화: 해당 값 영역만 `PARTIAL + DU`
- 빠른 패널 열기/닫기: 패널 전체 영역 `FULL + GC16`
- Wi‑Fi 목록 화면 전환: `FULL + GC16`
- 연속 변경은 병합하고, 완료 후 한 번만 품질 갱신
- 프레임 타이머, progress spinner, 초 단위 시계는 만들지 않음

화면 코드는 waveform ioctl을 직접 호출하지 않는다. View 영역과 의도를 EPD
서비스에 전달하고, SurfaceFlinger/HWC가 실제 dirty rectangle과 합쳐 최종
업데이트를 제출해야 한다.

## Android 8 이식 구조

### Settings

기존 `packages/apps/Settings`의 Wi‑Fi, 날짜/시간, 저장소, 앱, 기기 정보
fragment는 보존한다. E70Q10 전용 launcher activity/fragment만 추가해 이
fragment들로 명시적으로 이동한다. 원래 Settings 대시보드는 비상 접근용으로
남겨 두되 launcher에서는 숨긴다.

전용 구성요소:

- `RidiReaderSettingsActivity`
- `RidiReaderSettingsFragment`
- `FrontlightSettingsFragment`
- `EinkDisplaySettingsFragment`
- `ReaderPowerSettingsFragment`
- `FrontlightController`
- `EpdSettingsClient`

### SystemUI

기존 shade를 억지로 개조하기보다 E70Q10 전용 `ReaderQuickPanel`을 두고,
기본 shade/heads-up/최근 앱은 제품 overlay와 정책 코드로 비활성화한다.
SystemUI와 Settings는 동일한 `FrontlightController` 계약을 사용하되 서비스
호출 코드는 각각의 모듈에 얇게 둔다.

## 자산 선택

실제 기기의 세로 화면 밀도에 맞는 `sw702dp-xhdpi` RIDI 자산을 우선 추출했다.
설정용 60 px 아이콘과 actionbar용 80 px 아이콘은 흑백이라 E Ink에서 그대로
사용할 수 있다.

사용 우선순위:

1. RIDI 앱의 흑백 설정/QuickAction 자산
2. stock SystemUI의 Wi‑Fi·배터리·Back/Home 자산
3. stock Settings 자산은 RIDI에 대응 아이콘이 없을 때만 사용

로컬 추출물은 `ui-reference/extracted`, 비교표는
`ui-reference/contact-sheets`에 있다. 원본 APK 자산은 배포권을 별도로
확인해야 하므로 공개 저장소에 무조건 포함하지 않는다.

## 구현 순서

1. Settings 전용 launcher와 4개 정적 탭
2. 프론트라이트 Controller를 lights HAL에 연결
3. Wi‑Fi/날짜/저장소/앱/기기 정보 fragment 연결
4. EPD 갱신 설정과 전체 새로고침 동작 연결
5. ReaderQuickPanel과 Quick 버튼 짧게/길게 동작 연결
6. 기본 shade, heads-up, recent, Bluetooth/cellular UI 제거 검증
7. 1404 x 1872 실기기에서 dirty rectangle 및 잔상 검증

