# miniGIT UR3 RCI 기능명세서

*Functional Specification — RCI for UR3 (MQTT ↔ UR TCP, UDS Server/Diagnostic Agent)*

- 문서번호: MINIGIT-FUNC-URRCI-001
- 버전: 0.1 (초안)
- 작성일: 2026-07-29
- 분류: 학습용 (내부)
- 상위 문서: UR3 진단 통신 사양서 (작성 예정), [UR3(로봇) 기능명세서](UR3_기능명세서.md)

> RC카 세트의 RCI는 로직 없는 투명 중계기였으나, **UR3 세트의 RCI는 UDS 서버(진단 에이전트)**로서 요청 해석, 세션/보안/제어권 상태 관리, DTC 관리, 응답 생성을 직접 수행한다. 진단 항목(SID/DID/RID/DTC/NRC) 정의는 [UR3(로봇) 기능명세서](UR3_기능명세서.md)를 따른다. CAN 관련 규칙(필러, 8B 고정, ISO-TP, CAN ID)은 적용하지 않는다. UR3 세트의 통신은 CAN이 아닌 MQTT이며, MQTT는 CAN과 달리 프레임 크기가 8바이트로 고정되지 않으므로(DoIP처럼 가변 길이 페이로드를 하나의 메시지로 전달), 다중프레임 분할/재조립 자체가 필요 없다.

---

## 1. 범위 (Scope)

RCI는 Raspberry Pi 4(RSP4)에서 동작하며, PC 웹 진단 앱과 UR3(Control Box) 사이에 위치한다.

책임:
- 웹앱의 MQTT 진단 명령(raw UDS 페이로드) 수신 → UDS 서버로서 직접 해석·처리
- UR3에 대한 데이터 취득(RTDE)과 제어(Dashboard, RTDE IO, RTDEControlInterface 모션) 실행
- 긍정/부정 응답(UDS 바이트) 생성 → MQTT 발행
- 세션(0x10/0x3E/S3), 보안(0x27), 제어권(0x2F/0x31 상호배제), DTC(0x19/0x14) 상태 관리
- 로봇 통신 감시(RTDE 두절, 안전 이벤트, 카메라 연결) 및 DTC 설정

범위 밖:
- PC 웹 진단 앱 UI (물리값 표시/디코딩은 웹앱 담당, RCI는 raw 바이트만 발행)
- RC카 진단 세트 (별개 세트)

---

## 2. 하드웨어 / 네트워크 구성

| 구성 | 부품/값 | 인터페이스 | 비고 |
|---|---|---|---|
| 메인 보드 | Raspberry Pi 4 (RSP4) 2GB | — | RC카 세트 RCI와 동일 보드급 |
| 로봇 연결 | 유선 이더넷 | TCP/IP | Control Box와 동일 서브넷 |
| 클라우드 연결 | Wi-Fi 또는 유선 | MQTT (1883) | 클라우드 브로커 outbound 접속 |
| 대상 로봇 | UR3 + Control Box(CB-Series, PolyScope 3.x) | RTDE 30004 / Dashboard 29999 | — |
| 전원 | RCI 배터리 모듈 + 18650 | — | — |

CAN 하드웨어(MCP2515/TJA1050/OBD 케이블)는 본 세트에서 사용하지 않는다.

---

## 3. 소프트웨어 아키텍처

RCI는 클라우드(웹앱)와 로봇(UR3) 사이에서 통역과 감독을 동시에 하는 프로그램 하나다.

