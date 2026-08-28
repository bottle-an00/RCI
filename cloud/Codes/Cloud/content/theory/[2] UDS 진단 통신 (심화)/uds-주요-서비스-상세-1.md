---
title: UDS 주요 서비스 상세 - 1
group: UDS 진단 통신
group_order: 2
difficulty: 심화
order: 3
---

# (3) UDS 주요 서비스 상세 - 1

**다룬 서비스 : 0x10 / 0x11 / 0x14 / 0x19 / 0x22**

## **8. SID 0x10 - DiagnosticSessionControl**

## **8.1****서비스 개요 및 용도**

서비스 정의

- ECU의 진단 세션을 시작하거나 변경하는 서비스
- UDS 진단 통신의 출발점, 거의 모든 진단 시나리오의 첫 번째 단계
- ECU의 동작 모드를 변경하여 사용 가능한 서비스 범위 결정

용도

- Default Session에서 Extended Session으로 전환하여 고급 진단 기능 활성화
- Programming Session 진입으로 리프로그래밍 준비
- 진단 작업 완료 후 Default Session으로 복귀
- ECU의 P2/P2\* 타이밍 파라미터 값 확인

특징

- 모든 세션에서 호출 가능 (세션 제약 없음)
- SecurityAccess 인증 불필요
- 응답에 ECU의 타이밍 파라미터 정보 포함

**8.2 Sub-function****종류**

표준 정의 Sub-function

|  |  |  |  |
| --- | --- | --- | --- |
| **Sub-function** | **세션 이름** | **약어** | **용도** |
| 0x01 | defaultSession | DS | 기본 운영 상태, 진단 종료 시 사용 |
| 0x02 | programmingSession | PS | ECU 리프로그래밍 전용 |
| 0x03 | extendedDiagnosticSession | EDS | 고급 진단 기능 활성화 (가장 많이 사용) |
| 0x04 | safetySystemDiagnosticSession | SSDS | 에어백, ABS 등 안전 시스템 진단 |
| 0x40~0x5F | vehicleManufacturerSpecific | - | 제조사 정의 세션 |
| 0x60~0x7E | systemSupplierSpecific | - | 시스템 공급사 정의 세션 |

Suppress Positive Response 지원

- Sub-function의 bit 7을 1로 설정 시 Positive Response 억제
- 예: 0x83 → Extended Session 요청, 응답 억제

### **8.3 Request/Response****메시지 구조**

Request 메시지

      [SID][Sub-function]

       10    XX

       XX: 세션 종류 (0x01, 0x02, 0x03, 0x04 등)

Positive Response 메시지

      [SID + 0x40][Sub-function echo][P2\_Server(2바이트)][P2\*\_Server(2바이트)]

          50                      XX                        YY YY                      ZZ ZZ

      XX: 요청한 Sub-function 그대로 반환

      YY YY: P2\_Server 최대값 (단위 1ms)

      ZZ ZZ: P2\*\_Server 최대값 (단위 10ms)

Negative Response 메시지

[0x7F][요청 SID][NRC]

      7F     10      XX

      XX: NRC 코드 (0x12, 0x13, 0x22 등)

메시지 예시

|  |  |  |
| --- | --- | --- |
| **동작** | **Request** | **Response** |
| Default Session 진입 | 10 01 | 50 01 00 32 01 F4 |
| Programming Session 진입 | 10 02 | 50 02 00 32 13 88 |
| Extended Session 진입 | 10 03 | 50 03 00 32 01 F4 |
| Extended Session 진입 (응답 억제) | 10 83 | (응답 없음) |

### **8.4****응답 데이터 분석 (P2 / P2\* 값)**

응답 데이터 해석

50 03 00 32 01 F4

      - 50 03      : Session 전환 완료 (Extended Session)

      - 00 32      : P2\_Server = 0x0032 = 50ms

      - 01 F4      : P2\*\_Server = 0x01F4 × 10ms = 500 × 10 = 5000ms

P2/P2\* 단위 차이 주의

