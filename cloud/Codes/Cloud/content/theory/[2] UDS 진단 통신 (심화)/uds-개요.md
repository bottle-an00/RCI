---
title: UDS 개요
group: UDS 진단 통신
group_order: 2
difficulty: 심화
order: 1
---

# (1) UDS 개요

## **1. 진단 통신 개요**

### **1.1 UDS****정의 및 등장 배경**

UDS 정의

- Unified Diagnostic Services의 약자
- 차량 ECU와 진단기(Tester) 간의 진단 통신을 위한 응용 계층 프로토콜
- OSI 7계층 중 응용 계층(Layer 7)에 해당
- 데이터 링크 독립적 설계로 CAN, CAN FD, Ethernet(DoIP), LIN, FlexRay 등 다양한 물리 계층 위에서 동작

등장 배경

- 차량 전자화 심화로 ECU 수 증가 → 표준화된 진단 프로토콜 필요성 대두
- 기존 KWP2000(ISO 14230)의 한계: K-Line 단일 와이어 기반의 저속 통신(최대 10.4 Kbps), 제조사별로 변형된 형태로 사용되어 호환성 부족
- 통합된 진단 표준 요구 → 2006년 ISO 14229 제정
- 현재 차량 진단의 사실상 글로벌 표준으로 자리잡음

UDS의 핵심 가치

- 표준화: 제조사 간 호환성 확보
- 확장성: 새로운 서비스/기능 추가 용이
- 보안성: SecurityAccess를 통한 권한 관리
- 독립성: 물리 계층과 무관하게 동일한 서비스 사용 가능

### **1.2 KWP2000****과의 차이 및 발전 과정**

진단 프로토콜 발전 흐름

|  |  |  |  |  |
| --- | --- | --- | --- | --- |
| **시대** | **프로토콜** | **표준** | **물리 계층** | **특징** |
| 1990년대 | KWP2000 | ISO 14230 | K-Line | 단일 와이어, 저속 |
| 2000년대 | UDS | ISO 14229 | 주로 CAN | 고속, 표준화 강화 |
| 2010년대 | UDS on CAN FD | ISO 14229-3 | CAN FD | 페이로드 확장 (8→64바이트) |
| 2020년대 | UDS on DoIP | ISO 14229-5 + ISO 13400 | Ethernet | 대용량/고속 진단, OTA |

KWP2000과 UDS의 주요 차이

|  |  |  |
| --- | --- | --- |
| **항목** | **KWP2000** | **UDS** |
| 표준 | ISO 14230 | ISO 14229 |
| 물리 계층 | K-Line 중심 | CAN, Ethernet 등 다양 |
| 전송 속도 | 1.2 ~ 10.4 Kbps | 1 Mbps ~ 1 Gbps |
| 서비스 SID | 유사 (0x10, 0x14 등 일부 동일) | 확장 및 정교화 |
| 보안 메커니즘 | 단순 Seed & Key | Security Level 개념 도입, 더 정교 |
| 세션 관리 | 단순 | Default/Programming/Extended 세분화 |

UDS가 KWP2000을 계승한 점

- 기본 메시지 구조 (Request/Response, Positive/Negative)
- Seed & Key 보안 인증 개념
- 일부 SID는 동일하게 유지 (0x10, 0x14, 0x27 등)

UDS에서 새롭게 강화된 점

- 세션 관리 체계화 (Default, Programming, Extended Session)
- DTC 관리 서비스 정교화 (0x19 ReadDTCInformation의 Sub-function 다양화)
- 데이터 식별자(DID)와 루틴 식별자(RID) 표준 정의
- 리프로그래밍 프로세스 표준화 (0x34, 0x36, 0x37)

### **1.3****표준화 (ISO 14229 시리즈)**

ISO 14229는 여러 파트로 구성된 시리즈 표준이다. 각 파트는 UDS의 서로 다른 측면을 규정한다.

|  |  |  |
| --- | --- | --- |
| **표준** | **명칭** | **내용** |
| ISO 14229-1 | 일반 사양(AppLayer) | UDS의 핵심 표준, 26개 표준 서비스 SID/Sub-function/NRC/데이터 포맷 정의 |
| ISO 14229-2 | 세션 계층 | 클라이언트-서버 메시지 교환 규칙, 타이밍 파라미터(P2, P2\*, S3 등) 명세 |
| ISO 14229-3 | UDS on CAN | CAN 기반 UDS 구현, ISO 15765-2(CAN TP) 활용 규칙 |
| ISO 14229-4 | UDS on FR (FlexRay) | FlexRay 기반 UDS 구현, 적용 사례 제한적 |
| ISO 14229-5 | UDS on IP (DoIP) | Ethernet/IP 기반 UDS 구현, ISO 13400과 함께 사용 |
| ISO 14229-6 | UDS on K-Line | K-Line 기반, 레거시 시스템 호환용 |
| ISO 14229-7 | UDS on LIN | LIN 기반, 저속 편의장치 ECU 진단 |