```
   MQTT Broker (클라우드)
       │ (구독) minigit/req/urrobot     (발행) minigit/resp/urrobot, minigit/error/urrobot, minigit/status/rci-ur
       ▼
┌──────────────────────┐
│  mqtt_client          │  요청 수신 / 응답·에러·상태 발행, LWT
└──────────┬───────────┘
           ▼ (요청 큐: 기본 직렬화, 정지/취소 클래스는 최우선순위)
┌──────────────────────┐
│  uds_server           │  raw hex 파싱 → [SID] 디스패치 → 공통 유효성(길이/포맷) 검사
│  (dispatcher)         │  긍정(SID+0x40)/부정(7F) 응답 조립
└──────────┬───────────┘
           ▼
┌───────────────────────────────────────────────┐
│  서비스 핸들러                                    │
│  0x10 세션 / 0x3E TP / 0x27 보안 / 0x22 읽기      │
│  0x2E 쓰기 / 0x2F 강제구동 / 0x31 모션 / 0x11 리셋 │
│  0x19·0x14 DTC                                   │
└─────────┬─────────────────────┬────────────────┘
          ▼                     ▼
┌──────────────────────┐   ┌────────────────────────────┐
│  상태 저장소            │   │  robot_iface                │
│  세션/보안/제어권/       │   │  rtde_rx    : RTDE 30004 수신 → 최신값 캐시   │
│  robot_busy_owner/     │   │  rtde_ctrl  : RTDEControlInterface(모션)     │
│  DTC/설정(JSON 영속)    │   │  rtde_io    : speed slider, 그리퍼 I/O       │
└────────┬─────────────┘   │  dashboard  : 29999 명령/응답                │
         ▲                 │  camera_link: 카메라 연결 확인                │
         │ DTC 설정          └────────────┬───────────────┘
┌────────┴─────────┐                     │
│  dtc_monitor      │◀────────────────────┘
│  (주기 500ms 감시) │   통신 두절/안전 이벤트/과온/저전압/카메라 끊김
└──────────────────┘
```

**용어 설명**
- **디스패치(dispatch)**: 요청의 첫 바이트(SID)를 보고 알맞은 담당 핸들러에게 넘겨주는 것. 콜센터 상담원이 문의 종류를 보고 담당 부서로 연결해주는 것과 같다. `uds_server`가 이 역할을 한다.
- **캐시(cache)**: 로봇에 매번 물어보면 느리므로, RTDE로 계속 받아오는 최신 상태값을 미리 저장해뒀다가 요청이 오면 즉시 꺼내주는 것.
- **비동기(async) / 폴링(polling)**: 모션 명령을 보낸 뒤 로봇이 다 움직일 때까지 기다리지 않고 바로 다음 일을 처리하는 방식이 비동기다. 대신 "다 됐어?"를 나중에 반복해서 물어봐야 하는데, 그게 폴링이다.
- **헬스체크(health check)**: RCI가 시작될 때 이전에 하다 만 로봇 제어 스크립트가 남아있는지 미리 확인하고 정리하는 절차.

### 3.1 모듈 구성

| 모듈 | 책임 |
|---|---|
| `mqtt_client` | 브로커 연결, req 구독 / resp·error·status 발행, LWT |
| `uds_server` | raw 파싱, SID 라우팅, 길이/포맷 검사(`7F [SID] 13`), 응답 조립 |
| `session_mgr` | default/extended, S3 타임아웃(5s), TesterPresent 처리 |
| `security_mgr` | 고정 Seed/Key(`11 22 33 44`/`55 66 77 88`), 3회 실패 잠금·지연 |
| `did_read`(0x22) | DID → RTDE 캐시/Dashboard/설정 파일 매핑, 인코딩(빅엔디안) |
| `did_write`(0x2E) | 0xF1xx 설정 파일 쓰기, 보안/세션 검사 |
| `io_control`(0x2F) | DID → Dashboard/RTDE IO 실행, 제어권(returnControl) 관리, 0x0201 처리 시 `robot_busy_owner` 확인 |
| `motion_ctrl`(0x31, RID 0x03xx) | RTDEControlInterface 호출(moveJ/moveL/stopJ/stopL), 비동기 진행률 폴링, `robot_busy_owner` 관리, 목표값 범위 검증 |
| `agent_reset`(0x11) | 에이전트 소프트 리셋(세션/보안/제어권/robot_busy_owner 초기화) |
| `dtc_store`(0x19/0x14) | `{code(3B)→status(1B)}` 맵, JSON 영속 |
| `dtc_monitor` | RTDE 캐시/카메라 연결 주기 감시 → DTC 설정 |
| `robot_iface` | RTDE 수신 스레드, RTDEControlInterface 연결관리+헬스체크, RTDE IO, Dashboard TCP 클라이언트, 카메라 연결 확인 |
| `logger` | 요청/응답/에러/로봇 이벤트 로그 |

