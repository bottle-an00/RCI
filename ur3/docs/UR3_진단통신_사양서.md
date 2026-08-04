# miniGIT UR3 진단 통신 사양서

*Diagnostic Communication Specification — UR3 (Based on UDS, ISO 14229 concepts over MQTT)*

- 문서번호: MINIGIT-DIAG-UR3-001
- 버전: 0.1
- 작성일: 2026-07-29
- 분류: 학습용 (내부)

### 문서 개정 이력

| 버전 | 일자 | 변경 내용 |
|---|---|---|
| 0.1 | 2026-07-29 | 최초 작성 |

---

## 1. 범위 (Scope)

본 사양서는 miniGIT 프로젝트의 UR3 로봇팔 진단 세트에서 사용하는 진단 통신 프로토콜을 정의한다. 프로토콜은 UDS(ISO 14229-1, Unified Diagnostic Services)의 서비스 구조 개념을 차용해 MQTT 기반 학습용 환경에 맞게 재구성한 것이며, ISO 14229 표준을 그대로 준수하는 것은 아니다.

정의 대상:
- 진단 서비스(SID) 및 서브펑션
- 데이터 식별자(DID) 및 데이터 인코딩
- 루틴 식별자(RID)
- 고장 코드(DTC)
- 부정 응답 코드(NRC)
- 서비스별 요청/응답 메시지 시퀀스

RC카 세트와의 구조적 차이: RC카 세트는 RC카(ECU) 자체가 진단 요청을 해석하는 UDS 서버이고 RCI는 단순 중계자다. UR3 세트는 UR3가 UDS를 전혀 이해하지 못하므로, **RCI가 UDS 서버(진단 에이전트) 역할을 겸한다.**

---

## 2. 참조 표준 (Normative References)

| 표준 | 제목 |
|---|---|
| ISO 14229-1 | Road vehicles — Unified diagnostic services (UDS) — Part 1: Application layer |

주) 본 프로젝트는 학습용이므로 위 표준의 전체 요구사항을 준수하지 않으며, 서비스 구조 및 메시지 포맷의 핵심 개념만 차용한다. RC카 세트가 참조하는 ISO 14229-3(UDS on CAN)과 ISO 15765-2(ISO-TP)는 CAN 전송계층 전용 표준이라, CAN을 사용하지 않는 본 세트(MQTT 기반)에는 해당하지 않아 제외한다.

---

## 3. 용어 및 약어 (Terms and Abbreviations)

| 약어 | 전체 명칭 | 설명 |
|---|---|---|
| UDS | Unified Diagnostic Services | 통합 진단 서비스 (ISO 14229) |
| RCI | (본 프로젝트 자체 명칭) | UR3 세트에서는 MQTT↔로봇 사이의 UDS 서버(진단 에이전트) 역할을 겸함 |
| SID | Service Identifier | 서비스 식별자 (1 byte) |
| DID | Data Identifier | 데이터 식별자 (2 bytes) |
| RID | Routine Identifier | 루틴 식별자 (2 bytes) |
| DTC | Diagnostic Trouble Code | 고장 코드 (3 bytes + 상태 1 byte) |
| NRC | Negative Response Code | 부정 응답 코드 (1 byte) |
| SF | Sub-Function | 서비스 서브펑션 (1 byte) |
| RTDE | Real-Time Data Exchange | UR 로봇의 실시간 데이터 인터페이스(TCP 30004). 읽기 전용 텔레메트리(RTDEReceiveInterface)와 모션 제어(RTDEControlInterface)로 구분 |
| Dashboard | Dashboard Server | UR 컨트롤박스의 텍스트 기반 명령 인터페이스(TCP 29999) |
| 텔레메트리 | Telemetry | 로봇이 실시간으로 보내주는 상태 데이터를 받는 것 |

---

## 4. 시스템 구성 (System Architecture)

```
[PC 웹 진단 앱] --MQTT--> [RCI = UDS 서버/진단 에이전트] --TCP(RTDE 30004/Dashboard 29999)--> [UR3 Control Box + UR3]
     Tester                요청 해석·상태 관리·응답 생성              로봇 상태 조회/구동
     └────────── MQTT 응답 ◀── UDS 응답 조립 ◀── RTDE/Dashboard 응답 ◀──────┘
```

