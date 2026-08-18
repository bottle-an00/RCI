"""UR3 연결 설정. 실제 환경에 맞게 값을 수정하세요.

모든 값은 환경변수로 덮어쓸 수 있다. 라즈베리파이(RCI)·PC·클라우드에서 각각
다른 브로커를 봐야 하는데, 그때마다 이 파일을 고쳐 커밋하면 서로 충돌한다.

    RCI_BROKER_HOST / RCI_BROKER_PORT
    RCI_BROKER_USERNAME / RCI_BROKER_PASSWORD / RCI_BROKER_TLS   (클라우드 브로커용)
    UR3_ROBOT_IP

예) 핫스팟에서 PC 의 브로커에 붙기:
    RCI_BROKER_HOST=172.20.10.3 python scripts/mqtt_echo_test.py
"""
import os

ROBOT_IP = os.environ.get("UR3_ROBOT_IP", "192.168.1.101")  # UR3 컨트롤박스의 실제 IP
RTDE_PORT = 30004
DASHBOARD_PORT = 29999

# MQTT 브로커 (UR3_RCI_기능명세서.md §4.0 — 실제 클라우드 브로커 정보 미수령 상태.)
#
# 여기 값은 라즈베리파이가 '접속해 나갈' 목적지다. 지금은 클라우드 브로커가 없어서
# 클라우드 웹(FastAPI)을 띄운 PC 가 브로커를 겸하고 있고, 172.20.10.3 은 그 PC 의
# 무선 IP 다. 172.20.10.0/28 은 iOS 개인용 핫스팟 대역이라 재접속마다 바뀔 수 있으니,
# 안 붙으면 이 파일부터 의심하지 말고 PC 의 현재 IP 를 먼저 확인할 것(ipconfig).
#
# 0.0.0.0 / 127.0.0.1 을 넣지 말 것 — 둘 다 '이 기기 자신'이라 라즈베리파이가
# 자기에게 붙으려 하고 PC 에는 도달하지 못한다. 그 둘은 브로커 쪽(bind) 주소다.
BROKER_TLS = os.environ.get("RCI_BROKER_TLS", "").lower() in ("1", "true", "yes", "on")
BROKER_HOST = os.environ.get("RCI_BROKER_HOST", "172.20.10.3")
BROKER_PORT = int(os.environ.get("RCI_BROKER_PORT", "8883" if BROKER_TLS else "1883"))
BROKER_USERNAME = os.environ.get("RCI_BROKER_USERNAME") or None
BROKER_PASSWORD = os.environ.get("RCI_BROKER_PASSWORD") or None