### 3.2 실행 형태

- 단일 프로세스. 스레드: MQTT 수신 / 요청 처리 워커 / RTDE 수신 / dtc_monitor / S3 타이머.
- 동시 세션 1개 가정. **요청 큐는 기본 직렬화(1건씩 처리)하되, stopRoutine(및 향후 모든 정지/취소 클래스 요청)은 큐 최우선순위로 처리**한다(대기 중인 다른 요청보다 먼저 실행). 이는 모션 실행 중 비상정지가 지연되지 않도록 하기 위함이다(§7.4, §10 A2).
- 언어/런타임: Python + `paho-mqtt` + `ur_rtde`(RTDEReceiveInterface / RTDEControlInterface / RTDEIOInterface / DashboardClient) 권장.

---

## 4. MQTT 인터페이스 (확정)

### 4.0 브로커 / 연결

| 항목 | 값 |
|---|---|
| 브로커 위치 | 클라우드(원격) 호스팅 |
| RCI 역할 | MQTT 클라이언트 (req 구독 / resp·error·status 발행) |
| 포트 | 1883 |
| 인증/TLS | 학습용, 기본 미사용 |
| 프로토콜 | MQTT 3.1.1 이상 |

### 4.1 토픽 구조

| 방향 | 토픽 | 발행자 | 구독자 | QoS | Retained |
|---|---|---|---|---|---|
| 명령(요청) | `minigit/req/urrobot` | 웹앱 | RCI | 1 | N |
| 응답 | `minigit/resp/urrobot` | RCI | 웹앱 | 1 | N |
| 에러 | `minigit/error/urrobot` | RCI | 웹앱 | 1 | N |
| RCI 상태 | `minigit/status/rci-ur` | RCI | 웹앱 | 1 | Y (+LWT) |

### 4.2 요청 페이로드

```jsonc
{ "id": "u-0001", "raw": "22 01 01", "timeout_ms": 1000 }
```

`raw`는 UDS 유효 페이로드를 가변 길이로 그대로 담는다. MQTT는 CAN처럼 프레임이 8바이트로 고정되지 않으므로, 길이가 긴 요청(예: 모션 명령 18바이트)도 필러나 다중프레임 분할 없이 한 번의 메시지로 전달한다.

### 4.3 응답 페이로드

```jsonc
{ "id": "u-0001", "type": "positive", "raw": "62 01 07 07" }
{ "id": "u-0001", "type": "negative", "raw": "7F 22 31", "nrc": "31" }
{ "id": "u-0002", "type": "negative", "raw": "7F 2F 78", "nrc": "78" }   // responsePending 중간 통지, 같은 id로 최종 응답 재발행
```

### 4.4 에러 / 상태 페이로드

```jsonc
{ "id": "u-0003", "type": "error", "reason": "robot_unreachable", "message": "로봇 무응답" }
// reason ∈ { "robot_unreachable", "dashboard_error", "internal_error" }

{ "state": "online", "robot": "connected" }   // robot ∈ { "connected", "disconnected" }
```

### 4.5 표기 및 처리 규칙

- hex 표기: 대문자, 바이트 공백 구분, `0x` 없음
- `type` 판별: raw 첫 바이트 `0x7F` → `negative`, 그 외 → `positive`
- 물리값 디코딩·NRC 이름 매핑은 웹앱 담당, RCI는 raw 바이트만 발행

---

## 5. 처리 로직 (Transaction Logic)

### 5.1 요청 처리 흐름

1. MQTT 요청 수신 → JSON 파싱(`id`, `raw`) → 요청 큐 투입(정지/취소 클래스는 최우선순위)
2. raw hex → 바이트열 파싱
3. `uds_server`가 SID 추출 → 세션/보안/robot_busy_owner 전제조건 검사 → 핸들러 실행
4. 핸들러가 `robot_iface` 호출 → 긍정/부정 응답 바이트 생성
5. `minigit/resp/urrobot` 발행 (id 에코)

