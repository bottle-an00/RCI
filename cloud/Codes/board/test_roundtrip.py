"""웹 UI 스탠드인 — 왕복(round-trip) 검증 스크립트 (minigit 계약).

dev_broker.py 와 mock_rci.py 가 떠 있는 상태에서 실행하면, UDS 요청을 발행하고
목 RCI 의 응답을 받아 출력한다. 웹 UI 연결 전, 파이프가 왕복하는지 확인용.

실행:  python test_roundtrip.py [device] [raw]
예:    python test_roundtrip.py urrobot "22 01 07"     # 로봇 모드
       python test_roundtrip.py rccar "22 01 05"       # 조도
"""

import contextlib
import json
import sys
import time

import paho.mqtt.client as mqtt

with contextlib.suppress(Exception):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

device = sys.argv[1] if len(sys.argv) > 1 else "urrobot"
raw = sys.argv[2] if len(sys.argv) > 2 else "22 01 07"
REQ_ID = "t-0001"
RESP_TOPIC = f"minigit/resp/{device}"

received = []
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="web-sim")


def on_message(cl, ud, msg):
    """수신 메시지 중 '이번 요청의 응답'만 received 에 넣는다.

    개발 브로커(amqtt 0.11.4)는 구독 필터와 무관한 retained 메시지
    (minigit/status/rci-*, {"state","robot"} — "type"/"raw" 없음)를 한 건 흘려보낸다.
    필터 없이 첫 메시지를 응답으로 간주하면 KeyError: 'type' 으로 죽는다.
    (웹 UI 의 rci-live.js 는 토픽 접두어로 라우팅해 같은 문제를 이미 피하고 있다.)

    msg.topic = 실제 토픽, payload = 계약상 {id, type, raw, nrc?}.
    """
    if msg.topic != RESP_TOPIC:
        return                                  # 브로커의 retained 누수 차단
    payload = json.loads(msg.payload.decode())
    if payload.get("id") != REQ_ID:
        return                                  # 다른 클라이언트(브라우저 탭 등)의 응답 차단
    received.append(payload)


client.on_message = on_message
client.connect("127.0.0.1", 1883, 60)
client.loop_start()
client.subscribe(RESP_TOPIC, qos=1)
time.sleep(0.3)  # 구독 확립 대기

client.publish(f"minigit/req/{device}",
               json.dumps({"id": REQ_ID, "raw": raw, "timeout_ms": 1000}), qos=1)
print(f"→ req  minigit/req/{device}   {raw}")

deadline = time.time() + 3
while not received and time.time() < deadline:
    time.sleep(0.05)
client.loop_stop()
client.disconnect()

if received:
    r = received[0]
    tail = f'   nrc={r["nrc"]}' if r.get("nrc") else ""
    print(f'← res  {r["type"]:8} {r["raw"]}{tail}')
else:
    print("✗ 응답 없음 — dev_broker/mock_rci 실행 여부를 확인하세요.")
