"""서버측 MQTT 브리지 — FastAPI(웹) ↔ 브로커 ↔ RCI (minigit 계약).

계약: `Documents/MQTT_Interface_Contract.md`

    요청  minigit/req/{device}        {id, raw, timeout_ms}              웹 → RCI  QoS1
    응답  minigit/resp/{device}       {id, type, raw, nrc?}              RCI → 웹  QoS1
    에러  minigit/error/{device}      {id, type:"error", reason, message} RCI → 웹  QoS1
    상태  minigit/status/rci-{ur|rc}  {state, robot}                     retained + LWT

브라우저 직결 경로(`static/js/rci-live.js`, ws:8080)와 **병존**한다. 이쪽은 FastAPI
프로세스가 직접 브로커에 붙는 경로로, 브라우저 없이 `curl` 한 줄로 왕복을 확인할 수
있어 RCI 측 연결 테스트(`ur3/scripts/mqtt_echo_test.py`)의 상대역이 된다.

스레드 경계 주의
    paho 콜백은 paho 자신의 네트워크 스레드에서 실행된다. `asyncio.Future`/`Queue`
    는 이벤트 루프 스레드에서만 만져야 하므로, 콜백은 값만 뽑아 즉시
    `loop.call_soon_threadsafe()` 로 루프에 넘긴다. 루프 밖에서 Future 를 건드리면
    로컬에선 우연히 동작하다가 동시 요청에서 깨진다.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import ssl
import threading
from collections import OrderedDict

import paho.mqtt.client as mqtt

log = logging.getLogger("rci.mqtt")

# --------------------------------------------------------------------------- #
# 계약 상수
# --------------------------------------------------------------------------- #

DEVICES = ("urrobot", "rccar")
STATUS_TOPIC = {"urrobot": "minigit/status/rci-ur", "rccar": "minigit/status/rci-rc"}

REQ_PREFIX = "minigit/req/"
RESP_PREFIX = "minigit/resp/"
ERROR_PREFIX = "minigit/error/"
STATUS_PREFIX = "minigit/status/"

# 웹이 구독하는 토픽. RCI 가 발행하는 3종만 받는다(요청 토픽은 구독하지 않음).
SUBSCRIPTIONS = [(RESP_PREFIX + "+", 1), (ERROR_PREFIX + "+", 1), (STATUS_PREFIX + "+", 1)]

NRC_IN_PROGRESS = "78"   # 계약: 진행 중. 같은 id 로 최종 응답이 뒤이어 온다.
_SEEN_MAX = 512          # QoS1 중복 판별 캐시 상한(무한 증가 방지)
_EVENT_QUEUE_MAX = 200   # SSE 구독자당 버퍼. 넘치면 오래된 것부터 버린다.


class BridgeError(RuntimeError):
    """브리지 사용 오류(미연결·잘못된 device·발행 실패 등)."""


class RequestTimeout(BridgeError):
    """RCI 가 timeout_ms 안에 응답하지 않음."""


def normalize_hex(raw: str) -> str:
    """UDS raw 를 계약 표기(대문자·공백 1개 구분·`0x` 없음)로 정규화한다.

    사람이 손으로 넣는 값("22 01 07", "220107", "0x22 0x01 0x07")을 관용적으로
    받아주되, 브로커에 나가는 순간에는 계약 표기 한 가지로 통일한다.
    """
    text = raw.strip().replace("0x", "").replace("0X", "")
    tokens = text.split() if " " in text else [text[i:i + 2] for i in range(0, len(text), 2)]
    if not tokens or not all(tokens):
        raise ValueError(f"빈 UDS raw: {raw!r}")
    out = []
    for tok in tokens:
        if len(tok) != 2:
            raise ValueError(f"UDS raw 는 바이트(2자리 hex) 단위여야 합니다: {tok!r}")
        try:
            out.append(f"{int(tok, 16):02X}")
        except ValueError:
            raise ValueError(f"hex 가 아닌 토큰: {tok!r}") from None
    return " ".join(out)


class BrokerConfig:
    """브로커 접속 설정. 로컬 개발 기본값 + 환경변수 오버라이드.

    클라우드 브로커(HiveMQ/EMQX)로 이설할 때 코드 수정 없이 환경변수만 바꾼다.
    TLS 를 켜면 포트 기본값도 8883 으로 따라간다(관례).
    """

    def __init__(self, host, port, username=None, password=None, tls=False,
                 keepalive=30, client_id="rci-web"):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.tls = tls
        self.keepalive = keepalive
        self.client_id = client_id

    @classmethod
    def from_env(cls):
        tls = os.environ.get("RCI_BROKER_TLS", "").lower() in ("1", "true", "yes", "on")
        return cls(
            host=os.environ.get("RCI_BROKER_HOST", "127.0.0.1"),
            port=int(os.environ.get("RCI_BROKER_PORT", "8883" if tls else "1883")),
            username=os.environ.get("RCI_BROKER_USERNAME") or None,
            password=os.environ.get("RCI_BROKER_PASSWORD") or None,
            tls=tls,
            keepalive=int(os.environ.get("RCI_BROKER_KEEPALIVE", "30")),
            client_id=os.environ.get("RCI_MQTT_CLIENT_ID", "rci-web"),
        )

    def describe(self):
        scheme = "mqtts" if self.tls else "mqtt"
        auth = f"{self.username}@" if self.username else ""
        return f"{scheme}://{auth}{self.host}:{self.port}"


class MqttBridge:
    """FastAPI 프로세스가 소유하는 단일 MQTT 클라이언트.

    - 발행: `request()` — req 발행 후 같은 id 의 resp/error 를 await 로 기다린다.
    - 구독: resp/error/status 를 상시 구독하고, 수신분은 SSE 구독자에게 팬아웃한다.
    - status(retained)는 캐시해 `/api/health` 에서 그대로 노출한다.
    """

    def __init__(self, config: BrokerConfig):
        self._cfg = config
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = threading.Lock()          # _pending / _seq 를 두 스레드가 공유
        self._pending: dict[str, asyncio.Future] = {}
        self._seq = 0
        self._status: dict[str, dict] = {}     # device → 마지막 status 페이로드
        self._listeners: set[asyncio.Queue] = set()
        self._seen: OrderedDict[tuple, bool] = OrderedDict()
        self._connected = threading.Event()

        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=config.client_id,
        )
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)
        if config.username:
            self._client.username_pw_set(config.username, config.password)
        if config.tls:
            self._client.tls_set(cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLS_CLIENT)

    # ---- 수명주기 --------------------------------------------------------- #

    def start(self, loop: asyncio.AbstractEventLoop):
        """비차단 접속 시작. 브로커가 아직 안 떠 있어도 웹 서버는 정상 기동한다.

        `connect_async` + 재접속 백오프 조합이라, 나중에 브로커가 올라오면 알아서 붙는다.
        (동기 `connect()` 였다면 브로커 부재 시 uvicorn 기동 자체가 실패한다.)
        """
        self._loop = loop
        self._client.connect_async(self._cfg.host, self._cfg.port, self._cfg.keepalive)
        self._client.loop_start()
        log.info("MQTT 브리지 시작 — %s (client_id=%s)", self._cfg.describe(), self._cfg.client_id)

    def stop(self):
        self._client.loop_stop()
        self._client.disconnect()
        self._connected.clear()
        log.info("MQTT 브리지 종료")

    @property
    def connected(self) -> bool:
        return self._connected.is_set()

    def health(self) -> dict:
        return {
            "connected": self.connected,
            "broker": self._cfg.describe(),
            "client_id": self._cfg.client_id,
            "subscriptions": [t for t, _ in SUBSCRIPTIONS],
            "pending": len(self._pending),
            "rci_status": dict(self._status),
        }

    def status_of(self, device: str) -> dict | None:
        return self._status.get(device)

    # ---- paho 콜백 (paho 네트워크 스레드에서 실행됨) ------------------------ #

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code != 0:
            # 인증 실패(5)·프로토콜 거부 등. 조용히 재시도만 하면 원인을 못 찾는다.
            log.error("브로커 접속 거부 — %s (reason_code=%s)", self._cfg.describe(), reason_code)
            return
        self._connected.set()
        for topic, qos in SUBSCRIPTIONS:
            client.subscribe(topic, qos=qos)
        log.info("브로커 연결됨 — %s · 구독 %s",
                 self._cfg.describe(), ", ".join(t for t, _ in SUBSCRIPTIONS))
        self._emit({"kind": "broker", "state": "connected", "broker": self._cfg.describe()})

    def _on_disconnect(self, client, userdata, *args):
        # paho 2.x 는 (flags, reason_code, properties), 1.x 는 (rc) 를 넘긴다.
        self._connected.clear()
        reason = args[1] if len(args) >= 2 else (args[0] if args else "?")
        log.warning("브로커 연결 끊김 (reason=%s) — 재접속 시도 중", reason)
        self._emit({"kind": "broker", "state": "disconnected", "reason": str(reason)})

    def _on_message(self, client, userdata, msg):
        topic = msg.topic
        # 토픽 접두어로 라우팅한다. 개발 브로커(amqtt 0.11.4)는 구독 필터와 무관한
        # retained 메시지를 흘려보내는 버그가 있어, 접두어 검사가 방어선 역할도 한다.
        if not topic.startswith((RESP_PREFIX, ERROR_PREFIX, STATUS_PREFIX)):
            log.debug("구독 범위 밖 토픽 무시: %s", topic)
            return
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            log.warning("JSON 이 아닌 페이로드 무시: %s", topic)
            return
        if not isinstance(payload, dict):
            return

        if topic.startswith(STATUS_PREFIX):
            self._handle_status(topic, payload)
            return

        device = topic.rsplit("/", 1)[-1]
        # QoS1 중복 제거. id 만으로 판별하면 nrc=78(진행 중) 직후의 최종 응답이
        # '같은 id' 라는 이유로 버려진다 → (id, raw) 쌍으로 잡는다.
        key = (topic, payload.get("id"), payload.get("raw"), payload.get("message"))
        if self._is_duplicate(key):
            log.debug("QoS1 중복 무시: %s", key)
            return

        self._emit({"kind": "error" if topic.startswith(ERROR_PREFIX) else "resp",
                    "device": device, **payload})
        self._resolve(payload)

    # ---- 내부 헬퍼 -------------------------------------------------------- #

    def _handle_status(self, topic, payload):
        suffix = topic.rsplit("/", 1)[-1]           # rci-ur | rci-rc
        device = "urrobot" if suffix.endswith("-ur") else "rccar"
        self._status[device] = payload
        log.info("RCI 상태 · %s · %s", device, payload)
        self._emit({"kind": "status", "device": device, **payload})

    def _is_duplicate(self, key) -> bool:
        with self._lock:
            if key in self._seen:
                return True
            self._seen[key] = True
            while len(self._seen) > _SEEN_MAX:
                self._seen.popitem(last=False)
        return False

    def _resolve(self, payload):
        """수신 페이로드를 기다리는 request() 에 넘긴다(루프 스레드로 이관)."""
        req_id = payload.get("id")
        if not req_id:
            return
        # 진행 중 통지는 최종 응답이 아니다 — Future 를 깨우지 않고 계속 기다린다.
        if payload.get("type") == "negative" and str(payload.get("nrc", "")).upper() == NRC_IN_PROGRESS:
            log.info("진행 중(NRC 78) — id=%s 최종 응답 대기", req_id)
            return
        with self._lock:
            future = self._pending.get(req_id)
        if future is None or self._loop is None:
            return
        self._loop.call_soon_threadsafe(self._set_result, future, payload)

    @staticmethod
    def _set_result(future: asyncio.Future, payload):
        if not future.done():
            future.set_result(payload)

    def _emit(self, event: dict):
        """SSE 구독자 전원에게 이벤트 팬아웃(루프 스레드로 이관)."""
        if self._loop is None:
            return
        self._loop.call_soon_threadsafe(self._emit_in_loop, event)

    def _emit_in_loop(self, event: dict):
        for queue in list(self._listeners):
            if queue.full():
                queue.get_nowait()      # 느린 구독자 때문에 브리지가 막히면 안 된다
            queue.put_nowait(event)

    def _next_id(self) -> str:
        with self._lock:
            self._seq += 1
            return f"w-{self._seq:04d}"

    # ---- 공개 API --------------------------------------------------------- #

    async def request(self, device: str, raw: str, timeout_ms: int = 1000) -> dict:
        """UDS 요청을 발행하고 같은 id 의 응답(또는 에러)을 기다려 돌려준다."""
        if device not in DEVICES:
            # 클라이언트 입력 오류이므로 BridgeError(503)가 아니라 ValueError(400).
            raise ValueError(f"알 수 없는 device: {device!r} (가능: {', '.join(DEVICES)})")
        if not self.connected:
            raise BridgeError(f"브로커에 연결되지 않았습니다 — {self._cfg.describe()}")

        normalized = normalize_hex(raw)
        req_id = self._next_id()
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        with self._lock:
            self._pending[req_id] = future

        payload = {"id": req_id, "raw": normalized, "timeout_ms": timeout_ms}
        try:
            info = self._client.publish(REQ_PREFIX + device, json.dumps(payload), qos=1)
            if info.rc != mqtt.MQTT_ERR_SUCCESS:
                raise BridgeError(f"발행 실패 (rc={info.rc})")
            self._emit({"kind": "req", "device": device, **payload})
            log.info("→ req %s%s  %s  (id=%s)", REQ_PREFIX, device, normalized, req_id)
            # 발행 왕복 여유분(+0.5s). RCI 가 timeout_ms 를 다 쓰고 응답하는 경우 대비.
            return await asyncio.wait_for(future, timeout_ms / 1000 + 0.5)
        except asyncio.TimeoutError:
            raise RequestTimeout(
                f"RCI 무응답 — id={req_id} raw={normalized} ({timeout_ms}ms 초과)") from None
        finally:
            with self._lock:
                self._pending.pop(req_id, None)

    def listen(self) -> asyncio.Queue:
        """SSE 스트림용 이벤트 큐를 등록한다. 반드시 `unlisten()` 으로 해제할 것."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=_EVENT_QUEUE_MAX)
        self._listeners.add(queue)
        return queue

    def unlisten(self, queue: asyncio.Queue):
        self._listeners.discard(queue)