### 5.2 데이터 취득 (0x22)

- RTDE 수신 스레드가 125Hz로 출력 레시피를 수신해 최신값 캐시에 저장
- 0x22 핸들러는 캐시에서 읽어 즉시 응답
- 캐시 유효 시간 초과(1s 미갱신) 또는 RTDE 미접속 → `7F 22 22` + DTC `0x900002`
- 출력 레시피: `actual_q, actual_qd, actual_current, joint_temperatures, actual_TCP_pose, robot_mode, safety_mode, safety_status_bits, runtime_state, speed_scaling, actual_robot_voltage, actual_robot_current`
- `0x010E`(로드된 프로그램명), `0xF195`(PolyScope 버전)는 Dashboard 조회값을 캐시(TTL 5s)
- `0x010F`(그리퍼 상태)는 RCI가 보관한 마지막 명령값을 그대로 반환(위치 감지 센서 없음)
- `0x0110`(카메라 상태)는 `camera_link` 모듈의 연결 확인 결과를 반환. 연결 끊김 지속 시 DTC `0xC20301` 설정

### 5.3 제어 실행 (0x2F)

- Dashboard 명령은 개행 종료 텍스트이며, 1행 텍스트 응답으로 성공/실패 판정
- Dashboard 소켓 타임아웃 5s
- **0x0201(프로그램 실행 제어)과 모션(0x31)의 상호배제**: `robot_busy_owner`가 `MOTION_ROUTINE`인 상태에서 0x0201 재생 요청 시 `7F 2F 22` 반환. 재생 허용 시 다음 순서로 처리한다.
  1. `RTDEControlInterface` 연결을 명시적으로 해제(disconnect)
  2. Dashboard `play` 실행, `robot_busy_owner`=`URP_PROGRAM`
  3. 재생 종료(0x0201 stop/일시정지 또는 프로그램 자체 종료) 감지 시 `reuploadScript()`로 `RTDEControlInterface` 재연결, `robot_busy_owner`=`NONE`
- 0x0202/0x0203/0x0204/0x0206은 기존과 동일(returnControl 정책은 UR3 기능명세서 §3.3 참조)
- 강제 구동 중 DID 집합을 유지하고, 세션 종료/S3 타임아웃/리셋 시 전체 제어권 자동 반환

### 5.4 모션 실행 (0x31, RID 0x03xx) — 신규

**startRoutine(SF=0x01)**
1. `robot_busy_owner`가 `URP_PROGRAM`이면 `7F 31 22`(프로그램 재생 중)
2. `robot_busy_owner`가 이미 `MOTION_ROUTINE`이면 `7F 31 21`(busyRepeatRequest)
3. 0x0301/0x0302/0x0305/0x0306는 확장 세션+보안 접근, 0x0303은 확장 세션만 검사(미충족 `7F 31 33`/`7F 31 7F`)
4. 목표값 범위(화이트리스트) 검증, 벗어나면 `7F 31 31`
5. 통과 시 `RTDEControlInterface.moveJ()`/`moveL()`을 `async=True`로 호출, `robot_busy_owner`=`MOTION_ROUTINE`, 런어웨이 방지 타이머 시작(§10 A2)
6. 즉시 `71 01 [RID] 00` 반환(비동기 접수)

**RID 0x0305 Wave** — 시연용 손 흔들기 동작. 파라미터는 속도(1B,%)+가속도(1B,%)+반복횟수(1B,1~10)로 다른 RID(14B)와 길이가 다르다. 한 번의 `startRoutine` 호출로 ① 고정 인사 자세(`WAVE_START_POSE_DEG`, 가정치)로 이동 → ② 손목(wrist2/wrist3, 가정치 ±45도)만 좌우로 왕복 → ③ `startRoutine` 호출 시점의 원래 관절각으로 복귀까지 전부 처리한다 — 베이스/숄더/엘보는 왕복 구간에서 고정해 충돌 범위를 최소화한다. 내부적으로 백그라운드 스레드가 `moveJ`를 동기(`async=False`) 호출로 순차 실행하며, `stopRoutine`/S3 타임아웃/런어웨이 타임아웃 시 다음 스텝을 내보내지 않고 중단한다(이 경우 원위치 복귀도 생략됨). `requestRoutineResults`는 RTDE의 `getAsyncOperationProgress()` 대신 이 스레드의 완료 여부로 진행중/완료를 판단한다.