| 구성요소 | 하드웨어 | 역할 |
|---|---|---|
| PC 웹 진단 앱 | PC | 진단 명령 UI, 결과 표시, MQTT 발행/구독 |
| RCI | Raspberry Pi (RSP4) | MQTT 수신, UDS 해석, 세션/보안/제어권/DTC 상태 관리, RTDE/Dashboard로 로봇 조회·구동, 응답 생성 |
| UR3 + Control Box | UR3 (CB-Series, PolyScope 3.x) | RTDE 텔레메트리 제공, Dashboard 명령 수행, RTDEControlInterface로 모션 실행 |

진단 페이로드는 UDS 바이트 프레임이며, PC 웹앱 ↔ RCI 구간은 MQTT, RCI ↔ UR3 구간은 TCP(RTDE/Dashboard) 위에서 전송된다.

---

## 5. 메시지 포맷 (Message Format)

### 5.1 요청 / 응답 구조

| 구분 | 포맷 | 설명 |
|---|---|---|
| 요청 | [SID] [SF/DID/파라미터...] | 서비스 요청 |
| 긍정 응답 | [SID + 0x40] [데이터...] | 정상 처리 (예: 0x22 → 0x62) |
| 부정 응답 | 7F [SID] [NRC] | 처리 실패, NRC로 사유 표시 |

### 5.2 DID / RID 대역 규칙

| 대역 | 용도 | 관련 서비스 |
|---|---|---|
| 0x01xx | 상태/센서 데이터 (읽기 전용) | 0x22 |
| 0x02xx | 액추에이터 강제 구동 | 0x2F |
| 0xF1xx | 사양/식별 정보 (읽기/쓰기) | 0x22 / 0x2E |
| 0x03xx | 모션 제어 루틴 ID | 0x31 |

### 5.3 필러 바이트 — 해당없음

UR3 세트는 CAN이 아닌 **MQTT**로 통신한다. MQTT 메시지는 CAN 프레임처럼 8바이트로 고정되지 않으며, DoIP와 마찬가지로 가변 길이 페이로드를 하나의 메시지로 전달한다. 따라서 필러 바이트, DLC 고정, ISO-TP 다중프레임 개념은 본 세트에 적용하지 않는다.

---

## 6. 진단 서비스 정의 (Diagnostic Services)

| SID | 서비스명 (UDS) | UR3 세트 동작 |
|---|---|---|
| 0x10 | DiagnosticSessionControl | RCI 내부 세션 전환 (default/extended) |
| 0x11 | ECUReset | RCI 진단 에이전트 소프트 리셋(세션/보안/제어권 초기화). 로봇 본체 재시작 아님 |
| 0x14 | ClearDiagnosticInformation | RCI DTC 저장소 소거 |
| 0x19 | ReadDTCInformation | RCI DTC 저장소 조회 |
| 0x22 | ReadDataByIdentifier | RTDE 캐시/Dashboard/설정 파일 조회 |
| 0x27 | SecurityAccess | 고정 Seed/Key 인증 (학습용, 실제 보안 기능 아님) |
| 0x2E | WriteDataByIdentifier | RCI 설정 파일(0xF1xx) 쓰기 |
| 0x2F | InputOutputControlByIdentifier | Dashboard/RTDE IO로 로봇 강제 구동 |
| 0x31 | RoutineControl | 모션 실행(RID 0x03xx) |
| 0x3E | TesterPresent | S3 타이머(5s) 리셋 |

### 6.1 DiagnosticSessionControl (0x10)

| SF | 세션 | 설명 |
|---|---|---|
| 0x01 | defaultSession | 기본 세션 |
| 0x03 | extendedDiagnosticSession | 확장 진단 세션 (쓰기/강제구동/모션) |

```
요청 : 10 03
응답 : 50 03 00 32 01 F4      # P2=50ms, P2*=5000ms
```

### 6.2 TesterPresent (0x3E)

확장 세션 유지를 위해 웹앱이 주기적으로(권장 2초 이내) 전송한다.

```
요청 : 3E 00
응답 : 7E 00
```

### 6.3 SecurityAccess (0x27)

```
요청 : 27 01                  # Seed 요청
응답 : 67 01 11 22 33 44      # Seed = 0x11223344 (고정값)
요청 : 27 02 55 66 77 88      # Key = 0x55667788 (고정값)
응답 : 67 02                  # 인증 성공
```

