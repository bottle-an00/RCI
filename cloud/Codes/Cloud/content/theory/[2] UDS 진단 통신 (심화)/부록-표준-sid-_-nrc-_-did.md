---
title: [부록] 표준 SID _ NRC _ DID
group: UDS 진단 통신
group_order: 2
difficulty: 심화
order: 6
---

# (6) [부록] 표준 SID / NRC / DID

**25. 부록**

**25.1 UDS****서비스 SID 전체 목록표**

ISO 14229-1 표준 정의 SID 전체

|  |  |  |
| --- | --- | --- |
| **SID** | **서비스 이름** | **카테고리** |
| 0x10 | DiagnosticSessionControl | Diagnostic and Communication Management |
| 0x11 | ECUReset | Diagnostic and Communication Management |
| 0x14 | ClearDiagnosticInformation | Stored Data Transmission |
| 0x19 | ReadDTCInformation | Stored Data Transmission |
| 0x22 | ReadDataByIdentifier | Data Transmission |
| 0x23 | ReadMemoryByAddress | Data Transmission |
| 0x24 | ReadScalingDataByIdentifier | Data Transmission |
| 0x27 | SecurityAccess | Diagnostic and Communication Management |
| 0x28 | CommunicationControl | Diagnostic and Communication Management |
| 0x29 | Authentication | Diagnostic and Communication Management |
| 0x2A | ReadDataByPeriodicIdentifier | Data Transmission |
| 0x2C | DynamicallyDefineDataIdentifier | Data Transmission |
| 0x2E | WriteDataByIdentifier | Data Transmission |
| 0x2F | InputOutputControlByIdentifier | InputOutput Control |
| 0x31 | RoutineControl | Routine |
| 0x34 | RequestDownload | Upload Download |
| 0x35 | RequestUpload | Upload Download |
| 0x36 | TransferData | Upload Download |
| 0x37 | RequestTransferExit | Upload Download |
| 0x38 | RequestFileTransfer | Upload Download |
| 0x3D | WriteMemoryByAddress | Data Transmission |
| 0x3E | TesterPresent | Diagnostic and Communication Management |
| 0x83 | AccessTimingParameter | Diagnostic and Communication Management |
| 0x84 | SecuredDataTransmission | Diagnostic and Communication Management |
| 0x85 | ControlDTCSetting | Diagnostic and Communication Management |
| 0x86 | ResponseOnEvent | Diagnostic and Communication Management |
| 0x87 | LinkControl | Diagnostic and Communication Management |
| 0x7F | NegativeResponse | (응답 전용) |

## **25.2 NRC****전체 목록표**

ISO 14229-1 표준 정의 NRC 전체

기본 거부 NRC

| **NRC** | **이름** | **의미** |
| --- | --- | --- |
| 0x00 | positiveResponse | (사용 안 함) |
| 0x10 | generalReject | 일반적 거부 |
| 0x11 | serviceNotSupported | 서비스 미지원 |
| 0x12 | subFunctionNotSupported | Sub-function 미지원 |
| 0x13 | incorrectMessageLengthOrInvalidFormat | 메시지 길이/형식 오류 |
| 0x14 | responseTooLong | 응답 데이터가 너무 큼 |

조건/상태 관련 NRC

| **NRC** | **이름** | **의미** |
| --- | --- | --- |
| 0x21 | busyRepeatRequest | ECU 바쁨, 재시도 필요 |
| 0x22 | conditionsNotCorrect | 차량/ECU 조건 불만족 |
| 0x24 | requestSequenceError | 요청 순서 오류 |
| 0x25 | noResponseFromSubnetComponent | 서브넷 ECU 응답 없음 |
| 0x26 | failurePreventsExecutionOfRequestedAction | 다른 오류로 실행 불가 |

데이터/범위 관련 NRC

| **NRC** | **이름** | **의미** |
| --- | --- | --- |
| 0x31 | requestOutOfRange | 요청 파라미터 범위 초과 |

보안 관련 NRC

| **NRC** | **이름** | **의미** |
| --- | --- | --- |
| 0x33 | securityAccessDenied | SecurityAccess 인증 안 됨 |
| 0x34 | authenticationRequired | 인증 필요 |
| 0x35 | invalidKey | Key 값 오류 |
| 0x36 | exceedNumberOfAttempts | 시도 횟수 초과 |
| 0x37 | requiredTimeDelayNotExpired | 대기 시간 미경과 |
| 0x38~0x4F | secureDataTransmissionRequired 등 | Secured Data 관련 |
| 0x50 | secureDataTransmissionRequired | 보안 전송 필요 |
| 0x51 | secureDataTransmissionNotAllowed | 보안 전송 허용 안 됨 |
| 0x52 | secureDataVerificationFailed | 보안 데이터 검증 실패 |