**RID 0x0306 TableTour** — 시연용 모서리 순회+그리퍼 동작. 파라미터는 Wave와 동일한 3바이트(속도/가속도/그리퍼반복횟수 1~10). 한 번의 `startRoutine` 호출로 ① 테이블 4모서리(`TABLE_CORNER_POSES_M`, 가정치, TCP 위치/자세)를 `moveL`로 순서대로 이동 → ② 중앙(`TABLE_CENTER_POSE_M`)으로 이동 → ③ 그리퍼 개폐(`last_gripper_cmd` 토글, 실제 I/O는 그리퍼 인터페이스 미확정이라 미구현)를 지정 횟수만큼 반복 → ④ 원래 관절각으로 복귀(`moveJ`)까지 전부 처리한다. Wave와 동일하게 백그라운드 스레드+`_bg_stop_requested` 플래그로 중단을 처리하며, `requestRoutineResults`도 동일한 완료 판단 경로(`_bg_done`)를 공유한다.

**requestRoutineResults(SF=0x03)**
- `getAsyncOperationProgress()` 폴링(웹앱 권장 폴링 간격 200~500ms)
- 진행 중이면 `7F 31 78`
- 완료 시 결과 조립(성공/실패, 최종 관절각 또는 중단 지점, 실행 시간/사유코드) → `71 03 [RID] ...`, `robot_busy_owner`=`NONE`
- 런어웨이 타임아웃 초과 시 서버가 자체적으로 `stopJ()`/`stopL()` 호출 후 실패 결과로 조립

**stopRoutine(SF=0x02)** — 요청 큐 최우선순위로 처리
- 로봇 통신 두절 시 `7F 31 22`(다른 서비스와 동일)
- 통신이 살아있으면 RID와 무관하게 `stopJ()`/`stopL()` 호출, `robot_busy_owner`=`NONE`
- 실행 중인 모션이 없어도(통신이 살아있는 한) 항상 `71 02 [RID] 00` 반환(실패하지 않음)

### 5.5 responsePending(0x78) 정책

- 처리 소요 2s 초과가 예상되는 작업(전원on, 브레이크해제)은 즉시 `7F [SID] 78` 발행 후 완료 시 같은 id로 최종 응답 재발행
- 모션의 `requestRoutineResults` 폴링도 동일하게 진행 중일 때 `7F 31 78` 반환(§5.4)
- 0x78 반복 발행은 5s 간격 최대 6회(총 30s) 제한, 초과 시 error(`dashboard_error`)

### 5.6 세션 유지 (TesterPresent)

- `3E 00`은 웹앱이 주기(권장 2s 이내) 발행, RCI는 S3 타이머(5s) 리셋 후 `7E 00` 응답
- S3 타임아웃 → default 세션 복귀 + 보안/제어권/`robot_busy_owner` 초기화(단, 실행 중이던 모션은 안전을 위해 자동 stopJ/stopL 처리 후 초기화)
- 웹앱은 세션을 더 유지할 필요가 없어진 시점(사용자가 진단 화면을 벗어남, `10 01`로 기본세션 복귀를 직접 요청함 등)에 주기 발행을 멈춘다 — RCI 쪽 처리는 없으니 클라이언트(웹앱) 구현 규칙일 뿐이다

### 5.7 로봇 재접속 정책

