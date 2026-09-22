import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture
def client():
    main.broadcast_registry.clear()
    with TestClient(main.app) as c:
        yield c
    main.broadcast_registry.clear()


def test_broadcast_page_renders(client):
    response = client.get("/broadcast")
    assert response.status_code == 200
    assert "data-broadcast" in response.text


def test_create_channel_returns_id_and_pushes_list_to_subscribers(client):
    with client.websocket_connect("/ws/broadcast") as listener:
        listener.send_json({"type": "list"})
        initial = listener.receive_json()
        assert initial == {"type": "channel_list", "channels": []}

        with client.websocket_connect("/ws/broadcast") as master:
            master.send_json({"type": "create", "label": "UR3 시연"})
            created = master.receive_json()
            assert created["type"] == "created"
            channel_id = created["channel_id"]
            assert channel_id

            push = listener.receive_json()
            assert push == {
                "type": "channel_list",
                "channels": [{"channel_id": channel_id, "label": "UR3 시연"}],
            }


def test_join_notifies_master_with_viewer_id(client):
    with client.websocket_connect("/ws/broadcast") as master:
        master.send_json({"type": "create", "label": "UR3 시연"})
        channel_id = master.receive_json()["channel_id"]

        with client.websocket_connect("/ws/broadcast") as viewer:
            viewer.send_json({"type": "join", "channel_id": channel_id})
            joined = master.receive_json()
            assert joined["type"] == "viewer_joined"
            assert joined["viewer_id"]


def test_join_unknown_channel_returns_error(client):
    with client.websocket_connect("/ws/broadcast") as viewer:
        viewer.send_json({"type": "join", "channel_id": "no-such-id"})
        reply = viewer.receive_json()
        assert reply["type"] == "error"


def test_offer_answer_ice_relay_round_trip(client):
    with client.websocket_connect("/ws/broadcast") as master:
        master.send_json({"type": "create", "label": "UR3 시연"})
        channel_id = master.receive_json()["channel_id"]

        with client.websocket_connect("/ws/broadcast") as viewer:
            viewer.send_json({"type": "join", "channel_id": channel_id})
            viewer_id = master.receive_json()["viewer_id"]

            master.send_json({
                "type": "offer", "channel_id": channel_id,
                "viewer_id": viewer_id, "sdp": {"type": "offer", "sdp": "fake-offer"},
            })
            offer = viewer.receive_json()
            assert offer == {"type": "offer", "sdp": {"type": "offer", "sdp": "fake-offer"}}

            viewer.send_json({
                "type": "answer", "channel_id": channel_id,
                "sdp": {"type": "answer", "sdp": "fake-answer"},
            })
            answer = master.receive_json()
            assert answer == {
                "type": "answer", "viewer_id": viewer_id,
                "sdp": {"type": "answer", "sdp": "fake-answer"},
            }

            master.send_json({
                "type": "ice", "channel_id": channel_id,
                "viewer_id": viewer_id, "candidate": {"candidate": "fake-from-master"},
            })
            ice_to_viewer = viewer.receive_json()
            assert ice_to_viewer == {"type": "ice", "candidate": {"candidate": "fake-from-master"}}

            viewer.send_json({
                "type": "ice", "channel_id": channel_id,
                "candidate": {"candidate": "fake-from-viewer"},
            })
            ice_to_master = master.receive_json()
            assert ice_to_master == {
                "type": "ice", "viewer_id": viewer_id,
                "candidate": {"candidate": "fake-from-viewer"},
            }


def test_master_disconnect_closes_channel_and_notifies_viewer(client):
    with client.websocket_connect("/ws/broadcast") as master:
        master.send_json({"type": "create", "label": "UR3 시연"})
        channel_id = master.receive_json()["channel_id"]

        with client.websocket_connect("/ws/broadcast") as viewer:
            viewer.send_json({"type": "join", "channel_id": channel_id})
            master.receive_json()  # viewer_joined

            master.close()

            closed = viewer.receive_json()
            assert closed == {"type": "channel_closed", "channel_id": channel_id}

    assert main.broadcast_registry.get_channel(channel_id) is None


