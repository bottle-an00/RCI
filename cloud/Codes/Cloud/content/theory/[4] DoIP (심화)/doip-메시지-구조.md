---
title: DoIP 메시지 구조
group: DoIP
group_order: 4
difficulty: 심화
order: 6
---

# (6) DoIP 메시지 구조

**6. DoIP 메시지 구조**

**6.1 Generic Header 구조**

**모든 DoIP 메시지의 공통 형식**

- DoIP의 **모든 메시지**는 예외 없이 8 byte 공통 헤더로 시작
- 헤더 뒤에 메시지 종류별 페이로드가 이어짐

```
  ┌────────┬────────┬─────────────┬──────────────────┬─────────┐
  │Protocol│ Inverse│ Payload Type│  Payload Length  │ Payload │
  │Version │ Version│             │                  │         │
  │ 1 byte │ 1 byte │   2 byte    │      4 byte      │  가변    │
  └────────┴────────┴─────────────┴──────────────────┴─────────┘
   └──────────────── Generic Header (8 byte) ───────────┘
```

**필드별 상세**

| 필드 | 크기 | 내용 |
| --- | --- | --- |
| **Protocol Version** | 1 byte | DoIP 프로토콜 버전 |
| **Inverse Protocol Version** | 1 byte | 위 값의 **비트 반전값** (1의 보수) |
| **Payload Type** | 2 byte | 메시지 종류 식별자 |
| **Payload Length** | 4 byte | 페이로드 바이트 수 (헤더 제외) |

**Protocol Version 값**

| 값 | 의미 |
| --- | --- |
| 0x01 | ISO 13400-2:2010 (초판) |
| 0x02 | ISO 13400-2:2012 |
| 0x03 | ISO 13400-2:2019 이후 |
| 0xFF | Vehicle Identification Request 전용 (버전 미확정 시) |

- **0xFF의 용도** : 진단기가 차량의 지원 버전을 아직 모를 때, 탐색 요청에 한해 사용
- 탐색 이후에는 차량이 지원하는 실제 버전으로 통신

**Inverse Protocol Version의 역할**

```
  Protocol Version         : 0x02  →  0000 0010
  Inverse Protocol Version : 0xFD  →  1111 1101
                                       (비트 반전)

  검증 : Version + Inverse = 0xFF 이어야 정상
```

- 헤더 손상 여부를 **1차로 빠르게 검증**하는 장치
- 불일치 시 즉시 Header NACK 응답 후 처리 중단
- TCP가 이미 무결성을 보장하지만, UDP 메시지와 구현 오류 대비 목적

**Payload Length 주의점**

- **헤더 8 byte는 포함하지 않음** (페이로드만의 길이)
- TCP는 바이트 스트림이므로 메시지 경계를 보장하지 않음
- → 수신측은 **헤더 8 byte를 먼저 읽고, Payload Length만큼 추가 수신**하는 방식으로 메시지를 분리

```
  수신 처리 흐름
   [1] 8 byte 읽기 → 헤더 파싱
   [2] Payload Length 확인 (예: 0x00000009)
   [3] 9 byte 추가 수신
   [4] 하나의 완결된 메시지 완성 → 처리
   [5] 다음 메시지의 헤더 8 byte 읽기로 복귀
```

---

## 6.2 Payload Type 분류

**전체 분류표**

| Payload Type | 메시지 | 방향 | 전송 |
| --- | --- | --- | --- |
| **0x0000** | Generic Header NACK | 양방향 | TCP/UDP |
| **0x0001** | Vehicle Identification Request | Tester → 차량 | UDP |
| **0x0002** | Vehicle Identification Request (EID) | Tester → 차량 | UDP |
| **0x0003** | Vehicle Identification Request (VIN) | Tester → 차량 | UDP |
| **0x0004** | Vehicle Announcement / Identification Response | 차량 → Tester | UDP |
| **0x0005** | Routing Activation Request | Tester → 차량 | TCP |
| **0x0006** | Routing Activation Response | 차량 → Tester | TCP |
| **0x0007** | Alive Check Request | 차량 → Tester | TCP |
| **0x0008** | Alive Check Response | Tester → 차량 | TCP |
| **0x4001** | Entity Status Request | Tester → 차량 | UDP |
| **0x4002** | Entity Status Response | 차량 → Tester | UDP |
| **0x4003** | Power Mode Info Request | Tester → 차량 | UDP |
| **0x4004** | Power Mode Info Response | 차량 → Tester | UDP |
| **0x8001** | Diagnostic Message | 양방향 | TCP |
| **0x8002** | Diagnostic Message Positive ACK | 차량 → Tester | TCP |
| **0x8003** | Diagnostic Message Negative ACK | 차량 → Tester | TCP |

