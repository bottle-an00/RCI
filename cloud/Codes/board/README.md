# RCI 엣지 게이트웨이 (board)

라즈베리파이가 맡을 MQTT ↔ RTDE/URScript 브리지. **RCI 실물 도착 전**에는
목 게이트웨이 + 로컬 브로커로 메시지 왕복을 먼저 검증한다.

메시지 규격: [`Documents/MQTT_Interface_Contract.md`](../../Documents/MQTT_Interface_Contract.md)

## 설치

```bash
pip install -r requirements.txt
```

## 한 번에 실행 (권장)

Windows 탐색기에서 **`cloud/dev.bat` 더블클릭** — 브로커 + 목 RCI + 웹이 한 창에 뜬다.
끌 때는 그 창에서 **Ctrl+C**, 창을 X 로 닫아 프로세스가 남았으면 **`cloud/stop.bat` 더블클릭**.

터미널에서 직접 부를 수도 있다(옵션은 그대로 전달된다):

```bash
cloud\dev.bat                  # 더블클릭과 동일
cloud\dev.bat -Lan -NoMock     # 핫스팟에서 실물 RCI 테스트
pwsh -File scripts/dev.ps1     # Windows (PowerShell 7+)
bash scripts/dev.sh            # Git Bash / Linux
```

웹: http://localhost:8123

> `.ps1` 은 더블클릭하면 메모장으로 열리거나 실행 정책에 막힌다. `.bat` 이
> `-ExecutionPolicy Bypass` 로 대신 호출한다. 배치 파일 두 개는 **ASCII 전용**이다 —
> cmd.exe 가 배치를 콘솔 코드페이지로 한 줄씩 읽어서, 한글 주석을 넣으면 깨진
> 바이트를 명령으로 오인해 스크립트가 통째로 망가진다. 한글 메시지는 `.ps1` 쪽에 둔다.

## 종료가 어떻게 동작하나

끄는 경로가 두 겹이다. 하나만으로는 반드시 새는 경우가 생긴다.

| 상황 | 처리 |
|---|---|
| 창에서 **Ctrl+C** | `dev.ps1` 의 `finally` 가 자식 셋을 `Stop-Process` 하고 PID 파일을 지운다 |
| 창을 **X 로 닫음** | Windows 가 `CTRL_CLOSE_EVENT` 후 곧 강제 종료해 `finally` 가 못 돈다 → **고아 발생** |
| 고아 정리 | `stop.bat` 이 세 경로(PID 파일 · 포트 소유자 · 커맨드라인)로 찾아 종료 |

`stop.bat` 이 대상을 찾는 세 경로가 각각 필요한 이유:

1. **PID 파일** (`cloud/.dev-pids`, gitignore) — `dev.ps1`/`dev.sh` 가 자식 PID 를 남긴다. 가장 정확.
2. **포트 소유자** (1883 · 8080 · 8123) — PID 파일이 없거나 낡았을 때의 폴백.
3. **커맨드라인 스캔** — `mock_rci.py` 는 **포트를 열지 않아** 2번으로 안 잡힌다.
   또 Windows venv 의 `Scripts\python.exe` 는 런처 스텁이라 실제 인터프리터를
   **자식 프로세스로 다시 띄우므로**, 부모·자식 두 개를 모두 잡아야 한다.

신원 검증은 실행파일 경로가 아니라 **커맨드라인 시그니처**(`dev_broker.py`,
`mock_rci.py`, `uvicorn main:app`)로 한다. 위의 런처 스텁 때문에 자식의 실행 경로가
`.venv` 가 아니라 베이스 파이썬으로 보고되기 때문이다. 시그니처가 안 맞는 포트
점유자는 **죽이지 않고 목록만 보여준다** — 남의 프로세스일 수 있다.

```bash
cloud\stop.bat            # 정리
cloud\stop.bat -WhatIf    # 무엇을 죽일지 보기만
cloud\stop.bat -Force     # 시그니처 불일치 점유자까지 종료 (주의)
```

`dev.bat` 은 시작 전에 세 포트를 확인해서, 이미 사용 중이면 띄우지 않고
`stop.bat` 을 먼저 돌리라고 알려준다. (그냥 띄우면 브로커만 `address in use` 로
죽고 웹은 살아서 원인 찾기가 어렵다.)

## 핫스팟(LAN)에서 실물 RCI 테스트

사내 방화벽으로 포트가 막히면 PC·라즈베리파이(RCI)를 같은 **폰 핫스팟**에 물려
사설 LAN 에서 로컬 브로커로 직접 붙인다(클라우드 브로커 불필요).

```bash
pwsh -File scripts/dev.ps1 -Lan -NoMock      # Windows
bash scripts/dev.sh --lan --no-mock          # Git Bash / Linux
```

