---
title: [부록] CAN 데이터베이스(DBC)와 CANdb Editor
group: CAN 통신
group_order: 1
difficulty: 심화
order: 8
---

# (8) [부록] CAN 데이터베이스(DBC)와 CANdb++ Editor

## **8. CAN 데이터베이스(DBC)와 CANdb++ Editor**

### **8.1 메시지와 신호(Signal)**

- **CAN 프로토콜 자체는 데이터의 의미를 정의하지 않는다.**
- **메시지(Message): Identifier + DLC + Data Field(최대 8byte, CAN FD는 최대 64byte)로 구성되는 통신 객체**
- **신호(Signal): 메시지의 Data Field 내 특정 구간(1~64bit)이 나타내는 실제 의미 있는 정보**
  - **신호 설명 요소: 이름(symbolic name), 단위(unit), 변환식(conversion formula), 심볼릭 값(symbolic value)**
  - **물리값 변환식: `물리값 = Raw값 × Factor + Offset`**

### **8.2 Intel vs Motorola 포맷 (Byte Order)**

| **포맷** | **방향** |
| --- | --- |
| **Motorola** | **MSB(최상위 바이트)가 앞쪽(낮은 byte 번호)** |
| **Intel** | **LSB(최하위 바이트)가 앞쪽(낮은 byte 번호)** |

- **바이트 내부의 비트 유의성(significance)은 두 포맷에서 동일함 (bit7=msb, bit0=lsb)**
- **신호 길이가 8bit 이하인 경우 포맷 차이는 의미 없음**

### **8.3 CAN Database(DBC)의 역할**

- **모든 통신 정의(메시지, 신호, 노드, 관계)를 담는 데이터베이스로, Vector 도구 전반(CANoe, CANalyzer, CANape 등)에서 공통으로 사용**
- **트레이스 창(Trace Window)에서 원시 hex 값을 → 메시지명/신호명/물리값/심볼릭값으로 해석해서 보여주는 역할**
- **활용 분야: 분석(Analysis), 시뮬레이션(Simulation), 테스트(Test), 임베디드 SW(코드 생성)**

### **8.4 CANdb++ Editor**

- **CAN 네트워크 서술에 사용되는 dbc 파일을 다루는 Vector 전용 편집기**
- **주요 기능: 새 데이터베이스 생성, 기존 DB 열람/편집, Value Table을 이용한 신호 상세 설명, Attribute를 이용한 고급 설정**
- **CANalyzer/CANoe/CANape에 기본 포함되어 있으며 해당 툴 내에서 바로 실행 가능**

**데이터베이스 생성 순서**

1. **데이터베이스 생성 (템플릿 선택)**
2. **신호(Signal) 정의 (이름, bit 수, Intel/Motorola, factor & offset, 단위)**
3. **네트워크 노드(Node) 정의 (이름)**
4. **메시지(Message) 정의 (이름, DLC, Standard/Extended, ID, 송신 노드)**
5. **메시지에 신호 할당**
6. **신호 위치(Start bit, Layout) 확인/수정**
7. **수신 신호 매핑(Mapped Rx Signals)**
8. **데이터베이스 저장**

**Value Table: 특정 신호 값에 심볼릭(문자) 설명을 부여 (예: 기어 표시 0x0=Idle, 0x1=Gear\_1, ...)**

**Attribute: 메시지/신호/노드의 상세 정보(예: 송신 주기 GenMsgCycleTime, 송신 방식 GenSigSendType 등)를 정의. CANoe에서 Interaction Layer DLL로 노드를 시뮬레이션할 때 이 속성값을 참조한다.**
