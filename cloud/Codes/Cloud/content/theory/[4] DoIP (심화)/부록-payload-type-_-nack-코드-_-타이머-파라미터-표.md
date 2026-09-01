---
title: [부록] Payload Type _ NACK 코드 _ 타이머 파라미터 표
group: DoIP
group_order: 4
difficulty: 심화
order: 10
---

# (10) [부록] Payload Type / NACK 코드 / 타이머 파라미터 표

**10. [부록] 참조 표**

**10.1 Payload Type 전체**

| Type | 메시지 | 전송 | 방향 |
| --- | --- | --- | --- |
| 0x0000 | Generic Header NACK | TCP/UDP | 양방향 |
| 0x0001 | Vehicle Identification Request | UDP | T → V |
| 0x0002 | Vehicle Identification Request (EID) | UDP | T → V |
| 0x0003 | Vehicle Identification Request (VIN) | UDP | T → V |
| 0x0004 | Vehicle Announcement / Ident. Response | UDP | V → T |
| 0x0005 | Routing Activation Request | TCP | T → V |
| 0x0006 | Routing Activation Response | TCP | V → T |
| 0x0007 | Alive Check Request | TCP | V → T |
| 0x0008 | Alive Check Response | TCP | T → V |
| 0x4001 | DoIP Entity Status Request | UDP | T → V |
| 0x4002 | DoIP Entity Status Response | UDP | V → T |
| 0x4003 | Diagnostic Power Mode Request | UDP | T → V |
| 0x4004 | Diagnostic Power Mode Response | UDP | V → T |
| 0x8001 | Diagnostic Message | TCP | 양방향 |
| 0x8002 | Diagnostic Message Positive ACK | TCP | V → T |
| 0x8003 | Diagnostic Message Negative ACK | TCP | V → T |

※ T = Tester, V = Vehicle

---

## 10.2 Generic Header NACK Code

| 코드 | 의미 | 연결 처리 |
| --- | --- | --- |
| 0x00 | Incorrect Pattern Format | 종료 |
| 0x01 | Unknown Payload Type | 유지 |
| 0x02 | Message Too Large | 유지 |
| 0x03 | Out of Memory | 유지 |
| 0x04 | Invalid Payload Length | 종료 |

---

## 10.3 Routing Activation Response Code

| 코드 | 의미 |
| --- | --- |
| 0x00 | Unknown Source Address |
| 0x01 | 동시 연결 수 초과 |
| 0x02 | SA가 다른 소켓에 등록됨 |
| 0x03 | SA가 이미 등록되어 사용 중 |
| 0x04 | 인증 미완료 |
| 0x05 | 확인(Confirmation) 거부 |
| 0x06 | 지원하지 않는 Activation Type |
| 0x07 | 암호화된 연결 필요 (TLS) |
| **0x10** | **활성화 성공** |
| 0x11 | 성공, 추가 확인 필요 |

---

## 10.4 Diagnostic Message NACK Code

| 코드 | 의미 |
| --- | --- |
| 0x02 | Invalid Source Address |
| 0x03 | Unknown Target Address |
| 0x04 | Diagnostic Message Too Large |
| 0x05 | Out of Memory |
| 0x06 | Target Unreachable |
| 0x07 | Unknown Network |
| 0x08 | Transport Protocol Error |

---

## 10.5 타이머 파라미터

| 타이머 | 대략 값 | 용도 |
| --- | --- | --- |
| A\_DoIP\_Ctrl | 2 s | 제어 메시지 응답 대기 |
| A\_DoIP\_Announce\_Wait | 0~500 ms | Announcement 초기 랜덤 지연 |
| A\_DoIP\_Announce\_Interval | 500 ms | Announcement 반복 간격 |
| A\_DoIP\_Announce\_Num | 3 회 | Announcement 반복 횟수 |
| A\_DoIP\_Diagnostic\_Message | 2 s | 진단 메시지 ACK 대기 |
| T\_TCP\_General\_Inactivity | 5 s | 무통신 시 연결 해제 |
| T\_TCP\_Initial\_Inactivity | 2 s | Routing Activation 대기 |
| T\_TCP\_Alive\_Check | 500 ms | Alive Check 응답 대기 |
| P2 Server (UDS) | 50 ms | ECU 응답 시간 |
| P2\* Server (UDS) | 5000 ms | NRC 0x78 이후 연장 시간 |

※ 값은 표준 권장치이며 제조사 규격에 따라 조정됨

---

## 10.6 논리 주소 범위

| 범위 | 용도 |
| --- | --- |
| 0x0000 | 예약 |
| 0x0001 ~ 0x0DFF | 제조사 정의 |
| 0x0E00 ~ 0x0FFF | 외부 진단기(Tester) |
| 0x1000 ~ 0x7FFF | 제조사 정의 (ECU) |
| 0x8000 ~ 0xCFFF | 예약 |
| 0xE000 ~ 0xE3FF | 기능 주소 그룹 |
| 0xE400 ~ 0xEFFF | 제조사 정의 기능 주소 |
| 0xF000 ~ 0xFFFF | 예약 |

---

## 10.7 포트 및 주소 요약

| 항목 | 값 |
| --- | --- |
| UDP 탐색 포트 | 13400 |
| TCP 진단 포트 | 13400 |
| TCP 진단 포트 (TLS) | 3496 |
| AutoIP 범위 (IPv4) | 169.254.0.0/16 |
| IPv6 Link-Local | FE80::/10 |

---

## 10.8 OBD-II 커넥터 핀 (DoIP 관련)

| 핀 | 신호 |
| --- | --- |
| 1 | Activation Line |
| 3 | Ethernet RX+ |
| 8 | Ethernet TX+ |
| 11 | Ethernet RX− |
| 12 | Ethernet TX− |
| 6 / 14 | CAN High / Low (기존 유지) |
| 4 / 5 | Ground |
| 16 | Battery + |

---

## 10.9 용어 정리

| 용어 | 설명 |
| --- | --- |
| DoIP | Diagnostics over Internet Protocol |
| DoCAN | Diagnostic communication over CAN (ISO 15765) |
| Entity | 차량 측 DoIP 처리 노드 |
| Edge Node | 차량 외부와의 접점 노드 |
| Logical Address | 진단 대상 식별용 2 byte 주소 |
| VIN | Vehicle Identification Number (17 byte) |
| EID | Entity ID (통상 MAC 주소, 6 byte) |
| GID | Group ID (6 byte) |
| Routing Activation | 진단 경로 개방 인가 절차 |
| Alive Check | TCP 연결 생존 확인 절차 |
| Activation Line | 이더넷 진단 활성화 신호선 (핀 1) |

---

## 10.10 CAN 진단 vs DoIP 요약 비교

| 항목 | DoCAN | DoIP |
| --- | --- | --- |
| 전송 규격 | ISO 15765-2 | ISO 13400-2 |
| 물리 계층 | CAN (ISO 11898) | Ethernet (IEEE 802.3) |
| 속도 | 500 Kbps | 100 Mbps ~ 1 Gbps |
| 대상 지정 | CAN ID | IP + 논리 주소 |
| 분할·재조립 | ISO-TP 직접 구현 | TCP 자동 |
| 흐름 제어 | FC (BS, STmin) | TCP 윈도우 |
| 연결 개념 | 없음 | 있음 (탐색→연결→인가) |
| 접근 제어 | 없음 | Routing Activation |
| 원격 진단 | 불가 | 가능 |
| 응용 계층 | **UDS (ISO 14229) — 동일** | **UDS (ISO 14229) — 동일** |