**대역별 의미**

| 대역 | 용도 |
| --- | --- |
| 0x0000 | 오류 처리 |
| 0x0001 ~ 0x0004 | 차량 식별 / 탐색 (UDP) |
| 0x0005 ~ 0x0008 | 연결 관리 (TCP) |
| 0x4001 ~ 0x4004 | 상태 조회 (UDP) |
| 0x8001 ~ 0x8003 | **진단 메시지 (TCP)** |

- **0x8001이 실제 UDS 데이터를 담는 유일한 메시지**
- 나머지는 모두 이를 주고받기 위한 준비·관리용

---

## 6.3 주요 메시지 페이로드 구조

**Vehicle Identification Response (0x0004)** — 33 byte

| 순서 | 필드 | 크기 |
| --- | --- | --- |
| 1 | VIN | 17 byte |
| 2 | Logical Address | 2 byte |
| 3 | EID | 6 byte |
| 4 | GID | 6 byte |
| 5 | Further Action Required | 1 byte |
| 6 | VIN/GID Sync Status | 1 byte (선택) |

**Routing Activation Request (0x0005)** — 7 또는 11 byte

| 순서 | 필드 | 크기 |
| --- | --- | --- |
| 1 | Source Address | 2 byte |
| 2 | Activation Type | 1 byte |
| 3 | Reserved (ISO) | 4 byte |
| 4 | Reserved (OEM) | 4 byte (선택) |

**Routing Activation Response (0x0006)** — 9 또는 13 byte

| 순서 | 필드 | 크기 |
| --- | --- | --- |
| 1 | Logical Address of Tester | 2 byte |
| 2 | Logical Address of Entity | 2 byte |
| 3 | Response Code | 1 byte |
| 4 | Reserved (ISO) | 4 byte |
| 5 | Reserved (OEM) | 4 byte (선택) |

**Diagnostic Message (0x8001)** — 4 byte + UDS 데이터

| 순서 | 필드 | 크기 |
| --- | --- | --- |
| 1 | Source Address | 2 byte |
| 2 | Target Address | 2 byte |
| 3 | User Data (UDS) | 가변 |

**Entity Status Response (0x4002)**

| 순서 | 필드 | 크기 | 내용 |
| --- | --- | --- | --- |
| 1 | Node Type | 1 byte | 0x00: Gateway / 0x01: Node |
| 2 | Max Open Sockets | 1 byte | 최대 동시 연결 수 |
| 3 | Currently Open Sockets | 1 byte | 현재 사용 중인 연결 수 |
| 4 | Max Data Size | 4 byte | 처리 가능 최대 데이터 크기 (선택) |

- Entity Status는 **연결 실패 원인 분석에 유용** (동시 연결 수 초과 여부 확인)

---

## 6.4 메시지 구성 예시

**예시 : VIN 읽기 요청 (`22 F1 90`)**

```
  전체 바이트열
  ┌──────────────────────────┬──────────────┬───────────┐
  │      Generic Header      │  Src / Tgt   │ UDS Data  │
  │        (8 byte)          │   (4 byte)   │  (3 byte) │
  └──────────────────────────┴──────────────┴───────────┘

  02 FD 80 01 00 00 00 07 | 0E 00 0E 80 | 22 F1 90
```

**바이트별 해석**

| 바이트 | 값 | 의미 |
| --- | --- | --- |
| [0] | 0x02 | Protocol Version |
| [1] | 0xFD | Inverse Version (0x02의 반전) |
| [2:3] | 0x8001 | Payload Type — Diagnostic Message |
| [4:7] | 0x00000007 | Payload Length = 7 byte |
| [8:9] | 0x0E00 | Source Address (진단기) |
| [10:11] | 0x0E80 | Target Address (엔진 ECU) |
| [12:14] | 22 F1 90 | UDS 요청 (ReadDataByIdentifier, DID 0xF190) |

