---
title: UDS 주요 서비스 상세 - 2
group: UDS 진단 통신
group_order: 2
difficulty: 심화
order: 4
---

# (4) UDS 주요 서비스 상세 - 2

**다룬 서비스 : 0x27 / 0x28 / 0x2E / 0x2F / 0x31 / 0x34 / 0x36 / 0x37 / 0x3E**

**13. SID 0x27 - SecurityAccess**

**13.1****서비스 개요 및 용도**

- ECU의 보안 기능 접근 권한 획득
- Seed & Key 기반 챌린지-리스폰스 인증 방식

용도

- ECU 리프로그래밍 권한 획득
- 보안 DID 읽기/쓰기 권한 획득
- 위험한 RoutineControl 실행 권한

특징

- Default Session에서는 일반적으로 사용 불가
- 세션 변경 시 인증 상태 자동 해제
- ECU 리셋 시 인증 상태 해제

## **13.2 Seed & Key****메커니즘**

기본 4단계 동작

1. 진단기 → ECU: Seed 요청 (홀수 Sub-function)
2. ECU → 진단기: 랜덤 Seed 반환
3. 진단기 → ECU: Seed로 계산한 Key 전송 (짝수 Sub-function)
4. ECU → 진단기: 인증 결과

이미 인증된 상태에서 Seed 요청 시: ECU가 모든 0(0x00000000)을 Seed로 반환

## **13.3 Sub-function****구조 (홀수/짝수 페어)**

|  |  |
| --- | --- |
| **Sub-function** | **의미** |
| 0x01 | requestSeed (Level 1) |
| 0x02 | sendKey (Level 1) |
| 0x03 | requestSeed (Level 2) |
| 0x04 | sendKey (Level 2) |
| 0x05 | requestSeed (Level 3) |
| 0x06 | sendKey (Level 3) |
| 0x07~0x42 | 제조사 정의 Level |

규칙: 홀수 = Seed 요청, 짝수 = Key 전송 (짝수 = 홀수 + 1)

## **13.4 Security Level****개념**

|  |  |  |
| --- | --- | --- |
| **Level** | **Sub-function** | **일반적 접근 권한** |
| Level 1 | 0x01/0x02 | 일반 진단, 캘리브레이션 읽기 |
| Level 2 | 0x03/0x04 | DID 쓰기, 일부 IO 제어 |
| Level 3 | 0x05/0x06 | 리프로그래밍, 보안 데이터 쓰기 |

레벨별로 독립적 인증 필요

## **13.5****인증 실패 시 ECU 동작**

|  |  |  |
| --- | --- | --- |
| **NRC** | **의미** | **발생 조건** |
| 0x35 | invalidKey | 잘못된 Key 전송 |
| 0x36 | exceedNumberOfAttempts | 시도 횟수 초과 (보통 3회) |
| 0x37 | requiredTimeDelayNotExpired | Delay Timer 동작 중 |

동작 흐름

- 1~2회 실패: NRC 0x35
- 3회 실패: NRC 0x36, Delay Timer 시작 (보통 10초~600초)
- Delay 중 시도: NRC 0x37
- Delay 종료 후: Counter 리셋, 재시도 가능

## **13.6****실무 로그 예시**

[요청]  27 01                          ; Seed 요청

[응답]  67 01 12 34 56 78              ; Seed = 0x12345678

[요청]  27 02 A1 B2 C3 D4              ; Key 전송

[응답]  67 02                          ; 인증 성공

## **14. SID 0x28 - CommunicationControl**

**14.1****서비스 개요 및 용도**

- ECU의 일반 통신(CAN 메시지 송수신) 제어
- 진단 통신은 영향받지 않음

용도

- 리프로그래밍 중 일반 CAN 메시지 차단 (버스 부하 감소)
- 특정 ECU의 송신/수신만 선택적으로 차단

특징

- Extended Session 이상에서 사용
- 진단 세션 종료 또는 ECU 리셋 시 자동 복원

## **14.2 Sub-function****종류**

