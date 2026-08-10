"""ur3.mqtt_handler.UR3MqttHandler 단위 테스트.
shared.mqtt_client.MQTTClient를 모의 대체(가짜 브로커)해서 검증한다."""
from unittest.mock import MagicMock, patch

from ur3.mqtt_handler import UR3MqttHandler


def _make_handler_with_mock():
    with patch("ur3.mqtt_handler.MQTTClient") as mock_client_cls:
        mock_instance = MagicMock()
        mock_client_cls.return_value = mock_instance
        handler = UR3MqttHandler()
        return handler, mock_client_cls, mock_instance


def test_constructs_with_offline_will():
    handler, mock_client_cls, _ = _make_handler_with_mock()

    _, kwargs = mock_client_cls.call_args
    assert kwargs["will_topic"] == "minigit/status/rci-ur"
    assert kwargs["will_qos"] == 1
    assert kwargs["will_retain"] is True

    import json

    will_payload = json.loads(kwargs["will_payload"])
    assert will_payload == {"state": "offline", "robot": "disconnected"}


def test_subscribes_to_req_topic_with_qos_1():
    handler, _, mock_instance = _make_handler_with_mock()

    mock_instance.subscribe.assert_called_once()
    args, kwargs = mock_instance.subscribe.call_args
    assert args[0] == "minigit/req/urrobot"
    assert kwargs["qos"] == 1


def test_publish_response_uses_resp_topic_qos_1_not_retained():
    handler, _, mock_instance = _make_handler_with_mock()

    handler.publish_response("u-0001", bytes([0x62, 0x01, 0x07, 0x07]))

    mock_instance.publish.assert_called_once_with(
        "minigit/resp/urrobot", '{"id": "u-0001", "type": "positive", "raw": "62 01 07 07"}',
        qos=1, retain=False,
    )


def test_publish_error_uses_error_topic_qos_1_not_retained():
    handler, _, mock_instance = _make_handler_with_mock()

    handler.publish_error("u-0003", "robot_unreachable", "로봇 무응답")

    mock_instance.publish.assert_called_once_with(
        "minigit/error/urrobot",
        '{"id": "u-0003", "type": "error", "reason": "robot_unreachable", "message": "로봇 무응답"}',
        qos=1, retain=False,
    )


def test_publish_status_uses_status_topic_qos_1_retained():
    handler, _, mock_instance = _make_handler_with_mock()

    handler.publish_status("online", "connected")

    mock_instance.publish.assert_called_once_with(
        "minigit/status/rci-ur", '{"state": "online", "robot": "connected"}',
        qos=1, retain=True,
    )


def test_on_request_callback_invoked_with_parsed_request():
    handler, _, _ = _make_handler_with_mock()
    received = []
    handler.on_request = received.append

    fake_msg = MagicMock()
    fake_msg.payload = b'{"id":"u-0001","raw":"22 01 01","timeout_ms":1000}'
    handler._handle_message(None, None, fake_msg)

    assert received == [{"id": "u-0001", "raw": bytes([0x22, 0x01, 0x01]), "timeout_ms": 1000}]


def test_malformed_payload_does_not_raise_into_paho_callback():
    """깨진 페이로드 하나로 콜백이 예외를 던지면 그 뒤 수신이 조용히 멈춘다."""
    handler, _, _ = _make_handler_with_mock()
    received = []
    handler.on_request = received.append

    for bad in (b"not json", b'{"raw":"22 01 01"}', b'{"id":"u-1","raw":"ZZ"}', b"\xff\xfe"):
        fake_msg = MagicMock()
        fake_msg.payload = bad
        handler._handle_message(None, None, fake_msg)  # 예외 없이 넘어가야 함

    assert received == []


def test_credentials_and_tls_forwarded_to_client():
    with patch("ur3.mqtt_handler.MQTTClient") as mock_client_cls:
        mock_client_cls.return_value = MagicMock()

        UR3MqttHandler(username="rci", password="secret", tls=True)

        _, kwargs = mock_client_cls.call_args
        assert kwargs["username"] == "rci"
        assert kwargs["password"] == "secret"
        assert kwargs["tls"] is True


def test_connection_state_delegates_to_client():
    handler, _, mock_instance = _make_handler_with_mock()
    mock_instance.wait_connected.return_value = True
    mock_instance.is_connected = True

    assert handler.wait_connected(1.5) is True
    mock_instance.wait_connected.assert_called_once_with(1.5)
    assert handler.is_connected is True

    handler.connect_async()
    mock_instance.connect_async.assert_called_once()


def test_message_ignored_when_on_request_not_set():
    handler, _, _ = _make_handler_with_mock()
    fake_msg = MagicMock()
    fake_msg.payload = b'{"id":"u-0001","raw":"22 01 01"}'

    handler._handle_message(None, None, fake_msg)  # 예외 없이 조용히 무시되어야 함


def test_connect_and_disconnect_delegate_to_client():
    handler, _, mock_instance = _make_handler_with_mock()

    handler.connect()
    mock_instance.connect.assert_called_once()

    handler.disconnect()
    mock_instance.disconnect.assert_called_once()


def test_handler_wires_real_mqtt_client_correctly():
    """UR3MqttHandler가 (모의 대체된) MQTTClient가 아니라 실제 MQTTClient를 통해
    paho 계층까지 올바른 인자로 연결되는지 검증한다. paho.mqtt.client.Client만
    모의 대체해서, MQTTClient.__init__ 시그니처가 실제로 검증되게 한다."""
    with patch("shared.mqtt_client.mqtt.Client") as mock_paho_client_cls:
        mock_paho_instance = MagicMock()
        mock_paho_instance.is_connected.return_value = True
        mock_paho_client_cls.return_value = mock_paho_instance

        UR3MqttHandler()

        # will_set이 올바른 LWT 토픽과 offline/disconnected 상태로 디코딩되는 payload로 호출됨
        mock_paho_instance.will_set.assert_called_once()
        args, kwargs = mock_paho_instance.will_set.call_args
        assert args[0] == "minigit/status/rci-ur"
        payload = kwargs.get("payload") or (args[1] if len(args) > 1 else None)
        import json

        assert json.loads(payload) == {"state": "offline", "robot": "disconnected"}

        # is_connected()가 True이므로 구독이 즉시 적용됨
        mock_paho_instance.subscribe.assert_called_once_with("minigit/req/urrobot", qos=1)
