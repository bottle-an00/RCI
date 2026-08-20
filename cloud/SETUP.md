# 로컬 개발 환경 구축 (cloud)

`feat/cloud` 를 처음 받은 사람이 **로컬에서 서버를 띄우기까지** 필요한 절차.
한 번만 하면 되고, 이후에는 `dev.bat` 더블클릭이면 끝난다.

전체 흐름:

```
① Python 설치 확인  →  ② cloud/.venv 생성  →  ③ 의존성 설치  →  ④ dev.bat  →  ⑤ 확인
```

---

## 0. 전제

| 항목 | 요구 |
|---|---|
| Python | **3.10 이상** (`amqtt`·`fastapi`·`uvicorn` 이 `>=3.10` 요구). 개발 PC 기준 3.13.14 |
| OS | Windows 10/11 (권장) · Linux·macOS 는 `scripts/dev.sh` 로 동일 동작 |
| 셸 | PowerShell 7(`pwsh`) 권장. 없으면 Windows PowerShell 5.1 로 자동 폴백 |
| 포트 | `1883`(MQTT) · `8080`(MQTT over WebSocket) · `8123`(웹) 세 개가 비어 있어야 함 |

Python 확인:

```bash
py --version
```

`3.10` 미만이거나 없으면 [python.org](https://www.python.org/downloads/windows/) 에서 설치.
설치 시 **Add python.exe to PATH** 를 체크한다.

---

## 1. venv 는 반드시 `cloud/.venv` 에 만든다

경로와 이름이 **선택이 아니다.** `scripts/dev.ps1` 이 인터프리터를
`cloud/.venv/Scripts/python.exe` 로 직접 지목하기 때문에, `venv`·`.env` 같은 다른
이름으로 만들면 실행 즉시 이렇게 멈춘다.

```
.venv 파이썬을 찾을 수 없습니다: ...\cloud\.venv\Scripts\python.exe  (먼저 가상환경을 만드세요)
```

저장소 루트에서:

```bash
py -m venv cloud/.venv
```

> `cloud/.venv/` 는 `.gitignore` 에 있어 커밋되지 않는다. 그래서 받는 사람마다 이
> 작업을 한 번 해야 하고, 이 문서가 존재하는 이유다.

---

## 2. 의존성 설치 — requirements 는 두 개, venv 는 하나

`dev.bat` 은 **브로커 · 목 RCI · FastAPI 웹 세 프로세스를 같은 인터프리터로** 띄운다.
따라서 두 파일 모두 위에서 만든 하나의 venv 에 설치해야 한다.

| 파일 | 내용 |
|---|---|
| [`Codes/board/requirements.txt`](Codes/board/requirements.txt) | `paho-mqtt`, `amqtt` — 브로커 · 목 RCI |
| [`Codes/Cloud/requirements.txt`](Codes/Cloud/requirements.txt) | `fastapi`, `uvicorn[standard]`, `jinja2`, `paho-mqtt` — 웹 |

저장소 루트에서 (venv 를 활성화하지 않고 venv 파이썬을 직접 호출하는 방식 —
활성화 상태를 헷갈릴 여지가 없어 이 쪽을 권한다):

**Windows (PowerShell / cmd)**

```bash
cloud\.venv\Scripts\python.exe -m pip install -U pip
cloud\.venv\Scripts\python.exe -m pip install -r cloud\Codes\board\requirements.txt -r cloud\Codes\Cloud\requirements.txt
```

**Git Bash / Linux / macOS**

```bash
cloud/.venv/bin/python -m pip install -U pip -r cloud/Codes/board/requirements.txt -r cloud/Codes/Cloud/requirements.txt
```

(Linux·macOS venv 는 `Scripts/` 대신 `bin/` 이다. `dev.sh` 가 두 경로를 모두 시도한다.)

### 활성화해서 쓰고 싶다면

`pip` 를 짧게 치고 싶을 때만 필요하다. `dev.bat` 실행에는 **활성화가 필요 없다** —
스크립트가 venv 파이썬의 절대경로를 쓴다.

| 셸 | 명령 |
|---|---|
| PowerShell | `cloud\.venv\Scripts\Activate.ps1` |
| cmd | `cloud\.venv\Scripts\activate.bat` |
| Git Bash | `source cloud/.venv/Scripts/activate` |
| Linux/macOS | `source cloud/.venv/bin/activate` |

PowerShell 에서 실행 정책에 막히면(`... 스크립트를 로드할 수 없습니다`):

```bash
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

해제는 `deactivate`.

---

## 3. 실행

Windows 탐색기에서 **`cloud/dev.bat` 더블클릭.** 브로커 + 목 RCI + 웹이 한 창에 뜬다.

터미널에서 부를 수도 있다(옵션은 `dev.ps1` 로 그대로 전달된다):

```bash
cloud\dev.bat                    # 로컬 전용 + 목 RCI (기본 개발)
cloud\dev.bat -Lan -NoMock       # 핫스팟에서 실물 RCI 테스트
bash cloud/scripts/dev.sh        # Git Bash / Linux
```

- `-Lan` : 브로커·웹을 `0.0.0.0` 에 바인딩하고 접속용 IP 후보를 출력.
- `-NoMock` : 목 RCI 를 띄우지 않음(실물 RCI 가 브로커에 붙는 경우).

종료는 **그 창에서 Ctrl+C.** 창을 X 로 닫으면 자식 프로세스가 고아로 남으므로
`cloud/stop.bat` 을 돌린다. 자세한 종료 경로는
[`Codes/board/README.md`](Codes/board/README.md#종료가-어떻게-동작하나) 참조.

---

## 4. 확인

1. 브라우저에서 <http://localhost:8123> 접속.
2. 파이프 전체(브로커 연결 · RCI 생존 · 왕복 · id 상관)를 한 번에 검증:

```bash
cloud\.venv\Scripts\python.exe cloud\scripts\connection_test.py
```

실패하면 종료 코드 1 과 함께 어느 단계에서 끊겼는지 출력한다.

---

## 5. 자주 걸리는 것

| 증상 | 원인 / 해결 |
|---|---|
| `.venv 파이썬을 찾을 수 없습니다` | venv 위치·이름이 `cloud/.venv` 가 아니다. 1번을 다시. |
| `포트가 이미 사용 중입니다: 1883, ...` | 이전 실행이 남았다. `cloud\stop.bat` (무엇이 점유 중인지만 보려면 `cloud\stop.bat -WhatIf`) |
| `ModuleNotFoundError: No module named 'amqtt'` (또는 `fastapi`) | requirements 를 한쪽만 설치했다. 2번의 두 파일을 모두. |
| `Activate.ps1` 이 실행 정책에 막힘 | 위 `Set-ExecutionPolicy` 또는 애초에 활성화 없이 venv 파이썬 직접 호출 |
| 브로커 로그가 아무것도 안 찍힘 | 기본이 조용하다. `$env:RCI_BROKER_LOG="info"` 후 실행하면 접속/해제와 접속 IP 가 보인다. |
| Windows 방화벽이 python 인바운드를 물음 | `-Lan` 모드에서 정상. **사설 네트워크** 허용. |

브로커 주소·인증·TLS 등 환경변수는
[`Codes/board/README.md`](Codes/board/README.md#브로커-접속-설정-환경변수) 의 표를 따른다.

---

## 참고 — 다른 컴포넌트

이 문서는 `cloud/` 전용이다. 저장소에는 별도 의존성을 가진 컴포넌트가 더 있다
(`ur3/`, `rc-car/`, `web-ui/`). 각자 `requirements.txt` 를 가지며, 라즈베리파이(RCI)
쪽 코드인 `ur3/` 는 해당 디렉터리의 README 를 따른다. 루트 `tests/` 는 `ur3`·`shared`
를 대상으로 하고 `pytest` 가 추가로 필요하다.
