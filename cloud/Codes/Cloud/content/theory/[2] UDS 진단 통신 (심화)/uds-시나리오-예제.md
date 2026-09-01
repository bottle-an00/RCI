---
title: UDS 시나리오 예제
group: UDS 진단 통신
group_order: 2
difficulty: 심화
order: 5
---

# (5) UDS 시나리오 예제

**22.****진단 시나리오 예제**

**22.1 DTC****읽기/삭제 전체 흐름**

기본 시나리오

[Step 1] 세션 진입

      [요청]  10 03                          ; Extended Session

      [응답]  50 03 00 32 01 F4

[Step 2] DTC 개수 확인

      [요청]  19 01 08                       ; Confirmed DTC 개수 조회

      [응답]  59 01 FF 01 00 03              ; 3개의 DTC 존재

[Step 3] DTC 목록 조회

      [요청]  19 02 08                       ; Confirmed DTC 목록

      [응답]  59 02 FF P0301 2F P0420 2F C1234 2F

[Step 4] Snapshot 조회 (선택)

      [요청]  19 04 P0301 FF                 ; P0301 발생 당시 데이터

      [응답]  59 04 [Snapshot 데이터]

[Step 5] 정비 완료 후 DTC 삭제

      [요청]  14 FF FF FF                    ; 모든 DTC 삭제

      [응답]  54

[Step 6] 세션 종료

      [요청]  10 01                          ; Default Session 복귀

      [응답]  50 01 00 32 01 F4

## **22.2 ECU****식별 정보 읽기 시나리오**

여러 DID로 ECU 정보 조회

[Step 1] Default Session에서 가능 (대부분 식별 DID는 Default에서 읽기 가능)

[Step 2] VIN 조회

      [요청]  22 F1 90

      [응답]  62 F1 90 [VIN 17바이트]

[Step 3] S/W 버전 조회

      [요청]  22 F1 88

      [응답]  62 F1 88 [S/W 번호 데이터]

[Step 4] H/W 번호 조회

      [요청]  22 F1 91

      [응답]  62 F1 91 [H/W 번호 데이터]

[Step 5] 한 번에 다중 DID 조회 (지원 시)

      [요청]  22 F1 90 F1 88 F1 91

      [응답]  62 F1 90 [...] F1 88 [...] F1 91 [...]

## **22.3 VIN****쓰기 시나리오 (SecurityAccess 포함)**

전체 인증 및 쓰기 흐름

[Step 1] Extended Session 진입

      [요청]  10 03

      [응답]  50 03 00 32 01 F4

[Step 2] TesterPresent 주기 전송 시작 (백그라운드)

      [요청]  3E 80                          ; 2초마다 반복

[Step 3] Seed 요청

      [요청]  27 01

      [응답]  67 01 12 34 56 78              ; Seed

[Step 4] Key 계산 후 전송

      [요청]  27 02 A1 B2 C3 D4              ; Key

      [응답]  67 02                          ; 인증 성공

[Step 5] VIN 쓰기

      [요청]  2E F1 90 [VIN 17바이트]

      [응답]  6E F1 90

[Step 6] 쓰기 확인

      [요청]  22 F1 90

      [응답]  62 F1 90 [방금 쓴 VIN]

[Step 7] 세션 종료

      [요청]  10 01

      [응답]  50 01 00 32 01 F4

## **22.4****액추에이터 제어 시나리오 (IOControl)**

헤드라이트 강제 점등 테스트

[Step 1] 차량 정지, P단, 시동 ON 확인

[Step 2] Extended Session 진입

      [요청]  10 03

      [응답]  50 03 00 32 01 F4

[Step 3] SecurityAccess (필요 시)

      [요청]  27 01 / 27 02

      [응답]  67 01 / 67 02

[Step 4] TesterPresent 주기 전송 시작

[Step 5] 라이트 강제 점등

      [요청]  2F 12 34 03 01                 ; shortTermAdjustment, ON

      [응답]  6F 12 34 03 01

... 동작 확인 ...

[Step 6] 제어권 반환

      [요청]  2F 12 34 00

      [응답]  6F 12 34 00

[Step 7] 세션 종료

      [요청]  10 01

      [응답]  50 01 00 32 01 F4

## **22.5 ECU****리프로그래밍 전체 흐름**

[Step 1] Extended Session 진입

      [요청]  10 03

      [응답]  50 03 00 32 01 F4

[Step 2] 차량 전체 ECU 통신 차단 (Functional)

      [요청]  28 03 03                       ; 모든 ECU에 일반 통신 차단

      [응답]  68 03 (각 ECU)

[Step 3] 일반 DTC 발생 비활성화 (선택)

      [요청]  85 02                          ; ControlDTCSetting Off

      [응답]  C5 02

