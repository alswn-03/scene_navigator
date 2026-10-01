# Scene Navigator

macOS **QuickTime Player**로 영상을 재생하면서, 작은 보조 창에서 씬 구간을 빠르게 탐색하고 원하는 시점으로 이동하는 도구입니다.
새 영상 플레이어가 아니라, QuickTime을 원격 조종하는 컴팩트한 컨트롤러입니다.

- 씬 마커 클릭 / 타임라인 아무 곳 클릭으로 이동
- 현재 재생 위치와 재생 진행 표시, QuickTime과 실시간 동기화
- 타임라인 확대/축소, 좌우 이동(드래그 · 트랙패드 가로 스크롤 · 하단 바)
- 재생/일시정지, 이전/다음 씬, 재생 배속(0.5×–3×)

## 보안

완전 로컬로 동작합니다. 외부 통신, 업로드, 최근 파일/경로 저장이 없으며, 선택한 파일 경로는 프로그램을 끄면 사라집니다.
영상과 씬 데이터는 민감할 수 있어 `.gitignore`에서 `*.mov`, `*.mp4`, `*.m4v`, `*.json`(샘플 제외)을 제외해 두었습니다. **실제 데이터는 커밋하지 마세요.**

## 요구 사항

- macOS (QuickTime Player 필요)
- Python **3.12**

Python 3.12가 없다면 Homebrew로 설치합니다.

```bash
brew install python@3.12
```

## 설치

```bash
git clone <저장소 주소>
cd <클론된 폴더>

python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`.venv`는 컴퓨터마다 새로 만듭니다. 다른 컴퓨터로 복사하지 마세요.

## 실행

```bash
source .venv/bin/activate
python main.py
```

VSCode를 쓴다면 `Cmd+Shift+P` → `Python: Select Interpreter` → `.venv`를 고른 뒤 `main.py`를 실행해도 됩니다.

### 처음 실행할 때 권한

처음 QuickTime을 제어하려고 하면 macOS가 자동화 권한을 묻습니다.
**허용**해야 동작합니다. 실수로 거부했다면 `시스템 설정 → 개인정보 보호 및 보안 → 자동화`에서
터미널(또는 VSCode)의 **QuickTime Player** 항목을 켜 주세요.

## 사용법

1. 우측 상단 **Files**를 눌러 영상(`.mov` `.mp4` `.m4v`)과 씬 데이터(`.json`)를 각각 선택합니다.
   영상을 고르면 QuickTime Player에서 자동으로 열립니다.
2. 타임라인의 마커(씬 시작점)나 빈 곳을 클릭하면 QuickTime이 해당 시간으로 이동합니다.
3. 하단 슬라이더(또는 − / +)로 확대하고, 확대 상태에서는 드래그 / 트랙패드 가로 스크롤 / 하단 회색 바로 좌우 이동합니다.
4. 좌측 하단 `1×` 버튼으로 재생 배속을 바꿉니다.

> 제어 대상은 QuickTime의 **맨 앞에 있는 영상 창**입니다. 여러 영상을 열어 두었다면 원하는 창을 앞으로 가져오세요.

## 중단 / 종료

- 앱 창을 닫으면(`Cmd+Q`) 종료됩니다.
- 터미널에서 실행했다면 `Ctrl+C`로도 중단할 수 있습니다.
- 가상환경을 빠져나오려면:

```bash
deactivate
```

종료해도 QuickTime Player 창은 그대로 남습니다(영상은 계속 재생될 수 있어요).

## 씬 데이터 형식

시간은 `HH:MM:SS` 문자열입니다. `start`, `end`는 필수, `name`은 선택(`null` 가능)입니다.

```json
[
  { "name": null,   "start": "00:00:00", "end": "00:00:45" },
  { "name": "씬2",  "start": "00:00:45", "end": "00:04:01" }
]
```

샘플: [test_timeline_data.json](test_timeline_data.json)

## 파일 구조

| 파일 | 역할 |
|---|---|
| `main.py` | 앱 진입점, GUI 조립, QuickTime 상태 동기화 |
| `quicktime_controller.py` | QuickTime 제어(AppleScript) 및 백그라운드 폴링 |
| `scene_data.py` | 씬 JSON 읽기 / 검증 / 시간 변환 |
| `timeline_widget.py` | 타임라인 · 마커 · 줌 · 좌우 이동 |
| `files_dialog.py` | Files 선택 모달 |

## 문제 해결

| 증상 | 해결 |
|---|---|
| "QuickTime not running" 표시 | QuickTime Player를 실행하세요. |
| "No video in QuickTime" 표시 | QuickTime에 영상 창을 여세요(Files에서 영상 선택). |
| 클릭해도 이동하지 않음 | 위의 **자동화 권한**을 확인하세요. |
| `pip install` 실패 | `python --version`이 3.12인지, `.venv`가 활성화되어 있는지 확인하세요. |

## 알려진 한계

QuickTime의 위치 변화는 약 0.1–0.2초 간격으로 읽어 오므로, QuickTime에서 직접 조작한 내용이 약간의 지연 후 반영됩니다.
