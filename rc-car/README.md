# RC카

MQTT를 통해 명령을 수신하고 RC카를 제어하는 파트.

## 준비물

- Python 3.8 이상
- MQTT 브로커 (mosquitto) 실행 중

## 설치

```bash
pip install -r requirements.txt
```

## 설정

`main.py` 상단의 설정값을 실제 환경에 맞게 수정한다.

```python
BROKER_HOST = "localhost"
BROKER_PORT = 1883
```

## 실행

```bash
python main.py
```

## MQTT 토픽

| 방향 | 토픽 | 설명 |
|------|------|------|
| 구독 | `rci/rc-car/cmd` | 이동 명령 수신 |
| 발행 | `rci/rc-car/status` | 현재 상태 발행 |

## 트러블슈팅

- **MQTT 연결 실패**: 브로커가 실행 중인지 확인 (`mosquitto` 또는 루트 README 참고)
- **명령이 수신되지 않음**: 토픽명과 브로커 주소가 웹UI와 일치하는지 확인
