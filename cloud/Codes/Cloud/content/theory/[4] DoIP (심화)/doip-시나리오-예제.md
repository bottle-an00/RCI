---
title: DoIP 시나리오 예제
group: DoIP
group_order: 4
difficulty: 심화
order: 9
---

# (9) DoIP 시나리오 예제

**9. DoIP 시나리오 예제**

**9.1 시나리오 1 : 기본 진단 세션 (VIN 읽기)**

**목표**

- 진단기 연결부터 VIN 읽기까지의 최소 흐름 확인
- 지금까지 배운 절차가 실제로 어떻게 이어지는지 확인

**전제 조건**

| 항목 | 값 |
| --- | --- |
| 진단기 IP | 192.168.0.10 |
| 차량 게이트웨이 IP | 192.168.0.20 |
| 진단기 논리 주소 | 0x0E00 |
| 대상 ECU 논리 주소 | 0x0E80 |

**전체 흐름**

```
 [진단기]                                      [차량]

 ① Activation Line 인가  ──────────────────→  PHY 활성화
                         ←──────────────────  Link Up
 ② DHCP 요청             ←─────────────────→  IP 확보 (192.168.0.20)

 ③ (UDP)                 ←──────────────────  Vehicle Announcement ×3
                                               VIN / 0x0E00 / EID / GID

 ④ (TCP) SYN             ──────────────────→
                         ←──────────────────  SYN+ACK
     ACK                 ──────────────────→   [Socket Initialized]

 ⑤ Routing Activation Req ─────────────────→
    SA=0x0E00, Type=0x00
                         ←──────────────────  Response 0x10 (성공)
                                               [Registered]

 ⑥ Diagnostic Message    ──────────────────→
    0E00 → 0E80 : 22 F1 90
                         ←──────────────────  Diagnostic ACK (0x8002)
                         ←──────────────────  Diagnostic Message
                                               0E80 → 0E00 : 62 F1 90 [VIN]

 ⑦ TCP FIN               ──────────────────→   [연결 종료]
```

**⑥ 단계의 실제 바이트열**

**요청**

```
  02 FD 80 01 00 00 00 07 | 0E 00 0E 80 | 22 F1 90
```

| 구간 | 값 | 의미 |
| --- | --- | --- |
| Header | 02 FD 80 01 00000007 | Diagnostic Message, 페이로드 7 byte |
| SA / TA | 0E00 / 0E80 | 진단기 → 엔진 ECU |
| UDS | 22 F1 90 | ReadDataByIdentifier, DID 0xF190 |

**ACK 응답**

```
  02 FD 80 02 00 00 00 05 | 0E 80 0E 00 | 00
```

| 구간 | 값 | 의미 |
| --- | --- | --- |
| Header | 02 FD 80 02 00000005 | Positive ACK |
| SA / TA | 0E80 / 0E00 | **주소가 뒤바뀜** |
| ACK Code | 00 | 정상 수신 |

**UDS 응답**

```
  02 FD 80 01 00 00 00 18 | 0E 80 0E 00 | 62 F1 90 [VIN 17 byte]
```

| 항목 | 계산 |
| --- | --- |
| Payload Length | 2(SA) + 2(TA) + 3(SID+DID) + 17(VIN) = **24 = 0x18** |

**핵심 확인 포인트**

- ACK(0x8002)와 UDS 응답(0x8001)이 **각각 별도 메시지**로 도착
- 응답에서 SA/TA가 요청과 반대로 뒤바뀜
- Payload Length에 헤더 8 byte는 포함되지 않음

---

## 9.2 시나리오 2 : ECU 리프로그래밍

**목표**

- DoIP의 실질적 도입 목적인 플래싱 전체 흐름 확인

**단계별 흐름**

```
 [사전 준비]
  ① 차량 탐색 → TCP 연결 → Routing Activation
  ② 차량 상태 확인 (시동, 배터리, 주차 상태)

 [세션 및 인증]
  ③ 10 03        Extended Session 진입
  ④ 85 02        DTC 기록 중지
  ⑤ 28 03 03     통신 제어 (비진단 메시지 중지)
  ⑥ 10 02        Programming Session 진입
  ⑦ 27 01 / 27 02  SecurityAccess 인증

 [데이터 전송]
  ⑧ 34           RequestDownload
                 → maxNumberOfBlockLength 수신
  ⑨ 36 (반복)     TransferData — 블록 단위
  ⑩ 37           RequestTransferExit

 [검증 및 마무리]
  ⑪ 31 01 FF 01  RoutineControl (CheckMemory / CRC)
  ⑫ 11 01        ECUReset
  ⑬ 10 03 → 85 01 / 28 00  DTC·통신 복구
  ⑭ 10 01        Default Session 복귀
```

**⑧ RequestDownload 응답 비교**

| 환경 | maxNumberOfBlockLength | 10 MB 기준 TransferData 횟수 |
| --- | --- | --- |
| CAN | 약 4 KB | 약 2,500 회 |
| DoIP | 약 64 KB 이상 | 약 160 회 |

- 반복 횟수 감소가 **시간 단축의 직접적 원인**
- 블록당 오버헤드(요청·ACK·응답)가 곱해지므로 효과가 큼

**⑨ TransferData 구간의 DoIP 동작**

```
  [진단기]                          [차량]

  36 01 [블록 데이터]  ─────────→
                       ←─────────  Diagnostic ACK
                       ←─────────  76 01 (Positive Response)
  36 02 [블록 데이터]  ─────────→
                       ←─────────  Diagnostic ACK
                       ←─────────  7F 36 78 (ResponsePending)
                                     ↑ 플래시 쓰기 중
                       ←─────────  76 02 (완료)
```

