"""UR3 진단 MQTT 핸들러. shared.mqtt_client.MQTTClient를 UR3_RCI_기능명세서.md
§4.1 토픽에 맞춰 감싼다. SID 디스패치(uds_server)는 이 모듈의 범위 밖이며,
on_request 콜백으로 연결한다."""
import logging

from shared import topics
from shared.mqtt_client import MQTTClient
from ur3 import uds_payload

log = logging.getLogger("rci.ur3")


class UR3MqttHandler:
    def __init__(
        self,
        broker_host: str = "localhost",
        broker_port: int = 1883,
        client_id: str = "ur3-rci",
        username: str | None = None,
        password: str | None = None,
        tls: bool = False,
    ):
        offline_status = uds_payload.build_status("offline", "disconnected")
        self._client = MQTTClient(
            client_id,
            broker_host,
            broker_port,
            will_topic=topics.UR3_DIAG_STATUS,
            will_payload=offline_status,
            will_qos=1,
            will_retain=True,
            username=username,
            password=password,
            tls=tls,
        )
        self.on_request = None
        self._client.subscribe(topics.UR3_DIAG_REQ, callback=self._handle_message, qos=1)

    def _handle_message(self, client, userdata, msg):
        """수신 요청을 파싱해 on_request 로 넘긴다.

        깨진 페이로드 하나가 게이트웨이 전체를 죽이면 안 된다 — paho 콜백에서
        예외가 새면 그 뒤 메시지 처리가 조용히 멈춘다. 파싱 실패는 삼키고 남긴다.
        """
        try:
            request = uds_payload.parse_request(msg.payload.decode("utf-8"))
        except (ValueError, KeyError, UnicodeDecodeError) as exc:
            log.warning("계약에 맞지 않는 요청 무시 (%s): %r", exc, msg.payload[:120])
            return
        if self.on_request is not None:
            self.on_request(request)

    def connect(self):
        self._client.connect()

    def connect_async(self):
        """브로커가 아직 없어도 죽지 않고 시작한다(상시 구동용)."""
        self._client.connect_async()

    def wait_connected(self, timeout: float = 5.0) -> bool:
        return self._client.wait_connected(timeout)

    @property
    def is_connected(self) -> bool:
        return self._client.is_connected

    @property
    def last_reason_code(self):
        return self._client.last_reason_code

    def disconnect(self):
        self._client.disconnect()

    def publish_response(self, request_id: str, raw: bytes):
        payload = uds_payload.build_response(request_id, raw)
        self._client.publish(topics.UR3_DIAG_RESP, payload, qos=1, retain=False)

    def publish_error(self, request_id: str, reason: str, message: str):
        payload = uds_payload.build_error(request_id, reason, message)
        self._client.publish(topics.UR3_DIAG_ERROR, payload, qos=1, retain=False)

    def publish_status(self, state: str, robot: str):
        payload = uds_payload.build_status(state, robot)
        self._client.publish(topics.UR3_DIAG_STATUS, payload, qos=1, retain=True)