**보안 경고**: Seed/Key가 고정값이므로 재전송 공격을 막는 실제 보안 기능이 아니며, 세션/보안 절차의 흐름을 학습하기 위한 교육용 장치다.

### 6.4 ReadDataByIdentifier (0x22) — 상태/센서 데이터

| DID | 항목 | 길이 | 타입 | 인코딩 |
|---|---|---|---|---|
| 0x0101 | 조인트 각도(6축) | 12B | 6×int16 | 0.1도 단위 |
| 0x0102 | 조인트 속도(6축) | 12B | 6×int16 | 0.1도/초 단위 |
| 0x0103 | 조인트 온도(6축) | 12B | 6×int16 | 0.1도(섭씨) 단위 |
| 0x0104 | 조인트 전류(6축) | 12B | 6×int16 | mA 단위 |
| 0x0105 | TCP 위치(x,y,z) | 6B | 3×int16 | 0.1mm 단위 |
| 0x0106 | TCP 자세(rx,ry,rz) | 6B | 3×int16 | 0.001rad 단위 |
| 0x0107 | 로봇 모드 | 1B | int8 | 값 자체가 의미 (하단 표) |
| 0x0108 | 안전 모드 | 1B | uint8 | 값 자체가 의미 (하단 표) |
| 0x0109 | 프로그램 실행 상태 | 1B | uint8 | 값 자체가 의미 (하단 표) |
| 0x010A | 로봇 전압 | 2B | uint16 | mV 단위 |
| 0x010B | 로봇 전류 | 2B | uint16 | mA 단위 |
| 0x010C | 속도 스케일링 | 2B | uint16 | 0.1% 단위 |
| 0x010D | 안전 상태 비트 | 2B | uint16 bitfield | 가안, 실기 확인 필요 |
| 0x010E | 로드된 프로그램명 | 가변 | ASCII | 문자열 그대로 |
| 0x010F | 그리퍼 상태 | 1B | uint8 | 0~100(%), 위치 감지 센서 없음(마지막 명령값 echo) |
| 0x0110 | 카메라 상태 | 1B | uint8 | 0=연결안됨, 1=연결됨 |

**로봇 모드(0x0107)**: -1 NO_CONTROLLER, 0 DISCONNECTED, 1 CONFIRM_SAFETY, 2 BOOTING, 3 POWER_OFF, 4 POWER_ON, 5 IDLE, 6 BACKDRIVE, 7 RUNNING, 8 UPDATING_FIRMWARE

**안전 모드(0x0108)**: 1 NORMAL, 2 REDUCED, 3 PROTECTIVE_STOP, 4 RECOVERY, 5 SAFEGUARD_STOP, 6 SYSTEM_EMERGENCY_STOP, 7 ROBOT_EMERGENCY_STOP, 8 VIOLATION, 9 FAULT

**프로그램 실행 상태(0x0109)**: 0 STOPPING, 1 STOPPED, 2 PLAYING, 3 PAUSING, 4 PAUSED, 5 RESUMING

```
요청 : 22 01 07              # 로봇 모드 읽기
응답 : 62 01 07 07            # RUNNING

요청 : 22 01 0F              # 그리퍼 상태 읽기
응답 : 62 01 0F 32            # 50%
```

### 6.5 ReadDataByIdentifier (0x22) — 사양/식별 정보

| DID | 항목 | 길이 | 타입 | 인코딩 |
|---|---|---|---|---|
| 0xF199 | SW 업데이트 날짜 | 3B | BCD | YYMMDD |
| 0xF195 | SW 버전(PolyScope) | 가변 | ASCII | 예 "3.15.8" |
| 0xF18C | 시리얼 번호 | 가변 | ASCII | 가안, 실기 확인 필요 |
| 0xF1A0 | 로봇 IP 주소 | 4B | uint8×4 | IPv4 옥텟 |

```
요청 : 22 F1 99
응답 : 62 F1 99 26 07 27     # 2026-07-27
```

### 6.6 WriteDataByIdentifier (0x2E)

보안 접근(0x27) 완료 후 확장 세션에서만 허용. 대상은 0xF199, 0xF18C, 0xF1A0(쓰기 가능). 0xF195는 쓰기 불가(`7F 2E 31`).