관련 표준과의 관계

    [CAN 환경]

    ISO 14229 (UDS - 응용 계층)

            ↓

    ISO 15765 (CAN TP - 전송 계층)

            ↓

   ISO 11898 (CAN - 물리/데이터링크)

   [Ethernet 환경]

   ISO 14229 (UDS - 응용 계층)

           ↓

   ISO 13400 (DoIP - 전송 계층)

           ↓

   TCP/IP + IEEE 802.3 (Ethernet)

### **1.4 UDS****의 적용 범위**

진단기(Tester)와 ECU 간 통신

- 정비소 진단 (DTC 읽기, 센서값 확인)
- 생산 라인 검사 (전수 검사, ECU 식별 정보 쓰기)
- 개발/검증 단계 (ECU 동작 확인)

ECU 리프로그래밍 (Flash Programming)

- ECU 펌웨어 업데이트
- 캘리브레이션 데이터 변경
- 차종별 설정 변경

차량 보안 관련 동작

- 도난 방지 시스템 (Immobilizer) 등록/변경
- 키 매칭 (Key Learning)
- ECU 교체 시 인증

OBD-II 진단 (제한적)

- UDS는 제조사 진단에 주로 사용
- OBD-II는 배기가스 관련 표준 진단 (SAE J1979)
- 최근 OBDonUDS (SAE J1979-2)로 통합 추세

원격 진단 및 OTA

- DoIP 기반 원격 진단
- 클라우드 연동 차량 진단 서비스
- OTA(Over-The-Air) 업데이트

UDS가 적용되지 않는 영역

- ECU 간 일반 제어 신호 통신 (CAN 메시지 송수신)
- 카메라/센서의 실시간 데이터 스트리밍
- 차량 내부 V2X 통신

## **2. UDS****통신 모델**

### **2.1 Client-Server****구조**

기본 개념

- UDS는 1:1 또는 1:N의 Client-Server 모델로 동작
- Client = 진단기(Tester), 진단 요청을 보내는 주체
- Server = ECU, 진단 요청을 처리하고 응답하는 주체
- 모든 통신은 Client의 Request에서 시작

특징

- 비대칭 통신: ECU는 진단기에게 먼저 요청을 보내지 않음
- ECU는 수동적 응답자: Request가 와야만 동작
- 예외: 0x78 Response Pending은 ECU가 자발적으로 보내는 임시 응답

흐름 예시

[일반 통신]

진단기(Client) ──Request──→  ECU(Server)

진단기(Client) ←──Response── ECU(Server)

 

[ECU 처리 시간이 긴 경우]

진단기(Client) ──Request──→ ECU(Server)

진단기(Client) ←─0x78 Pending─ ECU(Server)  (처리 중)

진단기(Client) ←──Response── ECU(Server)    (완료)

### **2.2 Request/Response****메커니즘**

Request 메시지 구조

[SID][Sub-function][Parameter 1][Parameter 2]...

- SID (Service Identifier): 1바이트, 어떤 서비스를 요청하는지 식별
- Sub-function: 1바이트, 서비스의 세부 동작 지정 (서비스에 따라 없을 수도 있음)
- Parameter: 가변 길이, 서비스별 추가 데이터

Response 메시지 구조 (Positive)

[SID + 0x40][Sub-function][Response Data]...

- 응답 SID = 요청 SID + 0x40 (예: 0x10 → 0x50, 0x22 → 0x62)
- Sub-function echo: 요청한 Sub-function을 그대로 반환 (확인용)
- Response Data: 실제 응답 데이터

Response 메시지 구조 (Negative)

[0x7F][요청 SID][NRC]

- 0x7F: Negative Response를 나타내는 고정값
- 요청 SID: 어떤 서비스에 대한 거부인지 식별
- NRC (Negative Response Code): 거부 사유 (1바이트)

메시지 예시

|  |  |
| --- | --- |
| **상황** | **메시지** |
| Extended Session 요청 | 진단기 → ECU: 10 03 |
| 정상 응답 | ECU → 진단기: 50 03 00 32 01 F4 |
| 조건 불만족 거부 | ECU → 진단기: 7F 10 22 |

### **2.3 Positive Response vs Negative Response**

