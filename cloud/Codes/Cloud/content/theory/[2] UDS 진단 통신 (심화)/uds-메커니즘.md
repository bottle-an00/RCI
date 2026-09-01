---
title: UDS 메커니즘
group: UDS 진단 통신
group_order: 2
difficulty: 심화
order: 2
---

# (2) UDS 메커니즘

**4. UDS****타이밍 파라미터**

**4.1****타이밍 파라미터 개요**

타이밍 파라미터의 역할

- UDS 통신에서 진단기와 ECU 간의 응답 시간과 세션 유지 시간을 정의
- 통신 안정성과 진단 신뢰성을 보장하는 핵심 요소
- ISO 14229-2 (Session Layer Services)에서 규정

타이밍 파라미터 종류

|  |  |  |
| --- | --- | --- |
| **구분** | **파라미터** | **역할** |
| 응답 시간 | P2\_Client / P2\_Server | 일반적인 요청-응답 제한 시간 |
| 연장 응답 시간 | P2\_Client / P2\_Server | 0x78 Response Pending 이후 연장 제한 시간 |
| 세션 유지 시간 | S3\_Client / S3\_Server | 진단 세션 유지를 위한 TesterPresent 주기 |
| 바이트 간 간격 | P1 / P4 | 메시지 내 바이트 간 전송 간격 |

Client(진단기) vs Server(ECU) 파라미터

- 동일한 파라미터의 Client 측과 Server 측 값은 다를 수 있음
- Client는 약간 더 긴 시간을 적용 (네트워크 지연 고려)
- 예: P2\_Server = 50ms, P2\_Client = 50ms + α (네트워크 지연)

## **4.2 P2\_Client, P2\_Server**

P2\_Server (ECU 응답 제한 시간)

- ECU가 요청을 받은 후 응답을 보내야 하는 최대 시간
- 기본값: 50ms
- 이 시간을 초과하면 ECU는 0x78 Response Pending을 전송해야 함

P2\_Client (진단기 대기 시간)

- 진단기가 요청을 보낸 후 ECU 응답을 기다리는 최대 시간
- 기본값: 50ms (Server와 동일하거나 약간 더 김)
- 이 시간 내에 응답이 없으면 타임아웃으로 판단

동작 흐름

진단기 ──Request──→ ECU

       (시간 측정 시작)

              ↓

       P2 시간 (50ms) 내 처리 가능?

              ↓

       Yes → ECU ──Response──→ 진단기

       No  → ECU ──0x78 Pending──→ 진단기 (시간 연장)

진단기 측 타임아웃 처리

|  |  |
| --- | --- |
| **상황** | **진단기 동작** |
| P2\_Client 내 응답 수신 | 정상 처리 |
| P2\_Client 초과, 0x78 수신 | P2\*\_Client로 타이머 전환하여 대기 |
| P2\_Client 초과, 응답 없음 | 타임아웃 오류, 통신 실패 처리 |

## **4.3 P2\_Server, P2\_Client (Response Pending****연장 시간)**

P2\*\_Server (ECU 연장 응답 시간)

- ECU가 0x78(Response Pending) 전송 후 적용되는 연장 제한 시간
- 기본값: 5000ms
- ECU가 복잡한 작업(플래시 소거, 보안 인증 등)을 수행할 때 사용

P2\*\_Client (진단기 연장 대기 시간)

- 진단기가 0x78 수신 후 적용하는 연장 대기 시간
- 기본값: 5000ms
- 이 시간 내에 최종 응답이 와야 함

사용 시점

ECU가 50ms 이내에 처리할 수 없는 작업:

- 플래시 메모리 소거/쓰기
- 복잡한 자가 진단 루틴
- 보안 인증 알고리즘 연산
- 대용량 데이터 처리

동작 흐름

진단기 ──Request──→ ECU

       (P2 타이머 시작, 50ms)

              ↓

       50ms 초과 시

              ↓

       ECU ──0x78──→ 진단기

       (진단기: P2\* 타이머로 전환, 5000ms)

              ↓

       5000ms 내 처리 가능?

              ↓

       Yes → ECU ──최종 응답──→ 진단기

       No  → ECU ──0x78 재전송──→ 진단기 (P2\* 타이머 리셋)

