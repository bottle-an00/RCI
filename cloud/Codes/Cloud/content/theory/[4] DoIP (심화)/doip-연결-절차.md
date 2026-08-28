---
title: DoIP 연결 절차
group: DoIP
group_order: 4
difficulty: 심화
order: 5
---

# (5) DoIP 연결 절차

## **5. DoIP 연결 절차**

---

> ### ⚠ 본 장은 DoIP 학습의 핵심입니다
>
> - **CAN 진단과 DoIP의 가장 큰 차이가 바로 이 "연결 절차"** 입니다.
> - CAN은 케이블만 연결하면 즉시 UDS 요청을 보낼 수 있지만, DoIP는 **차량을 찾고 → 연결하고 → 인가를 받는** 3단계를 반드시 거쳐야 합니다.
> - 실무에서 발생하는 DoIP 통신 문제의 대부분은 진단 서비스가 아니라 **이 연결 절차 단계에서 발생**합니다.
> - 이후 6장(메시지 구조), 7장(진단 메시지 전송)의 내용도 본 장의 절차를 전제로 하므로, **반드시 흐름을 숙지하고 넘어가시기 바랍니다.**

---

#### 5.1 전체 절차 개요

**연결 6단계**

```
  [1] 물리 연결 및 IP 확보
       케이블 연결 → Activation Line → Link Up → IP 할당
                        ↓
  [2] 차량 탐색 (UDP 13400)
       Vehicle Identification Request  →  Response
       또는 차량이 먼저 Vehicle Announcement 송신
                        ↓
  [3] TCP 연결 수립 (TCP 13400)
       3-way handshake → Socket Initialized 상태
                        ↓
  [4] Routing Activation
       진단 경로 개방 요청 → 승인 → Registered 상태
                        ↓
  [5] 진단 메시지 교환
       UDS 요청 / 응답 반복
                        ↓
  [6] 연결 유지 및 종료
       Alive Check → TCP 종료
```

**단계별 사용 프로토콜**

| 단계 | 프로토콜 | 포트 | 통신 방식 |
| --- | --- | --- | --- |
| 차량 탐색 | UDP | 13400 | 브로드캐스트 |
| 차량 알림 | UDP | 13400 | 브로드캐스트 |
| TCP 연결 | TCP | 13400 (TLS: 3496) | 유니캐스트 |
| Routing Activation | TCP | 13400 | 유니캐스트 |
| 진단 메시지 | TCP | 13400 | 유니캐스트 |

**상태 전이**

```
   [Disconnected]
        │ TCP 연결
        ▼
   [Socket Initialized]     ← 연결은 되었으나 진단 불가
        │ Routing Activation 승인
        ▼
   [Registered / Activated] ← 진단 메시지 교환 가능
        │ 타임아웃 / 종료
        ▼
   [Disconnected]
```

- **핵심** : TCP 연결만으로는 진단할 수 없음. Routing Activation이 반드시 필요

---

#### 5.2 Vehicle Discovery (차량 탐색)

**목적**

- 진단기가 **차량의 IP 주소와 논리 주소를 알아내는 단계**
- 아직 상대 IP를 모르므로 **UDP 브로드캐스트** 사용

**동작 방식**

```
  [진단기]                              [차량 DoIP Entity]

  Vehicle Identification Request
  UDP 브로드캐스트 (255.255.255.255:13400)
        ──────────────────────────────→

                                        수신 및 응답 준비
        ←──────────────────────────────
  Vehicle Identification Response
  (VIN, 논리주소, EID, GID, 추가정보)
```

**3가지 요청 방식**

| 요청 종류 | Payload Type | 용도 |
| --- | --- | --- |
| **Vehicle Identification Request** | 0x0001 | 모든 차량에게 응답 요청 |
| **VIR with EID** | 0x0002 | 특정 EID(MAC) 차량만 응답 |
| **VIR with VIN** | 0x0003 | 특정 VIN 차량만 응답 |

- **0x0001** : 일반 정비 환경. 연결된 차량이 1대이므로 전체 요청으로 충분
- **0x0002 / 0x0003** : 생산 라인처럼 **여러 차량이 같은 네트워크에 있을 때** 대상 선별에 사용

**Vehicle Identification Response 응답 내용**

| 필드 | 크기 | 내용 |
| --- | --- | --- |
| VIN | 17 byte | 차대번호 |
| Logical Address | 2 byte | 해당 Entity의 논리 주소 |
| EID | 6 byte | Entity ID (보통 MAC 주소) |
| GID | 6 byte | Group ID |
| Further Action Required | 1 byte | 추가 조치 필요 여부 |
| VIN/GID Sync Status | 1 byte | VIN·GID 동기화 상태 (선택) |

**Further Action Required 필드**

| 값 | 의미 |
| --- | --- |
| 0x00 | 추가 조치 불필요 → 바로 연결 진행 가능 |
| 0x10 | 중앙 보안 인증 필요 → 별도 인증 절차 요구 |

**주의 사항**