Positive Response (성공)

- 요청이 정상적으로 처리되었음을 의미
- 응답 SID = 요청 SID + 0x40
- 서비스에 따라 응답 데이터 포함 (예: 0x22 응답은 실제 데이터 포함)

Negative Response (거부)

- 요청 처리 실패 또는 거부됨을 의미
- 항상 0x7F로 시작
- 형식: 0x7F + 요청 SID + NRC
- NRC 값으로 거부 사유를 정확하게 알 수 있음

주요 SID와 Response 매핑

|  |  |  |
| --- | --- | --- |
| **요청 SID** | **Positive Response SID** | **서비스** |
| 0x10 | 0x50 | DiagnosticSessionControl |
| 0x11 | 0x51 | ECUReset |
| 0x14 | 0x54 | ClearDiagnosticInformation |
| 0x19 | 0x59 | ReadDTCInformation |
| 0x22 | 0x62 | ReadDataByIdentifier |
| 0x27 | 0x67 | SecurityAccess |
| 0x28 | 0x68 | CommunicationControl |
| 0x2E | 0x6E | WriteDataByIdentifier |
| 0x2F | 0x6F | InputOutputControlByIdentifier |
| 0x31 | 0x71 | RoutineControl |
| 0x34 | 0x74 | RequestDownload |
| 0x36 | 0x76 | TransferData |
| 0x37 | 0x77 | RequestTransferExit |
| 0x3E | 0x7E | TesterPresent |

NRC 종류

- 0x10: generalReject (일반적 거부)
- 0x11: serviceNotSupported (서비스 미지원)
- 0x22: conditionsNotCorrect (조건 불만족)
- 0x31: requestOutOfRange (요청 범위 초과)
- 0x33: securityAccessDenied (보안 접근 거부)
- 0x78: requestCorrectlyReceivedResponsePending (응답 보류)

### **2.4 Suppress Positive Response****기능**

개념

- 일부 서비스의 Sub-function에서 Positive Response 전송을 억제하는 기능
- Sub-function의 최상위 비트(bit 7)를 1로 설정하면 활성화
- Negative Response는 영향 없음 (오류 시에는 항상 응답)

목적

- 버스 트래픽 감소
- 주기적으로 동일한 요청을 보낼 때 응답 부담 감소
- 가장 흔한 사용 예: TesterPresent (0x3E)

동작 방식

|  |  |  |
| --- | --- | --- |
| **Sub-function****값** | **Suppress Bit** | **동작** |
| 0x00 | 0 (비활성) | TesterPresent 요청, ECU가 Positive Response 전송 |
| 0x80 | 1 (활성) | TesterPresent 요청, ECU가 응답 없음 (정상 시) |

예시 (TesterPresent)

[일반 요청]

진단기 → ECU: 3E 00

ECU → 진단기: 7E 00  (Positive Response)

[Suppress 활성화]

진단기 → ECU: 3E 80

ECU → 진단기: (응답 없음, 정상)

[오류 발생 시 - Suppress 활성화여도]

진단기 → ECU: 3E 80

ECU → 진단기: 7F 3E 12  (Negative Response, NRC 0x12)

Suppress 적용 가능 여부

- 모든 Sub-function 기반 서비스가 Suppress를 지원하지는 않음
- 표준에서 명시한 서비스만 지원 (DiagnosticSessionControl, ECUReset, SecurityAccess, CommunicationControl, TesterPresent 등)

### **2.5 Functional vs Physical Addressing**

두 가지 주소 지정 방식

Physical Addressing (1:1)

- 진단기가 특정 ECU 1대를 지정하여 요청
- 1:1 단방향 통신
- 해당 ECU만 응답
- CAN ID: 보통 0x7E0~0x7E7 (요청), 0x7E8~0x7EF (응답)
- 활용: 특정 ECU 정밀 진단, DTC 읽기, 리프로그래밍

Functional Addressing (1:N, Broadcast)

- 진단기가 여러 ECU에게 동시에 요청
- 1:N 브로드캐스트 통신
- 해당 요청을 지원하는 모든 ECU가 응답 (각자 Physical 응답 ID로)
- CAN ID: 0x7DF (요청), ECU별 Physical 응답 ID로 응답
- 활용: 전체 ECU의 DTC 일괄 조회, 세션 일괄 전환

주요 차이점 비교