```
요청 : 2E F1 A0 C0 A8 01 66     # 로봇 IP 변경
응답 : 6E F1 A0
```

`0xF1A0`을 쓰면 실제 UR3 컨트롤박스의 네트워크 설정이 바뀌는 것이 아니라, RCI가 접속할 대상 IP가 변경되며 즉시 재접속을 시도한다.

### 6.7 InputOutputControlByIdentifier (0x2F) — 강제 구동

IOControlParameter: 0x00=제어권 반환(returnControlToECU), 0x03=단기 강제 조정(shortTermAdjustment)

| DID | 항목 | 제어 데이터 | 전제조건 |
|---|---|---|---|
| 0x0201 | 프로그램 실행 제어 | 1B: 0=정지/1=재생/2=일시정지 | 확장 세션 |
| 0x0202 | 속도 슬라이더 | 1B: 0~100(%) | 확장 세션 |
| 0x0203 | 전원/브레이크 | 1B: 0=전원끄기/1=전원켜기/2=브레이크해제 | 보안 접근 완료 |
| 0x0204 | 안전 복구 | 1B: 1=보호정지해제/2=팝업닫기/3=안전재시작 | 보안 접근 완료 |
| 0x0206 | 그리퍼 제어 | 1B: 0~100(%) | 확장 세션 |

```
요청 : 2F 02 01 03 01      # 프로그램 재생
응답 : 6F 02 01 03 01

요청 : 2F 02 06 03 32      # 그리퍼 50% 닫기
응답 : 6F 02 06 03 32
```

### 6.8 RoutineControl (0x31)

| SF | 동작 | 설명 |
|---|---|---|
| 0x01 | startRoutine | 루틴 시작 |
| 0x02 | stopRoutine | 루틴 정지 (RID 무관 항상 성공) |
| 0x03 | requestRoutineResults | 결과 요청 |

| RID | 루틴명 | 파라미터 | 필요 권한 |
|---|---|---|---|
| 0x0301 | MoveJoint | 6축 목표각(12B,0.1도)+속도(1B,%)+가속도(1B,%) | 확장 세션 + 보안 접근 완료 |
| 0x0302 | MoveLinear | TCP 위치(6B,0.1mm)+TCP 자세(6B,0.001rad)+속도(1B,%)+가속도(1B,%) | 확장 세션 + 보안 접근 완료 |
| 0x0303 | MoveToWaypoint | 웨이포인트 인덱스(1B) | 확장 세션 |
| 0x0304 | 이미지 캡처 | — | 가안, 추후 논의 |

```
요청 : 31 01 03 01 00 00 FC 7C 00 00 FC 7C 00 00 00 00 1E 1E   # MoveJoint 시작
응답 : 71 01 03 01 00                                           # 즉시 접수

요청 : 31 03 03 01           응답 : 7F 31 78                    # 진행중
요청 : 31 03 03 01           응답 : 71 03 03 01 01 ... 00 64    # 완료(실행시간 10.0초)

요청 : 31 02 03 01           응답 : 71 02 03 01 00              # 언제든 중단, 항상 성공
```

### 6.9 ReadDTCInformation (0x19) / ClearDiagnosticInformation (0x14)

| DTC | 의미 | 발생 조건 |
|---|---|---|
| 0x900002 | 로봇 통신 두절 | RTDE 수신 두절 또는 Dashboard TCP 재접속 실패 |
| 0xB10001 | 비상정지(E-Stop) | 안전 모드 = 6 또는 7 |
| 0xB10002 | 보호정지 | 안전 모드 = 3 |
| 0xB10003 | 세이프가드 정지 | 안전 모드 = 5 |
| 0xB10004 | 안전 위반/폴트 | 안전 모드 = 8 또는 9 |
| 0xC20101 | 조인트 과온 | 조인트 온도 1축 이상 50.0℃ 초과 |
| 0xC20201 | 로봇 저전압 | 로봇 전압 44.0V 미만 |
| 0xC20301 | 카메라 연결 끊김 | 카메라 상태(0x0110) 확인 실패 |

```
요청 : 19 02 08              # confirmed DTC 조회
응답 : 59 02 B1 00 02 08 C2 01 01 08

요청 : 14 FF FF FF           # 전체 소거
응답 : 54
```

---

## 7. 부정 응답 코드 (Negative Response Code)