def test_viewer_disconnect_notifies_master_only(client):
    with client.websocket_connect("/ws/broadcast") as master:
        master.send_json({"type": "create", "label": "UR3 시연"})
        channel_id = master.receive_json()["channel_id"]

        with client.websocket_connect("/ws/broadcast") as viewer:
            viewer.send_json({"type": "join", "channel_id": channel_id})
            viewer_id = master.receive_json()["viewer_id"]

        left = master.receive_json()
        assert left == {"type": "viewer_left", "viewer_id": viewer_id}

        channel = main.broadcast_registry.get_channel(channel_id)
        assert channel is not None
        assert viewer_id not in channel.viewers


def test_explicit_close_removes_channel_and_keeps_socket_open(client):
    with client.websocket_connect("/ws/broadcast") as master:
        master.send_json({"type": "create", "label": "채널 1"})
        channel_id = master.receive_json()["channel_id"]

        with client.websocket_connect("/ws/broadcast") as viewer:
            viewer.send_json({"type": "join", "channel_id": channel_id})
            master.receive_json()  # viewer_joined

            master.send_json({"type": "close", "channel_id": channel_id})

            closed = viewer.receive_json()
            assert closed == {"type": "channel_closed", "channel_id": channel_id}

        assert main.broadcast_registry.get_channel(channel_id) is None

        master.send_json({"type": "create", "label": "채널 2"})
        second = master.receive_json()
        assert second["type"] == "created"
        assert second["channel_id"] != channel_id


def test_second_create_on_same_socket_closes_previous_channel(client):
    with client.websocket_connect("/ws/broadcast") as master:
        master.send_json({"type": "create", "label": "채널 1"})
        channel_id_1 = master.receive_json()["channel_id"]

        with client.websocket_connect("/ws/broadcast") as viewer:
            viewer.send_json({"type": "join", "channel_id": channel_id_1})
            master.receive_json()  # viewer_joined

            master.send_json({"type": "create", "label": "채널 2"})

            closed = viewer.receive_json()
            assert closed == {"type": "channel_closed", "channel_id": channel_id_1}

            created = master.receive_json()
            assert created["type"] == "created"
            channel_id_2 = created["channel_id"]
            assert channel_id_2 != channel_id_1

        assert main.broadcast_registry.get_channel(channel_id_1) is None
        assert main.broadcast_registry.get_channel(channel_id_2) is not None

    # 소켓이 완전히 닫히면 마지막(두번째) 채널도 정리된다 — 유령으로 남지 않는다.
    assert main.broadcast_registry.get_channel(channel_id_2) is None


def test_second_join_on_same_socket_replaces_previous_viewer_registration(client):
    with client.websocket_connect("/ws/broadcast") as master:
        master.send_json({"type": "create", "label": "UR3 시연"})
        channel_id = master.receive_json()["channel_id"]

        with client.websocket_connect("/ws/broadcast") as viewer:
            viewer.send_json({"type": "join", "channel_id": channel_id})
            viewer_id_1 = master.receive_json()["viewer_id"]

            viewer.send_json({"type": "join", "channel_id": channel_id})

            left = master.receive_json()
            assert left == {"type": "viewer_left", "viewer_id": viewer_id_1}

            joined_again = master.receive_json()
            assert joined_again["type"] == "viewer_joined"
            viewer_id_2 = joined_again["viewer_id"]
            assert viewer_id_2 != viewer_id_1

            channel = main.broadcast_registry.get_channel(channel_id)
            assert viewer_id_1 not in channel.viewers
            assert viewer_id_2 in channel.viewers

        # 뷰어 소켓이 끊기면 최신 등록(viewer_id_2)만 정리되고, 첫 등록은 이미
        # 정리됐으므로 다시 알림이 오지 않는다.
        left_final = master.receive_json()
        assert left_final == {"type": "viewer_left", "viewer_id": viewer_id_2}

        channel = main.broadcast_registry.get_channel(channel_id)
        assert channel is not None
        assert channel.viewers == {}