업로드/다운로드 관련 NRC

| **NRC** | **이름** | **의미** |
| --- | --- | --- |
| 0x70 | uploadDownloadNotAccepted | 업/다운로드 거부 |
| 0x71 | transferDataSuspended | 데이터 전송 일시 중지 |
| 0x72 | generalProgrammingFailure | 일반적 프로그래밍 실패 |
| 0x73 | wrongBlockSequenceCounter | 블록 순서 번호 오류 |

응답 보류 NRC

| **NRC** | **이름** | **의미** |
| --- | --- | --- |
| 0x78 | requestCorrectlyReceivedResponsePending | 요청 수신, 응답 처리 중 |

세션 관련 NRC

| **NRC** | **이름** | **의미** |
| --- | --- | --- |
| 0x7E | subFunctionNotSupportedInActiveSession | 현재 세션에서 Sub-function 미지원 |
| 0x7F | serviceNotSupportedInActiveSession | 현재 세션에서 서비스 미지원 |

차량 운행 관련 NRC

| **NRC** | **이름** | **의미** |
| --- | --- | --- |
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

## **25.3****표준 DID 전체 목록표**

ECU 식별 정보 DID (0xF180 ~ 0xF1FF)

| **DID** | **이름** | **데이터** |
| --- | --- | --- |
| 0xF180 | BootSoftwareIdentification | 부트로더 S/W 버전 |
| 0xF181 | ApplicationSoftwareIdentification | 애플리케이션 S/W 버전 |
| 0xF182 | ApplicationDataIdentification | 애플리케이션 데이터 버전 |
| 0xF183 | BootSoftwareFingerprint | 부트로더 핑거프린트 |
| 0xF184 | ApplicationSoftwareFingerprint | 애플리케이션 핑거프린트 |
| 0xF185 | ApplicationDataFingerprint | 데이터 핑거프린트 |
| 0xF186 | ActiveDiagnosticSessionDataIdentifier | 현재 활성 진단 세션 (1바이트) |
| 0xF187 | VehicleManufacturerSparePartNumber | 제조사 부품 번호 |
| 0xF188 | VehicleManufacturerECUSoftwareNumber | 제조사 ECU S/W 번호 |
| 0xF189 | VehicleManufacturerECUSoftwareVersionNumber | 제조사 ECU S/W 버전 |
| 0xF18A | SystemSupplierIdentifier | 시스템 공급사 ID |
| 0xF18B | ECUManufacturingDate | ECU 제조일 |
| 0xF18C | ECUSerialNumber | ECU 시리얼 번호 |
| 0xF18D | SupportedFunctionalUnits | 지원 기능 단위 |
| 0xF18E | VehicleManufacturerKitAssemblyPartNumber | 제조사 키트 어셈블리 번호 |
| 0xF18F | RegulationXSoftwareIdentificationNumbers | 규제 S/W 번호 |
| 0xF190 | VIN | 차량 식별 번호 (17바이트 ASCII) |
| 0xF191 | VehicleManufacturerECUHardwareNumber | 제조사 ECU H/W 번호 |
| 0xF192 | SystemSupplierECUHardwareNumber | 공급사 ECU H/W 번호 |
| 0xF193 | SystemSupplierECUHardwareVersionNumber | 공급사 ECU H/W 버전 |
| 0xF194 | SystemSupplierECUSoftwareNumber | 공급사 ECU S/W 번호 |
| 0xF195 | SystemSupplierECUSoftwareVersionNumber | 공급사 ECU S/W 버전 |
| 0xF196 | ExhaustRegulationOrTypeApprovalNumber | 배출가스 규제 인증 번호 |
| 0xF197 | SystemNameOrEngineType | 시스템 이름 또는 엔진 타입 |
| 0xF198 | RepairShopCodeOrTesterSerialNumber | 정비소 코드 또는 진단기 시리얼 |
| 0xF199 | ProgrammingDate | 프로그래밍 날짜 |
| 0xF19A | CalibrationRepairShopCodeOrCalibrationEquipmentSerialNumber | 캘리브레이션 정비소 코드 |
| 0xF19B | CalibrationDate | 캘리브레이션 날짜 |
| 0xF19C | CalibrationEquipmentSoftwareNumber | 캘리브레이션 장비 S/W 번호 |
| 0xF19D | ECUInstallationDate | ECU 설치일 |
| 0xF19E | ODXFileDataIdentifier | ODX 파일 식별자 |
| 0xF19F | EntityDataIdentifier | 엔티티 데이터 식별자 |