[Step 4] Programming Session 진입

      [요청]  10 02

      [응답]  50 02 00 32 13 88              ; P2\*=50000ms (플래시 작업 대비)

[Step 5] SecurityAccess (Programming Level)

      [요청]  27 05

      [응답]  67 05 [Seed]

      [요청]  27 06 [Key]

      [응답]  67 06

[Step 6] TesterPresent 주기 전송 시작

[Step 7] 핑거프린트 쓰기 (Optional, 제조사별)

      [요청]  2E F1 84 [핑거프린트 데이터]

      [응답]  6E F1 84

[Step 8] 프로그래밍 의존성 검증

      [요청]  31 01 FF 01

      [응답]  71 01 FF 01 00                 ; 검증 통과

[Step 9] 플래시 메모리 소거

      [요청]  31 01 FF 00 [메모리 주소][크기]

      [응답]  7F 31 78                       ; Response Pending

      [응답]  71 01 FF 00 00                 ; 소거 완료

[Step 10] RequestDownload

      [요청]  34 00 44 [시작 주소][크기]

      [응답]  74 20 04 02                    ; max 블록 크기 1026바이트

[Step 11] TransferData 반복 (블록 단위)

      [요청]  36 01 [1024바이트 데이터]

      [응답]  76 01

      [요청]  36 02 [1024바이트 데이터]

      [응답]  76 02

      ... 모든 블록 전송까지 반복 ...

[Step 12] RequestTransferExit

      [요청]  37

      [응답]  77

[Step 13] 다운로드 무결성 검증

      [요청]  31 01 FF 01

      [응답]  71 01 FF 01 00                 ; 검증 통과

[Step 14] ECU 리셋 (새 펌웨어 적용)

      [요청]  11 01

      [응답]  51 01

      (ECU 재부팅 대기, 보통 1~2초)

[Step 15] Default Session 복귀 확인

      [요청]  10 01

      [응답]  50 01 00 32 01 F4

[Step 16] 차량 전체 ECU 통신 복원 (Functional)

      [요청]  28 00 03

      [응답]  68 00 (각 ECU)

[Step 17] DTC 삭제

      [요청]  14 FF FF FF

      [응답]  54

[Step 18] 새 펌웨어 버전 확인

      [요청]  22 F1 88

      [응답]  62 F1 88 [새 S/W 버전]

리프로그래밍 시간 비교 (참고)

| **환경** | **1MB****펌웨어 전송 시간** | **비고** |
| --- | --- | --- |
| CAN (500kbps) | 약 30분 ~ 1시간 | 멀티프레임, 흐름 제어로 인한 오버헤드 |
| CAN FD (5Mbps) | 약 5 ~ 10분 | 페이로드 64바이트로 증가 |
| DoIP (100Mbps) | 약 30초 ~ 1분 | 대용량 패킷 전송 |

## **23. 진단 통신 디버깅**

**23.1 NRC****코드별 트러블슈팅**

자주 마주치는 NRC 분석

NRC 0x22 conditionsNotCorrect

| **원인** | **대응** |
| --- | --- |
| 엔진 시동/정지 조건 불일치 | 시동 상태 확인 후 재요청 |
| 차량 전압 낮음 (10V 이하) | 배터리 점검 |
| 차속이 0이 아님 | 차량 정지 상태 확인 |
| 변속기 P 단 아님 | P 단 변경 후 재요청 |

NRC 0x31 requestOutOfRange

| **원인** | **대응** |
| --- | --- |
| 잘못된 DID 사용 | ODX 파일에서 정확한 DID 확인 |
| 지원하지 않는 RID | 서비스 0x31이 지원하는 RID 확인 |
| 메시지 페이로드 값 오류 | 메시지 구조 재검토 |

NRC 0x33 securityAccessDenied

| **원인** | **대응** |
| --- | --- |
| SecurityAccess 미수행 | 0x27로 인증 후 재시도 |
| 다른 Security Level 요구 | 올바른 Level의 Sub-function 사용 |
| 세션 변경으로 인증 해제 | 세션 진입 후 다시 인증 |

NRC 0x7E / 0x7F (세션 미지원)

| **원인** | **대응** |
| --- | --- |
| Default Session에서 비기본 서비스 요청 | Extended Session(10 03) 진입 후 재시도 |
| Extended Session에서 Programming 전용 요청 | Programming Session(10 02) 진입 후 재시도 |
| 세션 전환 실패 | 0x10 응답 확인, 조건 점검 |

NRC 0x78 requestCorrectlyReceivedResponsePending

| **원인** | **대응** |
| --- | --- |
| 시간 소요되는 작업 (플래시 등) | 정상 동작, P2\* 시간까지 대기 |
| 0x78 반복 후 응답 없음 | ECU 오류 의심, 리셋 후 재시도 |

