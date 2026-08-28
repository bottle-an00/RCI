---
title: DoIP 프로토콜 스택
group: DoIP
group_order: 4
difficulty: 심화
order: 2
---

# (2) DoIP 프로토콜 스택

## **2. DoIP 프로토콜 스택**

#### 2.1 OSI 계층 매핑

**DoIP의 계층 위치**

| OSI 계층 | 구성 요소 | 규격 |
| --- | --- | --- |
| L7 응용 | UDS 진단 서비스 | ISO 14229-1 |
| L6 표현 | (사용 안 함) | — |
| L5 세션 | **DoIP** — 연결 수립, Routing Activation, Alive Check | ISO 13400-2 |
| L4 전송 | TCP / UDP | RFC 793 / 768 |
| L3 네트워크 | IPv4 / IPv6 | RFC 791 / 8200 |
| L2 데이터링크 | Ethernet MAC, VLAN | IEEE 802.3 |
| L1 물리 | 100BASE-T1 / 1000BASE-T1 | IEEE 802.3bw / bp |

**DoIP가 걸쳐 있는 범위**

- 엄밀히는 **L5(세션) 중심**이며, 일부 L4 기능을 보조
- 표준에서는 "Transport protocol and network layer services"로 표현하지만, 실제 전송 신뢰성은 TCP가 담당
- DoIP 고유 역할은 **연결 대상 식별과 접근 인가**에 집중

**DoIP가 담당하는 3가지 기능**

| 기능 | 내용 |
| --- | --- |
| 차량 식별 | 어떤 차량인지 찾고 VIN·논리 주소 확인 |
| 접근 인가 | 진단 권한 확인 후 라우팅 경로 개방 |
| 메시지 라우팅 | 논리 주소 기반으로 대상 ECU에 UDS 메시지 전달 |

---

#### 2.2 UDS – DoIP – TCP/UDP/IP 연계

**전체 데이터 흐름**

```
  [Tester 측]                          [차량 측]

  UDS 요청 생성                         UDS 서비스 처리
   22 F1 90                                  ↑
       ↓                                     │
  DoIP 헤더 부착                        DoIP 헤더 해석
   [Header][Src][Tgt][UDS]              논리주소로 라우팅
       ↓                                     ↑
  TCP 세그먼트화                        TCP 재조립
       ↓                                     ↑
  IP 패킷화 / Ethernet 프레임  ──────→  수신 및 역캡슐화
```

**TCP와 UDP의 역할 분담**

| 구분 | UDP (포트 13400) | TCP (포트 13400) |
| --- | --- | --- |
| 사용 시점 | 연결 이전 (탐색 단계) | 연결 이후 (진단 단계) |
| 통신 방식 | 브로드캐스트 / 유니캐스트 | 유니캐스트 1:1 |
| 신뢰성 | 없음 (재전송 직접 구현) | TCP가 보장 |
| 주요 메시지 | Vehicle Identification, Vehicle Announcement, Entity Status | Routing Activation, Diagnostic Message, Alive Check |

**왜 이렇게 나누는가**

- **탐색 단계** : 상대 IP를 모르므로 브로드캐스트 필요 → TCP는 브로드캐스트 불가 → **UDP 사용**
- **진단 단계** : 대용량 데이터의 무결성·순서 보장이 필수 → **TCP 사용**
- 보안 적용 시 TCP는 **포트 3496(TLS)** 으로 대체

**TCP가 대신 처리해주는 것**

| 기능 | 효과 |
| --- | --- |
| 세그먼트 분할·재조립 | ISO-TP의 SF/FF/CF 로직 불필요 |
| 순번 및 재전송 | 패킷 손실 시 자동 복구 |
| 슬라이딩 윈도우 | 수신측 처리 능력에 맞춰 자동 조절 (STmin 불필요) |
| 혼잡 제어 | 네트워크 상황에 따른 전송률 조정 |

- 단, **UDS 메시지 경계는 TCP가 보장하지 않음**
- TCP는 바이트 스트림이므로, DoIP 헤더의 **Payload Length 필드**를 이용해 수신측이 메시지 경계를 직접 판별해야 함

---

#### 2.3 IP 계층 고려사항

**IP 주소 할당 방식**

| 방식 | 설명 | 적용 |
| --- | --- | --- |
| DHCP | 차량 또는 외부에서 주소 할당 | 일반적인 진단 환경 |
| AutoIP (Link-Local) | DHCP 실패 시 자체 주소 생성 | 169.254.x.x / IPv6 FE80:: |
| 고정 IP | 사전 정의된 주소 사용 | 생산 라인, 개발 환경 |