|  |  |  |  |
| --- | --- | --- | --- |
| **파라미터** | **단위** | **16****진수** | **시간** |
| P2\_Server | 1ms | 0x0032 | 50ms |
| P2\_Server | 1ms | 0x0064 | 100ms |
| P2\*\_Server | 10ms | 0x01F4 | 5000ms (5초) |
| P2\*\_Server | 10ms | 0x0BB8 | 30000ms (30초) |

세션별 일반적인 P2/P2\* 값

|  |  |  |  |
| --- | --- | --- | --- |
| **세션** | **P2\_Server** | **P2\*\_Server** | **이유** |
| Default | 50ms | 5000ms | 일반 응답 시간 |
| Extended | 50ms | 5000ms | 일반 응답 시간 |
| Programming | 50ms | 50000ms | 플래시 작업 시간 고려 |

### **8.5****세션 전환 시 ECU 내부 동작**

Default → Extended Session 진입

ECU 내부 동작:

1. 진단 기능 확장 모드로 전환
2. 일반 주행 모드 영향 없음
3. S3 타이머 시작 (5000ms)
4. 보안 레벨은 잠금 상태 유지
5. P2/P2\* 응답에 포함하여 전송

Default → Programming Session 진입

ECU 내부 동작:

1. 부트로더 모드로 전환 (일부 ECU)
2. 일반 애플리케이션 중지
3. 플래시 소거/쓰기 준비
4. 일반 CAN 메시지 송수신 차단 가능
5. 응답 후 ECU 재시작되는 경우 있음 (제조사별)

세션 전환 시 초기화되는 항목

- SecurityAccess 인증 상태 (다시 인증 필요)
- IO 제어 상태 (0x2F 설정 원복)
- 통신 제어 상태 (0x28 설정 원복)
- 진단 데이터 캐시

세션 전환 시 유지되는 항목

- DTC 상태 및 데이터
- ECU 식별 정보 (VIN, S/W 버전 등)
- 영구 저장된 캘리브레이션 데이터

### **8.6****발생 가능한 NRC**

|  |  |  |
| --- | --- | --- |
| **NRC** | **이름** | **발생 조건** |
| 0x12 | subFunctionNotSupported | 지원하지 않는 세션 요청 |
| 0x13 | incorrectMessageLengthOrInvalidFormat | 메시지 길이 오류 |
| 0x22 | conditionsNotCorrect | 차량 조건 불만족 (시동, 차속 등) |
| 0x78 | requestCorrectlyReceivedResponsePending | 세션 전환 처리 중 |

NRC 0x22 흔한 원인

- 차속이 0이 아닌 상태에서 Programming Session 요청
- 시동이 켜진 상태에서 일부 세션 전환 요청
- 배터리 전압 부족
- 기어가 P가 아닌 상태

### **8.7****실무 로그 예시**

기본 시나리오: Extended Session 진입

      [Tester → ECU]  10 03

      [ECU → Tester]  50 03 00 32 01 F4

      해석:

      - 요청: Extended Diagnostic Session 진입

      - 응답: 세션 전환 성공

      - P2 = 50ms, P2\* = 5000ms

Programming Session 진입 (시간 소요)

      [Tester → ECU]  10 02

      [ECU → Tester]  7F 10 78           ; Response Pending

      [ECU → Tester]  7F 10 78           ; 추가 시간 필요

      [ECU → Tester]  50 02 00 32 13 88

      해석:

      - 부트로더 전환에 시간 소요

      - 최종 P2 = 50ms, P2\* = 50000ms (플래시 작업 대비)

조건 불만족 시 (차량 주행 중 Programming 요청)

      [Tester → ECU]  10 02

      [ECU → Tester]  7F 10 22

      해석:

      - conditionsNotCorrect

      - 차속이 0이 아니거나 시동 상태가 부적합

      - 차량 정지 후 P 단으로 변경하고 재시도

응답 억제 사용

      [Tester → ECU]  10 83

      [ECU → Tester]  (응답 없음)

      해석:

      - Extended Session 진입 + Suppress Positive Response

      - 정상 처리되었으나 응답 없음

      - 오류 발생 시에만 NRC 응답

## **9. SID 0x11 - ECUReset**

### **9.1****서비스 개요 및 용도**

서비스 정의