0x78 반복 전송

- 5000ms 안에도 처리가 끝나지 않으면 ECU는 0x78을 다시 전송
- 0x78이 올 때마다 P2\*\_Client 타이머가 리셋됨
- 이론적으로 무한 반복 가능하지만, 실제로는 진단기가 일정 횟수 초과 시 오류 처리

## **4.4 0x78 (Response Pending)****동작 상세**

0x78 NRC의 의미

- Negative Response Code 중 유일하게 "거부"가 아닌 "처리 중" 의미
- 형식: 7F + 요청 SID + 78
- 예: 7F 27 78 (SecurityAccess 처리 중)

0x78 전송 시나리오

1. ECU가 요청 수신
2. 처리 시간이 P2\_Server(50ms)를 초과할 것으로 판단
3. P2\_Server 만료 전에 0x78 전송
4. 진단기는 P2\*\_Client(5000ms)로 타이머 전환
5. ECU가 작업 완료 후 최종 Positive/Negative Response 전송

로그 예시

      [Tester → ECU]  10 02              ; Programming Session 요청

      [ECU → Tester]  7F 10 78           ; Response Pending (처리 중)

      [ECU → Tester]  7F 10 78           ; 추가 처리 시간 필요

      [ECU → Tester]  50 02 00 32 13 88  ; 최종 Positive Response

0x78이 자주 발생하는 서비스

|  |  |
| --- | --- |
| **서비스** | **발생 이유** |
| 0x10 DiagnosticSessionControl | 세션 전환 시 ECU 초기화 작업 |
| 0x27 SecurityAccess | Seed 생성 및 Key 검증 알고리즘 |
| 0x31 RoutineControl | 메모리 소거, 자가 진단 등 시간 소요 작업 |
| 0x34 RequestDownload | 다운로드 영역 준비 |
| 0x36 TransferData | 플래시 쓰기 작업 |

## **4.5 S3 (Session Timeout)**

S3\_Server (ECU 세션 유지 시간)

- ECU가 비기본 세션을 유지하는 최대 시간
- 기본값: 5000ms (5초)
- 이 시간 동안 진단 요청이 없으면 Default Session으로 자동 복귀

S3\_Client (진단기 TesterPresent 전송 주기)

- 진단기가 TesterPresent(0x3E)를 전송해야 하는 최대 주기
- 일반적으로 S3\_Server보다 짧게 설정 (예: 2000ms~3000ms)
- 안전 마진을 두어 세션 끊김 방지

동작 원리

[비기본 세션 진입]

      진단기 → ECU: 10 03  (Extended Session 진입)

      ECU → 진단기: 50 03 ...

[세션 유지]

      진단기는 S3\_Client 주기마다 TesterPresent 전송

      ECU의 S3 타이머가 리셋됨

[세션 끊김]

      S3\_Server 시간 동안 요청 없음

      → ECU가 자동으로 Default Session 복귀

      → 이후 요청 시 세션 관련 NRC (예: 0x7F 22 7F)

TesterPresent 전송 패턴

      시간: 0ms     - Extended Session 진입 (10 03)

      시간: 2000ms  - TesterPresent 전송 (3E 80) ← Suppress

      시간: 4000ms  - TesterPresent 전송 (3E 80)

      시간: 6000ms  - TesterPresent 전송 (3E 80)

      ... 세션 유지 ...

## **4.6****타이밍 파라미터 조회 및 변경**

조회 방법

- 10 03 (Extended Session) 응답에서 ECU의 P2/P2\* 값 확인 가능
- 응답 형식: 50 03 [P2\_Server\_max(2바이트)][P2\*\_Server\_max(2바이트)]

예시

      [Tester → ECU]  10 03

      [ECU → Tester]  50 03 00 32 01 F4

      50 03      : Session 전환 완료

      00 32      : P2\_Server = 0x0032 = 50ms

      01 F4      : P2\*\_Server = 0x01F4 = 500 (단위 10ms) = 5000ms