- 표준은 DHCP를 우선 시도하고, 실패 시 AutoIP로 폴백하도록 규정
- IPv4·IPv6 모두 지원하며, 차량 내부에서는 IPv6 Link-Local 사용 사례가 많음

**MTU와 단편화**

- 이더넷 표준 MTU : 1500 byte
- DoIP 진단 메시지는 이를 초과할 수 있음 → **TCP가 자동 세그먼트화**
- IP 계층 단편화(Fragmentation)는 성능 저하 요인이므로 회피하는 것이 원칙

---

#### 2.4 DoCAN 대비 차이점

**기능 대응 관계**

| 기능 | DoCAN (ISO 15765-2) | DoIP (ISO 13400-2) |
| --- | --- | --- |
| 대상 지정 | CAN ID (11/29 bit) | IP 주소 + 논리 주소 (16 bit) |
| 메시지 분할 | SF / FF / CF 직접 구현 | TCP 자동 처리 |
| 흐름 제어 | Flow Control (BS, STmin) | TCP 슬라이딩 윈도우 |
| 재전송 | 미지원 (상위에서 처리) | TCP 자동 |
| 연결 개념 | 없음 (연결 없이 즉시 통신) | 있음 (탐색 → 연결 → 인가) |
| 접근 제어 | 없음 | Routing Activation |
| 연결 유지 확인 | 없음 | Alive Check |

**구조적 차이의 핵심**

- **DoCAN** : 연결 개념이 없음 → CAN ID만 알면 즉시 요청 전송 가능
- **DoIP** : 연결 지향 → 상대를 찾고, 연결하고, 인가받는 절차가 선행됨

**절차 비교**

```
  [DoCAN]
   케이블 연결 → 즉시 UDS 요청 전송

  [DoIP]
   케이블 연결 → IP 확보 → 차량 탐색 → TCP 연결
              → Routing Activation → UDS 요청 전송
```

- DoIP의 절차가 복잡한 이유는 **IP 네트워크가 다수 노드가 공존하는 개방 환경**이기 때문
- 누가 접속했는지 식별하고 권한을 확인하는 단계가 필수적

**타이밍 파라미터 대응**

| 항목 | DoCAN | DoIP |
| --- | --- | --- |
| 응답 대기 | P2 / P2\* Server | P2 / P2\* Server (동일) |
| 전송 계층 타이머 | N\_As, N\_Ar, N\_Bs, N\_Cr | A\_DoIP\_Ctrl, T\_TCP\_General\_Inactivity 등 |

- **UDS 레벨의 P2 타이머는 양쪽 동일** → 진단 시나리오 설계 방식은 변하지 않음
- 전송 계층 타이머만 각 규격에 맞게 별도 정의

---

#### 2.5 차량 내 스택 구현 관점

**게이트웨이의 이중 스택 구조**

```
        [외부 진단기]
              │ Ethernet
              ▼
     ┌────────────────────┐
     │   DoIP Gateway     │
     │  ┌──────────────┐  │
     │  │ DoIP Stack   │  │  ← Ethernet 측
     │  └──────┬───────┘  │
     │         │ 논리주소 변환
     │  ┌──────▼───────┐  │
     │  │ CAN TP Stack │  │  ← CAN 측
     │  └──────────────┘  │
     └────────┬───────────┘
              │ CAN
        [하위 ECU들]
```

- 게이트웨이는 **DoIP 논리 주소 ↔ CAN 진단 ID 매핑**을 수행
- 진단기는 목적지 논리 주소만 지정하면, 대상이 이더넷 ECU인지 CAN ECU인지 의식할 필요 없음
- 이 구조 덕분에 **기존 CAN ECU를 교체하지 않고도 DoIP 도입 가능**

**AUTOSAR 스택 상의 위치**

| 계층 | 모듈 |
| --- | --- |
| 응용 | DCM (Diagnostic Communication Manager) |
| 진단 전송 | **DoIP 모듈** / CanTp |
| 소켓 | SoAd (Socket Adaptor) |
| TCP/IP | TcpIp |
| 이더넷 | EthIf → EthDrv |

- DCM은 하위 전송 방식과 무관하게 동일하게 동작
- DoIP 모듈이 SoAd를 통해 TCP/UDP 소켓과 연결됨