- ECU를 리셋(재시작)하는 서비스
- 다양한 종류의 리셋 방식 제공

용도

- ECU 펌웨어 업데이트 후 새 펌웨어 적용
- ECU 동작 이상 시 강제 리셋
- 설정 변경 후 적용
- 진단 작업 완료 후 정상 상태 복귀

특징

- 일반적으로 Extended Session 이상에서 사용
- SecurityAccess가 필요한 경우 있음 (제조사별)
- 리셋 후 ECU는 자동으로 Default Session으로 복귀

### **9.2 Sub-function****종류**

표준 정의 Sub-function

|  |  |  |
| --- | --- | --- |
| **Sub-function** | **리셋 종류** | **설명** |
| 0x01 | hardReset | 전원을 끄고 다시 켜는 것과 동일, 가장 완전한 리셋 |
| 0x02 | keyOffOnReset | 키 OFF → ON 시뮬레이션 |
| 0x03 | softReset | 소프트웨어 재시작, 하드웨어 초기화 없음 |
| 0x04 | enableRapidPowerShutDown | 빠른 전원 종료 활성화 |
| 0x05 | disableRapidPowerShutDown | 빠른 전원 종료 비활성화 |
| 0x40~0x5F | vehicleManufacturerSpecific | 제조사 정의 |
| 0x60~0x7E | systemSupplierSpecific | 공급사 정의 |

### **9.3 Reset****종류별 차이**

hardReset (0x01)

- 전원을 끊었다가 다시 공급하는 것과 동일한 효과
- 모든 RAM 데이터 초기화
- 하드웨어 페리페럴 완전 재초기화
- 가장 강력한 리셋이지만 시간 가장 오래 소요
- 사용 예: 펌웨어 업데이트 후 재시작

keyOffOnReset (0x02)

- 차량 키를 OFF했다가 ON하는 것과 같은 효과
- IGN 사이클 시뮬레이션
- 일부 비휘발성 데이터는 유지
- DTC의 Operation Cycle 카운터 갱신
- 사용 예: 진단 세션 종료 후 정상 복귀

softReset (0x03)

- 소프트웨어 레벨에서 재시작
- 하드웨어 페리페럴은 초기화하지 않음
- 빠른 리셋 가능
- RAM 데이터 일부 유지 가능
- 사용 예: 설정 변경 적용

enableRapidPowerShutDown (0x04)

- 차량 키 OFF 후 빠른 종료 모드 활성화
- 일반적으로 ECU는 키 OFF 후에도 일정 시간 동작 (After-run)
- 이 기능 활성화 시 After-run 시간 단축

disableRapidPowerShutDown (0x05)

- enableRapidPowerShutDown 해제
- 일반 After-run 동작으로 복귀

### **9.4 Reset****후 세션 복귀 동작**

Reset 직후 ECU 상태

- Default Session으로 자동 복귀
- 모든 SecurityAccess 인증 해제
- IO 제어 상태 원복
- 통신 제어 상태 원복
- TesterPresent 카운터 초기화

진단기 측 대응

- 리셋 응답 수신 후 일정 시간 대기 (ECU 부팅 시간)
- 필요시 다시 세션 진입 및 보안 인증 수행
- DoIP 환경에서는 TCP 연결도 재수립 필요할 수 있음

### **9.5****발생 가능한 NRC**

|  |  |  |
| --- | --- | --- |
| **NRC** | **이름** | **발생 조건** |
| 0x12 | subFunctionNotSupported | 지원하지 않는 리셋 종류 |
| 0x13 | incorrectMessageLengthOrInvalidFormat | 메시지 길이 오류 |
| 0x22 | conditionsNotCorrect | 차량 운행 조건 불만족 |
| 0x33 | securityAccessDenied | SecurityAccess 필요 |
| 0x7F | serviceNotSupportedInActiveSession | 현재 세션에서 사용 불가 |

### **9.6****실무 로그 예시**

기본 시나리오: Hard Reset

      [Tester → ECU]  10 03                ; Extended Session 진입

      [ECU → Tester]  50 03 00 32 01 F4

      [Tester → ECU]  11 01                ; Hard Reset 요청

      [ECU → Tester]  51 01                ; 리셋 시작

                                            ; (ECU 재시작, 일정 시간 후 통신 가능)

