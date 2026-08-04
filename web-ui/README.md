# 웹UI

FastAPI 기반 웹 인터페이스. RC카·UR3에 MQTT 명령을 발행하고 상태를 수신한다.

## 준비물

- Python 3.8 이상
- MQTT 브로커 (mosquitto) 실행 중

## 설치

```bash
pip install -r requirements.txt
```

## 실행

```bash
uvicorn main:app --reload
```

브라우저에서 `http://localhost:8000` 접속.

## MQTT 토픽

| 방향 | 토픽 | 설명 |
|------|------|------|
| 발행 | `rci/rc-car/cmd` | RC카 이동 명령 |
| 발행 | `rci/ur3/cmd` | UR3 동작 명령 |
| 구독 | `rci/rc-car/status` | RC카 상태 수신 |
| 구독 | `rci/ur3/status` | UR3 상태 수신 |

## 트러블슈팅

- **서버 시작 실패**: `uvicorn`이 설치되어 있는지 확인 (`pip install uvicorn`)
- **MQTT 연결 실패**: 브로커가 실행 중인지 확인 (루트 README 참고)