P2 값의 단위 차이 주의

|  |  |  |
| --- | --- | --- |
| **파라미터** | **단위** | **예시 (Hex → 시간)** |
| P2 | 1ms | 0x0032 = 50ms |
| P2\* | 10ms | 0x01F4 = 500 × 10ms = 5000ms |

타이밍 변경 (AccessTimingParameter)

- 일부 ECU는 진단기가 타이밍 값을 변경하도록 허용
- ISO 14230 (KWP2000)에서는 0x83 서비스 사용
- UDS에서는 표준 서비스가 없으나, 제조사별로 별도 구현 가능

## **4.7****타이밍 관련 문제**

진단 통신 타임아웃 발생 원인

|  |  |  |
| --- | --- | --- |
| **증상** | **원인** | **대응** |
| P2\_Client 만료 후 응답 없음 | 네트워크 단절, ECU 동작 정지 | 물리 계층/케이블 점검 |
| 0x78 반복 후 응답 없음 | ECU 내부 처리 오류, Deadlock | ECU 리셋 후 재시도 |
| S3 시간 내 응답 없음 | 세션 자동 복귀 | TesterPresent 주기 단축 |
| TesterPresent 전송 후 세션 끊김 | S3\_Server보다 주기가 김 | 전송 주기를 S3\_Server의 절반 이하로 설정 |

## **5. 진단 세션 (Diagnostic Session)**

**5.1****세션의 개념과 필요성**

세션 정의

- ECU의 진단 동작 모드를 정의하는 상태(State)
- 세션에 따라 사용 가능한 서비스와 기능이 달라짐
- 모든 ECU는 부팅 시 Default Session으로 시작

세션 도입 이유

- 보안: 위험한 서비스(플래시 등)는 특정 세션에서만 허용
- 자원 관리: 일반 주행 중에는 불필요한 진단 서비스 비활성화
- 안전: 차량 운행 중 ECU 리프로그래밍 같은 위험 동작 방지

세션 구조

- ECU는 한 번에 하나의 세션만 활성화
- 새로운 세션 진입 시 이전 세션 자동 종료
- Default Session으로 돌아가면 보안 인증, 진단 상태 등이 초기화

## **5.2****세션 종류**

ISO 14229 표준 세션

|  |  |  |  |
| --- | --- | --- | --- |
| **Sub-function** | **세션 이름** | **약어** | **용도** |
| 0x01 | Default Session | DS | 기본 운영 상태, 일반 주행 모드 |
| 0x02 | Programming Session | PS | ECU 리프로그래밍 전용 |
| 0x03 | Extended Diagnostic Session | EDS | 고급 진단 서비스 접근 |
| 0x04 | Safety System Diagnostic Session | SSDS | 안전 관련 시스템 진단 |
| 0x40~0x5F | 제조사 정의 | - | 제조사 고유 세션 |
| 0x60~0x7E | 시스템 공급사 정의 | - | 공급사 고유 세션 |

Default Session (0x01)

- ECU 부팅 시 기본 진입 세션
- 사용 가능한 서비스 제한적 (주로 읽기 전용)
- 일반 ECU 동작에 영향 없음
- TesterPresent 전송 불필요

Programming Session (0x02)

- ECU 리프로그래밍 전용 세션
- 진입 시 ECU가 부트로더로 전환되는 경우가 많음
- 일반 CAN 통신 중단되는 경우 있음 (CommunicationControl로 사전 차단)
- 플래시 소거, RequestDownload, TransferData 등 가능

Extended Diagnostic Session (0x03)

- 고급 진단 기능 활성화
- DTC 읽기, IO 제어, 데이터 쓰기 등 사용 가능
- 일반 주행 중에도 진입 가능
- 가장 많이 사용되는 비기본 세션

Safety System Diagnostic Session (0x04)

- 에어백, ABS 등 안전 관련 시스템 진단
- 특수한 안전 절차 후 진입 가능
- 제한된 차종에서만 지원