플래시 업데이트 후 리셋

      [Tester → ECU]  37                   ; 데이터 전송 종료

      [ECU → Tester]  77

      [Tester → ECU]  31 01 FF 01          ; 무결성 검증

      [ECU → Tester]  71 01 FF 01

      [Tester → ECU]  11 01                ; Hard Reset

      [ECU → Tester]  51 01                ; ECU 재시작, 새 펌웨어 적용

응답 억제 사용

      [Tester → ECU]  11 81

      [ECU → Tester]  (응답 없음)

해석:

- Hard Reset + Suppress Positive Response

- 정상 처리되었으나 응답 없음

## **10. SID 0x14 - ClearDiagnosticInformation**

### **10.1****서비스 개요 및 용도**

서비스 정의

- ECU의 DTC(Diagnostic Trouble Code) 및 관련 정보를 삭제하는 서비스
- 진단 데이터 초기화 목적

용도

- 정비 완료 후 DTC 삭제
- 검사 전 ECU 상태 초기화
- 시험/개발 단계에서 진단 데이터 리셋
- Snapshot 데이터, Extended Data 함께 삭제

특징

- DTC 그룹 단위로 삭제 가능 (개별 DTC 단위 X)
- 일반적으로 Extended Session 이상에서 사용
- 일부 DTC는 삭제 불가 (영구 DTC 등)

### **10.2 Request****메시지 구조 (Group of DTC)**

Request 메시지

      [SID][groupOfDTC(3바이트)]

       14    XX YY ZZ

      XX YY ZZ: 삭제할 DTC 그룹 코드

Positive Response 메시지

      [SID + 0x40]

          54

      응답이 매우 단순함 (Sub-function echo 없음, 데이터 없음)

### **10.3 DTC****그룹 코드**

표준 정의 그룹 코드

|  |  |
| --- | --- |
| **그룹 코드** | **의미** |
| 0xFFFFFF | 모든 DTC 그룹 삭제 (전체 삭제) |
| 0x000000~0xEFFFFF | 시스템별/그룹별 DTC |
| 0xFFFF33 | Emissions-related 시스템 |

ISO 15031-6 표준 그룹

|  |  |
| --- | --- |
| **그룹 코드** | **시스템** |
| 0x000000 | Powertrain |
| 0x400000 | Chassis |
| 0x800000 | Body |
| 0xC00000 | Network Communication |

실무에서 가장 많이 사용

- 0xFFFFFF: 전체 DTC 삭제, 가장 일반적

### **10.4 OBD****관련 DTC vs 제조사 DTC 삭제 범위**

OBD-II 관련 DTC

- 배기가스 관련 DTC (예: P0001~P0FFF)
- 법규에 따라 삭제 제한이 있을 수 있음
- 일부는 ECU 자가 진단으로만 클리어 가능

제조사 정의 DTC

- 0x14 서비스로 삭제 가능
- 차종/ECU별 자체 정의 DTC

삭제되지 않는 DTC

- Permanent DTC (영구 DTC): OBD-II 법규상 ECU가 자체 판단으로만 삭제
- 일부 안전 관련 DTC: 별도 조건 만족 시에만 삭제 가능

### **10.5****발생 가능한 NRC**

|  |  |  |
| --- | --- | --- |
| **NRC** | **이름** | **발생 조건** |
| 0x13 | incorrectMessageLengthOrInvalidFormat | 메시지 길이 오류 (3바이트 필수) |
| 0x22 | conditionsNotCorrect | 시동 켜진 상태 등 |
| 0x31 | requestOutOfRange | 지원하지 않는 DTC 그룹 |
| 0x33 | securityAccessDenied | SecurityAccess 필요 (제조사별) |
| 0x72 | generalProgrammingFailure | DTC 삭제 실패 |
| 0x7F | serviceNotSupportedInActiveSession | 현재 세션에서 불가 |

### **10.6****실무 로그 예시**