|  |  |  |
| --- | --- | --- |
| **Sub-function** | **이름** | **동작** |
| 0x00 | enableRxAndTx | 수신/송신 모두 활성화 (기본 상태) |
| 0x01 | enableRxAndDisableTx | 수신 활성, 송신 비활성 |
| 0x02 | disableRxAndEnableTx | 수신 비활성, 송신 활성 |
| 0x03 | disableRxAndTx | 수신/송신 모두 비활성 (리프로그래밍 시 자주 사용) |

## **14.3 communicationType****비트 정의**

|  |  |
| --- | --- |
| **값** | **의미** |
| 0x01 | 일반 애플리케이션 메시지만 |
| 0x02 | 네트워크 관리 메시지만 |
| 0x03 | 일반 + 네트워크 관리 메시지 (리프로그래밍 시 자주 사용) |

## **14.4****리프로그래밍 시 활용**

- Programming Session 진입 전 모든 ECU에게 일반 통신 차단 요청 (Functional Addressing)
- 플래시 작업 시 CAN 버스 부하 감소 및 ECU 간 간섭 방지
- 작업 완료 후 통신 복원 (0x28 00)

## **14.5****발생 가능한 NRC**

|  |  |  |
| --- | --- | --- |
| **NRC** | **이름** | **발생 조건** |
| 0x12 | subFunctionNotSupported | 지원하지 않는 Sub-function |
| 0x22 | conditionsNotCorrect | 조건 불만족 |
| 0x31 | requestOutOfRange | communicationType 값 범위 초과 |
| 0x33 | securityAccessDenied | SecurityAccess 필요 |

## **14.6****실무 로그 예시**

[요청]  28 03 03                       ; 일반 + 네트워크 관리 모두 차단

[응답]  68 03                          ; 통신 차단 완료

## **15. SID 0x2E - WriteDataByIdentifier**

**15.1****서비스 개요 및 용도**

- DID를 통해 ECU에 데이터를 쓰는 서비스
- 0x22 (ReadDataByIdentifier)의 쓰기 버전

용도

- VIN 등록 또는 변경
- 캘리브레이션 데이터 쓰기
- 정비소 코드, 진단기 시리얼 등록

특징

- 대부분의 DID에 SecurityAccess 필요
- Extended Session 또는 Programming Session 필요
- 영구 저장(비휘발성 메모리)되는 경우가 많음

## **15.2****쓰기 가능한 DID 범위**

쓰기 가능 DID

| **DID** | **이름** |
| --- | --- |
| 0xF190 | VIN |
| 0xF198 | RepairShopCodeOrTesterSerialNumber |
| 0xF199 | ProgrammingDate |
| 0xF19D | ECUInstallationDate |
| 0xFD00~0xFEFF | 제조사 정의 |

읽기 전용 DID (쓰기 불가)

- 0xF180 BootSoftwareIdentification
- 0xF18A SystemSupplierIdentifier
- 0xF18C ECUSerialNumber
- 대부분 H/W 정보 관련 DID

## **15.3 SecurityAccess****요구 조건**

쓰기 작업 일반 흐름

1. Extended Session 진입 (10 03)
2. SecurityAccess 인증 (27 01 → 27 02)
3. WriteDataByIdentifier 실행 (2E XX XX [data])
4. 필요시 ECU 리셋 (11 01)

## **15.4****데이터 무결성 검증 (ECU 측)**

- DID에 정의된 데이터 길이 일치 확인
- 데이터 형식 검증 (예: VIN은 17자리 ASCII)
- 데이터 범위 검증

## **15.5****발생 가능한 NRC**

| **NRC** | **이름** | **발생 조건** |
| --- | --- | --- |
| 0x13 | incorrectMessageLengthOrInvalidFormat | 데이터 길이/형식 오류 |
| 0x22 | conditionsNotCorrect | 조건 불만족 |
| 0x31 | requestOutOfRange | 쓰기 불가 DID 또는 데이터 범위 초과 |
| 0x33 | securityAccessDenied | SecurityAccess 필요 |
| 0x72 | generalProgrammingFailure | ECU 쓰기 실패 |

## **15.6****실무 로그 예시**

[요청]  2E F1 90 [VIN 17바이트]        ; VIN 쓰기

[응답]  6E F1 90                       ; 쓰기 성공

## **16. SID 0x2F - InputOutputControlByIdentifier**