## **5.3****세션별 가능한 서비스**

서비스별 세션 요구사항 (대표 예)

|  |  |  |  |
| --- | --- | --- | --- |
| **서비스** | **Default** | **Extended** | **Programming** |
| 0x10 DiagnosticSessionControl | O | O | O |
| 0x11 ECUReset | O | O | O |
| 0x14 ClearDiagnosticInformation | △ | O | X |
| 0x19 ReadDTCInformation | O | O | △ |
| 0x22 ReadDataByIdentifier | O | O | △ |
| 0x27 SecurityAccess | △ | O | O |
| 0x28 CommunicationControl | X | O | O |
| 0x2E WriteDataByIdentifier | X | O | △ |
| 0x2F InputOutputControlByIdentifier | X | O | X |
| 0x31 RoutineControl | △ | O | O |
| 0x34 RequestDownload | X | △ | O |
| 0x36 TransferData | X | △ | O |
| 0x37 RequestTransferExit | X | △ | O |
| 0x3E TesterPresent | O | O | O |

               범례: O = 사용 가능, X = 사용 불가, △ = 제한적 (DID/RID에 따라)

세션 요구사항을 어길 경우

- NRC 0x7E: subFunctionNotSupportedInActiveSession
- NRC 0x7F: serviceNotSupportedInActiveSession
- 예: Default Session에서 0x2E 요청 → 0x7F 2E 7F

## **5.4****세션 전환 시 ECU 동작**

Default → Extended Session

      [Tester → ECU]  10 03

      [ECU → Tester]  50 03 00 32 01 F4

ECU 내부 동작:

      - 진단 기능 확장 모드로 전환

      - P2/P2\* 타이밍 파라미터 응답에 포함

      - S3 타이머 시작 (5000ms)

      - 보안 레벨은 잠금 상태 유지

Default → Programming Session

      [Tester → ECU]  10 02

      [ECU → Tester]  50 02 00 32 13 88

ECU 내부 동작:

      - 부트로더 모드로 전환 (일부 ECU)

      - 일반 애플리케이션 동작 중지

      - 플래시 소거/쓰기 준비

      - 일반 CAN 메시지 송수신 차단 가능

세션 전환 시 초기화되는 항목

- 보안 접근 상태 (SecurityAccess 다시 필요)
- IO 제어 상태 (0x2F로 제어한 액추에이터 원복)
- 통신 제어 상태 (0x28 설정 원복)
- 진단 데이터 캐시

세션 전환 시 유지되는 항목

- DTC 상태
- ECU 식별 정보
- 영구 저장된 캘리브레이션 데이터

## **5.5****세션 유지 (TesterPresent 0x3E)**

TesterPresent의 역할

- 비기본 세션 유지를 위한 Keep-alive 메시지
- ECU의 S3 타이머를 리셋
- Suppress Positive Response (0x80) 옵션 활용 권장

전송 주기 결정

- S3\_Server 기본값: 5000ms
- 권장 전송 주기: S3\_Server의 절반 이하 (예: 2000ms)
- 안전 마진 확보를 위함

기본 사용 패턴

[Tester → ECU]  3E 80                ; Suppress Positive Response

                                      ; (ECU 응답 없음, 정상)

세션 끊김 방지 시나리오

       시간 0ms    : 진단기 → ECU: 10 03 (Extended Session 진입)

       시간 0ms    : ECU → 진단기: 50 03 00 32 01 F4

       시간 2000ms : 진단기 → ECU: 3E 80 (TesterPresent, ECU S3 리셋)

       시간 4000ms : 진단기 → ECU: 3E 80

       시간 6000ms : 진단기 → ECU: 3E 80

       ... 진단 작업 수행 ...

       시간 N ms   : 진단기 → ECU: 10 01 (Default Session 복귀)

TesterPresent를 안 보내면

- S3\_Server(5000ms) 경과 시 ECU가 Default Session으로 자동 복귀
- 이후 모든 비기본 세션 전용 서비스가 NRC 응답
- 보안 접근 상태도 초기화됨

## **6. 보안 접근 (Security Access)**