```
부정 응답 포맷: 7F [SID] [NRC]
```

### 7.1 공통 NRC

| NRC | 이름 | 의미 |
|---|---|---|
| 0x10 | generalReject | 일반 거부 |
| 0x11 | serviceNotSupported | 미지원 서비스 |
| 0x12 | subFunctionNotSupported | 미지원 서브펑션 |
| 0x13 | incorrectMessageLengthOrInvalidFormat | 길이/포맷 오류 |
| 0x14 | responseTooLong | 응답 길이 초과 |
| 0x21 | busyRepeatRequest | 처리 중, 재요청 요망 |
| 0x22 | conditionsNotCorrect | 조건 불충족 |
| 0x24 | requestSequenceError | 요청 순서 오류 |
| 0x31 | requestOutOfRange | 요청 범위 밖 |
| 0x33 | securityAccessDenied | 보안 접근 거부 |
| 0x35 | invalidKey | 잘못된 키 |
| 0x36 | exceededNumberOfAttempts | Key 시도 횟수 초과 |
| 0x37 | requiredTimeDelayNotExpired | 지연시간 미경과 |
| 0x78 | requestCorrectlyReceived-ResponsePending | 정상 수신, 응답 지연 |
| 0x7E | subFunctionNotSupportedInActiveSession | 현재 세션에서 미지원 서브펑션 |
| 0x7F | serviceNotSupportedInActiveSession | 현재 세션에서 미지원 서비스 |

### 7.2 상태/조건 관련 NRC

| NRC | 이름 | 의미 |
|---|---|---|
| 0x92 | voltageTooHigh | 전압 과다 |
| 0x93 | voltageTooLow | 전압 부족 |

---

## 8. NRC 적용 예시 (Use Cases)

| 상황 | 응답 | NRC |
|---|---|---|
| 보안 미완료 상태에서 전원 제어 | 7F 2F 33 | securityAccessDenied |
| 존재하지 않는 DID 읽기 | 7F 22 31 | requestOutOfRange |
| 로봇 통신 두절 중 읽기 | 7F 22 22 | conditionsNotCorrect |
| 보호정지 후 5초 미경과 해제 시도 | 7F 2F 37 | requiredTimeDelayNotExpired |
| 브레이크 해제 등 장시간 처리 | 7F 2F 78 → 최종 응답 | responsePending |
| 프로그램 재생 중 모션 시도 | 7F 31 22 | conditionsNotCorrect |
| 이미 실행 중인 모션에 재시작 시도 | 7F 31 21 | busyRepeatRequest |
| 자유 모션(0x0301/0x0302)에서 보안 미완료 | 7F 31 33 | securityAccessDenied |
| 그리퍼 범위 밖(101 이상) | 7F 2F 31 | requestOutOfRange |

---

## 9. 전체 진단 시나리오 예시 (End-to-End Sequence)

확장 세션 진입 → 보안 접근 → 모션 실행 → 결과 조회의 전형적 흐름.

```
웹앱                                  RCI
  |-- 10 03 -------------------------->|   확장 세션 진입
  |<------------------------- 50 03 ...|
  |-- 27 01 -------------------------->|   Seed 요청
  |<--------------- 67 01 11 22 33 44 -|
  |-- 27 02 55 66 77 88 -------------->|   Key 전송
  |<------------------------- 67 02 ---|   인증 성공
  |-- 31 01 03 01 ... ----------------->|   MoveJoint 시작
  |<------------------- 71 01 03 01 00-|   비동기 접수
  |-- 31 03 03 01 --------------------->|   진행 확인
  |<--------------------- 7F 31 78 ----|   진행중
  |-- 31 03 03 01 (반복) --------------->|
  |<---------- 71 03 03 01 01 ... ------|   완료
  |-- 3E 00 (주기적) ------------------>|   세션 유지
  |<------------------------- 7E 00 ---|
```

---

## 10. 기능 명세 반영 예정 (Planned for Functional Spec)

| 항목 | 반영 예정 내용 | 관련 트리거 |
|---|---|---|
| 이미지 캡처 결과 표시 | 촬영 완료 여부와 참조값을 웹 UI에 표시하는 방식(실제 이미지 전달 채널 미정) | 0x31 RID 0x0304 |

주) 상세 논의는 UR3 클라우드 기능개발 요청서 §8/§9 참조.
