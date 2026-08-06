"""
UR3 진단 MQTT 왕복 연결 테스트.

로봇을 전혀 움직이지 않는다. UDS 디스패처(uds_server)는 아직 없으므로
실제 진단 서비스는 처리하지 않고, MQTT 왕복 자체가 되는지만 확인한다.

- 시작 시 minigit/status/rci-ur 에 online/connected 발행
- minigit/req/urrobot 수신 시 콘솔에 로그
  - raw가 "3E 00"(TesterPresent)이면 사양서 §6.2대로 "7E 00" 긍정 응답
  - 그 외에는 UDS 미구현임을 솔직하게 알리는 negative 에러 응답
- 종료(Ctrl+C) 시 offline/disconnected 발행 후 연결 해제

실행: python scripts/mqtt_echo_test.py
"""
import os
import sys
import time

_UR3_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_UR3_DIR)
sys.path.append(_UR3_DIR)  # config, mqtt_handler를 기존 scripts/ 관례대로 top-level import
sys.path.append(_REPO_ROOT)  # mqtt_handler.py가 내부적으로 쓰는 shared 패키지용
from config import BROKER_HOST, BROKER_PORT

from mqtt_handler import UR3MqttHandler

TESTER_PRESENT_REQUEST = bytes([0x3E, 0x00])
TESTER_PRESENT_RESPONSE = bytes([0x7E, 0x00])


def on_request(request: dict):
    print(f"[수신] id={request['id']} raw={request['raw'].hex(' ').upper()}")

    if request["raw"] == TESTER_PRESENT_REQUEST:
        handler.publish_response(request["id"], TESTER_PRESENT_RESPONSE)
        print(f"[응답] id={request['id']} raw=7E 00 (TesterPresent ack)")
    else:
        handler.publish_error(
            request["id"],
            "internal_error",
            "UDS 디스패처 미구현 - 연결 테스트용 스텁입니다",
        )
        print(f"[응답] id={request['id']} UDS 미구현 에러 회신")


def main():
    global handler
    print(f"[연결 시도] MQTT 브로커 -> {BROKER_HOST}:{BROKER_PORT}")
    handler = UR3MqttHandler(broker_host=BROKER_HOST, broker_port=BROKER_PORT)
    handler.on_request = on_request
    handler.connect()

    time.sleep(1)  # 연결 완료 대기 (간단한 테스트 스크립트이므로 폴링 대신 고정 대기)
    handler.publish_status("online", "connected")
    print("[성공] 연결됨. minigit/req/urrobot 수신 대기 중 (Ctrl+C로 종료)")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        handler.publish_status("offline", "disconnected")
        time.sleep(0.5)  # 발행 전송 대기
        handler.disconnect()
        print("[종료] 연결 해제")


if __name__ == "__main__":
    main()