**6.1 Security Access****의 필요성**

보안 접근이 필요한 이유

- 위험한 진단 동작으로부터 ECU 보호
- 무단 ECU 리프로그래밍 방지
- 보안 관련 정보(키, 인증서 등) 무단 변경 방지
- 도난 방지 시스템 우회 시도 차단

보안 접근이 요구되는 서비스

|  |  |
| --- | --- |
| **서비스** | **SecurityAccess****필요 여부** |
| 0x22 ReadDataByIdentifier (보안 DID) | O |
| 0x2E WriteDataByIdentifier | O (대부분 DID) |
| 0x2F InputOutputControlByIdentifier | O (대부분 RID) |
| 0x31 RoutineControl | O (위험 루틴) |
| 0x34 RequestDownload | O (필수) |
| 0x35 RequestUpload | O (필수) |
| 0x36 TransferData | 0x34 통과 후 자동 인증 |
| 0x37 RequestTransferExit | 0x34 통과 후 자동 인증 |

## **6.2 Seed & Key****메커니즘**

기본 동작 원리

1. 진단기가 ECU에게 Seed 요청 (홀수 Sub-function)
2. ECU가 랜덤 Seed 생성하여 응답
3. 진단기가 Seed로부터 Key 계산 (제조사별 알고리즘)
4. 진단기가 Key를 ECU에 전송 (짝수 Sub-function)
5. ECU가 Key 검증 후 권한 부여

홀수/짝수 Sub-function 쌍

|  |  |  |
| --- | --- | --- |
| **Sub-function** | **의미** | **응답** |
| 0x01 | requestSeed (Level 1) | Seed 반환 |
| 0x02 | sendKey (Level 1) | 인증 결과 |
| 0x03 | requestSeed (Level 2) | Seed 반환 |
| 0x04 | sendKey (Level 2) | 인증 결과 |
| 0x05 | requestSeed (Level 3) | Seed 반환 |
| 0x06 | sendKey (Level 3) | 인증 결과 |
| ... | ... | ... |

        홀수 = Seed 요청, 짝수 = Key 전송 (홀수 + 1)

기본 메시지 예시 (Level 1)

[Step 1: Seed 요청]

      [Tester → ECU]  27 01

      [ECU → Tester]  67 01 [Seed 4바이트]

      예: 67 01 AB CD EF 12

[Step 2: 진단기가 Key 계산]

      Seed: AB CD EF 12

      Key 계산 (제조사 알고리즘 적용): 34 56 78 90

[Step 3: Key 전송]

      [Tester → ECU]  27 02 34 56 78 90

      [ECU → Tester]  67 02     ; 인증 성공

[인증 실패 시]

      [ECU → Tester]  7F 27 35  ; invalidKey

## **6.3 Security Level****개념**

보안 레벨 분류

- ECU는 여러 보안 레벨을 가질 수 있음
- 각 레벨마다 다른 Sub-function 쌍 사용
- 레벨별로 접근 가능한 서비스/DID 다름

레벨별 권한 예시 (제조사마다 다름)

|  |  |  |
| --- | --- | --- |
| **Security Level** | **Sub-function** | **권한 범위** |
| Level 1 | 0x01/0x02 | 일반 진단 기능, 캘리브레이션 읽기 |
| Level 2 | 0x03/0x04 | DID 쓰기, 일부 IO 제어 |
| Level 3 | 0x05/0x06 | 리프로그래밍, 보안 데이터 쓰기 |
| Level 4 | 0x07/0x08 | 제조사 전용 깊은 진단 |

레벨 잠금 동작

- 세션 변경 시 모든 보안 레벨 잠금 상태로 초기화
- ECU 리셋(0x11) 시 모든 보안 레벨 잠금
- 일정 시간 비활성 시 자동 잠금 (제조사 정책)

이미 인증된 상태에서 Seed 요청 시

- ECU가 모든 0(0x0000...)을 Seed로 반환
- 이는 "이미 인증됨"을 의미

## **6.4****인증 실패 시 ECU 동작**

