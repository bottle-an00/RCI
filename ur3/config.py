"""UR3 연결 설정. 실제 환경에 맞게 값을 수정하세요."""

ROBOT_IP = "192.168.1.101"  # UR3 컨트롤박스(Control Box)의 실제 IP로 변경할 것
RTDE_PORT = 30004
DASHBOARD_PORT = 29999

# MQTT 브로커 (UR3_RCI_기능명세서.md §4.0 — 실제 클라우드 브로커 정보 미수령 상태.
# 로컬 테스트 중에는 브로커를 띄운 PC의 LAN IP로 바꿀 것.)
BROKER_HOST = "localhost"
BROKER_PORT = 1883