| 상황 | 동작 |
|---|---|
| RTDE 수신 두절 | DTC 0x900002 설정, status `robot:"disconnected"` 발행, 5s 간격 재접속 시도 |
| Dashboard 소켓 끊김 | 소켓 close 완료를 확인한 뒤 재접속(최대 1회 재시도). close 완료 전 재연결을 시도하면 거부되거나 응답이 멎는 사례가 보고되어 있어, close 완료 확인을 반드시 선행한다 |
| RCI 기동 시 | `isProgramRunning()`으로 이전 세션이 남긴 제어 스크립트가 로봇에 상주 중인지 확인 → 남아있으면 `reuploadScript()`로 정리 후 재연결(좀비 스크립트 방지) |
| 재접속 성공 | status `robot:"connected"` 발행 (DTC는 유지, 소거는 0x14로만) |
| 0xF1A0(로봇 IP) 쓰기 | 즉시 기존 연결 종료 후 새 IP로 재접속 |

---

## 6. UR 인터페이스 상세 (Robot Layer)

| 항목 | 값 | 비고 |
|---|---|---|
| RTDE 읽기 | TCP 30004, `RTDEReceiveInterface` | 출력 레시피 §5.2, 125Hz |
| RTDE 모션 제어 | TCP 30004, `RTDEControlInterface` | `moveJ`/`moveL`(async=True), `stopJ`/`stopL`, `getAsyncOperationProgress()`, `getRobotStatus()`. 연결 유지 중 로봇에 제어 스크립트 상주(§5.7) |
| Dashboard | TCP 29999 | 텍스트 명령/응답, `\n` 종료 |
| RTDE IO | `speed_slider_mask`=1, `speed_slider_fraction`=0.0~1.0 | 0x2F 0x0202 |
| 그리퍼 I/O | 디지털/아날로그 출력(가안, 실제 배선 확인 필요) | 0x2F 0x0206, 위치 감지 센서 없음(확정) |
| 카메라 연결 확인 | 별도 드라이버/프로세스 연결 상태 확인(가안, RTDE/Dashboard 무관) | 0x22 0x0110 |
| 사용 Dashboard 명령 | `play`, `stop`, `pause`, `get loaded program`, `power on`, `power off`, `brake release`, `unlock protective stop`, `close safety popup`, `restart safety`, `PolyscopeVersion`, `safetymode` | — |
| 제약 | unlock protective stop은 보호정지 후 5s 경과 필요 | `7F 2F 37` |

---

## 7. 상태 전이 (State Machines)

### 7.1 세션

```
default ──10 03──▶ extended
   ▲                  │
   └── S3 타임아웃 / 10 01 / 11 01(리셋) ◀──┘
```
extended에서 S3 타임아웃(TesterPresent 부재) → default 복귀 + 보안/제어권 초기화.

### 7.2 보안

```
locked ──27 01──▶ seedIssued ──27 02(정답)──▶ unlocked
                     │  27 02(오답)×3
                     ▼
                  delayLock ──(지연 경과)──▶ locked
```
unlocked는 세션 전환/리셋/타임아웃 시 locked로 복귀.

### 7.3 제어권 (0x2F 강제 구동)

forced 상태 DID 집합 유지. returnControl(0x00)/세션종료/타임아웃/리셋 → 해당 항목 기본값 복귀.

### 7.4 robot_busy_owner (신규 — 0x0201과 0x31의 상호배제)

```
        ┌──(0x0201 play 접수)──▶ URP_PROGRAM ──(재생 종료)──┐
NONE ◀──┤                                                    ├──▶ NONE
        └──(0x31 startRoutine 접수)──▶ MOTION_ROUTINE ──(완료/stopRoutine)──┘
```

- `URP_PROGRAM` 상태에서 0x31 startRoutine 요청 → `7F 31 22`
- `MOTION_ROUTINE` 상태에서 0x0201 play 요청 → `7F 2F 22`
- `stopRoutine`은 상태와 무관하게(로봇 통신이 살아있다면) 항상 성공하며 즉시 `NONE`으로 복귀(§5.4). 로봇 통신 두절 시에는 다른 서비스와 동일하게 `7F 31 22`
- S3 타임아웃/에이전트 리셋 시 `NONE`으로 강제 초기화(모션 중이었다면 stopJ/stopL 선행)

---

## 8. 로그 (Logging)

- 요청/응답: `id`, raw, 처리 시간, 결과(type/nrc)
- 로봇 이벤트: RTDE 접속/두절, safety_mode 변화, Dashboard 명령·응답 원문, robot_busy_owner 전이
- DTC 설정/소거 이력