- `-Lan` : 브로커·웹을 `0.0.0.0` 에 바인딩(다른 기기 접속 가능) + 접속용 IP 출력.
- `-NoMock` : 목 RCI 생략(실물 RCI 가 브로커에 붙음).

절차:
1. PC 와 RCI(라즈베리파이)를 같은 폰 핫스팟에 연결.
2. 위 명령 실행 → 출력된 `이 PC IP` 확인(예: `192.168.x.y`).
3. RCI 의 MQTT 브로커 주소를 `이 PC IP:1883` 으로 설정(계약: `minigit/*`).
4. 브라우저에서 `http://이 PC IP:8123` 접속(웹 WS 는 같은 호스트 `:8080` 로 자동 연결).
5. Windows 방화벽이 python 인바운드 허용을 물으면 **사설 네트워크** 허용.

## 왕복 테스트 (수동 · 터미널 3개)

개별 프로세스를 따로 확인하고 싶을 때:

```bash
# ① 로컬 브로커
python dev_broker.py

# ② 목 RCI 게이트웨이
python mock_rci.py

# ③ 웹 UI 스탠드인 — 요청 발행 후 응답 확인
python test_roundtrip.py urrobot "22 01 07"    # 로봇 모드
python test_roundtrip.py rccar "22 01 05"       # 조도
```

기대 출력(③): `← res  positive 62 01 07 07`

토픽·페이로드 규격은 [MQTT 인터페이스 계약](../../Documents/MQTT_Interface_Contract.md) 참조
(`minigit/{req|resp|error|status}/{device}`, device = `urrobot`|`rccar`).

## 전 구간 연결 테스트 (FastAPI 경유)

위 `test_roundtrip.py` 는 MQTT 에 **직접** 붙어 파이프만 본다. FastAPI 를 **경유**하는
실제 서비스 경로까지 보려면:

```bash
python ../../scripts/connection_test.py            # 목 RCI 상대
python ../../scripts/connection_test.py --stub     # 실물 RCI(UDS 미구현 스텁) 상대
python ../../scripts/connection_test.py --base-url http://192.168.x.y:8123
```

브로커 연결 · RCI 생존(retained) · 왕복 · id 상관 · 계약 표기 검증을 순서대로 찍고,
하나라도 실패하면 종료 코드 1 과 원인을 남긴다.

## 웹(FastAPI) 측 MQTT

FastAPI 프로세스도 브로커에 직접 붙는다(`Codes/Cloud/mqtt_bridge.py`). 브라우저
직결 경로(`static/js/rci-live.js`, ws:8080)와 **병존**하며, 브라우저 없이 RCI 와
왕복을 확인할 수 있다.

| 엔드포인트 | 설명 |
|---|---|
| `GET /api/health` | 브로커 연결 여부 · 구독 목록 · 마지막 RCI 상태 |
| `GET /api/status/{device}` | RCI 생존 상태(retained). 미수신이면 404 |
| `POST /api/diag/{device}/request` | `{"raw":"22 01 07","timeout_ms":1000}` → 계약 응답 그대로 |
| `GET /api/events` | 오가는 MQTT 메시지 SSE 스트림 |

```bash
curl -X POST http://localhost:8123/api/diag/urrobot/request \
     -H "Content-Type: application/json" -d '{"raw":"22 01 07"}'
# {"id":"w-0001","type":"positive","raw":"62 01 07 07"}

curl -N http://localhost:8123/api/events      # 다른 터미널에서 통신 관찰
```

응답 코드: `400` 계약 위반(raw 표기·device) · `503` 브로커 미연결 · `504` RCI 무응답.

### 브로커 접속 설정 (환경변수)

클라우드 브로커(HiveMQ/EMQX)로 이설할 때 코드 수정 없이 환경변수만 바꾼다.

| 변수 | 기본값 | 비고 |
|---|---|---|
| `RCI_BROKER_HOST` | `127.0.0.1` | |
| `RCI_BROKER_PORT` | `1883` (TLS 시 `8883`) | |
| `RCI_BROKER_USERNAME` / `RCI_BROKER_PASSWORD` | 없음 | 클라우드 브로커 인증 |
| `RCI_BROKER_TLS` | `false` | `1`/`true` 로 켜면 시스템 CA 로 서버 인증서 검증 |
| `RCI_MQTT_CLIENT_ID` | `rci-web` | 같은 id 로 둘이 붙으면 서로 끊는다 |

RCI 측(`ur3/`)도 같은 이름의 환경변수를 읽는다.

## 구성

| 파일 | 역할 | 실물 도착 후 |
|------|------|--------------|
| `dev_broker.py`     | 개발용 로컬 브로커(amqtt) | 클라우드 브로커로 대체 |
| `mock_rci.py`       | 목 RCI (계약 이행)         | 실 RCI 게이트웨이 코드로 대체 |
| `test_roundtrip.py` | 왕복 검증(웹 UI 대역)      | 실제 웹 UI 로 대체 |