실패 시 발생하는 NRC

|  |  |  |
| --- | --- | --- |
| **NRC** | **의미** | **발생 조건** |
| 0x35 | invalidKey | 잘못된 Key 전송 |
| 0x36 | exceedNumberOfAttempts | 시도 횟수 초과 |
| 0x37 | requiredTimeDelayNotExpired | 대기 시간 미경과 |

Attempt Counter 동작

- ECU는 인증 시도 횟수를 카운트 (보통 3회)
- 일정 횟수 실패 시 일정 시간 동안 인증 시도 차단
- 차단 해제 시간: 보통 10초 ~ 600초

Delay Timer 동작

[1차 인증 시도]

       [Tester → ECU]  27 02 [wrong key]

       [ECU → Tester]  7F 27 35    ; invalidKey

[2차 인증 시도]

       [Tester → ECU]  27 02 [wrong key]

       [ECU → Tester]  7F 27 35    ; invalidKey

[3차 인증 시도]

       [Tester → ECU]  27 02 [wrong key]

       [ECU → Tester]  7F 27 36    ; exceedNumberOfAttempts

                              (Delay Timer 시작, 예: 10초)

[10초 내 재시도]

       [Tester → ECU]  27 01

       [ECU → Tester]  7F 27 37    ; requiredTimeDelayNotExpired

[10초 경과 후 재시도]

       [Tester → ECU]  27 01

       [ECU → Tester]  67 01 [Seed] ; 정상 동작

보안 정책 예시

|  |  |
| --- | --- |
| **시도 횟수** | **ECU****동작** |
| 1~2회 실패 | NRC 0x35 (invalidKey) |
| 3회 실패 | NRC 0x36, Delay Timer 시작 |
| Delay 중 시도 | NRC 0x37 |
| Delay 종료 후 | Counter 리셋, 다시 인증 가능 |

## **6.5 SecurityAccess****흐름**

전체 인증 시나리오

[Step 0: 사전 조건 확인]

- Extended Session 또는 Programming Session 진입

- TesterPresent 전송 시작

[Step 1: Seed 요청]

       [Tester → ECU]  27 01

       [ECU → Tester]  67 01 12 34 56 78    ; Seed 4바이트

[Step 2: 진단기가 Key 계산]

       입력: Seed = 12 34 56 78

       알고리즘 적용 (제조사 비공개)

       출력: Key = A1 B2 C3 D4

[Step 3: Key 전송]

       [Tester → ECU]  27 02 A1 B2 C3 D4

       [ECU → Tester]  67 02                ; 인증 성공

[Step 4: 보안 작업 수행]

       [Tester → ECU]  2E F1 90 [VIN data]  ; WriteDataByIdentifier

       [ECU → Tester]  6E F1 90              ; 정상 완료

[Step 5: 세션 종료]

       [Tester → ECU]  10 01                ; Default Session 복귀

       [ECU → Tester]  50 01 ...

SecurityAccess 사용 시 주의사항

- 인증 후에도 세션 변경 시 잠금 상태로 복귀
- 같은 레벨로 다시 요청 시 ECU가 새로운 Seed 발급
- 인증 실패 횟수 초과 전에 정확한 Key 전송 필요
- TesterPresent 누락으로 세션 끊기면 인증도 함께 풀림

## **7. NRC (Negative Response Code)**

**7.1 NRC****응답 형식**

기본 구조

[0x7F][요청 SID][NRC]

      0x7F: Negative Response 시작 코드 (고정)

      요청 SID: 거부 대상 서비스 SID

      NRC: 1바이트 거부 사유 코드

예시

      7F 22 33  → ReadDataByIdentifier 요청이 보안 미인증으로 거부

      7F 27 35  → SecurityAccess Key가 잘못됨

      7F 10 7F  → 현재 세션에서 요청한 세션 전환 불가

## **7.2****주요 NRC 코드 정리**

기본 거부 코드