|  |  |  |
| --- | --- | --- |
| **항목** | **Physical Addressing** | **Functional Addressing** |
| 통신 구조 | 1:1 | 1:N (브로드캐스트) |
| 요청 CAN ID | 0x7E0~0x7E7 | 0x7DF |
| 응답 CAN ID | 0x7E8~0x7EF | 각 ECU의 Physical 응답 ID |
| 응답 노드 수 | 1개 | 다수 (해당 요청 지원 ECU 모두) |
| 멀티프레임 가능 | 가능 | 일부 제한 (Single Frame만 권장) |
| 활용 예 | DTC 읽기, 플래시 | 전체 DTC 조회, 세션 전환 |

Functional Addressing의 제약

- 응답 충돌 방지를 위해 Single Frame(7바이트 이하) 요청만 사용
- 데이터가 많은 서비스(예: 0x2E WriteDataByIdentifier)는 부적합
- ECU가 동시에 응답하므로 진단기는 응답 ID로 ECU를 구별

활용 예시 (전체 ECU DTC 일괄 조회)

진단기 → 모든 ECU (Functional, 0x7DF):

07DF  02  19 02 FF

ECM → 진단기 (Physical 응답):

07E8  06  59 02 FF [DTC 데이터]

TCU → 진단기 (Physical 응답):

07E6  02  59 02 00

BCM → 진단기 (Physical 응답):

07E4  06  59 02 FF [DTC 데이터]

DoIP에서의 어드레싱

- CAN ID 대신 논리 주소(Logical Address) 사용
- Physical: 진단기 → 특정 ECU 논리 주소 (예: 0x0010 ECM)
- Functional: 진단기 → 그룹 논리 주소 (예: 0xE400 전체 ECU)
- 어드레싱 원리는 CAN과 동일

## **3. UDS****프로토콜 스택**

### **3.1 OSI****계층에서의 UDS 위치**

UDS의 OSI 매핑

UDS는 응용 계층(Layer 7) 프로토콜로, 하위 계층은 사용 환경(CAN, Ethernet 등)에 따라 달라진다.

|  |  |  |
| --- | --- | --- |
| **OSI****계층** | **UDS on CAN** | **UDS on DoIP** |
| 7. 응용 | UDS (ISO 14229) | UDS (ISO 14229) |
| 6. 표현 | - | DoIP (ISO 13400) |
| 5. 세션 | UDS 세션 관리 | UDS 세션 관리 |
| 4. 전송 | ISO 15765-2 (CAN TP) | TCP / UDP |
| 3. 네트워크 | - | IP |
| 2. 데이터링크 | CAN 프레임 | 이더넷 MAC |
| 1. 물리 | CAN\_H / CAN\_L (NRZ) | 100BASE-T1 (PAM3) |

핵심 포인트

- UDS는 응용 계층에서 동일한 서비스 제공
- 하위 계층만 환경에 맞게 교체
- 진단기 입장에서 UDS 메시지(예: 22 F1 90)는 환경과 무관하게 동일

### **3.2 UDS on CAN (ISO 15765-2 TP)**

ISO 15765-2의 역할

- CAN의 프레임 크기 제약(8바이트, CAN FD는 64바이트)을 극복
- 큰 UDS 메시지를 여러 프레임으로 분할/재조립
- 흐름 제어로 송수신 측 동기화

4가지 프레임 타입 요약

|  |  |  |  |
| --- | --- | --- | --- |
| **프레임 타입** | **PCI** | **사용 시점** | **구조** |
| Single Frame (SF) | 0x0 | 데이터 7바이트 이하 | [PCI(SF\_DL)][Data 1]...[Data 7] |
| First Frame (FF) | 0x1 | 데이터 8바이트 초과의 첫 프레임 | [PCI + 전체길이(2바이트)][Data 1]...[Data 6] |
| Consecutive Frame (CF) | 0x2 | FF 이후 이어지는 프레임 | [PCI + SN][Data 1]...[Data 7] |
| Flow Control (FC) | 0x3 | 수신 측이 송신 조건 통보 | [PCI + FS][BS][STmin] |

Single Frame (SF) 예시

02 10 03

└─ PCI=0x02 (2바이트 데이터)

   └─ UDS 데이터: 10 03

First Frame (FF) 예시

10 14 2E F1 90 31 32 33 34

└─ PCI=0x1, 전체 길이=0x014(20바이트)

   └─ UDS 데이터 시작

Consecutive Frame (CF)의 SN

- 순서 번호 (Sequence Number)
- 0x21, 0x22 ... 0x2F → 0x20으로 순환

Flow Control (FC) 필드 상세