기본 시나리오: 전체 DTC 삭제

      [Tester → ECU]  10 03                ; Extended Session 진입

      [ECU → Tester]  50 03 00 32 01 F4

      [Tester → ECU]  14 FF FF FF          ; 모든 DTC 삭제

      [ECU → Tester]  54                   ; 삭제 완료

특정 그룹만 삭제 (Powertrain DTC)

      [Tester → ECU]  14 00 00 00          ; Powertrain DTC 삭제

      [ECU → Tester]  54

조건 불만족 시

      [Tester → ECU]  14 FF FF FF

      [ECU → Tester]  7F 14 22             ; conditionsNotCorrect

      해석:

      - 시동 ON 상태에서 일부 DTC 삭제 불가

      - 시동 OFF 후 재시도

## **11. SID 0x19 - ReadDTCInformation**

### **11.1****서비스 개요 및 용도**

서비스 정의

- DTC 관련 정보를 다양한 방식으로 읽는 서비스
- UDS에서 Sub-function이 가장 다양한 서비스 중 하나 (20개 이상)

용도

- 현재 발생한 DTC 목록 조회
- DTC 발생 당시의 환경 데이터(Snapshot) 조회
- DTC 발생 빈도, 통계 정보 조회
- ECU가 지원하는 DTC 목록 조회

특징

- Default Session에서도 일부 Sub-function 사용 가능
- SecurityAccess 불필요 (대부분)
- 멀티프레임 응답 빈번 (DTC 개수 많을 때)

### **11.2****주요 Sub-function 상세**

자주 사용되는 Sub-function

|  |  |  |
| --- | --- | --- |
| **Sub-function** | **이름** | **용도** |
| 0x01 | reportNumberOfDTCByStatusMask | 상태 조건에 해당하는 DTC 개수 조회 |
| 0x02 | reportDTCByStatusMask | 상태 조건에 해당하는 DTC 목록 조회 (가장 많이 사용) |
| 0x03 | reportDTCSnapshotIdentification | Snapshot이 있는 DTC 식별 |
| 0x04 | reportDTCSnapshotRecordByDTCNumber | 특정 DTC의 Snapshot 데이터 |
| 0x06 | reportDTCExtDataRecordByDTCNumber | 특정 DTC의 Extended Data |
| 0x0A | reportSupportedDTC | ECU가 지원하는 모든 DTC |
| 0x14 | reportDTCFaultDetectionCounter | DTC 검출 카운터 |
| 0x15 | reportDTCWithPermanentStatus | 영구 DTC 조회 |

0x02 reportDTCByStatusMask 메시지 구조

Request:

      [SID][Sub-function][DTCStatusMask]

       19          02                  XX

       XX: 상태 마스크 (1바이트, 비트 조합)

Response:

      [SID + 0x40][Sub-function][DTCStatusAvailabilityMask][DTC 1(3바이트)][Status 1(1바이트)]...

          59                 02                          YY                                AA BB CC          ZZ

### **11.3 DTC Status Mask****비트 해석**

DTC Status (1바이트) 비트 정의

|  |  |  |
| --- | --- | --- |
| **비트** | **이름** | **의미** |
| bit 0 | testFailed | 현재 테스트 실패 |
| bit 1 | testFailedThisOperationCycle | 이번 동작 사이클에서 실패 |
| bit 2 | pendingDTC | Pending DTC (확정 전) |
| bit 3 | confirmedDTC | Confirmed DTC (확정) |
| bit 4 | testNotCompletedSinceLastClear | 마지막 클리어 후 테스트 미완료 |
| bit 5 | testFailedSinceLastClear | 마지막 클리어 후 실패한 적 있음 |
| bit 6 | testNotCompletedThisOperationCycle | 이번 사이클에서 테스트 미완료 |
| bit 7 | warningIndicatorRequested | 경고등 점등 요청 |

상태 마스크 예시

|  |  |
| --- | --- |
| **마스크 값** | **의미** |
| 0xFF | 모든 DTC (어떤 상태든) |
| 0x08 | Confirmed DTC만 (bit 3 활성) |
| 0x04 | Pending DTC만 (bit 2 활성) |
| 0x09 | Confirmed + testFailed |

