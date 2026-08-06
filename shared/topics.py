"""MQTT 토픽 상수 정의."""

RC_CAR_CMD = "rci/rc-car/cmd"
RC_CAR_STATUS = "rci/rc-car/status"

UR3_CMD = "rci/ur3/cmd"
UR3_STATUS = "rci/ur3/status"

# UR3 RCI 진단 인터페이스 토픽 (UR3_RCI_기능명세서.md §4.1, 확정)
# 위 UR3_CMD/UR3_STATUS(rci/ur3/*)와 이름 체계가 다르다.
# 통합 여부는 팀 합의 보류 — 지금은 두 체계가 병존한다.
UR3_DIAG_REQ = "minigit/req/urrobot"       # 웹앱 발행 → RCI 구독. QoS 1, Retained N
UR3_DIAG_RESP = "minigit/resp/urrobot"     # RCI 발행 → 웹앱 구독. QoS 1, Retained N
UR3_DIAG_ERROR = "minigit/error/urrobot"   # RCI 발행 → 웹앱 구독. QoS 1, Retained N
UR3_DIAG_STATUS = "minigit/status/rci-ur"  # RCI 발행 → 웹앱 구독. QoS 1, Retained Y (+LWT)
