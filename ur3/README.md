# UR3-RPi-Test

라즈베리파이와 실제 UR3 로봇팔 사이의 통신을 확인하고, 간단한 제어 명령을 한 번 넣어보기 위한 최소 테스트 코드다.

`docs/` 폴더에는 miniGIT 프로젝트에서 설계한 UR3 진단 통신 문서 4종(사양서/기능명세서/RCI 기능명세서/클라우드 요청서)이 참고용으로 들어있다. 이 저장소의 코드는 그 설계를 구현한 것이 아니라, 본격적인 개발에 앞서 "라즈베리파이에서 UR3에 실제로 연결되고 명령이 먹히는지"만 먼저 확인하기 위한 것이다.

## 준비물

- 라즈베리파이(Python 3 설치되어 있어야 함)
- UR3 + Control Box(CB-Series), 라즈베리파이와 같은 네트워크(서브넷)에 이더넷으로 연결
- UR3 PolyScope 화면에서 확인한 로봇의 IP 주소 (Settings > System > Network)

## 설치

```bash
pip3 install -r requirements.txt
```

라즈베리파이가 32비트 OS이거나 `ur_rtde`의 사전 빌드된 패키지(wheel)가 없는 경우, 소스 빌드가 필요할 수 있다(Boost, CMake 필요). 자세한 내용은 [ur_rtde 공식 문서](https://sdurobotics.gitlab.io/ur_rtde/)를 참고할 것.

## 설정

`config.py`를 열어 `ROBOT_IP`를 실제 UR3 IP로 변경한다.

```python
ROBOT_IP = "192.168.1.101"  # <- 실제 값으로 변경
```

## 실행 순서

로봇을 움직이지 않는 것부터 먼저 확인하고, 마지막에 실제 이동 테스트를 한다.

1. **상태 읽기 (로봇이 움직이지 않음)**
   ```bash
   python scripts/read_state.py
   ```
   관절 각도, TCP 위치, robot_mode, safety_mode가 출력되면 RTDE 통신이 정상이다.

2. **Dashboard 명령 테스트 (로봇이 움직이지 않음)**
   ```bash
   python scripts/dashboard_test.py
   ```
   robotmode/safetymode/로드된 프로그램명이 출력되면 Dashboard(TCP 29999) 통신이 정상이다.

3. **간단한 이동 테스트 (⚠️ 로봇이 실제로 움직임)**
   ```bash
   python scripts/move_test.py
   ```
   손목 관절(6번 조인트) 하나만 5도 회전시키는 아주 작은 동작이다. 실행 전 터미널에 안전 확인 문구가 뜨고 `yes`를 입력해야 실제로 동작한다.

## MQTT 왕복 연결 테스트 (로봇이 움직이지 않음)

클라우드 웹앱과의 진단 통신 경로(`minigit/*` 계약)가 뚫렸는지만 확인한다. UDS
디스패처는 아직 없으므로 TesterPresent(`3E 00`)만 긍정 응답하고, 나머지 서비스는
"미구현" 에러를 솔직하게 회신한다.

```bash
python scripts/mqtt_echo_test.py                       # config.py 의 브로커 사용
python scripts/mqtt_echo_test.py --host 192.168.0.10   # 브로커만 바꿔서
RCI_BROKER_HOST=192.168.0.10 python scripts/mqtt_echo_test.py
```

브로커 주소·계정은 `config.py` 기본값을 환경변수로 덮어쓴다 — `RCI_BROKER_HOST`,
`RCI_BROKER_PORT`, `RCI_BROKER_USERNAME`, `RCI_BROKER_PASSWORD`, `RCI_BROKER_TLS`.
클라우드 웹(FastAPI)도 같은 이름을 읽으므로 양쪽에 같은 값을 주면 된다.

`[성공] 연결됨` 이 뜨면 CONNACK 까지 확인된 것이다(TCP 만 붙은 상태와 구분됨).
연결이 안 되면 원인(`reason_code=5` 인증 실패 등)을 그대로 출력한다.

**웹 쪽에서 메시지 보내기** — 이 스크립트를 띄운 채로, 웹 서버가 도는 PC 에서:

```bash
curl -X POST http://localhost:8123/api/diag/urrobot/request \
     -H "Content-Type: application/json" -d '{"raw":"3E 00"}'
# {"id":"w-0001","type":"positive","raw":"7E 00"}
```

전 구간을 한 번에 점검하려면 클라우드 쪽 스크립트를 쓴다:

```bash
python cloud/scripts/connection_test.py --stub --base-url http://<웹 IP>:8123
```

## 안전 주의사항

- `move_test.py`는 실제로 로봇을 움직인다. 실행 전 반드시 로봇 주변에 사람과 장애물이 없는지 확인할 것.
- 비상정지 버튼에 손이 닿는 위치에서 실행할 것.
- 처음 테스트할 때는 UR 컨트롤박스의 Safety Configuration(Installation 탭)에서 속도/힘 제한을 낮게 설정해두는 것을 권장한다.
- UR3가 Local(PolyScope 자체 프로그램 실행 중) 상태이거나 보호정지/비상정지 상태이면 RTDEControlInterface 연결 또는 moveJ 호출이 실패할 수 있다. 이 경우 PolyScope 화면에서 로봇 상태를 먼저 정상화한다.

## 폴더 구조

```
UR3-RPi-Test/
├── config.py              # 로봇 IP·브로커 등 연결 설정 (환경변수로 덮어쓰기 가능)
├── mqtt_handler.py        # minigit 계약 토픽 래퍼 (shared.mqtt_client 기반)
├── uds_payload.py         # 계약 페이로드 인코딩/디코딩
├── requirements.txt
├── scripts/
│   ├── read_state.py      # RTDE 읽기 전용 테스트
│   ├── dashboard_test.py  # Dashboard 명령 테스트
│   ├── mqtt_echo_test.py  # MQTT 왕복 연결 테스트 (로봇 미동작)
│   └── move_test.py       # 간단한 moveJ 이동 테스트 (실제 동작)
└── docs/                  # miniGIT UR3 진단 통신 설계 문서 4종 (참고용)
```