Status 해석 예시

      DTC Status = 0x2F (이진수: 0010 1111)

      - bit 0 (testFailed): 1 → 현재 실패

      - bit 1 (testFailedThisOpCycle): 1 → 이번 사이클 실패

      - bit 2 (pendingDTC): 1 → Pending

      - bit 3 (confirmedDTC): 1 → Confirmed

      - bit 5 (testFailedSinceLastClear): 1 → 클리어 후 실패한 적 있음

      - 나머지: 0

      → 활성화된 Confirmed DTC로 현재도 발생 중

### **11.4 DTC****코드 구조 (3바이트)**

DTC 코드 형식

      [1바이트][1바이트][1바이트]

        XX        YY         ZZ

      상위 2비트로 시스템 분류

|  |  |  |
| --- | --- | --- |
| **상위 2비트** | **시스템** | **코드 접두어** |
| 00 | Powertrain | P |
| 01 | Chassis | C |
| 10 | Body | B |
| 11 | Network | U |

DTC 코드 변환 예시

  HEX: P0301

      이진: 00 00 0011 0000 0001

      - 상위 2비트 00 → P (Powertrain)

      - 나머지: 0301

      - 결과: P0301 (3번 실린더 미스파이어)

   HEX: B1234

      - 상위 2비트 10 → B (Body)

      - 나머지: 1234

      - 결과: B1234

   HEX 3바이트: 03 01 00

      - 첫 바이트 03 = 00000011 → 상위 2비트 00 → P

      - 코드: P0301

      - 마지막 바이트 00은 추가 정보 (제조사 정의)

### **11.5 Snapshot/Extended Data****개념**

Snapshot Data

- DTC 발생 당시의 차량 상태 캡처
- 엔진 RPM, 차속, 온도, 연료량 등 환경 정보
- DTC 원인 분석에 매우 유용
- Sub-function 0x04로 조회

Extended Data

- DTC의 추가 메타 정보
- 발생 횟수 카운터
- 첫 발생 시각, 마지막 발생 시각
- 발생 사이클 정보
- Sub-function 0x06으로 조회

**11.6****실무 로그 예시**

기본 시나리오: Confirmed DTC 조회

      [Tester → ECU]  19 02 08             ; Confirmed DTC만 조회

      [ECU → Tester]  59 02 FF

                P0301코드 2F

                P0420코드 2F

      해석:

      - 2개의 Confirmed DTC 발생

      - DTC 1: P0301, Status 0x2F (Confirmed + 현재 실패)

      - DTC 2: P0420, Status 0x2F

모든 DTC 조회

      [Tester → ECU]  19 02 FF             ; 모든 상태 DTC 조회

      [ECU → Tester]  59 02 FF

                      [DTC 1][Status 1]

                      [DTC 2][Status 2]

                      [DTC 3][Status 3]

DTC 개수만 조회

      [Tester → ECU]  19 01 08

      [ECU → Tester]  59 01 FF 01 00 03

해석:

      - 0x01: 형식 정보

      - 0xFF: Status Availability Mask

      - 0x01 00 03: DTC 개수 = 3개

Snapshot 조회

      [Tester → ECU]  19 04 P0301 FF       ; P0301의 모든 Snapshot

      [ECU → Tester]  59 04 [Snapshot 데이터]

                             RPM 1800

                             차속 60km/h

                             엔진온도 90도

                             ...

DTC 없음

      [Tester → ECU]  19 02 FF

      [ECU → Tester]  59 02 FF             ; DTC 데이터 없음

## **12. SID 0x22 - ReadDataByIdentifier**

### **12.1****서비스 개요 및 용도**

서비스 정의

- DID(Data Identifier)로 식별되는 데이터를 ECU로부터 읽는 서비스
- UDS에서 가장 빈번하게 사용되는 서비스 중 하나

용도

- ECU 식별 정보 조회 (VIN, 펌웨어 버전, 하드웨어 번호 등)
- 센서 값 읽기 (RPM, 차속, 온도 등)
- 진단 데이터 조회
- 캘리브레이션 값 확인

특징

- DID 하나로 다양한 데이터 접근
- 일부 DID는 SecurityAccess 필요
- 멀티 DID 동시 요청 가능
- 응답 데이터 길이는 DID에 따라 가변

