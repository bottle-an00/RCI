"""
UR3 진단 MQTT 왕복 연결 테스트 (RCI 측).

로봇을 전혀 움직이지 않는다. UDS 디스패처(uds_server)는 아직 없으므로
실제 진단 서비스는 처리하지 않고, MQTT 왕복 자체가 되는지만 확인한다.

- 시작 시 브로커 연결을 **확인**하고(CONNACK 대기) 실패 원인을 그대로 출력
- minigit/status/rci-ur 에 online/connected 발행 (retained · LWT 는 핸들러가 설정)
- minigit/req/urrobot 수신 시 콘솔에 로그
  - raw가 "3E 00"(TesterPresent)이면 사양서 §6.2대로 "7E 00" 긍정 응답
  - 그 외에는 UDS 미구현임을 솔직하게 알리는 negative 에러 응답
- 종료(Ctrl+C) 시 offline/disconnected 발행 후 연결 해제

상대역: 클라우드 웹(FastAPI)의 `cloud/scripts/connection_test.py --stub`.
계약: `cloud/Documents/MQTT_Interface_Contract.md`

실행:
    python scripts/mqtt_echo_test.py                       # config.py 값 사용
    python scripts/mqtt_echo_test.py --host 172.20.10.3    # 브로커만 바꿔서
    RCI_BROKER_HOST=172.20.10.3 python scripts/mqtt_echo_test.py
"""
import argparse
import contextlib
import logging
import os
import sys
import time

# 파이프·리다이렉트(nohup, systemd, tee)로 돌릴 때 진행 로그가 버퍼에 갇히지 않게 한다.
with contextlib.suppress(Exception):
    sys.stdout.reconfigure(line_buffering=True)

_UR3_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_UR3_DIR)
sys.path.append(_UR3_DIR)  # config, mqtt_handler를 기존 scripts/ 관례대로 top-level import
sys.path.append(_REPO_ROOT)  # mqtt_handler.py가 내부적으로 쓰는 shared 패키지용
import config

from mqtt_handler import UR3MqttHandler

TESTER_PRESENT_REQUEST = bytes([0x3E, 0x00])
TESTER_PRESENT_RESPONSE = bytes([0x7E, 0x00])

CONNECT_TIMEOUT = 10.0   # CONNACK 대기(초). 무선/핫스팟 감안한 여유값.
PUBLISH_DRAIN = 0.5      # 종료 직전 마지막 발행이 실제로 나갈 시간


def make_request_handler(handler):
    """수신 요청 처리기. handler 를 클로저로 잡아 전역 변수를 쓰지 않는다."""

    def on_request(request):
        raw = request["raw"]
        print(f"[수신] id={request['id']} raw={raw.hex(' ').upper()}")

        if raw == TESTER_PRESENT_REQUEST:
            handler.publish_response(request["id"], TESTER_PRESENT_RESPONSE)
            print(f"[응답] id={request['id']} raw=7E 00 (TesterPresent ack)")
        else:
            handler.publish_error(
                request["id"],
                "internal_error",
                "UDS 디스패처 미구현 - 연결 테스트용 스텁입니다",
            )
            print(f"[응답] id={request['id']} UDS 미구현 에러 회신")

    return on_request


def parse_args():
    parser = argparse.ArgumentParser(description="UR3 진단 MQTT 왕복 연결 테스트")
    parser.add_argument("--host", default=config.BROKER_HOST, help="MQTT 브로커 주소")
    parser.add_argument("--port", type=int, default=config.BROKER_PORT)
    parser.add_argument("--client-id", default="ur3-rci",
                        help="MQTT client_id. 같은 id 로 둘이 붙으면 서로 끊는다.")
    parser.add_argument("--tls", action="store_true", default=config.BROKER_TLS)
    parser.add_argument("--verbose", action="store_true", help="MQTT 계층 로그까지 출력")
    return parser.parse_args()


def main():
    args = parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)-7s %(name)s: %(message)s")

    scheme = "mqtts" if args.tls else "mqtt"
    print(f"[연결 시도] MQTT 브로커 -> {scheme}://{args.host}:{args.port} "
          f"(client_id={args.client_id})")

    handler = UR3MqttHandler(
        broker_host=args.host,
        broker_port=args.port,
        client_id=args.client_id,
        username=config.BROKER_USERNAME,
        password=config.BROKER_PASSWORD,
        tls=args.tls,
    )
    handler.on_request = make_request_handler(handler)

    # connect_async: 브로커가 아직 안 떠 있어도 예외로 죽지 않고 재시도한다.
    # 다만 '떴는지'는 반드시 확인해야 한다 — 예전처럼 sleep(1) 로 넘기면 인증
    # 실패를 한참 뒤 '요청이 안 온다' 로 잘못 진단하게 된다.
    handler.connect_async()
    if not handler.wait_connected(CONNECT_TIMEOUT):
        reason = handler.last_reason_code
        print(f"[실패] {CONNECT_TIMEOUT:.0f}초 안에 브로커에 연결되지 못했습니다.")
        if reason is not None:
            print(f"       브로커 거부 reason_code={reason} (5=인증 실패, 4=잘못된 계정)")
        else:
            print(f"       {args.host}:{args.port} 에 브로커가 떠 있는지, 방화벽이 "
                  f"막지 않는지 확인하세요.")
            print("       PC 브로커에 붙는 경우:  RCI_BROKER_HOST=<PC IP> 로 지정")
        handler.disconnect()
        return 1

    handler.publish_status("online", "connected")
    print(f"[성공] 연결됨. {handler.__class__.__name__} 가 minigit/req/urrobot 수신 대기 중 "
          f"(Ctrl+C로 종료)")
    print("       웹 쪽에서 보내보기:")
    print('         curl -X POST http://<웹 IP>:8123/api/diag/urrobot/request \\')
    print('              -H "Content-Type: application/json" -d \'{"raw":"3E 00"}\'')

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        # 정상 종료는 LWT 가 안 나가므로 offline 을 직접 발행한다.
        if handler.is_connected:
            handler.publish_status("offline", "disconnected")
            time.sleep(PUBLISH_DRAIN)
        handler.disconnect()
        print("[종료] 연결 해제")
    return 0


if __name__ == "__main__":
    sys.exit(main())