**Payload Length 계산 확인**

```
  Source Address  2 byte
  Target Address  2 byte
  UDS Data        3 byte
  ─────────────────────
  합계            7 byte  →  0x00000007  ✔
```

- 헤더 8 byte는 길이에 포함되지 않음
- 전체 전송 바이트 수 = 8 (헤더) + 7 (페이로드) = **15 byte**

---

## 6.5 Generic Header NACK (0x0000)

**목적**

- 수신한 메시지의 **헤더 자체에 문제가 있을 때** 반환하는 오류 응답
- 페이로드 내용을 해석하기 이전 단계에서 발생

**페이로드 구조** — 1 byte

| 필드 | 크기 | 내용 |
| --- | --- | --- |
| NACK Code | 1 byte | 오류 코드 |

**NACK Code 목록**

| 코드 | 의미 | 발생 원인 | 후속 조치 |
| --- | --- | --- | --- |
| **0x00** | Incorrect Pattern Format | Version + Inverse 불일치 | **연결 종료** |
| **0x01** | Unknown Payload Type | 지원하지 않는 Payload Type | 연결 유지 |
| **0x02** | Message Too Large | 수신측 버퍼 초과 | 연결 유지 |
| **0x03** | Out of Memory | 처리 자원 부족 | 연결 유지 |
| **0x04** | Invalid Payload Length | 실제 길이와 불일치 | **연결 종료** |

**연결 종료 여부 구분**

| 구분 | 코드 | 이유 |
| --- | --- | --- |
| 즉시 종료 | 0x00, 0x04 | **동기화 실패** — 스트림 경계를 신뢰할 수 없어 이후 파싱 불가 |
| 연결 유지 | 0x01, 0x02, 0x03 | 해당 메시지만 폐기하면 됨 |

**헤더 검증 순서**

```
  [1] Protocol Version + Inverse Version 확인
        불일치 → NACK 0x00 → 연결 종료
                    ↓ 정상
  [2] Payload Type 지원 여부 확인
        미지원 → NACK 0x01 → 메시지 폐기
                    ↓ 정상
  [3] Payload Length 유효성 확인
        비정상 → NACK 0x04 → 연결 종료
                    ↓ 정상
  [4] 버퍼 수용 가능 여부 확인
        초과   → NACK 0x02 / 0x03 → 메시지 폐기
                    ↓ 정상
  [5] 페이로드 처리 시작
```

**Header NACK vs UDS NRC**

| 구분 | Header NACK (0x0000) | UDS NRC (0x7F) |
| --- | --- | --- |
| 계층 | DoIP (전송) | UDS (응용) |
| 원인 | 헤더 형식 오류 | 진단 서비스 처리 실패 |
| 예시 | 버전 불일치, 길이 오류 | 조건 미충족, 권한 없음 |
| 판단 시점 | 페이로드 해석 **이전** | 서비스 실행 **중** |

- 두 오류는 **계층이 다르므로 혼동하지 말 것**
- Header NACK이 발생하면 UDS 서비스는 아예 실행되지 않음

---

## 6.6 메시지 처리 요약

**수신측 처리 흐름**

```
  TCP 스트림 수신
        ↓
  헤더 8 byte 파싱
        ↓
  헤더 검증 ──── 실패 ──→ Header NACK (0x0000)
        ↓ 통과
  Payload Length만큼 수신
        ↓
  Payload Type 분기
        ├─ 0x0005 → Routing Activation 처리
        ├─ 0x0007/8 → Alive Check 처리
        └─ 0x8001 → 진단 메시지 처리
                      ↓
                 SA 등록 여부 확인 ── 미등록 ──→ Diagnostic NACK
                      ↓ 등록됨
                 TA 유효성 확인 ──── 무효 ────→ Diagnostic NACK
                      ↓ 유효
                 Positive ACK 송신 → UDS 계층으로 전달
```

**분석 시 확인 순서 (Wireshark 등)**

| 순서 | 확인 항목 |
| --- | --- |
| 1 | Protocol Version / Inverse 일치 여부 |
| 2 | Payload Type이 기대한 값인지 |
| 3 | Payload Length와 실제 데이터 길이 일치 |
| 4 | Source / Target Address 정확성 |
| 5 | UDS 데이터 부분의 SID 및 응답 코드 |