### **12.2 DID (Data Identifier)****개념**

DID 정의

- 2바이트(16비트) 식별자로 ECU의 데이터를 가리킴
- 0x0000 ~ 0xFFFF 범위
- 표준 DID와 제조사 정의 DID로 구분

DID 범위별 용도

|  |  |
| --- | --- |
| **DID****범위** | **용도** |
| 0x0000 ~ 0xEFFF | 시스템 공급사 정의 |
| 0xF000 ~ 0xF00F | 네트워크 설정 |
| 0xF010 ~ 0xF0FF | 시스템 공급사 정의 |
| 0xF100 ~ 0xF17F | ID 식별 (Identification) |
| 0xF180 ~ 0xF1FF | UDS 표준 식별 정보 |
| 0xF200 ~ 0xF2FF | Periodic 데이터 |
| 0xF300 ~ 0xF3FF | Dynamic 데이터 |
| 0xF400 ~ 0xF4FF | OBD 관련 |
| 0xF500 ~ 0xF5FF | OBD 관련 |
| 0xF600 ~ 0xF6FF | OBD 관련 |
| 0xF700 ~ 0xF7FF | OBD 관련 |
| 0xF800 ~ 0xF8FF | OBD 관련 |
| 0xFA00 ~ 0xFA0F | 시스템 공급사 식별 |
| 0xFA10 ~ 0xFAFF | 시스템 공급사 정의 |
| 0xFD00 ~ 0xFEFF | 제조사 정의 |
| 0xFF00 ~ 0xFFFF | 예약 |

### **12.3****주요 표준 DID 정리**

ECU 식별 정보 DID (0xF180 ~ 0xF1FF)

|  |  |  |
| --- | --- | --- |
| **DID** | **이름** | **설명** |
| 0xF180 | BootSoftwareIdentification | 부트로더 소프트웨어 버전 |
| 0xF181 | ApplicationSoftwareIdentification | 애플리케이션 소프트웨어 버전 |
| 0xF182 | ApplicationDataIdentification | 애플리케이션 데이터 버전 |
| 0xF183 | BootSoftwareFingerprint | 부트로더 핑거프린트 |
| 0xF184 | ApplicationSoftwareFingerprint | 애플리케이션 핑거프린트 |
| 0xF185 | ApplicationDataFingerprint | 데이터 핑거프린트 |
| 0xF186 | ActiveDiagnosticSessionDataIdentifier | 현재 활성 진단 세션 |
| 0xF187 | VehicleManufacturerSparePartNumber | 제조사 부품 번호 |
| 0xF188 | VehicleManufacturerECUSoftwareNumber | 제조사 ECU 소프트웨어 번호 |
| 0xF189 | VehicleManufacturerECUSoftwareVersionNumber | 제조사 ECU 소프트웨어 버전 |
| 0xF18A | SystemSupplierIdentifier | 시스템 공급사 ID |
| 0xF18B | ECUManufacturingDate | ECU 제조일 |
| 0xF18C | ECUSerialNumber | ECU 시리얼 번호 |
| 0xF18D | SupportedFunctionalUnits | 지원 기능 단위 |
| 0xF190 | VIN (Vehicle Identification Number) | 차량 식별 번호 (17자리) |
| 0xF191 | VehicleManufacturerECUHardwareNumber | 제조사 ECU 하드웨어 번호 |
| 0xF192 | SystemSupplierECUHardwareNumber | 공급사 ECU 하드웨어 번호 |
| 0xF193 | SystemSupplierECUHardwareVersionNumber | 공급사 ECU 하드웨어 버전 |
| 0xF194 | SystemSupplierECUSoftwareNumber | 공급사 ECU 소프트웨어 번호 |
| 0xF195 | SystemSupplierECUSoftwareVersionNumber | 공급사 ECU 소프트웨어 버전 |
| 0xF196 | ExhaustRegulationOrTypeApprovalNumber | 배출가스 규제 인증 번호 |
| 0xF197 | SystemNameOrEngineType | 시스템 이름 또는 엔진 타입 |
| 0xF198 | RepairShopCodeOrTesterSerialNumber | 정비소 코드 또는 진단기 시리얼 |
| 0xF199 | ProgrammingDate | 프로그래밍 날짜 |
| 0xF19D | ECUInstallationDate | ECU 설치일 |

