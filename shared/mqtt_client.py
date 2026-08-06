"""공통 MQTT 클라이언트 래퍼."""
import paho.mqtt.client as mqtt


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
    ):
        self._broker_host = broker_host
        self._broker_port = broker_port
        self._subscriptions = []  # list[tuple[str, int, callable | None]] — connect() 전 구독 요청 큐

        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
        )
        self._client.on_connect = self._on_connect
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)

        if will_topic is not None:
            self._client.will_set(
                will_topic, payload=will_payload, qos=will_qos, retain=will_retain
            )

    def _on_connect(self, client, userdata, connect_flags, reason_code, properties):
        """연결(또는 재연결) 성공 시 큐에 쌓인 구독을 전부 적용한다.

        connect() 이전에 subscribe()가 호출돼도 실제 구독이 누락되지 않게 하기 위함이다.
        """
        for topic, qos, callback in self._subscriptions:
            self._client.subscribe(topic, qos=qos)
            if callback is not None:
                self._client.message_callback_add(topic, callback)

    def connect(self):
        self._client.connect(self._broker_host, self._broker_port)
        self._client.loop_start()

    def disconnect(self):
        self._client.loop_stop()
        self._client.disconnect()

    def publish(self, topic: str, payload: str, qos: int = 0, retain: bool = False):
        return self._client.publish(topic, payload, qos=qos, retain=retain)

    def subscribe(self, topic: str, callback=None, qos: int = 1):
        """구독을 등록한다. 아직 연결되지 않았으면 큐에 쌓아두고 connect() 성공 시 적용한다."""
        self._subscriptions.append((topic, qos, callback))
        if self._client.is_connected():
            self._client.subscribe(topic, qos=qos)
            if callback is not None:
                self._client.message_callback_add(topic, callback)