## **23.2****타임아웃 발생 원인 (P2/P2\* 초과)**

P2\_Client 타임아웃 (50ms 초과)

| **원인** | **대응** |
| --- | --- |
| ECU 동작 정지 | ECU 리셋 시도 |
| 네트워크 단절 | 물리 계층/케이블 점검 |
| ECU가 0x78 보내지 않음 | ECU 펌웨어 버그 의심 |

P2\*\_Client 타임아웃 (5000ms 초과)

| **원인** | **대응** |
| --- | --- |
| ECU 내부 작업 지연 | 대기 후 재시도 |
| ECU 처리 Deadlock | ECU 리셋 |
| 잘못된 P2\* 값 사용 | ECU 응답의 P2\* 재확인 |

S3 타임아웃 (5000ms 초과)

| **원인** | **대응** |
| --- | --- |
| TesterPresent 누락 | 전송 주기 재확인 |
| 전송 주기가 S3보다 김 | 주기를 S3의 절반 이하로 단축 |

## **23.3****세션 전환 실패 분석**

세션 전환 시 점검 사항

| **증상** | **원인** | **대응** |
| --- | --- | --- |
| 10 02 요청 시 NRC 0x22 | 차량 운행 중 | 정지 후 재시도 |
| 10 02 요청 시 NRC 0x12 | 해당 ECU가 Programming 미지원 | ECU 사양 확인 |
| 세션 진입 후 즉시 Default 복귀 | TesterPresent 누락 | 주기 전송 확인 |
| 세션 응답 없음 | ECU 응답 안 함 | 물리 계층 점검 |

## **23.4 SecurityAccess****실패 분석**

NRC별 대응

| **NRC** | **원인** | **대응** |
| --- | --- | --- |
| 0x35 invalidKey | Key 계산 오류 | 알고리즘 재확인, ODX 파일 확인 |
| 0x36 exceedNumberOfAttempts | 시도 횟수 초과 | Delay 시간 대기 후 재시도 |
| 0x37 requiredTimeDelayNotExpired | Delay Timer 동작 중 | 대기 후 재시도 |
| 0x7F serviceNotSupportedInActiveSession | 세션 미지원 | Extended/Programming Session 진입 |

Key 알고리즘 오류 의심 시

- ECU 측 Seed 값 정확히 수신했는지 확인
- 알고리즘 입력 형식 확인 (Big-endian vs Little-endian)
- Key 계산 결과 길이 확인 (보통 4바이트)

## **23.5****리프로그래밍 실패 분석**

단계별 실패 원인

| **단계** | **증상** | **원인** |
| --- | --- | --- |
| Programming Session 진입 | NRC 0x22 | 차량 운행 조건 불만족 |
| SecurityAccess | NRC 0x35 | Programming Level Key 알고리즘 오류 |
| 메모리 소거 | NRC 0x72 | 플래시 ECU 동작 이상 |
| RequestDownload | NRC 0x31 | 메모리 주소/크기 잘못됨 |
| TransferData | NRC 0x73 | 블록 순서 오류 (네트워크 손실 등) |
| TransferData | NRC 0x72 | 플래시 쓰기 실패 |
| RequestTransferExit | NRC 0x31 | 전송 미완료 |
| 무결성 검증 | NRC 0x72 | 다운로드 데이터 손상 |

리프로그래밍 실패 시 ECU 상태

- 정상 종료되지 않은 경우 부트로더 모드로 남을 수 있음
- ECU가 정상 펌웨어 부팅 실패 시 진단 통신만 가능
- 이 경우 재플래시로 복구

## **23.6****로그 분석 방법론**

체계적 분석 단계

1) 물리 계층 확인

   - 케이블, 커넥터, OBD 핀 상태

   - 이더넷 링크 LED (DoIP의 경우)

2) CAN/이더넷 메시지 캡처

   - CAN 분석기 (Vector CANoe, Kvaser 등)

   - DoIP의 경우 Wireshark

3) UDS 메시지 흐름 추적

   - SID, Sub-function 순서대로 확인

   - NRC 발생 시점 확인

4) 사전 조건 점검

   - 현재 세션 (10 03 응답의 P2/P2\*)

   - SecurityAccess 상태

   - 차량 운행 조건

5) NRC 분석

   - NRC 코드별 대응 매뉴얼 적용

   - 재시도 또는 사전 조건 충족 후 재요청

## **24. CAN UDS vs DoIP UDS****차이**

**24.1****메시지 캡슐화 차이**

UDS on CAN

      [CAN ID][CAN TP PCI][UDS 메시지]

예시:

      07E0  02  10 03

      - 07E0: CAN ID (Physical Addressing 요청)

      - 02:   PCI (Single Frame, 2바이트)

      - 10 03: UDS 메시지

      UDS on DoIP

      [이더넷 헤더][IP 헤더][TCP 헤더][DoIP 헤더][UDS 메시지]

