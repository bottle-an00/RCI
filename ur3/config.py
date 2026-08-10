"""UR3 연결 설정. 실제 환경에 맞게 값을 수정하세요.

모든 값은 환경변수로 덮어쓸 수 있다. 라즈베리파이(RCI)·PC·클라우드에서 각각
다른 브로커를 봐야 하는데, 그때마다 이 파일을 고쳐 커밋하면 서로 충돌한다.

    RCI_BROKER_HOST / RCI_BROKER_PORT
    RCI_BROKER_USERNAME / RCI_BROKER_PASSWORD / RCI_BROKER_TLS   (클라우드 브로커용)
    UR3_ROBOT_IP

예) 핫스팟에서 PC 의 브로커에 붙기:
    RCI_BROKER_HOST=192.168.x.y python scripts/mqtt_echo_test.py
"""
import os

ROBOT_IP = os.environ.get("UR3_ROBOT_IP", "192.168.1.101")  # UR3 컨트롤박스의 실제 IP
RTDE_PORT = 30004
DASHBOARD_PORT = 29999

# MQTT 브로커 (UR3_RCI_기능명세서.md §4.0 — 실제 클라우드 브로커 정보 미수령 상태.
# 로컬 테스트 중에는 브로커를 띄운 PC의 LAN IP로 바꿀 것.)
BROKER_TLS = os.environ.get("RCI_BROKER_TLS", "").lower() in ("1", "true", "yes", "on")
BROKER_HOST = os.environ.get("RCI_BROKER_HOST", "172.20.10.11")
BROKER_PORT = int(os.environ.get("RCI_BROKER_PORT", "8883" if BROKER_TLS else "1883"))
BROKER_USERNAME = os.environ.get("RCI_BROKER_USERNAME") or None
BROKER_PASSWORD = os.environ.get("RCI_BROKER_PASSWORD") or None
