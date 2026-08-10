"""개발용 로컬 MQTT 브로커 (amqtt, 순수 파이썬).

RCI 실물·Mosquitto 없이 localhost:1883 에서 왕복 테스트를 돌리기 위한 임시 브로커.
프로토 이후 클라우드(HiveMQ/EMQX)로 이설할 때는 이 파일 대신 브로커 접속 정보만 바꾼다.

실행:  python dev_broker.py      (Ctrl+C 로 종료)
"""

import asyncio
import contextlib
import os
import sys

from amqtt.broker import Broker

# 콘솔 기본 인코딩(예: Windows cp949)이 유니코드 기호를 못 찍어 죽는 것을 방지.
with contextlib.suppress(Exception):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 바인드 주소. 기본은 로컬 전용(127.0.0.1). 핫스팟(LAN) 테스트에서 다른 기기(라즈베리파이
# RCI·태블릿)가 붙게 하려면 RCI_BIND_HOST=0.0.0.0 으로 실행한다.
BIND_HOST = os.environ.get("RCI_BIND_HOST", "127.0.0.1")

CONFIG = {
    "listeners": {
        # 게이트웨이·백엔드용 순수 TCP.
        "default": {"type": "tcp", "bind": f"{BIND_HOST}:1883"},
        # 브라우저용 MQTT-over-WebSocket. 웹 UI 는 ws://<호스트>:8080/mqtt 로 붙는다.
        "ws": {"type": "ws", "bind": f"{BIND_HOST}:8080"},
    },
    "plugins": {
        # 익명 접속 허용 (개발 전용). 프로토 후 클라우드에선 인증 플러그인으로 교체.
        "amqtt.plugins.authentication.AnonymousAuthPlugin": {"allow_anonymous": True},
    },
}


async def main():
    broker = Broker(CONFIG)
    await broker.start()
    print(f"[dev-broker] up - tcp {BIND_HOST}:1883 | ws {BIND_HOST}:8080/mqtt (Ctrl+C to stop)",
          flush=True)
    with contextlib.suppress(asyncio.CancelledError):
        await asyncio.Event().wait()


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