**16.1****서비스 개요 및 용도**

- ECU의 입력/출력을 진단기가 제어하는 서비스
- 액추에이터 강제 동작, 센서 값 강제 설정 가능

용도

- 액추에이터 동작 테스트 (라이트, 모터, 솔레노이드)
- 센서 값 강제 입력 (시뮬레이션)
- 정비 검증 (예: 연료 펌프 강제 동작)

특징

- Extended Session 필요
- SecurityAccess 필요한 경우 많음
- 일정 시간 후 ECU가 자동 제어권 회수 (안전)

## **16.2 IOControlParameter****종류**

|  |  |  |
| --- | --- | --- |
| **값** | **이름** | **동작** |
| 0x00 | returnControlToECU | ECU에게 제어권 반환 |
| 0x01 | resetToDefault | 기본값으로 초기화 |
| 0x02 | freezeCurrentState | 현재 상태 고정 |
| 0x03 | shortTermAdjustment | 단기 조정 (진단기 직접 제어, 가장 많이 사용) |

## **16.3 ECU****제어권 자동 반환 조건**

- 진단기가 0x00 returnControlToECU 명시적 요청
- TesterPresent 누락으로 세션 종료
- ECU 리셋 발생
- 일정 시간 경과 (제조사별, 보통 10~30초)
- 차량 운행 조건 변화 (속도 증가, 시동 OFF 등)

## **16.4****안전 관련 주의사항**

위험한 액추에이터 제어

- 엔진 제어 (RPM, 분사량) → 차량 정지 후만 가능
- 브레이크 시스템 → 차량 정지 시만 가능
- 에어백 관련 → 별도 보안 절차 필요

## **16.5****발생 가능한 NRC**

|  |  |  |
| --- | --- | --- |
| **NRC** | **이름** | **발생 조건** |
| 0x13 | incorrectMessageLengthOrInvalidFormat | 메시지 형식 오류 |
| 0x22 | conditionsNotCorrect | 차량 운행 조건 불만족 |
| 0x31 | requestOutOfRange | 지원하지 않는 DID 또는 ControlState |
| 0x33 | securityAccessDenied | SecurityAccess 필요 |

## **16.6****실무 로그 예시**

[요청]  2F 12 34 03 01                 ; 헤드라이트 강제 점등 (shortTermAdjustment)

[응답]  6F 12 34 03 01                 ; 제어 성공

[요청]  2F 12 34 00                    ; 제어권 반환

[응답]  6F 12 34 00                    ; ECU 자동 제어로 복귀

## **17. SID 0x31 - RoutineControl**

**17.1****서비스 개요 및 용도**

- ECU 내부의 진단 루틴을 실행하는 서비스
- 시작/정지/결과 조회 기능 제공

용도

- 메모리 소거 (플래시 영역)
- ECU 자가 진단 실행
- 캘리브레이션 학습
- 프로그래밍 의존성 검증

특징

- Extended Session 또는 Programming Session 필요
- SecurityAccess 필요한 경우 많음
- 시간이 오래 걸리는 작업 → 0x78 Response Pending 자주 발생

## **17.2 Sub-function****종류**

|  |  |  |
| --- | --- | --- |
| **Sub-function** | **이름** | **동작** |
| 0x01 | startRoutine | 루틴 실행 시작 |
| 0x02 | stopRoutine | 루틴 실행 중지 |
| 0x03 | requestRoutineResults | 루틴 결과 조회 |

## **17.3****주요 표준 RID**

|  |  |  |
| --- | --- | --- |
| **RID** | **이름** | **용도** |
| 0xFF00 | eraseMemory | 플래시 메모리 소거 (리프로그래밍 시 필수) |
| 0xFF01 | checkProgrammingDependencies | 프로그래밍 의존성 검증 |
| 0xFF02 | eraseMirrorMemoryDTCs | Mirror Memory DTC 삭제 |

## **17.4 RID****범위별 용도**

|  |  |
| --- | --- |
| **RID****범위** | **용도** |
| 0x0000 ~ 0xDFFF | 시스템 공급사 정의 |
| 0xE200 ~ 0xE2FF | OBD 관련 |
| 0xF000 ~ 0xFEFF | 제조사 정의 |
| 0xFF00 ~ 0xFFFF | ISO 표준 정의 |

