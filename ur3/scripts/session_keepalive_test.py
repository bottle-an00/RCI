"""
확장 세션을 열고 TesterPresent(0x3E)를 2초 주기로 발행해 유지하는 테스터(클라이언트) 스크립트.

RCI가 아니라 웹앱 역할의 테스터를 흉내낸다 — minigit/req/urrobot 에 요청을
발행하고 minigit/resp/urrobot, minigit/error/urrobot 을 구독해 응답을 출력한다.

동작:
1. 연결 후 "10 03"을 발행해 확장 세션에 진입한다.
2. 백그라운드 스레드가 2초 간격으로 "3E 00"을 발행해 S3 타이머(5s)가
   만료되지 않게 한다(UR3_RCI_기능명세서.md §5.6).
3. 콘솔에 raw hex를 입력하면 그 요청을 즉시 발행한다 — 0x2F/0x31처럼
   확장 세션이 필요한 명령을 세션 걱정 없이 수동으로 테스트할 때 쓴다.
4. Ctrl+C 또는 "quit" 입력 시 키프얼라이브를 멈추고 연결을 끊는다.
   여기서 10 01을 따로 보내진 않는다 — 발행을 멈추면 RCI가 S3 타임아웃(5s)으로
   스스로 default 세션으로 돌아간다.

실행:
    python scripts/session_keepalive_test.py
    python scripts/session_keepalive_test.py --host 172.20.10.3
"""
import argparse
import contextlib
import itertools
import json
import os
import sys
import threading
import time

with contextlib.suppress(Exception):
    sys.stdout.reconfigure(line_buffering=True)

_UR3_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_UR3_DIR)
sys.path.append(_UR3_DIR)
sys.path.append(_REPO_ROOT)
import config

from shared import topics
from shared.mqtt_client import MQTTClient

KEEPALIVE_INTERVAL_SEC = 2.0
CONNECT_TIMEOUT = 10.0

EXTENDED_SESSION_REQUEST = "10 03"
TESTER_PRESENT_REQUEST = "3E 00"


def build_request_payload(req_id, raw_hex, timeout_ms=1000):
    return json.dumps({"id": req_id, "raw": raw_hex, "timeout_ms": timeout_ms})


def make_response_handler():
    def on_response(client, userdata, msg):
        print(f"[응답] {msg.topic} -> {msg.payload.decode('utf-8')}")

    return on_response


def keepalive_loop(mqtt_client, stop_event, id_counter):
    """세션 종료 신호(stop_event)가 오기 전까지 2초 간격으로 3E 00을 발행한다"""
    while not stop_event.wait(KEEPALIVE_INTERVAL_SEC):
        req_id = f"ka-{next(id_counter)}"
        mqtt_client.publish(
            topics.UR3_DIAG_REQ, build_request_payload(req_id, TESTER_PRESENT_REQUEST), qos=1
        )
        print(f"[발행] id={req_id} raw={TESTER_PRESENT_REQUEST} (keepalive)")


def parse_args():
    parser = argparse.ArgumentParser(description="확장 세션 유지 테스터")
    parser.add_argument("--host", default=config.BROKER_HOST, help="MQTT 브로커 주소")
    parser.add_argument("--port", type=int, default=config.BROKER_PORT)
    parser.add_argument("--client-id", default="ur3-tester")
    parser.add_argument("--tls", action="store_true", default=config.BROKER_TLS)
    return parser.parse_args()


def main():
    args = parse_args()
    mqtt_client = MQTTClient(
        args.client_id, args.host, args.port,
        username=config.BROKER_USERNAME, password=config.BROKER_PASSWORD, tls=args.tls,
    )
    mqtt_client.subscribe(topics.UR3_DIAG_RESP, callback=make_response_handler(), qos=1)
    mqtt_client.subscribe(topics.UR3_DIAG_ERROR, callback=make_response_handler(), qos=1)

    print(f"[연결 시도] {args.host}:{args.port} (client_id={args.client_id})")
    mqtt_client.connect_async()
    if not mqtt_client.wait_connected(CONNECT_TIMEOUT):
        print(f"[실패] {CONNECT_TIMEOUT:.0f}초 안에 연결되지 않음 "
              f"(reason_code={mqtt_client.last_reason_code})")
        return 1

    id_counter = itertools.count(1)
    mqtt_client.publish(
        topics.UR3_DIAG_REQ, build_request_payload("session-open", EXTENDED_SESSION_REQUEST), qos=1
    )
    print(f"[발행] id=session-open raw={EXTENDED_SESSION_REQUEST} (확장 세션 진입)")

    stop_event = threading.Event()
    keepalive_thread = threading.Thread(
        target=keepalive_loop, args=(mqtt_client, stop_event, id_counter), daemon=True,
    )
    keepalive_thread.start()
    print(f"[키프얼라이브 시작] {KEEPALIVE_INTERVAL_SEC:.0f}초 간격으로 3E 00 발행 중")
    print("       raw hex를 입력하면 그대로 발행합니다. 종료: Ctrl+C 또는 quit 입력")

    try:
        while True:
            line = sys.stdin.readline()
            if not line:
                time.sleep(0.2)
                continue
            line = line.strip()
            if not line:
                continue
            if line.lower() in ("quit", "exit"):
                break
            req_id = f"cmd-{next(id_counter)}"
            mqtt_client.publish(topics.UR3_DIAG_REQ, build_request_payload(req_id, line), qos=1)
            print(f"[발행] id={req_id} raw={line}")
    except KeyboardInterrupt:
        pass
    finally:
        print("[종료] 키프얼라이브 중단, 연결 해제")
        stop_event.set()
        keepalive_thread.join(timeout=1.0)
        mqtt_client.disconnect()

    return 0


if __name__ == "__main__":
    sys.exit(main())
