# 시스템 아키텍처

## 전체 데이터 흐름

```
[웹UI (FastAPI)]
      |
      | MQTT publish/subscribe
      v
[MQTT 브로커 (mosquitto)]
      |
   ┌──┴──┐
   v      v
[RC카]  [UR3]
```

## MQTT 토픽 규칙

형식: `rci/{파트}/{방향}`

| 토픽 | 발행자 | 구독자 | 설명 |
|------|--------|--------|------|
| `rci/rc-car/cmd` | 웹UI | RC카 | RC카 이동 명령 |
| `rci/rc-car/status` | RC카 | 웹UI | RC카 현재 상태 |
| `rci/ur3/cmd` | 웹UI | UR3 | UR3 동작 명령 |
| `rci/ur3/status` | UR3 | 웹UI | UR3 현재 상태 |

## 컴포넌트별 역할

- **웹UI**: 사용자 인터페이스, 명령 발행, 상태 시각화
- **RC카**: 이동 명령 수신 및 실행, 상태 발행
- **UR3**: 동작 명령 수신 및 실행, 상태 발행
- **shared**: 공통 MQTT 클라이언트 및 토픽 상수
