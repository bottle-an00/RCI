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


# --------------------------------------------------------------------------- #
# 여러 마스터 · 여러 채널 동시 운영 — 이 기능의 핵심 요구사항("여러 강사가 각자
# 독립된 채널을 동시에")이 기존 테스트(전부 마스터 1 · 뷰어 1)에는 전혀 없었다.
# --------------------------------------------------------------------------- #

def test_two_masters_two_channels_both_appear_in_list(client):
    with client.websocket_connect("/ws/broadcast") as listener:
        listener.send_json({"type": "list"})
        listener.receive_json()  # 초기 빈 목록

        with client.websocket_connect("/ws/broadcast") as master_a, \
                client.websocket_connect("/ws/broadcast") as master_b:
            master_a.send_json({"type": "create", "label": "A 강사"})
            channel_a = master_a.receive_json()["channel_id"]
            listener.receive_json()  # A 만 있는 목록 푸시

            master_b.send_json({"type": "create", "label": "B 강사"})
            channel_b = master_b.receive_json()["channel_id"]
            push = listener.receive_json()

            ids = {c["channel_id"] for c in push["channels"]}
            assert ids == {channel_a, channel_b}


def test_viewer_join_only_notifies_that_channels_own_master(client):
    with client.websocket_connect("/ws/broadcast") as master_a, \
            client.websocket_connect("/ws/broadcast") as master_b:
        master_a.send_json({"type": "create", "label": "A 강사"})
        channel_a = master_a.receive_json()["channel_id"]
        master_b.send_json({"type": "create", "label": "B 강사"})
        master_b.receive_json()["channel_id"]

        with client.websocket_connect("/ws/broadcast") as viewer:
            viewer.send_json({"type": "join", "channel_id": channel_a})

            joined = master_a.receive_json()
            assert joined["type"] == "viewer_joined"

            # B 의 마스터는 아무 알림도 받지 않는다 — 아직 아무것도 안 보냈으므로
            # close() 시 소켓 버퍼가 비어 있어야 한다(수신 시도 시 예외 없이 통과).
            master_b.send_json({"type": "list"})  # 살아있는지 확인용 핑 대용
            reply = master_b.receive_json()
            assert reply["type"] == "channel_list"  # viewer_joined 가 아님


def test_closing_one_channel_does_not_affect_the_other(client):
    with client.websocket_connect("/ws/broadcast") as master_a, \
            client.websocket_connect("/ws/broadcast") as master_b:
        master_a.send_json({"type": "create", "label": "A 강사"})
        channel_a = master_a.receive_json()["channel_id"]
        master_b.send_json({"type": "create", "label": "B 강사"})
        channel_b = master_b.receive_json()["channel_id"]

        with client.websocket_connect("/ws/broadcast") as viewer_a, \
                client.websocket_connect("/ws/broadcast") as viewer_b:
            viewer_a.send_json({"type": "join", "channel_id": channel_a})
            master_a.receive_json()  # viewer_joined
            viewer_b.send_json({"type": "join", "channel_id": channel_b})
            master_b.receive_json()  # viewer_joined

            master_a.send_json({"type": "close", "channel_id": channel_a})

            closed = viewer_a.receive_json()
            assert closed == {"type": "channel_closed", "channel_id": channel_a}

            # B 채널은 영향받지 않는다 — 레지스트리에 그대로 남고, 새로 list 를
            # 구독해도 여전히 보인다.
            assert main.broadcast_registry.get_channel(channel_a) is None
            assert main.broadcast_registry.get_channel(channel_b) is not None

            with client.websocket_connect("/ws/broadcast") as fresh_listener:
                fresh_listener.send_json({"type": "list"})
                fresh = fresh_listener.receive_json()
                ids = {c["channel_id"] for c in fresh["channels"]}
                assert channel_b in ids
                assert channel_a not in ids


# --------------------------------------------------------------------------- #
# ice 채널 소속 검증 (Finding 5) — A 채널에 join 한 뷰어가 channel_id 만 B 로
# 바꿔 ice 를 보내면, 서버는 이 연결의 실제 joined_channel_id(A)와 다르므로
# 조용히 버려야 한다 — B 의 마스터에게 끼어들면 안 된다.
# --------------------------------------------------------------------------- #

def test_ice_with_mismatched_channel_id_is_dropped_not_relayed(client):
    with client.websocket_connect("/ws/broadcast") as master_a, \
            client.websocket_connect("/ws/broadcast") as master_b:
        master_a.send_json({"type": "create", "label": "A 강사"})
        channel_a = master_a.receive_json()["channel_id"]
        master_b.send_json({"type": "create", "label": "B 강사"})
        channel_b = master_b.receive_json()["channel_id"]

        with client.websocket_connect("/ws/broadcast") as viewer:
            viewer.send_json({"type": "join", "channel_id": channel_a})
            master_a.receive_json()  # viewer_joined

            # channel_a 에 join 한 뷰어가 channel_b 를 목적지로 속여 ice 를 보낸다.
            viewer.send_json({
                "type": "ice", "channel_id": channel_b,
                "candidate": {"candidate": "spoofed"},
            })

            # B 의 마스터에게는 아무것도 오지 않는다 — 대신 살아있는지 list 로 확인한다.
            master_b.send_json({"type": "list"})
            reply = master_b.receive_json()
            assert reply["type"] == "channel_list"  # ice 가 아님

            # 정상 경로(channel_a)는 여전히 살아있다 — 검증이 과하게 막지 않았는지 확인.
            viewer.send_json({
                "type": "ice", "channel_id": channel_a,
                "candidate": {"candidate": "legit"},
            })
            ice_to_master = master_a.receive_json()
            assert ice_to_master["type"] == "ice"
            assert ice_to_master["candidate"] == {"candidate": "legit"}
