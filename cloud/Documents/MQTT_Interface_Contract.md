# RCI MQTT 인터페이스 계약 (v1 · 사양서 정렬)

웹 진단 앱(클라우드) ↔ 클라우드 브로커 ↔ RCI 게이트웨이 사이 메시지 규격.
**출처**: `UR3 클라우드 기능개발 요청서 §3` (SSOT = `UR3 진단 통신 사양서`). RCI 실물 도착
전에는 `Codes/board/mock_rci.py`(목 게이트웨이)가 이 계약을 이행한다.

## 역할 분담 (요청서 §1.1)

| 작업 | 담당 |
|------|------|
| UI 조작 → UDS 요청 raw 조립 (예: "관절각 읽기" → `22 01 01`) | 클라우드(웹앱) |
| MQTT 발행/구독 | 클라우드 |
| UDS 해석·세션/보안/DTC 상태관리·응답 생성 | RCI |
| **응답 raw → 물리값 디코딩, NRC → 이름 매핑** | **클라우드** |

> 게이트웨이는 raw 바이트만 주고받는다. **의미 해석(디코딩)은 웹앱의 책임.**

## 핵심 구조 차이 (사양서)

| 대상 | 전송(웹↔RCI) | UDS 서버 | 비고 |
|------|--------------|----------|------|
| RC카 | MQTT | **ECU 자체** (RCI는 CAN 중계) | RCI↔ECU = CAN |
| UR Robot | MQTT | **RCI 겸함** (RTDE/Dashboard 번역) | RCI↔UR = RTDE 30004 / Dashboard 29999 |

메시지(UDS 프레임)는 공통, 달라지는 건 전송수단·처리 주체뿐.

## 토픽 (요청서 §3.2)

`{device}` = `urrobot` | `rccar`. QoS 1.

```
minigit/req/{device}       명령   웹앱 → RCI      QoS1
minigit/resp/{device}      응답   RCI → 웹앱      QoS1
minigit/error/{device}     에러   RCI → 웹앱      QoS1
minigit/status/rci-{ur|rc} 생존   RCI            QoS1 · Retained · +LWT
```

> RC카 토픽(`.../rccar`, `minigit/status/rci-rc`)은 RC 사양서에 MQTT 계약이 없어 **UR 구조와
> 대칭으로 잠정 정의**. RC/RCI 팀과 확인 필요.

## 페이로드 (JSON, UTF-8)

### 요청 `minigit/req/{device}`
```json
{ "id": "u-0001", "raw": "22 01 01", "timeout_ms": 1000 }
```
- `id`: 요청-응답 상관용 고유 문자열(웹앱 생성, RCI 에코).
- `raw`: UDS 유효 페이로드 hex(필러 없음, 가변 길이).
- `timeout_ms`: 선택(기본 1000). 전원/모션 등 장시간 작업은 상향.

### 응답 `minigit/resp/{device}`
```json
{ "id": "u-0001", "type": "positive", "raw": "62 01 07 07" }
{ "id": "u-0001", "type": "negative", "raw": "7F 22 31", "nrc": "31" }
```
- `type`: raw 첫 바이트가 `7F` 면 `negative`, 아니면 `positive`.
- `nrc`: negative 일 때 세 번째 바이트.
- 진행중: `type=negative, nrc="78"` — 같은 `id` 로 최종 응답이 뒤이어 온다("진행중" 표시).

### 에러 `minigit/error/{device}`
```json
{ "id": "u-0003", "type": "error", "reason": "robot_unreachable", "message": "로봇 무응답" }
```
- `reason ∈ { robot_unreachable, dashboard_error, internal_error }`

### 상태 `minigit/status/rci-{ur|rc}` (retained)
```json
{ "state": "online", "robot": "connected" }
// LWT(RCI 비정상 종료): { "state": "offline" }
```

## 표기·처리 규칙 (요청서 §3.4)

- hex: **대문자, 바이트 공백 구분, `0x` 접두 없음** (예 `"62 01 07 07"`, `nrc="31"`).
- 다바이트 값은 **빅엔디안**, `int16` 음수는 **2의 보수**.
- 동시 1요청(단일 세션) 권장. **QoS1 중복 수신 대비**: 같은 `id` 재수신 시 화면에 다시 반영 금지.
- 세션 유지(`3E 00`)는 웹앱이 **2초 이내 주기로 자동 발행**(미발행 시 5초 후 default 복귀).

## UDS 서비스 (요청서 §5.1)

| SID | 서비스 | 응답 SID |
|-----|--------|----------|
| 10 세션제어 · 11 리셋 · 14 DTC소거 · 19 DTC읽기 · 22 읽기 · 27 보안 · 2E 쓰기 · 2F 강제구동 · 31 모션 · 3E 세션유지 | | +0x40 |

DID 대역: `01xx` 상태/센서(0x22) · `02xx` 강제구동(0x2F) · `F1xx` 사양(0x22/0x2E) · `03xx` 모션 RID(0x31).
