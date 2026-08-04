"""공통 MQTT 클라이언트 래퍼."""
import paho.mqtt.client as mqtt


class MQTTClient:
    def __init__(self, client_id: str, broker_host: str = "localhost", broker_port: int = 1883):
        self._client = mqtt.Client(client_id=client_id)
        self._broker_host = broker_host
        self._broker_port = broker_port

    def connect(self):
        self._client.connect(self._broker_host, self._broker_port)
        self._client.loop_start()

    def disconnect(self):
        self._client.loop_stop()
        self._client.disconnect()

    def publish(self, topic: str, payload: str):
        self._client.publish(topic, payload)

    def subscribe(self, topic: str, callback):
        self._client.subscribe(topic)
        self._client.message_callback_add(topic, callback)