---

## 9. NRC 참조 (웹앱 매핑용)

| NRC | 이름 |
|---|---|
| 0x11 | serviceNotSupported |
| 0x13 | incorrectMessageLengthOrInvalidFormat |
| 0x21 | busyRepeatRequest |
| 0x22 | conditionsNotCorrect |
| 0x24 | requestSequenceError |
| 0x31 | requestOutOfRange |
| 0x33 | securityAccessDenied |
| 0x35 | invalidKey |
| 0x37 | requiredTimeDelayNotExpired |
| 0x78 | responsePending |
| 0x7F | serviceNotSupportedInActiveSession |

RCI는 0x78만 내부적으로 인식해 타이머를 연장하며, 나머지 이름 매핑은 웹앱이 수행한다.

---

## 10. 가정 및 확정 필요 항목 (Assumptions & TBD)

| # | 항목 | 상태 |
|---|---|---|
| A1 | DTC 정상복귀 시 상태 | 미결 — 이상 원인이 해소돼도 DTC 상태를 계속 "유지"할지, 자동으로 지울지 결정 필요(RC카 세트도 아직 "유지"로 잠정 운영 중, §9 참조) |
| A2 | 모션 런어웨이 방지 타임아웃 | 가정: 30~60초 — 실기 튜닝 필요(UR3 기능명세서 §7과 동일 항목) |
| A3 | 그리퍼/카메라 연결 방식 | 가안 — UR3 기능명세서 §2.1 참조, 실제 배선/드라이버 확인 필요 |

---

## 부록 A. 엔드투엔드 흐름 예시 (조인트 각도 읽기)

```
[웹앱] publish minigit/req/urrobot {"id":"u-0001","raw":"22 01 01"}
[RCI]  RTDE 캐시 actual_q 조회 → rad→0.1° 변환
       publish resp {"id":"u-0001","type":"positive","raw":"62 01 01 FC 7C ... 00 03"}
```

## 부록 B. 엔드투엔드 흐름 예시 (브레이크 해제, responsePending)

```
[웹앱] req u-0002 {"raw":"2F 02 03 03 02","timeout_ms":30000}
[RCI]  Dashboard "brake release" 송신
       publish resp {"type":"negative","raw":"7F 2F 78","nrc":"78"}   # 중간 통지
[UR3]  브레이크 해제 진행
[RCI]  publish resp {"type":"positive","raw":"6F 02 03 03 02"}        # 최종 응답
```

## 부록 C. 엔드투엔드 흐름 예시 (보호정지 발생 → 조회 → 복구)

```
[UR3]  보호정지 발생(safety_mode=3)
[RCI]  dtc_monitor: DTC 0xB10002 설정
[웹앱] req {"raw":"19 02 08"} → resp {"raw":"59 02 B1 00 02 08"}
[웹앱] (5초 후) req {"raw":"2F 02 04 03 01"} → resp {"raw":"6F 02 04 03 01"}
[웹앱] req {"raw":"14 FF FF FF"} → resp {"raw":"54"}
```

## 부록 D. 엔드투엔드 흐름 예시 (모션 실행)

```
[웹앱] req {"raw":"31 01 03 01 00 00 FC 7C 00 00 FC 7C 00 00 00 00 1E 1E"}
[RCI]  robot_busy_owner=NONE 확인 → 세션/보안 통과 → 목표값 검증 통과
       moveJ(async=True) 호출, robot_busy_owner=MOTION_ROUTINE
       publish resp {"type":"positive","raw":"71 01 03 01 00"}
[웹앱] (300ms 후) req {"raw":"31 03 03 01"} → resp {"raw":"7F 31 78"}          # 진행중
[웹앱] (반복 폴링, 완료 시) req {"raw":"31 03 03 01"}
[RCI]  getAsyncOperationProgress() 완료 확인, robot_busy_owner=NONE
       publish resp {"raw":"71 03 03 01 01 00 00 FC 7C ... 00 64"}             # 성공
```
