"""shared.mqtt_client.MQTTClient 단위 테스트. 실제 브로커 없이
paho.mqtt.client.Client를 모의 대체(가짜 브로커)해서 검증한다."""
from unittest.mock import MagicMock, patch

import paho.mqtt.client as mqtt

from shared.mqtt_client import MQTTClient


def _make_client_with_mock():
    """MQTTClient를 만들고, 내부에서 생성된 mock Client 인스턴스를 함께 반환한다."""
    with patch("shared.mqtt_client.mqtt.Client") as mock_client_cls:
        mock_instance = MagicMock()
        mock_instance.is_connected.return_value = False
        mock_client_cls.return_value = mock_instance
        client = MQTTClient("test-client")
        return client, mock_client_cls, mock_instance


def test_uses_callback_api_version_2():
    client, mock_client_cls, _ = _make_client_with_mock()

    _, kwargs = mock_client_cls.call_args
    assert kwargs.get("callback_api_version") == mqtt.CallbackAPIVersion.VERSION2


def test_publish_forwards_qos_and_retain():
    client, _, mock_instance = _make_client_with_mock()

    client.publish("minigit/resp/urrobot", '{"id":"u-0001"}', qos=1, retain=False)

    mock_instance.publish.assert_called_once_with(
        "minigit/resp/urrobot", '{"id":"u-0001"}', qos=1, retain=False
    )


def test_will_set_called_with_topic_and_payload():
    with patch("shared.mqtt_client.mqtt.Client") as mock_client_cls:
        mock_instance = MagicMock()
        mock_client_cls.return_value = mock_instance

        MQTTClient(
            "test-client",
            will_topic="minigit/status/rci-ur",
            will_payload='{"state":"offline","robot":"disconnected"}',
            will_qos=1,
            will_retain=True,
        )

        mock_instance.will_set.assert_called_once_with(
            "minigit/status/rci-ur",
            payload='{"state":"offline","robot":"disconnected"}',
            qos=1,
            retain=True,
        )


def test_will_set_not_called_when_no_will_topic():
    _, _, mock_instance = _make_client_with_mock()
    mock_instance.will_set.assert_not_called()


def test_subscribe_before_connect_is_queued_then_applied_on_connect():
    client, _, mock_instance = _make_client_with_mock()
    callback = MagicMock()

    # connect() 이전 subscribe() 호출 — 이 시점엔 실제 구독이 일어나면 안 된다
    client.subscribe("minigit/req/urrobot", callback=callback, qos=1)
    mock_instance.subscribe.assert_not_called()

    # 브로커가 on_connect를 호출했다고 가정 (reason_code=0은 성공)
    client._on_connect(mock_instance, None, MagicMock(), 0, MagicMock())

    mock_instance.subscribe.assert_called_once_with("minigit/req/urrobot", qos=1)
    mock_instance.message_callback_add.assert_called_once_with(
        "minigit/req/urrobot", callback
    )


def test_subscribe_after_connect_applies_immediately():
    client, _, mock_instance = _make_client_with_mock()
    mock_instance.is_connected.return_value = True
    callback = MagicMock()

    client.subscribe("minigit/req/urrobot", callback=callback, qos=1)

    mock_instance.subscribe.assert_called_once_with("minigit/req/urrobot", qos=1)
    mock_instance.message_callback_add.assert_called_once_with(
        "minigit/req/urrobot", callback
    )


def test_reconnect_delay_set_is_configured():
    _, _, mock_instance = _make_client_with_mock()
    mock_instance.reconnect_delay_set.assert_called_once_with(min_delay=1, max_delay=30)