## **17.5****발생 가능한 NRC**

|  |  |  |
| --- | --- | --- |
| **NRC** | **이름** | **발생 조건** |
| 0x12 | subFunctionNotSupported | 지원하지 않는 Sub-function |
| 0x24 | requestSequenceError | 잘못된 순서 (예: stop 전 start 안 함) |
| 0x31 | requestOutOfRange | 지원하지 않는 RID |
| 0x33 | securityAccessDenied | SecurityAccess 필요 |
| 0x72 | generalProgrammingFailure | 루틴 실행 실패 |
| 0x78 | requestCorrectlyReceivedResponsePending | 처리 중 |

## **17.6****실무 로그 예시**

[요청]  31 01 FF 00                    ; 메모리 소거 시작

[응답]  7F 31 78                       ; Response Pending (시간 소요)

[응답]  71 01 FF 00 00                 ; 소거 완료

## **18. SID 0x34 - RequestDownload**

**18.1****서비스 개요 및 용도**

- ECU에 데이터를 다운로드(쓰기)하기 위한 요청 시작 서비스
- 리프로그래밍의 핵심 첫 단계

용도

- ECU 펌웨어 다운로드 시작
- 캘리브레이션 데이터 다운로드 시작

특징

- Programming Session 필수
- SecurityAccess 필수
- 응답에 maxNumberOfBlockLength 포함 (블록 크기 협상)
- 이후 0x36 → 0x37로 이어짐

## **18.2 Request****메시지 주요 파라미터**

|  |  |
| --- | --- |
| **파라미터** | **설명** |
| dataFormatIdentifier | 압축/암호화 방식 (0x00 = 압축/암호화 없음) |
| addressAndLengthFormatIdentifier | memoryAddress와 memorySize의 길이 정보 (예: 0x44 = 주소 4바이트, 크기 4바이트) |
| memoryAddress | 다운로드할 메모리 시작 주소 |
| memorySize | 다운로드 전체 크기 |

## **18.3 Response****의 maxNumberOfBlockLength**

- ECU가 한 번에 받을 수 있는 최대 블록 크기
- 진단기는 이 값 이하 크기로 0x36 TransferData 전송
- 일반적으로 0x102(258바이트), 0x402(1026바이트) 등

## **18.4 RequestUpload (0x35)****와의 차이**

| **항목** | **0x34 RequestDownload** | **0x35 RequestUpload** |
| --- | --- | --- |
| 방향 | 진단기 → ECU | ECU → 진단기 |
| 용도 | 데이터 쓰기 | 데이터 읽기 |

## **18.5****사전 조건**

1. Programming Session 진입 (10 02)
2. SecurityAccess 인증 (27 05, 27 06 등)
3. 메모리 소거 (31 01 FF 00)

## **18.6****발생 가능한 NRC**

|  |  |  |
| --- | --- | --- |
| **NRC** | **이름** | **발생 조건** |
| 0x22 | conditionsNotCorrect | 조건 불만족 |
| 0x31 | requestOutOfRange | 메모리 주소/크기 범위 오류 |
| 0x33 | securityAccessDenied | SecurityAccess 필요 |
| 0x70 | uploadDownloadNotAccepted | 다운로드 거부 |

## **18.7****실무 로그 예시**

[요청]  34 00 44 00 04 00 00 00 02 00 00   ; 시작 주소 0x00040000, 크기 128KB

[응답]  74 20 04 02                         ; 최대 블록 크기 1026바이트

## **19. SID 0x36 - TransferData**

**19.1****서비스 개요 및 용도**

- 실제 데이터를 ECU에 전송하는 서비스
- 0x34 이후 반복 호출하여 블록 단위 전송

특징

- maxNumberOfBlockLength 이하 크기로 분할 전송
- blockSequenceCounter로 순서 관리
- 0x78 Response Pending 자주 발생 (플래시 쓰기 시간)

## **19.2 blockSequenceCounter**

- 0x01부터 시작
- 매 블록마다 +1 증가
- 0xFF 다음은 0x00 (순환)
- 순서 오류 시 NRC 0x73 발생 (wrongBlockSequenceCounter)