DID 범위별 전체 분류

| **DID****범위** | **용도** |
| --- | --- |
| 0x0000 ~ 0x00FF | 시스템 공급사 정의 |
| 0x0100 ~ 0xEFFF | 시스템 공급사 정의 |
| 0xF000 ~ 0xF00F | 네트워크 설정 데이터 |
| 0xF010 ~ 0xF0FF | 시스템 공급사 정의 |
| 0xF100 ~ 0xF17F | ID 식별 |
| 0xF180 ~ 0xF1FF | UDS 표준 식별 정보 |
| 0xF200 ~ 0xF2FF | Periodic 데이터 |
| 0xF300 ~ 0xF3FF | Dynamic 데이터 |
| 0xF400 ~ 0xF5FF | OBD 관련 |
| 0xF600 ~ 0xF6FF | OBD 모니터링 데이터 |
| 0xF700 ~ 0xF7FF | OBD InfoType |
| 0xF800 ~ 0xF8FF | OBD 정보 |
| 0xF900 ~ 0xF9FF | 안전 시스템 데이터 |
| 0xFA00 ~ 0xFA0F | 시스템 공급사 식별 |
| 0xFA10 ~ 0xFAFF | 시스템 공급사 정의 |
| 0xFB00 ~ 0xFCFF | 제조사 정의 |
| 0xFD00 ~ 0xFEFF | 제조사 정의 |
| 0xFF00 ~ 0xFFFF | 예약 |

## **25.4****표준 RID 전체 목록표**

ISO 표준 정의 RID (0xFF00 ~ 0xFFFF)

| **RID** | **이름** | **용도** |
| --- | --- | --- |
| 0xFF00 | eraseMemory | 플래시 메모리 소거 |
| 0xFF01 | checkProgrammingDependencies | 프로그래밍 의존성 검증 |
| 0xFF02 | eraseMirrorMemoryDTCs | Mirror Memory DTC 삭제 |

RID 범위별 전체 분류

| **RID****범위** | **용도** |
| --- | --- |
| 0x0000 ~ 0x00FF | 시스템 공급사 정의 |
| 0x0100 ~ 0x01FF | 진단 시퀀스 정의 |
| 0x0200 ~ 0xDFFF | 시스템 공급사 정의 |
| 0xE000 ~ 0xE1FF | 시스템 공급사 정의 |
| 0xE200 ~ 0xE2FF | OBD 관련 |
| 0xE300 ~ 0xEFFF | 예약 |
| 0xF000 ~ 0xFEFF | 제조사 정의 |
| 0xFF00 ~ 0xFFFF | ISO 표준 정의 |

## **25.5****자주 사용하는 UDS 메시지 패턴**

세션 진입 패턴

      [요청]  10 03                    ; Extended Session

      [응답]  50 03 00 32 01 F4

      [요청]  10 02                    ; Programming Session

      [응답]  50 02 00 32 13 88

SecurityAccess 패턴 (Level 1)

      [요청]  27 01                    ; Seed 요청

      [응답]  67 01 [Seed 4바이트]

      [요청]  27 02 [Key 4바이트]      ; Key 전송

      [응답]  67 02                    ; 인증 성공

DTC 조회 패턴

      [요청]  19 02 08                 ; Confirmed DTC만

      [응답]  59 02 FF [DTC 1][Status 1][DTC 2][Status 2]...

      [요청]  19 02 FF                 ; 모든 DTC

      [응답]  59 02 FF [DTC list]

      ECU 정보 조회 패턴

      [요청]  22 F1 90                 ; VIN

      [응답]  62 F1 90 [VIN 17바이트]

      [요청]  22 F1 88                 ; S/W 번호

      [응답]  62 F1 88 [데이터]

DTC 삭제 패턴

      [요청]  14 FF FF FF              ; 모든 DTC 삭제

      [응답]  54

TesterPresent 패턴

      [요청]  3E 80                    ; Keep-alive (Suppress)

      [응답]  (없음)

ECU 리셋 패턴

      [요청]  11 01                    ; Hard Reset

      [응답]  51 01

리프로그래밍 핵심 패턴

      [요청]  10 02                    ; Programming Session

      [요청]  27 05 / 27 06            ; Programming SecurityAccess

      [요청]  31 01 FF 00              ; 메모리 소거

      [요청]  34 00 44 [주소][크기]    ; RequestDownload

      [요청]  36 01 [data]             ; TransferData (반복)

      [요청]  37                       ; RequestTransferExit

      [요청]  31 01 FF 01              ; 무결성 검증

      [요청]  11 01                    ; ECU Reset