- 플래시 쓰기 중 **NRC 0x78이 다수 발생** → P2\* 타이머로 대기
- 이 구간에서 **Alive Check Request가 오면 즉시 응답**해야 연결 유지

**주의 사항**

| 항목 | 내용 |
| --- | --- |
| TesterPresent | 플래싱 중에도 주기 송신 (S3 타이머 방지) |
| Alive Check | 대기 중에도 응답 필수 |
| 전원 관리 | 전송은 빨라졌으나 플래시 쓰기 중 단전은 여전히 치명적 |
| 병목 인식 | 네트워크가 아닌 **ECU 쓰기 속도**가 상한 |

---

## 9.3 시나리오 3 : 다중 ECU 순차 진단

**목표**

- 하나의 연결로 여러 ECU를 진단하는 DoIP의 장점 확인

**흐름**

```
  Routing Activation 완료 (SA = 0x0E00)
            │
            ├─→ TA = 0x0E10 (ADAS)      : 19 02 09  → DTC 수신
            ├─→ TA = 0x0E11 (인포테인먼트) : 19 02 09  → DTC 수신
            ├─→ TA = 0x0E80 (엔진, CAN)   : 19 02 09  → DTC 수신
            └─→ TA = 0x0E81 (브레이크, CAN): 19 02 09  → DTC 수신
```

**핵심 포인트**

- **TCP 연결과 Routing Activation은 1회만** 수행
- 이후 Target Address만 변경하며 순차 진단
- 대상이 이더넷 ECU인지 CAN ECU인지 **진단기는 구분할 필요 없음**

**CAN ECU 대상 시 유의점**

| 항목 | 내용 |
| --- | --- |
| 속도 | 게이트웨이 하위 CAN 구간은 여전히 느림 |
| 응답 지연 | ISO-TP 처리로 인해 이더넷 ECU보다 느린 응답 |
| NACK 0x06/0x08 | CAN 구간 문제 시 발생 |

**기능 주소 활용 (전체 ECU 세션 전환)**

```
  TA = 0xE400 (기능 주소 그룹)
       10 03  ─────────→  게이트웨이가 그룹 내 전 ECU에 복제 전송
                      ←─  0x0E10 : 50 03
                      ←─  0x0E11 : 50 03
                      ←─  0x0E80 : 50 03
```

- 여러 ECU가 **각각 응답**하므로 SA로 구분하여 수집
- 주로 `0x3E`, `0x10`, `0x11` 브로드캐스트에 사용

---

## 9.4 Wireshark 로그 분석

**캡처 준비**

| 항목 | 설정 |
| --- | --- |
| 인터페이스 | 진단기가 연결된 이더넷 포트 |
| 필터 (전체) | `udp.port==13400 || tcp.port==13400` |
| 필터 (진단만) | `doip` |
| TLS 구간 | 포트 3496 — 복호화 불가 (키 없이는 내용 확인 불가) |

**정상 흐름 캡처 예시**

| No. | Protocol | Info |
| --- | --- | --- |
| 1 | DHCP | Discover / Offer / Request / ACK |
| 2 | DoIP (UDP) | Vehicle Announcement |
| 3 | TCP | SYN → SYN,ACK → ACK |
| 4 | DoIP | Routing Activation Request |
| 5 | DoIP | Routing Activation Response (0x10) |
| 6 | DoIP | Diagnostic Message (22 F1 90) |
| 7 | DoIP | Diagnostic ACK |
| 8 | DoIP | Diagnostic Message (62 F1 90 ...) |

**확인 순서**

```
  [1] Protocol Version / Inverse 일치 여부
  [2] Payload Type이 기대값인지
  [3] Payload Length와 실제 데이터 길이 일치
  [4] SA / TA 값 정확성
  [5] UDS SID 및 응답 코드
```

**이상 패턴과 해석**

| 캡처 상 관찰 | 해석 |
| --- | --- |
| UDP 요청만 있고 응답 없음 | Activation Line 미인가 / 방화벽 차단 |
| TCP SYN 반복, SYN,ACK 없음 | 포트 미개방 / 동시 연결 초과 |
| Routing Act. Response 0x00 | SA 값 불일치 |
| Diagnostic NACK 0x03 | Target Address 오류 |
| ACK만 있고 UDS 응답 없음 | ECU 처리 지연 또는 정지 |
| 0x7F ... 78 반복 | 정상 (ResponsePending) |
| TCP RST 발생 | Inactivity 만료 / Alive Check 실패 |

**CANoe 등 도구 활용**

| 기능 | 용도 |
| --- | --- |
| DoIP 채널 설정 | 진단기 IP·논리 주소 구성 |
| ODX/CDD 로딩 | UDS 서비스 심볼릭 표시 |
| Trace 창 | DoIP·UDS 계층 동시 관찰 |
| 시뮬레이션 | 차량 없이 DoIP Entity 모사 |

---

## 9.5 시나리오별 체크리스트

| 단계 | 확인 항목 |
| --- | --- |
| 물리 | 케이블, 미디어 컨버터, Activation Line |
| IP | DHCP 응답 또는 AutoIP 주소 확인, ping 성공 |
| 탐색 | UDP 13400 브로드캐스트 도달, 방화벽 해제 |
| 연결 | TCP 13400 연결, 동시 연결 수 여유 |
| 인가 | SA 값, Activation Type, Response 0x10 |
| 진단 | Target Address 정확성, ACK 수신 |
| 유지 | Alive Check 즉시 응답, TesterPresent 주기 송신 |