DoIP 헤더 (8바이트):

- 프로토콜 버전 (1바이트)

- 역버전 (1바이트)

- 페이로드 타입 (2바이트)

- 페이로드 길이 (4바이트)

핵심 차이

- UDS 메시지 자체는 동일 (10 03, 22 F1 90 등)
- 하위 계층 캡슐화만 다름

## **24.2****라우팅 활성화 추가 단계**

UDS on CAN

      물리 연결 → 바로 UDS 요청 가능

UDS on DoIP

      물리 연결 → DHCP → ARP → UDP 차량 탐색 → TCP 연결 → 라우팅 활성화 → UDS 요청

DoIP의 라우팅 활성화

- TCP 연결 성공 후 반드시 수행
- 진단기의 논리 주소와 ECU 경로 등록
- 활성화 실패 시 UDS 통신 불가
- 페이로드 타입 0x0005 (Request), 0x0006 (Response)

## **24.3****동시 다중 ECU 진단**

UDS on CAN

- 한 번에 하나의 ECU와 통신
- 멀티 ECU 진단 시 순차적 처리 필요

UDS on DoIP

- 여러 ECU와 동시에 TCP 연결 가능
- 병렬 진단으로 시간 단축
- 생산 라인 검사에서 큰 이점

## **24.4****어드레싱 차이**

| **항목** | **UDS on CAN** | **UDS on DoIP** |
| --- | --- | --- |
| 진단기 식별 | CAN ID (예: 0x7E0) | 논리 주소 + IP (예: 0x0E00 + 192.168.1.100) |
| ECU 식별 | CAN ID (예: 0x7E8) | 논리 주소 (예: 0x0010) |
| 브로드캐스트 | 0x7DF (Functional) | 그룹 논리 주소 (예: 0xE400) |

## **24.5****페이로드 크기 차이**

| **항목** | **UDS on CAN** | **UDS on DoIP** |
| --- | --- | --- |
| 단일 프레임 페이로드 | 7바이트 (CAN), 63바이트 (CAN FD) | 1500바이트 |
| 멀티프레임 분할 | CAN TP가 수동 처리 | TCP가 자동 처리 |
| 최대 메시지 크기 | 4095바이트 | 사실상 무제한 |

## **24.6****전송 속도 비교**

| **환경** | **속도** | **1MB****전송 시간 (이론)** |
| --- | --- | --- |
| CAN (500kbps) | 500kbps | 약 16초 (오버헤드 포함 약 30분) |
| CAN FD (5Mbps) | 5Mbps | 약 1.6초 (실제 5~10분) |
| DoIP (100Mbps) | 100Mbps | 약 0.08초 (실제 30초~1분) |
| DoIP (1Gbps) | 1Gbps | 약 0.008초 (실제 수 초) |

## **24.7****실무 마이그레이션 시 고려사항**

UDS 서비스 측면

- 7계층 UDS 서비스는 완전히 동일
- SID, Sub-function, NRC 등 모두 그대로 사용
- 기존 CAN UDS 개발 지식 그대로 활용 가능

진단기 측 추가 구현 사항

- TCP/IP 스택
- DHCP 클라이언트
- DoIP 헤더 처리
- 라우팅 활성화 로직
- Wireshark 등 네트워크 분석 도구 활용

차량 측 추가 구성

- DoIP 게이트웨이 (HPVC)
- 이더넷 PHY (트랜시버)
- OBD 커넥터에 이더넷 핀 (1번, 9번)

과도기 차량 진단

- D-CAN과 DoIP 둘 다 지원하는 진단기 필요
- 차량 진단 시 자동 감지 후 적절한 프로토콜 선택

## **24.8****정리 비교표**

| **항목** | **UDS on CAN (D-CAN)** | **UDS on DoIP** |
| --- | --- | --- |
| 표준 | ISO 14229-3 | ISO 14229-5 + ISO 13400 |
| 물리 계층 | CAN | Ethernet |
| 속도 | 1Mbps (CAN FD: 8Mbps) | 100Mbps ~ 1Gbps |
| OBD 핀 | 6번, 14번 | 1번, 9번 |
| 연결 준비 | 즉시 가능 | DHCP → ARP → TCP → 라우팅 활성화 |
| 어드레싱 | CAN ID | 논리 주소 + IP |
| 페이로드 | 8 (CAN), 64 (FD) 바이트 | 최대 1500 바이트 |
| 멀티 ECU 진단 | 순차적 | 동시 가능 |
| 원격 진단 | 불가 | 가능 (TCP/IP) |
| 보안 | 제한적 | TLS 등 적용 가능 |
| 적용 시기 | 과거 ~ 현재 | 현재 ~ 미래 (확산 중) |