자주 사용되는 DID

- 0xF190 VIN: 가장 많이 조회되는 DID
- 0xF188 / 0xF189: 펌웨어 버전 확인
- 0xF186: 현재 세션 확인 (1바이트 응답)

### **12.4****동시 다중 DID 요청**

여러 DID를 한 번에 요청 가능

Request:

      [SID][DID 1(2바이트)][DID 2(2바이트)][DID 3(2바이트)]...

       22    XX XX              YY YY               ZZ ZZ

Response:

      [SID + 0x40][DID 1][Data 1][DID 2][Data 2]...

          62            XX XX  ...          YY YY  ...

예시

      [Tester → ECU]  22 F1 90 F1 88

      [ECU → Tester]  62

                      F1 90 [VIN 17바이트]

                      F1 88 [S/W 번호 데이터]

장점

- 통신 횟수 감소
- 진단 시간 단축

단점

- 멀티프레임 응답 필요 (데이터 양 증가)
- 일부 ECU에서 지원하지 않음

### **12.5 DID****데이터 길이 가변성**

DID마다 응답 데이터 길이가 다름

|  |  |  |
| --- | --- | --- |
| **DID** | **데이터 길이** | **예시** |
| 0xF190 (VIN) | 17바이트 | "KMHXX000000000001" |
| 0xF186 (Active Session) | 1바이트 | 0x03 (Extended) |
| 0xF188 (S/W 번호) | 가변 | 제조사별 |
| 0xF180 (Boot S/W ID) | 가변 | ASCII 문자열 |

DID 데이터 길이는 ODX 파일에 정의

- 진단기는 ODX 파일에서 각 DID의 정확한 길이와 형식 파악
- 응답 데이터 파싱 시 ODX 정보 필수

### **12.6****발생 가능한 NRC**

|  |  |  |
| --- | --- | --- |
| **NRC** | **이름** | **발생 조건** |
| 0x13 | incorrectMessageLengthOrInvalidFormat | DID 형식 오류 |
| 0x14 | responseTooLong | 응답 데이터가 너무 큼 |
| 0x22 | conditionsNotCorrect | 조건 불만족 |
| 0x31 | requestOutOfRange | 지원하지 않는 DID |
| 0x33 | securityAccessDenied | 보안 인증 필요 |
| 0x7F | serviceNotSupportedInActiveSession | 현재 세션에서 불가 |

### **12.7****실무 로그 예시**

VIN 조회

      [Tester → ECU]  22 F1 90

      [ECU → Tester]  62 F1 90 4B 4D 48 58 58 30 30 30 30 30 30 30 30 30 30 30 31

      해석:

      - DID: F1 90 (VIN)

      - 데이터: ASCII로 "KMHXX000000000001"

소프트웨어 버전 조회

      [Tester → ECU]  22 F1 88

      [ECU → Tester]  62 F1 88 56 31 2E 32 2E 33

      해석:

      - DID: F1 88 (S/W 번호)

      - 데이터: ASCII로 "V1.2.3"

현재 세션 확인

      [Tester → ECU]  22 F1 86

      [ECU → Tester]  62 F1 86 03

      해석:

      - 현재 Extended Diagnostic Session (0x03) 활성

다중 DID 요청

      [Tester → ECU]  22 F1 90 F1 88 F1 86

      [ECU → Tester]  62

                      F1 90 [VIN 17바이트]

                      F1 88 [S/W 번호]

                      F1 86 03

지원하지 않는 DID 요청

      [Tester → ECU]  22 12 34

      [ECU → Tester]  7F 22 31

      해석:

      - DID 0x1234는 ECU가 지원하지 않음

      - requestOutOfRange

보안 인증 미수행

      [Tester → ECU]  22 F1 9D

      [ECU → Tester]  7F 22 33

      해석:

      - ECUInstallationDate는 보안 DID

      - SecurityAccess 필요