## **19.3****블록 크기 계산**

maxNumberOfBlockLength = 0x402 (1026바이트) 예시

블록당 전송 가능 데이터 = 1026 - 1(SID) - 1(Counter) = 1024바이트

## **19.4****발생 가능한 NRC**

|  |  |  |
| --- | --- | --- |
| **NRC** | **이름** | **발생 조건** |
| 0x24 | requestSequenceError | 0x34 없이 0x36 시도 |
| 0x31 | requestOutOfRange | 데이터 크기 초과 |
| 0x71 | transferDataSuspended | 전송 일시 중지 |
| 0x72 | generalProgrammingFailure | 플래시 쓰기 실패 |
| 0x73 | wrongBlockSequenceCounter | 블록 순서 번호 오류 |
| 0x78 | requestCorrectlyReceivedResponsePending | 처리 중 |

## **19.5****실무 로그 예시**

[요청]  36 01 [1024바이트 데이터]      ; 1번 블록 전송

[응답]  76 01                          ; 블록 1 완료

## **20. SID 0x37 - RequestTransferExit**

**20.1****서비스 개요 및 용도**

- 0x34/0x35 시작된 데이터 전송을 종료하는 서비스
- 리프로그래밍 다운로드 흐름의 마지막 단계

특징

- 모든 0x36 TransferData 완료 후 호출
- 응답에 ECU의 최종 처리 결과 포함 가능 (CRC 등)
- 0x37 이후 0x36 호출 불가 (다시 0x34부터 시작 필요)

## **20.2****전체 다운로드 흐름**

[1] RequestDownload (0x34) - 다운로드 시작, 블록 크기 협상

[2] TransferData (0x36) 반복 - 블록 단위 전송

[3] RequestTransferExit (0x37) - 전송 완료 알림

[4] RoutineControl (0x31 01 FF 01) - 무결성 검증

[5] ECUReset (0x11 01) - 새 펌웨어 적용

## **20.3****발생 가능한 NRC**

|  |  |  |
| --- | --- | --- |
| **NRC** | **이름** | **발생 조건** |
| 0x24 | requestSequenceError | 0x34/0x36 없이 0x37 시도 |
| 0x31 | requestOutOfRange | 모든 데이터 전송 완료되지 않음 |
| 0x72 | generalProgrammingFailure | 종료 처리 실패 |

## **20.4****실무 로그 예시**

[요청]  37                             ; 전송 종료

[응답]  77                             ; 종료 완료

## **21. SID 0x3E - TesterPresent**

**21.1****서비스 개요 및 용도**

- 진단기가 ECU에게 자신의 존재를 알리는 Keep-alive 메시지
- 비기본 세션과 SecurityAccess 상태 유지

용도

- Extended/Programming Session 유지
- ECU의 S3 타이머 리셋

특징

- 모든 세션에서 사용 가능
- SecurityAccess 불필요
- Suppress Positive Response 적극 활용
- 가장 빈번하게 전송되는 진단 메시지

## **21.2 Sub-function**

|  |  |  |
| --- | --- | --- |
| **Sub-function** | **이름** | **동작** |
| 0x00 | zeroSubFunction | Keep-alive 신호 |
| 0x80 | zeroSubFunction + Suppress | Keep-alive + 응답 억제 (실무에서 가장 많이 사용) |

## **21.3****전송 주기**

- S3\_Server 기본값: 5000ms
- 권장 전송 주기: S3\_Server의 절반 이하 (보통 2000ms ~ 3000ms)
- 안전 마진을 두어 세션 끊김 방지

|  |  |
| --- | --- |
| **ECU S3\_Server** | **권장 진단기 전송 주기** |
| 5000ms (기본) | 2000ms ~ 3000ms |
| 10000ms | 4000ms ~ 5000ms |

## **21.4****세션 끊김 시 영향**

- SecurityAccess 인증 해제
- IOControl 제어권 자동 반환
- CommunicationControl 설정 원복
- 진행 중인 작업 중단

## **21.5****실무 로그 예시**

[요청]  3E 80                          ; TesterPresent (Suppress)

[응답]  (응답 없음, 정상)
