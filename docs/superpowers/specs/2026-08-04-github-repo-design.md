# RCI GitHub 리포지토리 설계

## 개요

RC카, UR3, 웹UI 세 파트로 구성된 팀 협업 프로젝트의 Monorepo 구조 설계.
각 파트는 독립적으로 개발 후 MQTT 기반으로 통합한다.

## 기술 스택

| 파트 | 언어 | 비고 |
|------|------|------|
| RC카 | Python | MQTT 클라이언트 |
| UR3 | Python | MQTT 클라이언트 |
| 웹UI | Python (FastAPI) | MQTT 클라이언트 |
| 통신 | MQTT | mosquitto 브로커 |

## 디렉토리 구조

```
RCI/
├── rc-car/
│   ├── main.py
│   ├── requirements.txt
│   └── README.md
├── ur3/
│   ├── main.py
│   ├── requirements.txt
│   └── README.md
├── web-ui/
│   ├── main.py
│   ├── requirements.txt
│   └── README.md
├── shared/
│   ├── mqtt_client.py     # 공통 MQTT 연결/발행/구독
│   └── topics.py          # MQTT 토픽 상수 정의
├── integration/
│   └── test_integration.py
├── docs/
│   └── architecture.md
└── README.md
```

## README 전략

### 루트 README.md
- 프로젝트 전체 목적 및 아키텍처 개요
- MQTT 브로커(mosquitto) 설치 및 실행 방법
- 전체 시스템 실행 순서: 브로커 → UR3 → RC카 → 웹UI
- 통합 테스트 실행 방법

### 파트별 README.md
- 해당 파트 단독 구동 방법
- 환경 설정: `pip install -r requirements.txt`
- 실행: `python main.py`
- 발행/구독하는 MQTT 토픽 목록
- 트러블슈팅 FAQ

### docs/architecture.md
- 전체 데이터 흐름 다이어그램
- MQTT 토픽 네이밍 규칙 (예: `rci/rc-car/cmd`, `rci/ur3/status`)

## 브랜치 전략

```
main          # 안정된 통합 코드
└── dev       # 통합 전 개발 베이스
    ├── feat/rc-car-xxx
    ├── feat/ur3-xxx
    └── feat/web-ui-xxx
```

- 팀원은 `dev`에서 브랜치 생성 → PR로 `dev` 머지
- 통합 테스트 통과 후 `dev` → `main` 머지
- 커밋 메시지 prefix: `[rc-car]`, `[ur3]`, `[web-ui]`, `[shared]`, `[integration]`

## 통합 계획

- 파트별 독립 개발 단계에서 각 README만으로 단독 실행 가능
- 로컬 테스트 시 mosquitto로 MQTT 브로커 대체 가능
- 통합 테스트는 `integration/test_integration.py`에서 전체 시스템 검증
