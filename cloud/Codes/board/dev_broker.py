"""개발용 로컬 MQTT 브로커 (amqtt, 순수 파이썬).

RCI 실물·Mosquitto 없이 localhost:1883 에서 왕복 테스트를 돌리기 위한 임시 브로커.
프로토 이후 클라우드(HiveMQ/EMQX)로 이설할 때는 이 파일 대신 브로커 접속 정보만 바꾼다.

실행:  python dev_broker.py      (Ctrl+C 로 종료)
"""

import asyncio
import contextlib
import logging
import os
import sys

from amqtt.broker import Broker

# 콘솔 기본 인코딩(예: Windows cp949)이 유니코드 기호를 못 찍어 죽는 것을 방지.
with contextlib.suppress(Exception):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 바인드 주소. 기본은 로컬 전용(127.0.0.1). 핫스팟(LAN) 테스트에서 다른 기기(라즈베리파이
# RCI·태블릿)가 붙게 하려면 RCI_BIND_HOST=0.0.0.0 으로 실행한다.
BIND_HOST = os.environ.get("RCI_BIND_HOST", "0.0.0.0")

# 로그 수준. 기본은 조용(WARNING)하다 — 브로커·목 RCI·웹이 콘솔 하나를 공유하므로
# (scripts/dev.ps1 이 -NoNewWindow 로 띄운다) 브로커까지 떠들면 정작 봐야 할
# req/resp 왕복이 스크롤로 밀려 올라간다. 필요할 때만 환경변수로 올린다.
#
#   RCI_BROKER_LOG=info    누가 언제 붙고 끊는지. 실물 RCI 연동 테스트용 기본값.
#                          amqtt 가 "Connection from <IP>:<port>" 를 찍어주므로,
#                          라즈베리파이가 정말 이 브로커까지 도달했는지 확인된다.
#   RCI_BROKER_LOG=debug   client_id·구독 등록·모든 MQTT 패킷. 원인 불명일 때만.
#                          keepalive PINGREQ 도배를 각오할 것.
#
# 기본(WARNING)에서도 조용하지 않은 것이 둘 있고, 일부러 남겨둔다. 놓치면 원인을
# 못 찾는 사건들이다: client_id 중복 접속("performing take-over" — 웹 브리지를 두 번
# 띄우면 서로 끊는다)과 재접속 폭주.
LOG_LEVELS = {
    "off": logging.WARNING,
    "warning": logging.WARNING,
    "info": logging.INFO,
    "debug": logging.DEBUG,
}
# 빈 값은 미설정과 같게 본다. `RCI_BROKER_LOG=` 로 끄는 습관이 흔하고, 이 저장소의
# 다른 환경변수(RCI_BROKER_USERNAME 등)도 빈 문자열을 미설정으로 취급한다.
_requested = os.environ.get("RCI_BROKER_LOG", "").strip().lower() or "off"
LOG_LEVEL = LOG_LEVELS.get(_requested, logging.WARNING)
VERBOSE = LOG_LEVEL <= logging.INFO

logging.basicConfig(
    level=LOG_LEVEL,
    # 세 프로세스가 한 콘솔을 공유하니 '어느 프로세스인지'가 타임스탬프보다 먼저다.
    format="[dev-broker] %(levelname)s %(name)s · %(message)s",
)

# amqtt 가 끌고 오는 서드파티 로거를 눌러둔다. 이것들을 그대로 두면 INFO 출력의
# 절반 이상이 브로커와 무관한 내부 상태전이로 채워져, 정작 봐야 할
# "Connection from <IP>" 가 묻힌다. (측정: 프로브 1대 접속에 transitions 만 12줄)
#
#   transitions  — amqtt 세션 상태머신. 콜백 실행마다 INFO 를 찍는다. 이 로그가
#                  Session(clientId=...) 를 흘려서 client_id 를 알려주긴 하지만,
#                  라이브러리 내부 표현이라 버전이 바뀌면 그대로 깨진다. client_id 가
#                  필요하면 debug 로 올려 amqtt 자신이 찍는 것을 볼 것.
#   websockets   — "connection open" 이 amqtt 의 접속 로그와 그대로 겹친다.
for _noisy in ("transitions", "websockets"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

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

# 관측용 플러그인은 로그를 켰을 때만 붙인다 — 기본 실행의 동작을 지금 그대로 두기
# 위해서다. BrokerSysPlugin 이 $SYS/broker/version 을 retained 로 남기는데, amqtt
# 0.11.4 는 구독 필터와 무관하게 retained 를 흘려보내는 버그가 있어(mqtt_bridge.py
# _on_message 주석 참고) 접속하는 클라이언트마다 엉뚱한 토픽을 한 번씩 받는다.
# 웹 브리지는 접두어 검사로, 목 RCI 는 JSON 파싱 실패로 각각 흘리므로 해는 없지만
# 노이즈다. 관측을 원해서 켠 사람만 감수하면 된다.
if VERBOSE:
    CONFIG["plugins"].update({
        # 접속/해제를 INFO 로 올린다. amqtt 는 해제를 DEBUG 로만 찍어서, 이게 없으면
        # '붙는 건 보이는데 끊기는 건 안 보이는' 비대칭이 생긴다.
        "amqtt.plugins.logging_amqtt.EventLoggerPlugin": {},
        # $SYS/broker/... 통계를 주기적으로 발행. 아무 MQTT 클라이언트로 '$SYS/#' 를
        # 구독하면 접속 수·메시지 수가 보인다. 단 '누가' 붙었는지는 안 나온다 —
        # 디바이스 목록은 계약상 minigit/status/# (retained) 이고, 웹의 /api/health
        # 가 그것을 rci_status 로 이미 노출한다.
        "amqtt.plugins.sys.broker.BrokerSysPlugin": {"sys_interval": 20},
    })


async def main():
    if _requested not in LOG_LEVELS:
        print(f"[dev-broker] 알 수 없는 RCI_BROKER_LOG={_requested!r} - off 로 진행 "
              f"(가능: {', '.join(LOG_LEVELS)})", flush=True)
    broker = Broker(CONFIG)
    await broker.start()
    print(f"[dev-broker] up - tcp {BIND_HOST}:1883 | ws {BIND_HOST}:8080/mqtt (Ctrl+C to stop)",
          flush=True)
    # 로그가 꺼져 있다는 사실 자체를 알려준다. 아무것도 안 찍히는 브로커를 보고
    # '죽었나?' 하고 의심하는 것이 이 스택에서 가장 흔한 착각이다.
    print(f"[dev-broker] log={logging.getLevelName(LOG_LEVEL).lower()} "
          f"(RCI_BROKER_LOG=info|debug 로 상세 로그)", flush=True)
    with contextlib.suppress(asyncio.CancelledError):
        await asyncio.Event().wait()


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
