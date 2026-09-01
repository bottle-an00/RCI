---
title: 데이터 보호(Data Protection) 및 Fault Confinement 상세
group: CAN 통신
group_order: 1
difficulty: 심화
order: 7
---

# (7) 데이터 보호(Data Protection) 및 Fault Confinement 상세

**7. 데이터 보호(Data Protection) 및 Fault Confinement 상세**

**7.1 데이터 보호의 3단계**

1. **Bit Error 예방: 물리적 수단 (5장 참고 - 꼬임선, 종단저항 등)**
2. **남은 Bit Error 처리: 프로토콜 내 논리적 수단 (에러 검출/신호화/재전송)**
3. **Fault Confinement: Tx/Rx 에러 카운터를 이용한 결함 노드 격리**

## **7.2 에러 검출 메커니즘 (5가지)**

| **메커니즘** | **설명** |
| --- | --- |
| **Bit Monitoring** | **송신자가 보낸 값과 버스에서 읽은 값 비교 (중재/ACK 구간은 예외)** |
| **Acknowledgement Check** | **ACK 비트 슬롯에서 dominant 값을 기대** |
| **Stuff Check** | **5개 동일 비트 이후 반전 비트가 있어야 함** |
| **CRC Check** | **수신 CRC와 송신 CRC 값 비교** |
| **Form Check** | **특정 필드(예: EOF 등)는 모두 recessive(1)이어야 함** |

## **7.3 에러 신호화(Error Signaling)**

- **에러 검출 시 Error Frame(6bit Error Flag + 8bit Error Delimiter)을 전송하여 해당 프레임을 무효화**
- **Error Flag는 6개의 dominant 비트로, 스터핑 규칙 등 프로토콜 규칙을 고의로 위반하여 모든 노드가 프레임 무효를 인지하게 함**
- **CRC 에러의 경우 Error Flag 대신 Negative Acknowledgement로 시작됨**

## **7.4 Fault Confinement (결함 격리)**

**각 노드는 TEC(Transmission Error Counter)와 REC(Receive Error Counter) 두 개의 8bit 레지스터를 관리한다.**

| **이벤트** | **TEC** | **REC** |
| --- | --- | --- |
| **Error Flag 전송(송신자)** | **+8** | **-** |
| **Error Flag 전송(수신자)** | **-** | **+1 (또는 primary 에러 시 +8)** |
| **성공적 송신** | **-1** | **-** |
| **성공적 수신** | **-** | **-1** |

**노드 상태 전이**

**Error Active (TEC≤127, REC≤127)**  
**↓ REC>127 또는 TEC>127 ↑ REC<128 & TEC<128**  
**Error Passive (Error Flag는 항상 recessive 6bit)**  
**↓ TEC>255**  
**Bus Off (버스 접근 완전 차단, Software-Reset 및 128×11 recessive bit 필요)**

- **Error Active: 정상 노드. Error Flag는 6개의 dominant bit**
- **Error Passive: Error Flag가 6개의 recessive bit로 전송됨(다른 노드에 영향 최소화). 또한 SOF 전송 권한이 Intermission 직후가 아니라 8bit 지연(Suspend Transmission)된 후에만 허용됨**
- **Bus Off: 버스 접근 권한 완전 상실. 소프트웨어 리셋 및 128×11 recessive bit 관측 후 Error Active로 복귀 가능**