|  |  |  |
| --- | --- | --- |
| **NRC** | **이름** | **의미** |
| 0x10 | generalReject | 일반적 거부 (구체적 사유 없음) |
| 0x11 | serviceNotSupported | 해당 서비스 SID 미지원 |
| 0x12 | subFunctionNotSupported | Sub-function 미지원 |
| 0x13 | incorrectMessageLengthOrInvalidFormat | 메시지 길이 또는 형식 오류 |

세션 관련 NRC

|  |  |  |
| --- | --- | --- |
| **NRC** | **이름** | **의미** |
| 0x7E | subFunctionNotSupportedInActiveSession | 현재 세션에서 Sub-function 미지원 |
| 0x7F | serviceNotSupportedInActiveSession | 현재 세션에서 서비스 미지원 |

조건/상태 관련 NRC

|  |  |  |
| --- | --- | --- |
| **NRC** | **이름** | **의미** |
| 0x21 | busyRepeatRequest | ECU가 바쁨, 재시도 필요 |
| 0x22 | conditionsNotCorrect | 차량/ECU 조건 불만족 (시동, 전압 등) |
| 0x24 | requestSequenceError | 요청 순서 오류 |
| 0x25 | noResponseFromSubnetComponent | 서브넷 ECU 응답 없음 |
| 0x26 | failurePreventsExecutionOfRequestedAction | 다른 오류로 인해 실행 불가 |

데이터/범위 관련 NRC

|  |  |  |
| --- | --- | --- |
| **NRC** | **이름** | **의미** |
| 0x31 | requestOutOfRange | 요청 파라미터(DID/RID 등) 범위 초과 |

보안 관련 NRC

|  |  |  |
| --- | --- | --- |
| **NRC** | **이름** | **의미** |
| 0x33 | securityAccessDenied | SecurityAccess 인증 안 됨 |
| 0x35 | invalidKey | 전송한 Key 값 오류 |
| 0x36 | exceedNumberOfAttempts | 인증 시도 횟수 초과 |
| 0x37 | requiredTimeDelayNotExpired | 인증 차단 대기 시간 미경과 |

업로드/다운로드 관련 NRC

|  |  |  |
| --- | --- | --- |
| **NRC** | **이름** | **의미** |
| 0x70 | uploadDownloadNotAccepted | 업/다운로드 거부 |
| 0x71 | transferDataSuspended | 데이터 전송 일시 중지 |
| 0x72 | generalProgrammingFailure | 일반적 프로그래밍 실패 |
| 0x73 | wrongBlockSequenceCounter | 블록 순서 번호 오류 (0x36) |

응답 보류 NRC (특수)

|  |  |  |
| --- | --- | --- |
| **NRC** | **이름** | **의미** |
| 0x78 | requestCorrectlyReceivedResponsePending | 요청 정상 수신, 응답 처리 중 |

차량 운행 관련 NRC

|  |  |  |
| --- | --- | --- |
| **NRC** | **이름** | **의미** |
| 0x81 | rpmTooHigh | 엔진 RPM 너무 높음 |
| 0x82 | rpmTooLow | 엔진 RPM 너무 낮음 |
| 0x83 | engineIsRunning | 엔진 작동 중 |
| 0x84 | engineIsNotRunning | 엔진 정지 상태 |
| 0x85 | engineRunTimeTooLow | 엔진 작동 시간 부족 |
| 0x86 | temperatureTooHigh | 온도 너무 높음 |
| 0x87 | temperatureTooLow | 온도 너무 낮음 |
| 0x88 | vehicleSpeedTooHigh | 차속 너무 높음 |
| 0x89 | vehicleSpeedTooLow | 차속 너무 낮음 |
| 0x8A | throttle/PedalTooHigh | 스로틀/페달 너무 높음 |
| 0x8B | throttle/PedalTooLow | 스로틀/페달 너무 낮음 |
| 0x8C | transmissionRangeNotInNeutral | 변속기 중립 아님 |
| 0x8D | transmissionRangeNotInGear | 변속기 기어 미체결 |
| 0x8F | brakeSwitch(es)NotClosed | 브레이크 미체결 |
| 0x90 | shifterLeverNotInPark | P 단 아님 |
| 0x91 | torqueConverterClutchLocked | 토크 컨버터 클러치 잠김 |
| 0x92 | voltageTooHigh | 전원 전압 너무 높음 |
| 0x93 | voltageTooLow | 전원 전압 너무 낮음 |

