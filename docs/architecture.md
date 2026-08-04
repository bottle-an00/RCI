# 시스템 아키텍처

## 전체 데이터 흐름

```
[PC 웹 진단 앱]
      │
      │ MQTT (클라우드 브로커, port 1883)
      │ req: minigit/req/urrobot
      │ resp: minigit/resp/urrobot
      ▼
[RCI — Raspberry Pi 4]
  UR3 세트: UDS 서버/진단 에이전트 역할
  RC카 세트: 투명 중계기 역할
      │
      │ TCP
      ├─────────────────────────────┐
      │ RTDE (port 30004)           │ Dashboard (port 29999)
      ▼                             ▼
[UR3 Control Box + UR3]
  RTDEReceiveInterface (상태 읽기 125Hz)
  RTDEControlInterface (모션 제어: moveJ/moveL)
  Dashboard Server     (프로그램/전원/안전 제어)
```

> RC카 세트의 RCI는 로직 없는 투명 중계기이고,
> UR3 세트의 RCI는 MQTT 수신 → UDS 해석 → RTDE/Dashboard 실행 → 응답 생성을 직접 수행하는 UDS 서버다.

---

## UR3 MQTT 토픽

| 방향 | 토픽 | 발행자 | 구독자 | QoS | Retained |
|------|------|--------|--------|-----|----------|
| 명령(요청) | `minigit/req/urrobot` | 웹앱 | RCI | 1 | N |
| 응답 | `minigit/resp/urrobot` | RCI | 웹앱 | 1 | N |
| 에러 | `minigit/error/urrobot` | RCI | 웹앱 | 1 | N |
| RCI 상태 | `minigit/status/rci-ur` | RCI | 웹앱 | 1 | Y (+LWT) |

### 페이로드 형식

**요청**
```json
{ "id": "u-0001", "raw": "22 01 01", "timeout_ms": 1000 }
```

**응답**
```json
{ "id": "u-0001", "type": "positive", "raw": "62 01 07 07" }
{ "id": "u-0001", "type": "negative", "raw": "7F 22 31", "nrc": "31" }
```

- `raw`는 UDS 페이로드를 hex 문자열(대문자, 공백 구분)로 담음
- 물리값 디코딩·NRC 이름 매핑은 웹앱 담당, RCI는 raw 바이트만 발행

---

## UR3 ↔ RCI 인터페이스 (TCP)

| 인터페이스 | 포트 | 용도 |
|-----------|------|------|
| RTDE (RTDEReceiveInterface) | 30004 | 상태 읽기 (125Hz 캐시) |
| RTDE (RTDEControlInterface) | 30004 | 모션 제어 (moveJ/moveL, async) |
| RTDE IO | 30004 | 속도 슬라이더, 그리퍼 I/O |
| Dashboard Server | 29999 | 프로그램/전원/안전 제어 |

---

## RCI 소프트웨어 구조

```
MQTT 수신 (minigit/req/urrobot)
    │
    ▼ (요청 큐: 정지/취소 클래스 최우선)
uds_server (SID 디스패치, 공통 유효성 검사)
    │
    ├── 0x10 세션 / 0x3E TesterPresent
    ├── 0x27 보안 접근
    ├── 0x22 ReadDataByIdentifier  ──▶ RTDE 캐시 / Dashboard
    ├── 0x2E WriteDataByIdentifier ──▶ RCI 설정 파일
    ├── 0x2F InputOutputControl    ──▶ Dashboard / RTDE IO
    ├── 0x31 RoutineControl        ──▶ RTDEControlInterface (moveJ/moveL)
    ├── 0x11 ECUReset
    └── 0x19/0x14 DTC 조회/소거
```

---

## UDS 서비스 주요 대응표

| SID | 서비스 | UR3 측 동작 |
|-----|--------|------------|
| 0x22 | ReadDataByIdentifier | RTDE 캐시 조회 (DID 0x01xx), Dashboard 조회 (DID 0xF1xx) |
| 0x2F | InputOutputControl | Dashboard 명령 (프로그램/전원/안전), RTDE IO (속도), 그리퍼 I/O |
| 0x31 | RoutineControl | RTDEControlInterface moveJ/moveL (비동기), 완료는 폴링 |
| 0x27 | SecurityAccess | 고정 Seed/Key (학습용) |
| 0x19/0x14 | DTC 조회/소거 | RCI 내부 DTC 저장소 |