|  |  |  |
| --- | --- | --- |
| **필드** | **값** | **의미** |
| FS (Flow Status) | 0x00 | ContinueToSend |
| FS | 0x01 | Wait |
| FS | 0x02 | Overflow |
| BS (Block Size) | 0x00 | 제한 없음, 한 번에 모두 전송 |
| BS | 0xNN | NN개 CF 전송 후 다시 FC 대기 |
| STmin | 0x00~0x7F | 0~127ms |
| STmin | 0xF1~0xF9 | 100~900μs |

멀티프레임 전송 흐름

진단기 → ECU: FF (전체 길이 포함)

ECU → 진단기: FC (BS, STmin 통보)

진단기 → ECU: CF 0x21

진단기 → ECU: CF 0x22

        ...

진단기 → ECU: CF 0x2N

ECU → 진단기: 응답 (SF 또는 FF+CF)

UDS와 CAN TP의 관계

- UDS는 메시지 자체만 정의 (예: 10 03)
- CAN TP가 PCI 헤더를 붙여 CAN 프레임에 매핑
- 8바이트 이하 메시지: SF 한 개로 전송
- 8바이트 초과 메시지: FF + CF로 분할 전송

### **3.3 UDS on DoIP (ISO 13400)**

DoIP의 역할

- UDS 메시지를 TCP/IP 위에서 전송
- ISO 13400으로 표준화
- 차량용 이더넷 환경에서 UDS 진단 가능

DoIP 메시지 캡슐화 구조

[이더넷 헤더][IP 헤더][TCP/UDP 헤더][DoIP 헤더][UDS 메시지]

DoIP 헤더 (8바이트)

|  |  |  |
| --- | --- | --- |
| **필드** | **크기** | **설명** |
| 프로토콜 버전 | 1바이트 | DoIP 버전 (0x02) |
| 역버전 | 1바이트 | 프로토콜 버전 비트 반전 (오류 검출) |
| 페이로드 타입 | 2바이트 | 메시지 종류 (0x8001 = DiagnosticMessage 등) |
| 페이로드 길이 | 4바이트 | 뒤따르는 데이터 길이 |

UDS on DoIP 특징

- TCP 포트 13400: 실제 UDS 진단 메시지 전송
- UDP 포트 13400: 차량 탐색(Vehicle Discovery)
- Routing Activation: TCP 연결 후 진단 경로 개통 필수
- 논리 주소(Logical Address)로 ECU 식별 (예: ECM = 0x0010)

UDS on CAN과의 차이

|  |  |  |
| --- | --- | --- |
| **항목** | **UDS on CAN** | **UDS on DoIP** |
| 전송 계층 | ISO 15765-2 (CAN TP) | TCP / UDP |
| 어드레싱 | CAN ID (11/29비트) | 논리 주소 + IP |
| 페이로드 분할 | SF/FF/CF/FC 필요 | TCP가 자동 처리 |
| 라우팅 활성화 | 없음 | 필수 |
| 최대 페이로드 | 4095바이트 | 사실상 무제한 |
| 전송 속도 | 1 Mbps (FD: 8 Mbps) | 100 Mbps 이상 |

UDS 메시지 자체는 동일

- UDS 메시지 내용(예: 22 F1 90)은 CAN과 DoIP에서 완전히 동일
- 하위 전송 수단만 다름

### **3.4 UDS on LIN, FlexRay**

UDS on LIN

- ISO 14229-7로 표준화
- LIN 마스터-슬레이브 구조에 맞게 적용
- 저속 편의장치 ECU 진단 (시트, 미러, 조명 등)
- 전송 속도: 최대 20 Kbps
- 진단 프레임 ID: 0x3C (Master Request), 0x3D (Slave Response)

UDS on FlexRay

- ISO 14229-4로 표준화
- 시간 동기화 기반 결정론적 통신 활용
- 샤시, 안전 관련 시스템 진단 (ABS, 에어백)
- 전송 속도: 최대 10 Mbps
- 실제 적용 사례는 제한적 (대부분 CAN/이더넷으로 통합)

적용 현황

|  |  |  |
| --- | --- | --- |
| **프로토콜** | **적용 도메인** | **현재 사용도** |
| UDS on CAN | 파워트레인, 샤시, 바디 | 매우 높음 (대부분 차량) |
| UDS on DoIP | 진단/플래시, OTA | 빠르게 증가 중 |
| UDS on LIN | 저속 편의장치 | 유지 (특정 도메인) |
| UDS on FlexRay | 안전 시스템 | 감소 (이더넷 대체) |

핵심 결론

- 어떤 물리 계층을 사용하든 UDS 응용 계층 서비스는 동일
- 진단기는 한 번 UDS를 익히면 모든 환경에서 동일하게 활용 가능
- 환경별 차이는 하위 계층(전송/물리)에서만 발생
