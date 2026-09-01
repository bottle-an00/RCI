---
title: CAN 통신 소개
group: CAN 통신
group_order: 1
difficulty: 심화
order: 2
---

# (2) CAN 통신 소개

**2. CAN 통신 소개**

**2.1 CAN이란?**

![](assets/can-통신-소개/img01.png)

- **CAN(Controller Area Network): ECU들이 서로 통신하기 위해 설계된 표준 통신 규격**

## **2.2 CAN 노드 구성 (노드 = ECU)**

![](assets/can-통신-소개/img02.png)

| **구성요소** | **역할** |
| --- | --- |
| **MCU (마이크로컨트롤러)** | **ECU의 두뇌. 수신 CAN 신호를 해석하고 어떤 신호를 전송할지 결정 (Application software)** |
| **CAN 컨트롤러** | **CAN 프로토콜이 요구하는 통신 기능 수행. 송신 메시지 완성, 수신 메시지 체크, 버스 접근/비트타이밍 제어** |
| **CAN 트랜시버** | **컨트롤러와 CAN BUS 사이 인터페이스. 송신 시 비트→전압 변환, 수신 시 전압 샘플링 후 컨트롤러로 전달** |

> **Controller vs Transceiver 역할 구분**
>
> - **Controller: CAN 버스를 통해 디지털 데이터를 송수신하기 위한 작업 수행 (Data Link Layer, MAC, 디지털 비트 영역 담당 → "Digital Domain")**
> - **Transceiver: CAN 버스에 물리적 신호(전압)를 인가하거나 읽음 (Physical Layer, PHY, 아날로그 전압 영역 담당 → "Analog Domain")**
>
> **트랜시버가 인가하는 전압 레벨은 초당 최대 100만 번까지 바뀔 수 있어 반사(reflection)가 발생할 수 있으며, 이를 억제하기 위해 버스 양 끝단에 120Ω 종단저항을 사용하는 것이 효과적인 방법이다.**

## **2.3 CAN Data 예시 (DBC 정의)**

| **ID** | **메시지 이름** | **Byte** | **신호 이름** | **단위** |
| --- | --- | --- | --- | --- |
| **0x0C8** | **Engine\_Status** | **0,1** | **Engine\_RPM** | **RPM** |
|  |  | **2,3** | **Vehicle\_Speed** | **km/h** |
|  |  | **4** | **Coolant\_Temp** | **°C** |
|  |  | **5** | **Throttle\_Position** | **%** |
| **0x1A0** | **ABS\_Status** | **0,1** | **Wheel\_Speed\_FL** | **km/h** |
|  |  | **2,3** | **Wheel\_Speed\_FR** | **km/h** |
|  |  | **4** | **ABS\_Active** | **0=비활성/1=활성** |
| **0x2B0** | **BCM\_Status** | **0** | **Door\_Lock** | **0=잠금/1=열림** |
|  |  | **1** | **Headlight** | **0=OFF/1=ON** |
|  |  | **2** | **Wiper** | **0=OFF/1=ON** |

**※ 위 데이터는 교육용 가상 예시이며 실제 차량 데이터와 다를 수 있습니다.**

> **신호 해석 예시 - 로그 데이터 변환 (PDF) 실제 로그: `CAN0 0x0C8 8 09 C4 3C 00 6E 32 00 00`**
>
> - **`Engine_RPM` = 09 C4(hex) → 0x09C4 = (9×256)+(12×16)+4 = 2304+192+4 = 2500 RPM**
> - **`Vehicle_Speed` = 3C 00 → 60 km/h**
> - **`Coolant_Temp` = 6E → 110 °C**
> - **`Throttle_Position` = 32 → 50 %**
> - **`Door_Lock` = 00 → 잠금, `Headlight` = 01 → ON**
>
> **이처럼 CAN 프로토콜 자체는 "신뢰성 있는 전송"만 보장할 뿐 데이터의 의미는 정의하지 않는다. 송신측과 수신측이 같은 의미로 해석하려면 별도의 데이터베이스(DBC, K-Matrix, 통신 매트릭스)가 필요하다. (자세한 내용은 7장 참고)**