## **7.3 NRC****별 발생 원인 및 실무 대응**

자주 마주치는 NRC 분석

NRC 0x22 conditionsNotCorrect

|  |  |
| --- | --- |
| **발생 원인** | **대응 방법** |
| 엔진 시동/정지 조건 불일치 | 시동 상태 확인 후 재요청 |
| 차량 전압이 낮음 (10V 이하) | 배터리 점검 |
| 차속이 0이 아님 | 차량 정지 상태 확인 |
| 변속기 P 단 아님 | P 단 변경 후 재요청 |
| ECU 내부 상태가 조건 미충족 | DTC 확인 후 ECU 상태 점검 |

NRC 0x31 requestOutOfRange

|  |  |
| --- | --- |
| **발생 원인** | **대응 방법** |
| 잘못된 DID 사용 | ODX 파일에서 정확한 DID 확인 |
| 지원하지 않는 RID | 서비스 0x31이 지원하는 RID 확인 |
| Sub-function 값이 범위 초과 | 표준 또는 ODX 명세 확인 |
| 메시지 페이로드 값 오류 | 메시지 구조 재검토 |

NRC 0x33 securityAccessDenied

|  |  |
| --- | --- |
| **발생 원인** | **대응 방법** |
| SecurityAccess 미수행 | 0x27로 인증 후 재시도 |
| 다른 Security Level 요구 | 올바른 Level의 Sub-function 사용 |
| 세션 변경으로 인증 해제 | 세션 진입 후 다시 인증 |
| ECU 리셋으로 인증 해제 | 리셋 후 다시 인증 |

NRC 0x7E / 0x7F (세션 미지원)

|  |  |
| --- | --- |
| **발생 원인** | **대응 방법** |
| Default Session에서 비기본 서비스 요청 | Extended Session(10 03) 진입 후 재시도 |
| Extended Session에서 Programming 전용 요청 | Programming Session(10 02) 진입 후 재시도 |
| 세션 전환 실패 | 0x10 응답 확인, 조건 점검 |

NRC 0x78 requestCorrectlyReceivedResponsePending

|  |  |
| --- | --- |
| **발생 원인** | **대응 방법** |
| 시간 소요되는 작업 (플래시 등) | 정상 동작, P2\* 시간까지 대기 |
| Key 검증 알고리즘 연산 | 정상 동작, 대기 |
| 0x78 반복 후 응답 없음 | ECU 오류 의심, 리셋 후 재시도 |

## **7.4 NRC****분석 체크리스트**

진단 통신 실패 시 점검 순서

      NRC 코드 확인

         - 7F XX YY 형식에서 YY 값 추출

      NRC 분류 판단

         - 세션/보안/조건/범위 등 카테고리 분류

      사전 조건 점검

         - 현재 세션 확인 (10 03 응답에서 P2/P2\*)

         - SecurityAccess 상태 확인

         - 차량 운행 조건 확인 (시동, 전압, 속도)

      메시지 구조 점검

         - SID, Sub-function, 페이로드 형식

         - 길이, 순서 번호 등

      재시도

         - 사전 조건 충족 후 재요청

자주 발생하는 조합 패턴

|  |  |  |
| --- | --- | --- |
| **시나리오** | **NRC****시퀀스** | **분석** |
| 세션 미진입 | 0x7F → 인증 시도 | 0x10 03 먼저 수행 |
| 인증 미수행 | 0x33 | 0x27 수행 후 재시도 |
| 시도 초과 | 0x35 → 0x35 → 0x36 → 0x37 | Delay 종료까지 대기 |
| 차량 조건 | 0x22 | 시동/속도/전압 점검 |
| 잘못된 DID | 0x31 | ODX/DBC 파일 확인 |
| 처리 중 | 0x78 → 0x78 → 정상 응답 | 대기 |
