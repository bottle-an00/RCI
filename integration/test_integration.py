"""전체 시스템 통합 테스트. MQTT 브로커와 각 파트가 실행 중인 상태에서 실행한다."""
import time
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.mqtt_client import MQTTClient
from shared import topics

BROKER_HOST = "localhost"
BROKER_PORT = 1883
TIMEOUT = 5


def test_rc_car_status():
    received = []

    def on_message(client, userdata, msg):
        received.append(msg.payload.decode())

    client = MQTTClient("integration-test", BROKER_HOST, BROKER_PORT)
    client.subscribe(topics.RC_CAR_STATUS, on_message)
    client.connect()
    client.publish(topics.RC_CAR_CMD, "ping")

    time.sleep(TIMEOUT)
    client.disconnect()

    assert received, "RC카에서 상태 응답 없음"
    print(f"[PASS] RC카 통신 확인: {received[0]}")


def test_ur3_status():
    received = []

    def on_message(client, userdata, msg):
        received.append(msg.payload.decode())

    client = MQTTClient("integration-test-ur3", BROKER_HOST, BROKER_PORT)
    client.subscribe(topics.UR3_STATUS, on_message)
    client.connect()
    client.publish(topics.UR3_CMD, "ping")

    time.sleep(TIMEOUT)
    client.disconnect()

    assert received, "UR3에서 상태 응답 없음"
    print(f"[PASS] UR3 통신 확인: {received[0]}")


if __name__ == "__main__":
    test_rc_car_status()
    test_ur3_status()
    print("[완료] 통합 테스트 통과")