- UDP는 **재전송을 보장하지 않음** → 진단기가 직접 재시도 로직 구현 필요
- 표준은 일정 간격으로 요청을 반복 송신하도록 권장
- 여러 Entity가 각각 응답할 수 있으므로, **GID로 같은 차량 소속 여부 판별**

---

#### 5.3 Vehicle Announcement (차량 알림)

**목적**

- 차량이 **스스로 자신의 존재를 알리는** 메시지
- 진단기의 요청 없이 차량이 먼저 송신 (Push 방식)

**발생 시점**

- 차량이 IP 주소를 획득한 직후
- 즉, Activation Line 인가 → Link Up → IP 할당 완료 시점

**동작 방식**

```
  [차량]                                [진단기]

  IP 주소 획득 완료
        │
  Vehicle Announcement (UDP 브로드캐스트)
        ──────────────────────────────→   수신 → 차량 정보 확보
        ──────────────────────────────→   (동일 메시지 반복 송신)
        ──────────────────────────────→
```

**반복 송신 규칙**

| 항목 | 내용 |
| --- | --- |
| 송신 횟수 | 3회 (표준 권장) |
| 송신 간격 | 500 ms 간격 |
| 초기 지연 | 0 ~ 500 ms 랜덤 |

- **UDP 패킷 손실에 대비**한 3회 반복
- **랜덤 초기 지연**은 여러 차량이 동시에 브로드캐스트하여 충돌하는 것을 방지

**Discovery와 Announcement 비교**

| 구분 | Vehicle Discovery | Vehicle Announcement |
| --- | --- | --- |
| 개시 주체 | 진단기 (Pull) | 차량 (Push) |
| Payload Type | 0x0001~0x0003 (요청) / 0x0004 (응답) | **0x0004** (동일 포맷) |
| 발생 시점 | 진단기가 필요할 때 | 차량 IP 획득 직후 |
| 활용 | 이미 연결된 차량 재탐색 | 신규 연결 즉시 인지 |

- **두 메시지의 응답 포맷은 0x0004로 동일**
- 실무에서는 Announcement를 수신하면 Discovery를 생략하고 바로 TCP 연결로 진행

---

#### 5.4 TCP 연결 수립

**절차**

```
  [진단기]                              [차량]

   SYN            ──────────────────→
                  ←──────────────────    SYN + ACK
   ACK            ──────────────────→

   → TCP 연결 완료 : Socket Initialized 상태
```

- 표준 TCP 3-way handshake 그대로 사용
- 목적지 : 탐색 단계에서 확보한 차량 IP + 포트 13400
- 보안 적용 시 포트 3496으로 TLS 핸드셰이크 추가 수행

**Socket Initialized 상태의 제약**

| 가능 | 불가능 |
| --- | --- |
| Routing Activation 요청 | **진단 메시지 송신** |
| Alive Check 응답 | 논리 주소 기반 라우팅 |

- 이 상태에서 진단 메시지를 보내면 **NACK 응답 후 연결 해제**
- 반드시 다음 단계(Routing Activation)를 거쳐야 함

**초기 Inactivity 타이머**

- TCP 연결 후 일정 시간 내 Routing Activation이 없으면 연결 자동 해제
- 무단 연결 점유를 방지하기 위한 장치

---

#### 5.5 Routing Activation

**목적**

- 진단기가 **진단 경로를 열어달라고 요청**하고, 차량이 이를 승인하는 절차
- DoIP에만 존재하는 개념 (CAN 진단에는 대응 절차 없음)

**왜 필요한가**

| 이유 | 설명 |
| --- | --- |
| 접근 통제 | 누가 접속했는지 식별하고 권한 확인 |
| 주소 등록 | 진단기의 Source Address를 차량에 등록 |
| 자원 관리 | 동시 연결 수 제한 및 배타적 작업 보호 |
| 목적 구분 | 일반 진단인지 특수 작업인지 구분 |

**메시지 교환**

```
  [진단기]                              [차량]

  Routing Activation Request (0x0005)
  - Source Address : 0x0E00
  - Activation Type : 0x00
        ──────────────────────────────→
                                        권한 확인
                                        SA 등록
        ←──────────────────────────────
  Routing Activation Response (0x0006)
  - Response Code : 0x10 (성공)
```

**Request 주요 필드**

| 필드 | 크기 | 내용 |
| --- | --- | --- |
| Source Address | 2 byte | 진단기 논리 주소 |
| Activation Type | 1 byte | 활성화 유형 |
| Reserved (ISO) | 4 byte | 0x00000000 고정 |
| Reserved (OEM) | 4 byte | 제조사 정의 (선택) |

**Activation Type**

| 값 | 유형 | 용도 |
| --- | --- | --- |
| 0x00 | Default | 일반 진단 |
| 0x01 | WWH-OBD | 법규 대응 배출가스 진단 |
| 0xE0 | Central Security | 중앙 보안 인증 경로 |

**Response Code (주요)**

