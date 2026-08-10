"""공통 MQTT 클라이언트 래퍼."""
import logging
import ssl
import threading

import paho.mqtt.client as mqtt

log = logging.getLogger("rci.mqtt")


class MQTTClient:
    def __init__(
        self,
        client_id: str,
        broker_host: str = "localhost",
        broker_port: int = 1883,
        will_topic: str | None = None,
        will_payload: str | None = None,
        will_qos: int = 1,
        will_retain: bool = True,
        username: str | None = None,
        password: str | None = None,
        tls: bool = False,
        keepalive: int = 60,
    ):
        self._broker_host = broker_host
        self._broker_port = broker_port
        self._keepalive = keepalive
        self._subscriptions = []  # list[tuple[str, int, callable | None]] — connect() 전 구독 요청 큐

        # CONNACK 수신 여부. connect() 반환은 TCP 연결까지만 보장하므로,
        # 인증 실패 같은 브로커측 거부는 이 이벤트로만 구분할 수 있다.
        self._connected = threading.Event()
        self._last_reason = None

        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
        )
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)

        if username is not None:
            self._client.username_pw_set(username, password)
        if tls:
            # 클라우드 브로커(HiveMQ/EMQX)용. 시스템 CA 로 서버 인증서를 검증한다.
            self._client.tls_set(cert_reqs=ssl.CERT_REQUIRED,
                                 tls_version=ssl.PROTOCOL_TLS_CLIENT)

        if will_topic is not None:
            self._client.will_set(
                will_topic, payload=will_payload, qos=will_qos, retain=will_retain
            )

    def _on_connect(self, client, userdata, connect_flags, reason_code, properties):
        """연결(또는 재연결) 성공 시 큐에 쌓인 구독을 전부 적용한다.

        connect() 이전에 subscribe()가 호출돼도 실제 구독이 누락되지 않게 하기 위함이다.
        연결이 실패한 경우(reason_code != 0)는 구독을 재생하지 않는다.
        """
        self._last_reason = reason_code
        if reason_code != 0:
            # 재접속 루프가 조용히 돌면 원인을 못 찾는다. 5 = not authorised 등.
            log.error("브로커 접속 거부 — %s:%s (reason_code=%s)",
                      self._broker_host, self._broker_port, reason_code)
            return
        self._connected.set()
        log.info("브로커 연결됨 — %s:%s", self._broker_host, self._broker_port)
        for topic, qos, callback in self._subscriptions:
            self._client.subscribe(topic, qos=qos)
            if callback is not None:
                self._client.message_callback_add(topic, callback)

    def _on_disconnect(self, client, userdata, *args):
        """끊김을 남긴다. paho 2.x 는 (flags, reason_code, properties) 를 넘긴다."""
        self._connected.clear()
        reason = args[1] if len(args) >= 2 else (args[0] if args else "?")
        log.warning("브로커 연결 끊김 (reason=%s) — 재접속 시도 중", reason)

    def connect(self):
        self._client.connect(self._broker_host, self._broker_port, self._keepalive)
        self._client.loop_start()

    def connect_async(self):
        """브로커가 아직 없어도 예외 없이 시작하고, 뜨면 자동으로 붙는다.

        connect() 는 브로커 부재 시 ConnectionRefusedError 로 즉시 죽는다. 상시
        구동되는 게이트웨이·웹 서버는 이쪽이 맞다.
        """
        self._client.connect_async(self._broker_host, self._broker_port, self._keepalive)
        self._client.loop_start()

    def wait_connected(self, timeout: float = 5.0) -> bool:
        """CONNACK 수신까지 최대 timeout 초 기다린다. 연결되면 True.

        고정 sleep 으로 '연결됐겠거니' 하고 넘어가면, 인증 실패·토픽 권한 문제를
        한참 뒤 '응답 없음' 으로 잘못 진단하게 된다.
        """
        return self._connected.wait(timeout)

    @property
    def is_connected(self) -> bool:
        return self._connected.is_set()

    @property
    def last_reason_code(self):
        """마지막 CONNACK 의 reason_code. 연결 실패 원인 표시에 쓴다."""
        return self._last_reason

    def disconnect(self):
        self._client.loop_stop()
        self._client.disconnect()
        self._connected.clear()

    def publish(self, topic: str, payload: str, qos: int = 0, retain: bool = False):
        return self._client.publish(topic, payload, qos=qos, retain=retain)

    def subscribe(self, topic: str, callback=None, qos: int = 1):
        """구독을 등록한다. 아직 연결되지 않았으면 큐에 쌓아두고 connect() 성공 시 적용한다."""
        self._subscriptions.append((topic, qos, callback))
        if self._client.is_connected():
            self._client.subscribe(topic, qos=qos)
            if callback is not None:
                self._client.message_callback_add(topic, callback)
