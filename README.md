# RCI

RC카·UR3·웹UI를 MQTT로 연결하는 통합 제어 시스템.

## 구성

| 파트 | 경로 | 설명 |
|------|------|------|
| RC카 | `rc-car/` | Python 기반 RC카 제어 |
| UR3 | `ur3/` | Python 기반 UR3 로봇팔 제어 |
| 웹UI | `web-ui/` | FastAPI 기반 통합 대시보드 |
| 공통 | `shared/` | MQTT 클라이언트, 토픽 상수 |

## 전체 시스템 실행 방법

### 1. MQTT 브로커 설치 및 실행

```bash
# macOS
brew install mosquitto
brew services start mosquitto

# Ubuntu/Raspberry Pi
sudo apt install mosquitto mosquitto-clients
sudo systemctl start mosquitto

# Windows
# https://mosquitto.org/download/ 에서 설치 후
mosquitto
```

### 2. 각 파트 실행 (순서 권장)

터미널을 3개 열어 각각 실행한다.

```bash
# 터미널 1 — UR3
cd ur3
pip install -r requirements.txt
python scripts/read_state.py   # 연결 확인 후
python main.py

# 터미널 2 — RC카
cd rc-car
pip install -r requirements.txt
python main.py

# 터미널 3 — 웹UI
cd web-ui
pip install -r requirements.txt
uvicorn main:app --reload
```

브라우저에서 `http://localhost:8000` 접속.

### 3. 통합 테스트

모든 파트가 실행 중인 상태에서:

```bash
python integration/test_integration.py
```

## 파트별 단독 실행

각 파트는 MQTT 브로커만 있으면 독립적으로 동작한다.  
자세한 내용은 각 폴더의 `README.md`를 참고한다.

- [RC카 README](rc-car/README.md)
- [UR3 README](ur3/README.md)
- [웹UI README](web-ui/README.md)

## 아키텍처

자세한 내용은 [docs/architecture.md](docs/architecture.md) 참고.

## 브랜치 전략

```
main      # 안정된 통합 코드
└── dev   # 통합 전 개발 베이스
    ├── feat/rc-car-xxx
    ├── feat/ur3-xxx
    └── feat/web-ui-xxx
```

커밋 메시지 prefix: `[rc-car]`, `[ur3]`, `[web-ui]`, `[shared]`, `[integration]`