| 값 | 의미 | 조치 |
| --- | --- | --- |
| **0x10** | **활성화 성공** | 진단 메시지 교환 시작 |
| 0x00 | 알 수 없는 Source Address | SA 값 확인 |
| 0x01 | 동시 연결 수 초과 | 기존 연결 해제 후 재시도 |
| 0x02 | SA가 다른 소켓에 이미 등록됨 | 중복 연결 확인 |
| 0x03 | SA가 이미 등록되어 사용 중 | 기존 세션 정리 |
| 0x04 | 인증 필요 (미완료) | 보안 인증 수행 |
| 0x05 | 확인(Confirmation) 거부 | 사용자 승인 필요 |
| 0x06 | 지원하지 않는 Activation Type | Type 값 변경 |
| 0x11 | 활성화 성공, 추가 확인 필요 | 후속 절차 진행 |

- **0x10 수신 = 진단 준비 완료**
- 실패 시 연결은 유지되지만 진단 메시지는 여전히 차단됨

---

#### 5.6 Alive Check (연결 생존 확인)

**목적**

- 차량이 **진단기가 아직 살아있는지 확인**하는 절차
- 비정상 종료된 연결을 정리하여 자원을 회수

**필요한 이유**

- 케이블이 갑자기 빠지거나 진단기가 강제 종료되면 TCP FIN이 오지 않음
- 차량 입장에서는 연결이 살아있는 것으로 오인 → 소켓 자원 점유 지속
- 다른 진단기의 접속을 막게 되므로 명시적 확인이 필요

**메시지 교환**

```
  [차량]                                [진단기]

  Alive Check Request (0x0007)
        ──────────────────────────────→
                                        즉시 응답
        ←──────────────────────────────
  Alive Check Response (0x0008)
  - Source Address 포함
```

**동작 규칙**

| 항목 | 내용 |
| --- | --- |
| 개시 주체 | 주로 **차량(Entity)** 측 |
| 발생 시점 | 일정 시간 무통신 시 / 신규 연결 요청으로 자원 부족 시 |
| 응답 제한 시간 | 약 500 ms (A\_DoIP\_Ctrl) |
| 무응답 시 | 해당 TCP 연결 강제 해제 |

- 진단기는 Alive Check Request 수신 시 **즉시 응답해야 함**
- 응답 지연은 진단 세션 강제 종료로 이어짐

**TesterPresent와의 차이**

| 구분 | Alive Check (DoIP) | TesterPresent 0x3E (UDS) |
| --- | --- | --- |
| 계층 | DoIP (전송) | UDS (응용) |
| 유지 대상 | **TCP 연결** | **ECU 진단 세션** |
| 개시 주체 | 차량 | 진단기 |

- 두 가지는 **역할이 다르므로 병행 사용**
- Alive Check만으로는 ECU 세션이 Default로 복귀하는 것을 막을 수 없음

---

#### 5.7 연결 종료

**정상 종료**

- 진단기가 TCP FIN 송신 → 정상 4-way handshake
- 차량은 해당 소켓의 SA 등록 해제 및 자원 회수

**비정상 종료 및 처리**

| 상황 | 차량 측 처리 |
| --- | --- |
| 무통신 타임아웃 | Inactivity 타이머 만료 → 연결 해제 |
| Alive Check 무응답 | 강제 해제 |
| 물리 링크 다운 | 즉시 해제 |
| Activation Line 차단 | PHY 비활성화 → 전체 연결 종료 |

**주요 타이머**

| 타이머 | 대략 값 | 용도 |
| --- | --- | --- |
| A\_DoIP\_Ctrl | 2 s | 제어 메시지 응답 대기 |
| A\_DoIP\_Announce\_Wait | 0~500 ms | Announcement 초기 랜덤 지연 |
| A\_DoIP\_Announce\_Interval | 500 ms | Announcement 반복 간격 |
| T\_TCP\_General\_Inactivity | 5 s | 무통신 시 연결 해제 |
| T\_TCP\_Initial\_Inactivity | 2 s | Routing Activation 대기 |
| T\_TCP\_Alive\_Check | 500 ms | Alive Check 응답 대기 |

- 값은 표준 권장치이며, **제조사 규격에 따라 조정될 수 있음**

---

#### 5.8 전체 시퀀스 정리

```
 [진단기]                                        [차량]

  Activation Line 인가 ──────────────────────→  PHY 활성화
                       ←────────────────────  Link Up
  DHCP / AutoIP        ←───────────────────→  IP 주소 확보

  (UDP)                ←────────────────────  Vehicle Announcement ×3
  Vehicle Ident. Req   ──────────────────────→
                       ←────────────────────  Vehicle Ident. Response

  (TCP) SYN            ──────────────────────→
                       ←────────────────────  SYN+ACK
        ACK            ──────────────────────→   [Socket Initialized]

  Routing Activation Req ────────────────────→
                       ←────────────────────  Response 0x10  [Registered]

  Diagnostic Message   ──────────────────────→
                       ←────────────────────  Diagnostic ACK
                       ←────────────────────  UDS Response
       ⋮ (반복) ⋮
                       ←────────────────────  Alive Check Request
  Alive Check Response ──────────────────────→

  TCP FIN              ──────────────────────→   [연결 종료]
```
