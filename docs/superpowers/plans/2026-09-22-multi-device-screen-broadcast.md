# 화면 실시간 송출(멀티 채널 브로드캐스트) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 여러 강사(마스터)가 각자 채널을 열어 자기 화면을 학생 노트북에 WebRTC로 실시간 공유하고, 학생은 `/broadcast` 페이지에서 생방송 중인 채널 목록을 보고 골라 참여하는 기능을 `cloud/Codes/Cloud` 교육 플랫폼에 추가한다.

**Architecture:** FastAPI에 새 WebSocket 엔드포인트(`/ws/broadcast`)를 시그널링 전용으로 추가한다. 서버는 SDP offer/answer와 ICE candidate를 그대로 중계만 하고, 실제 영상은 마스터가 학생마다 맺는 `RTCPeerConnection`을 통해 P2P로 흐른다(메시 구조). 채널 상태는 `mqtt_bridge.MqttBridge`와 같은 패턴으로 프로세스 메모리에 둔다.

**Tech Stack:** FastAPI(WebSocket) + 순수 JS(WebRTC, `getDisplayMedia`) — 새 의존성 없음.

**Spec:** [docs/superpowers/specs/2026-09-22-multi-device-screen-broadcast-design.md](../specs/2026-09-22-multi-device-screen-broadcast-design.md)

## Global Constraints

- 화면(비디오)만 송출한다 — 음성(마이크/시스템 오디오)은 다루지 않는다.
- 같은 LAN 접속을 전제로 한다 — STUN/TURN 서버를 두지 않는다.
- 채널당 학생 10대 이하를 기준으로 한다(메시 구조 대역폭 전제).
- 인증/권한 체계를 두지 않는다(로컬망 신뢰 전제, 기존 플랫폼도 로그인 없음).
- WS 재연결 로직을 넣지 않는다 — 끊기면 학생은 목록 화면으로 돌아가 다시 고른다.
- 채널 상태는 프로세스 메모리에만 둔다 — 서버 재시작 시 모든 방송이 끊긴다(DB 불필요).
- 스펙의 시그널링 메시지 표에는 없지만, 스펙 §채널 수명주기 5번("학생 WS 종료 → 마스터에게 알려 해당 PeerConnection만 정리")을 구현하려면 서버→마스터 메시지가 하나 더 필요하다. 이 계획에서는 이를 `viewer_left {viewer_id}`로 정의해 추가한다(스펙 의도의 보충이지 범위 변경이 아니다).

---

### Task 1: BroadcastRegistry — 채널/뷰어 상태 관리 (순수 로직)

**Files:**
- Create: `cloud/Codes/Cloud/broadcast.py`
- Create: `cloud/Codes/Cloud/tests/conftest.py`
- Test: `cloud/Codes/Cloud/tests/test_broadcast_registry.py`

**Interfaces:**
- Produces: `broadcast.Channel` (필드: `channel_id: str`, `label: str`, `master`, `viewers: dict[str, Any]`, `created_at: datetime`), `broadcast.BroadcastRegistry` — 이후 Task 2가 그대로 쓴다.
  - `create_channel(label: str, master) -> Channel`
  - `get_channel(channel_id: str) -> Channel | None`
  - `remove_channel(channel_id: str) -> Channel | None`
  - `add_viewer(channel_id: str, viewer) -> str | None` (viewer_id 반환, 채널 없으면 None)
  - `remove_viewer(channel_id: str, viewer_id: str) -> None`
  - `list_channels() -> list[dict]` (각 원소 `{"channel_id":..., "label":...}`)
  - `add_list_subscriber(sub) -> None` / `remove_list_subscriber(sub) -> None` / `list_subscribers() -> list`
  - `clear() -> None` (테스트 전용 — 상태 초기화)

이 단계에서는 `master`/`viewer`/`sub` 자리에 실제 WebSocket이 아니라 아무 객체나 넣어도 된다 — 레지스트리는 이 값들을 들고 있기만 하고 메서드를 호출하지 않는다(전송은 Task 2 몫).

- [ ] **Step 1: 테스트용 sys.path 설정 작성**

`cloud/Codes/Cloud/tests/conftest.py`:

```python
"""pytest가 cloud/Codes/Cloud 를 sys.path에 포함시키도록 한다.

main.py 가 `import theory_content` 처럼 형제 모듈을 절대 임포트로 불러오므로,
테스트에서도 이 디렉터리가 sys.path에 있어야 `import broadcast`/`import main`이
동작한다(루트 tests/conftest.py가 리포지토리 루트를 넣는 것과 같은 이유).
"""
import os
import sys

_APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)
```

- [ ] **Step 2: 실패하는 테스트 작성**

`cloud/Codes/Cloud/tests/test_broadcast_registry.py`:

```python
import broadcast


def test_create_channel_assigns_id_and_stores_it():
    registry = broadcast.BroadcastRegistry()
    master = object()

    channel = registry.create_channel("강사 시연", master)

    assert channel.label == "강사 시연"
    assert channel.master is master
    assert registry.get_channel(channel.channel_id) is channel


def test_list_channels_reflects_created_channels():
    registry = broadcast.BroadcastRegistry()
    registry.create_channel("채널 A", object())
    registry.create_channel("채널 B", object())

    labels = sorted(c["label"] for c in registry.list_channels())

    assert labels == ["채널 A", "채널 B"]


def test_remove_channel_deletes_it():
    registry = broadcast.BroadcastRegistry()
    channel = registry.create_channel("채널 A", object())

    removed = registry.remove_channel(channel.channel_id)

    assert removed is channel
    assert registry.get_channel(channel.channel_id) is None


def test_remove_unknown_channel_returns_none():
    registry = broadcast.BroadcastRegistry()

    assert registry.remove_channel("no-such-id") is None


def test_add_viewer_registers_under_channel():
    registry = broadcast.BroadcastRegistry()
    channel = registry.create_channel("채널 A", object())
    viewer_ws = object()

    viewer_id = registry.add_viewer(channel.channel_id, viewer_ws)

    assert viewer_id is not None
    assert registry.get_channel(channel.channel_id).viewers[viewer_id] is viewer_ws


def test_add_viewer_to_unknown_channel_returns_none():
    registry = broadcast.BroadcastRegistry()

    assert registry.add_viewer("no-such-id", object()) is None


def test_remove_viewer_leaves_other_viewers_intact():
    registry = broadcast.BroadcastRegistry()
    channel = registry.create_channel("채널 A", object())
    viewer_a = registry.add_viewer(channel.channel_id, object())
    viewer_b = registry.add_viewer(channel.channel_id, object())

    registry.remove_viewer(channel.channel_id, viewer_a)

    remaining = registry.get_channel(channel.channel_id).viewers
    assert viewer_a not in remaining
    assert viewer_b in remaining


def test_list_subscribers_add_and_remove():
    registry = broadcast.BroadcastRegistry()
    sub = object()

    registry.add_list_subscriber(sub)
    assert sub in registry.list_subscribers()

    registry.remove_list_subscriber(sub)
    assert sub not in registry.list_subscribers()
```

- [ ] **Step 3: 테스트 실행 → 실패 확인**

Run: `pytest cloud/Codes/Cloud/tests/test_broadcast_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'broadcast'`

- [ ] **Step 4: `broadcast.py` 최소 구현**

`cloud/Codes/Cloud/broadcast.py`:

```python
"""화면 실시간 송출 — 채널 레지스트리 + WebSocket 시그널링 중계.

여러 강사(마스터)가 각자 채널을 열고, 학생(뷰어)이 채널을 골라 참여한다.
이 모듈은 SDP/ICE 내용을 해석하지 않고 그대로 중계만 한다 — 실제 영상은
WebRTC로 P2P 전송되고, 여기는 연결을 맺기 위한 시그널링 경로다.

설계: docs/superpowers/specs/2026-09-22-multi-device-screen-broadcast-design.md
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

log = logging.getLogger("rci.broadcast")


@dataclass
class Channel:
    channel_id: str
    label: str
    master: Any
    viewers: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)


class BroadcastRegistry:
    """프로세스 메모리에 채널 상태를 둔다 (mqtt_bridge.MqttBridge 와 같은 패턴).

    서버가 재시작되면 모든 방송도 함께 끊긴다 — 별도 영속화는 하지 않는다.
    """

    def __init__(self) -> None:
        self._channels: dict[str, Channel] = {}
        self._list_subscribers: set = set()

    def create_channel(self, label: str, master: Any) -> Channel:
        channel_id = uuid.uuid4().hex
        channel = Channel(channel_id=channel_id, label=label, master=master)
        self._channels[channel_id] = channel
        return channel

    def get_channel(self, channel_id: str) -> Channel | None:
        return self._channels.get(channel_id)

    def remove_channel(self, channel_id: str) -> Channel | None:
        return self._channels.pop(channel_id, None)

    def add_viewer(self, channel_id: str, viewer: Any) -> str | None:
        channel = self._channels.get(channel_id)
        if channel is None:
            return None
        viewer_id = uuid.uuid4().hex
        channel.viewers[viewer_id] = viewer
        return viewer_id

    def remove_viewer(self, channel_id: str, viewer_id: str) -> None:
        channel = self._channels.get(channel_id)
        if channel is not None:
            channel.viewers.pop(viewer_id, None)

    def list_channels(self) -> list[dict]:
        return [{"channel_id": c.channel_id, "label": c.label} for c in self._channels.values()]

    def add_list_subscriber(self, sub: Any) -> None:
        self._list_subscribers.add(sub)

    def remove_list_subscriber(self, sub: Any) -> None:
        self._list_subscribers.discard(sub)

    def list_subscribers(self) -> list:
        return list(self._list_subscribers)

    def clear(self) -> None:
        """테스트 전용 — 레지스트리를 초기 상태로 되돌린다."""
        self._channels.clear()
        self._list_subscribers.clear()
```

- [ ] **Step 5: 테스트 실행 → 통과 확인**

Run: `pytest cloud/Codes/Cloud/tests/test_broadcast_registry.py -v`
Expected: PASS (8 passed)

- [ ] **Step 6: 커밋**

```bash
git add cloud/Codes/Cloud/broadcast.py cloud/Codes/Cloud/tests/conftest.py cloud/Codes/Cloud/tests/test_broadcast_registry.py
git commit -m "feat(broadcast): BroadcastRegistry 채널/뷰어 상태 관리 추가"
```

---

### Task 2: WS 시그널링 디스패처 + main.py 연결

**Files:**
- Modify: `cloud/Codes/Cloud/broadcast.py` (Task 1에서 만든 파일에 이어 씀)
- Modify: `cloud/Codes/Cloud/main.py:29` (import에 `WebSocket` 추가)
- Modify: `cloud/Codes/Cloud/main.py:36-38` (import 블록에 `import broadcast` 추가)
- Modify: `cloud/Codes/Cloud/main.py:44` (`bridge = MqttBridge(...)` 다음 줄에 레지스트리 인스턴스화)
- Modify: `cloud/Codes/Cloud/main.py:1867-1873` (`search()` 라우트와 `# --- MQTT API ---` 주석 사이에 두 라우트 삽입 — `/{target_id}` 캐치올보다 반드시 먼저)
- Create: `cloud/Codes/Cloud/templates/broadcast.html` (최소 스텁 — 전체 UI는 Task 3)
- Test: `cloud/Codes/Cloud/tests/test_broadcast_ws.py`

**Interfaces:**
- Consumes: Task 1의 `broadcast.BroadcastRegistry`, `broadcast.Channel`.
- Produces: `broadcast.handle_connection(websocket, registry) -> None` (async) — Task 4(JS)가 이 프로토콜에 맞춰 메시지를 보낸다. `main.broadcast_registry`(싱글턴), 라우트 `GET /broadcast`, `WS /ws/broadcast`.

**시그널링 프로토콜** (클라이언트→서버 `type`: `create`/`list`/`join`/`offer`/`answer`/`ice`/`close`, 서버→클라이언트 `type`: `created`/`channel_list`/`viewer_joined`/`offer`/`answer`/`ice`/`viewer_left`/`channel_closed`/`error`)는 스펙 §시그널링 프로토콜 + 본 계획의 Global Constraints 보충사항을 그대로 따른다.

- [ ] **Step 1: 최소 템플릿 스텁 작성** (라우트 테스트가 200을 받으려면 템플릿이 있어야 한다)

`cloud/Codes/Cloud/templates/broadcast.html`:

```html
{% extends "base_shell.html" %}
{% block title %}RCI · 화면 실시간 송출{% endblock %}
{% block content %}
<div class="broadcast" data-broadcast></div>
{% endblock %}
```

- [ ] **Step 2: 실패하는 통합 테스트 작성**

`cloud/Codes/Cloud/tests/test_broadcast_ws.py`:

```python
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
```

- [ ] **Step 3: 테스트 실행 → 실패 확인**

Run: `pytest cloud/Codes/Cloud/tests/test_broadcast_ws.py -v`
Expected: FAIL — `AttributeError: module 'main' has no attribute 'broadcast_registry'` (또는 라우트 404)

- [ ] **Step 4: `handle_connection` 구현 — `broadcast.py`에 이어서 작성**

`cloud/Codes/Cloud/broadcast.py` 맨 위 import 블록을 다음과 같이 바꾼다(Task 1에서 쓴 `from typing import Any` 아래에 fastapi import를 추가):

```python
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
```

그리고 파일 끝(Task 1의 `BroadcastRegistry` 클래스 뒤)에 다음을 추가:

```python
async def _safe_send(websocket: Any, payload: dict) -> None:
    """상대가 이미 끊긴 상태에서 보내다 실패해도 다른 연결에 영향 주지 않는다."""
    try:
        await websocket.send_json(payload)
    except Exception:
        log.debug("broadcast: 전송 실패(이미 끊긴 연결로 추정) type=%s", payload.get("type"))


async def _push_channel_list(registry: BroadcastRegistry) -> None:
    payload = {"type": "channel_list", "channels": registry.list_channels()}
    for sub in registry.list_subscribers():
        await _safe_send(sub, payload)


async def _close_hosted_channel(registry: BroadcastRegistry, channel_id: str) -> None:
    channel = registry.remove_channel(channel_id)
    if channel is None:
        return
    for viewer_ws in channel.viewers.values():
        await _safe_send(viewer_ws, {"type": "channel_closed", "channel_id": channel_id})


async def handle_connection(websocket: WebSocket, registry: BroadcastRegistry) -> None:
    """WS 연결 하나의 전체 수명 — 역할(마스터/뷰어/목록 구독자)은 첫 메시지로 정해진다.

    한 연결이 `list` 로 목록을 구독한 채로 나중에 `join` 도 보낼 수 있다(학생이
    목록 화면에서 채널을 고르는 흐름과 맞춘다) — 그래서 역할별 상태를 모두
    지역 변수로 들고, 종료 시 해당되는 것만 정리한다.
    """
    await websocket.accept()

    hosted_channel_id: str | None = None
    joined_channel_id: str | None = None
    viewer_id: str | None = None
    is_list_subscriber = False

    try:
        while True:
            msg = await websocket.receive_json()
            mtype = msg.get("type")

            if mtype == "create":
                channel = registry.create_channel(msg.get("label", ""), websocket)
                hosted_channel_id = channel.channel_id
                await websocket.send_json({"type": "created", "channel_id": channel.channel_id})
                await _push_channel_list(registry)

            elif mtype == "list":
                is_list_subscriber = True
                registry.add_list_subscriber(websocket)
                await websocket.send_json(
                    {"type": "channel_list", "channels": registry.list_channels()}
                )

            elif mtype == "join":
                channel = registry.get_channel(msg.get("channel_id", ""))
                if channel is None:
                    await websocket.send_json(
                        {"type": "error", "message": "채널을 찾을 수 없습니다"}
                    )
                    continue
                viewer_id = registry.add_viewer(channel.channel_id, websocket)
                joined_channel_id = channel.channel_id
                await _safe_send(channel.master, {"type": "viewer_joined", "viewer_id": viewer_id})

            elif mtype == "offer":
                channel = registry.get_channel(msg.get("channel_id", ""))
                if channel is None or channel.master is not websocket:
                    await websocket.send_json(
                        {"type": "error", "message": "채널을 찾을 수 없습니다"}
                    )
                    continue
                target = channel.viewers.get(msg.get("viewer_id", ""))
                if target is not None:
                    await _safe_send(target, {"type": "offer", "sdp": msg.get("sdp")})

            elif mtype == "answer":
                channel = registry.get_channel(joined_channel_id or "")
                if channel is not None:
                    await _safe_send(
                        channel.master,
                        {"type": "answer", "viewer_id": viewer_id, "sdp": msg.get("sdp")},
                    )

            elif mtype == "ice":
                channel = registry.get_channel(msg.get("channel_id", ""))
                if channel is None:
                    continue
                if channel.master is websocket:
                    target = channel.viewers.get(msg.get("viewer_id", ""))
                    if target is not None:
                        await _safe_send(target, {"type": "ice", "candidate": msg.get("candidate")})
                else:
                    await _safe_send(
                        channel.master,
                        {"type": "ice", "viewer_id": viewer_id, "candidate": msg.get("candidate")},
                    )

            elif mtype == "close":
                if hosted_channel_id is not None:
                    await _close_hosted_channel(registry, hosted_channel_id)
                    hosted_channel_id = None
                    await _push_channel_list(registry)

    except WebSocketDisconnect:
        pass
    finally:
        if hosted_channel_id is not None:
            await _close_hosted_channel(registry, hosted_channel_id)
            await _push_channel_list(registry)
        if joined_channel_id is not None and viewer_id is not None:
            registry.remove_viewer(joined_channel_id, viewer_id)
            channel = registry.get_channel(joined_channel_id)
            if channel is not None:
                await _safe_send(channel.master, {"type": "viewer_left", "viewer_id": viewer_id})
        if is_list_subscriber:
            registry.remove_list_subscriber(websocket)
```

- [ ] **Step 5: `main.py` 연결**

`cloud/Codes/Cloud/main.py:29` — fastapi import에 `WebSocket` 추가:

```python
from fastapi import FastAPI, HTTPException, Request, WebSocket
```

`cloud/Codes/Cloud/main.py:36-38` 부근 — 기존 import 블록:

```python
import theory_content
import visit_log
from mqtt_bridge import BridgeError, BrokerConfig, MqttBridge, RequestTimeout
```

다음과 같이 수정:

```python
import broadcast
import theory_content
import visit_log
from mqtt_bridge import BridgeError, BrokerConfig, MqttBridge, RequestTimeout
```

`cloud/Codes/Cloud/main.py:44` 부근 — 기존:

```python
bridge = MqttBridge(BrokerConfig.from_env())
```

다음과 같이 수정:

```python
bridge = MqttBridge(BrokerConfig.from_env())
broadcast_registry = broadcast.BroadcastRegistry()
```

`cloud/Codes/Cloud/main.py`의 `search()` 라우트(1867-1873행)와 `# --- MQTT API ---` 주석 블록(1875행) 사이에 삽입:

```python
@app.get("/broadcast", response_class=HTMLResponse)
def broadcast_page(request: Request):
    """강사 화면 실시간 공유 — 대상(target)과 무관한 독립 화면.

    `/{target_id}` 캐치올보다 먼저 선언해야 한다(survey/search 와 같은 이유).
    """
    return templates.TemplateResponse(
        request, "broadcast.html",
        {"bottom_nav": BOTTOM_NAV, "status": "화면 실시간 송출",
         "crumbs": [{"text": "화면 실시간 송출", "tier": "content"}]},
    )


@app.websocket("/ws/broadcast")
async def ws_broadcast(websocket: WebSocket):
    await broadcast.handle_connection(websocket, broadcast_registry)
```

- [ ] **Step 6: 테스트 실행 → 통과 확인**

Run: `pytest cloud/Codes/Cloud/tests/test_broadcast_ws.py -v`
Expected: PASS (8 passed)

- [ ] **Step 7: 기존 테스트 회귀 확인**

Run: `pytest cloud/Codes/Cloud/tests -v`
Expected: PASS (Task 1 + Task 2 테스트 모두 통과)

- [ ] **Step 8: 커밋**

```bash
git add cloud/Codes/Cloud/broadcast.py cloud/Codes/Cloud/main.py cloud/Codes/Cloud/templates/broadcast.html cloud/Codes/Cloud/tests/test_broadcast_ws.py
git commit -m "feat(broadcast): WS 시그널링 디스패처 + /broadcast 라우트 연결"
```

---

### Task 3: `/broadcast` 페이지 UI (템플릿 + CSS)

**Files:**
- Modify: `cloud/Codes/Cloud/templates/broadcast.html` (Task 2의 스텁을 전체 마크업으로 교체)
- Modify: `cloud/Codes/Cloud/static/css/styles.css` (파일 끝에 `.broadcast__*` 섹션 추가)

**Interfaces:**
- Consumes: 없음(서버 라우트는 Task 2에서 이미 연결됨).
- Produces: Task 4가 사용할 `data-broadcast-*` 속성들 — `data-broadcast`, `data-broadcast-list`, `data-broadcast-host`, `data-broadcast-view`, `data-broadcast-channels`, `data-broadcast-empty`, `data-broadcast-start-mode`, `data-broadcast-label`, `data-broadcast-go-live`, `data-broadcast-cancel-host`, `data-broadcast-live`, `data-broadcast-viewer-count`, `data-broadcast-stop`, `data-broadcast-host-error`, `data-broadcast-back`, `data-broadcast-view-label`, `data-broadcast-video`, `data-broadcast-view-error`.

이 태스크에는 서버 테스트가 없다(마크업/스타일 변경) — 이미 있는 `test_broadcast_page_renders`가 여전히 통과하는지만 회귀 확인하고, 나머지는 브라우저로 육안 확인한다.

- [ ] **Step 1: 전체 템플릿 작성**

`cloud/Codes/Cloud/templates/broadcast.html` 전체를 다음으로 교체:

```html
{% extends "base_shell.html" %}
{% block title %}RCI · 화면 실시간 송출{% endblock %}

{% block content %}
{# 목록/방송 시작/시청 3개 섹션을 한 페이지에 두고, static/js/broadcast.js 가
   hidden 속성으로 전환한다. 대상(target)과 무관한 독립 화면이라 target 관련
   컨텍스트 변수는 주지 않는다(partials/_subhead.html 이 없는 경우를 처리한다). #}
<div class="broadcast" data-broadcast>

  <section class="broadcast__list" data-broadcast-list>
    <div class="broadcast__list-head">
      <h1 class="broadcast__title">생방송 중인 채널</h1>
      <button class="btn btn--primary" type="button" data-broadcast-start-mode>화면 공유 시작</button>
    </div>
    <ul class="broadcast__channels" data-broadcast-channels></ul>
    <p class="broadcast__empty" data-broadcast-empty>현재 생방송 중인 채널이 없습니다.</p>
  </section>

  <section class="broadcast__host" data-broadcast-host hidden>
    <h1 class="broadcast__title">화면 공유 시작</h1>
    <div class="broadcast__field">
      <label for="broadcast-label">채널 이름</label>
      <input type="text" id="broadcast-label" data-broadcast-label
             placeholder="예: UR3 강제구동 시연" maxlength="60" autocomplete="off">
    </div>
    <div class="broadcast__actions">
      <button class="btn btn--ghost" type="button" data-broadcast-cancel-host>취소</button>
      <button class="btn btn--primary" type="button" data-broadcast-go-live>공유 시작</button>
    </div>
    <div class="broadcast__live" data-broadcast-live hidden>
      <p><b data-broadcast-viewer-count>0</b>명 시청 중</p>
      <button class="btn btn--stop" type="button" data-broadcast-stop>방송 종료</button>
    </div>
    <p class="broadcast__error" data-broadcast-host-error hidden></p>
  </section>

  <section class="broadcast__view" data-broadcast-view hidden>
    <div class="broadcast__view-head">
      <button class="btn btn--ghost" type="button" data-broadcast-back>‹ 목록으로</button>
      <span data-broadcast-view-label></span>
    </div>
    <video class="broadcast__video" data-broadcast-video autoplay playsinline></video>
    <p class="broadcast__error" data-broadcast-view-error hidden></p>
  </section>

</div>
{% endblock %}

{% block scripts %}
{{ super() }}
<script src="{{ asset('js/broadcast.js') }}"></script>
{% endblock %}
```

- [ ] **Step 2: CSS 추가**

`cloud/Codes/Cloud/static/css/styles.css` 맨 끝에 추가:

```css

/* =========================================================================
   화면 실시간 송출 — templates/broadcast.html · static/js/broadcast.js
   목록/방송 시작/시청 3개 섹션을 한 페이지에 두고 JS 가 hidden 속성으로 전환한다.
   ========================================================================= */
.broadcast {
  flex: 1; overflow-y: auto; background: #e6e9ee; padding: 22px 26px;
  display: flex; justify-content: center; align-items: flex-start;
}
.broadcast__list, .broadcast__host, .broadcast__view {
  width: 100%; max-width: 900px;
  background: #fff; border: 1px solid var(--border); padding: 26px 30px 24px;
}
.broadcast__title { font-size: 19px; font-weight: 700; margin: 0; }

.broadcast__list-head {
  display: flex; align-items: center; justify-content: space-between; margin-bottom: 18px;
}
.broadcast__channels { list-style: none; margin: 0; padding: 0; }
.broadcast__channel { border-bottom: 1px solid var(--border); }
.broadcast__channel-btn {
  width: 100%; text-align: left; font: inherit; font-size: 14px; font-weight: 600;
  padding: 14px 4px; background: none; border: none; color: var(--ink); cursor: pointer;
}
.broadcast__channel-btn:hover { color: var(--brand-blue); }
.broadcast__empty { color: var(--muted); font-size: 13.5px; padding: 20px 4px; }

.broadcast__field { display: flex; flex-direction: column; gap: 6px; margin-bottom: 18px; }
.broadcast__field label { font-size: 12.5px; font-weight: 600; color: var(--muted); }
.broadcast__field input {
  font: inherit; font-size: 14px; padding: 9px 11px;
  border: 1px solid var(--border); background: #fff; color: var(--ink);
}
.broadcast__field input:focus { outline: none; border-color: var(--brand-blue); }
.broadcast__actions { display: flex; gap: 10px; justify-content: flex-end; }
.broadcast__live {
  margin-top: 18px; display: flex; align-items: center; justify-content: space-between;
}
.broadcast__error { margin-top: 12px; font-size: 13px; color: var(--pdf-tag); }

.broadcast__view-head {
  display: flex; align-items: center; gap: 14px; margin-bottom: 14px; font-weight: 600;
}
.broadcast__video {
  width: 100%; background: #14161b; aspect-ratio: 16 / 9; display: block;
}
```

- [ ] **Step 3: 회귀 테스트 확인**

Run: `pytest cloud/Codes/Cloud/tests/test_broadcast_ws.py::test_broadcast_page_renders -v`
Expected: PASS

- [ ] **Step 4: 브라우저로 육안 확인**

```bash
cd cloud/Codes/Cloud
uvicorn main:app --reload --port 8123
```

`http://localhost:8123/broadcast` 접속 후 확인:
- "생방송 중인 채널" 제목과 "현재 생방송 중인 채널이 없습니다." 문구가 보인다.
- "화면 공유 시작" 버튼은 보이지만 클릭해도 아직 반응 없음(JS는 Task 4에서 붙인다) — 정상.

- [ ] **Step 5: 커밋**

```bash
git add cloud/Codes/Cloud/templates/broadcast.html cloud/Codes/Cloud/static/css/styles.css
git commit -m "feat(broadcast): /broadcast 페이지 UI 마크업 + 스타일 추가"
```

---

### Task 4: `broadcast.js` — 클라이언트 WebRTC 로직 + 수동 종단 검증

**Files:**
- Create: `cloud/Codes/Cloud/static/js/broadcast.js`
- Modify (참고용, 변경 없음): `cloud/Codes/Cloud/templates/broadcast.html` (이미 `{{ asset('js/broadcast.js') }}` 로 참조 중)

**Interfaces:**
- Consumes: Task 2의 `/ws/broadcast` 시그널링 프로토콜, Task 3의 `data-broadcast-*` 마크업.
- Produces: 없음(최종 사용자 대상 클라이언트 코드).

이 저장소에는 JS 테스트 도구가 없다(스펙의 "테스트 전략"과 동일하게, 실제 WebRTC 송출은 자동화하지 않고 브라우저로 직접 확인한다). 그래서 이 태스크는 "테스트 먼저" 대신 "구현 → 수동 확인" 순서로 진행한다.

- [ ] **Step 1: `broadcast.js` 전체 작성**

`cloud/Codes/Cloud/static/js/broadcast.js`:

```javascript
/* 화면 실시간 송출 — 강사(마스터) 시연 화면을 학생 노트북에 WebRTC로 공유.
 *
 * 서버(/ws/broadcast)는 SDP/ICE 를 그대로 중계만 한다 — 영상은 P2P 로 흐른다.
 * 프로토콜은 docs/superpowers/specs/2026-09-22-multi-device-screen-broadcast-design.md
 * 와 그 계획 문서(Global Constraints)의 viewer_left 보충을 따른다.
 */
(function () {
  "use strict";

  var root = document.querySelector("[data-broadcast]");
  if (!root) return;

  var listSection = root.querySelector("[data-broadcast-list]");
  var hostSection = root.querySelector("[data-broadcast-host]");
  var viewSection = root.querySelector("[data-broadcast-view]");

  var channelsEl = root.querySelector("[data-broadcast-channels]");
  var emptyEl = root.querySelector("[data-broadcast-empty]");
  var startModeBtn = root.querySelector("[data-broadcast-start-mode]");

  var labelInput = root.querySelector("[data-broadcast-label]");
  var goLiveBtn = root.querySelector("[data-broadcast-go-live]");
  var cancelHostBtn = root.querySelector("[data-broadcast-cancel-host]");
  var liveEl = root.querySelector("[data-broadcast-live]");
  var viewerCountEl = root.querySelector("[data-broadcast-viewer-count]");
  var stopBtn = root.querySelector("[data-broadcast-stop]");
  var hostErrorEl = root.querySelector("[data-broadcast-host-error]");

  var backBtn = root.querySelector("[data-broadcast-back]");
  var viewLabelEl = root.querySelector("[data-broadcast-view-label]");
  var videoEl = root.querySelector("[data-broadcast-video]");
  var viewErrorEl = root.querySelector("[data-broadcast-view-error]");

  function wsUrl() {
    var proto = location.protocol === "https:" ? "wss:" : "ws:";
    return proto + "//" + location.host + "/ws/broadcast";
  }

  function showSection(section) {
    [listSection, hostSection, viewSection].forEach(function (el) {
      el.hidden = el !== section;
    });
  }

  /* ---- 목록 모드 — 페이지 진입 즉시 연결해 생방송 목록을 구독한다 ---- */

  var listSocket = null;

  function renderChannels(channels) {
    channelsEl.innerHTML = "";
    emptyEl.hidden = channels.length > 0;
    channels.forEach(function (ch) {
      var li = document.createElement("li");
      li.className = "broadcast__channel";
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "broadcast__channel-btn";
      btn.textContent = ch.label || "(이름 없음)";
      btn.addEventListener("click", function () {
        joinChannel(ch.channel_id, ch.label);
      });
      li.appendChild(btn);
      channelsEl.appendChild(li);
    });
  }

  function connectList() {
    if (listSocket) return;
    listSocket = new WebSocket(wsUrl());
    listSocket.addEventListener("open", function () {
      listSocket.send(JSON.stringify({ type: "list" }));
    });
    listSocket.addEventListener("message", function (event) {
      var msg = JSON.parse(event.data);
      if (msg.type === "channel_list") renderChannels(msg.channels || []);
    });
  }

  connectList();

  /* ---- 방송 시작 모드 (마스터) ---- */

  var hostSocket = null;
  var hostChannelId = null;
  var screenStream = null;
  var peers = {}; // viewer_id -> RTCPeerConnection

  startModeBtn.addEventListener("click", function () {
    labelInput.value = "";
    liveEl.hidden = true;
    hostErrorEl.hidden = true;
    showSection(hostSection);
  });

  cancelHostBtn.addEventListener("click", function () {
    showSection(listSection);
  });

  function updateViewerCount() {
    viewerCountEl.textContent = String(Object.keys(peers).length);
  }

  function closeAllPeers() {
    Object.keys(peers).forEach(function (vid) {
      peers[vid].close();
    });
    peers = {};
    updateViewerCount();
  }

  function stopBroadcast() {
    if (hostSocket && hostChannelId) {
      try {
        hostSocket.send(JSON.stringify({ type: "close", channel_id: hostChannelId }));
      } catch (e) {
        /* 이미 끊긴 경우 무시 */
      }
    }
    closeAllPeers();
    if (screenStream) {
      screenStream.getTracks().forEach(function (t) {
        t.stop();
      });
      screenStream = null;
    }
    if (hostSocket) {
      hostSocket.close();
      hostSocket = null;
    }
    hostChannelId = null;
    showSection(listSection);
  }

  function createPeerForViewer(viewerId) {
    var pc = new RTCPeerConnection();
    peers[viewerId] = pc;
    screenStream.getTracks().forEach(function (track) {
      pc.addTrack(track, screenStream);
    });
    pc.addEventListener("icecandidate", function (event) {
      if (event.candidate) {
        hostSocket.send(
          JSON.stringify({
            type: "ice",
            channel_id: hostChannelId,
            viewer_id: viewerId,
            candidate: event.candidate,
          })
        );
      }
    });
    pc.createOffer()
      .then(function (offer) {
        return pc.setLocalDescription(offer);
      })
      .then(function () {
        hostSocket.send(
          JSON.stringify({
            type: "offer",
            channel_id: hostChannelId,
            viewer_id: viewerId,
            sdp: pc.localDescription,
          })
        );
      });
    updateViewerCount();
    return pc;
  }

  goLiveBtn.addEventListener("click", function () {
    hostErrorEl.hidden = true;
    if (!navigator.mediaDevices || !navigator.mediaDevices.getDisplayMedia) {
      hostErrorEl.textContent = "이 브라우저는 화면 공유를 지원하지 않습니다.";
      hostErrorEl.hidden = false;
      return;
    }
    navigator.mediaDevices
      .getDisplayMedia({ video: true })
      .then(function (stream) {
        screenStream = stream;
        screenStream.getVideoTracks()[0].addEventListener("ended", stopBroadcast);

        hostSocket = new WebSocket(wsUrl());
        hostSocket.addEventListener("open", function () {
          hostSocket.send(
            JSON.stringify({
              type: "create",
              label: labelInput.value.trim() || "이름 없는 방송",
            })
          );
        });
        hostSocket.addEventListener("message", function (event) {
          var msg = JSON.parse(event.data);
          if (msg.type === "created") {
            hostChannelId = msg.channel_id;
            liveEl.hidden = false;
            updateViewerCount();
          } else if (msg.type === "viewer_joined") {
            createPeerForViewer(msg.viewer_id);
          } else if (msg.type === "answer") {
            var pc = peers[msg.viewer_id];
            if (pc) pc.setRemoteDescription(msg.sdp);
          } else if (msg.type === "ice") {
            var pc2 = peers[msg.viewer_id];
            if (pc2 && msg.candidate) pc2.addIceCandidate(msg.candidate);
          } else if (msg.type === "viewer_left") {
            var pc3 = peers[msg.viewer_id];
            if (pc3) {
              pc3.close();
              delete peers[msg.viewer_id];
              updateViewerCount();
            }
          }
        });
      })
      .catch(function () {
        hostErrorEl.textContent = "화면 공유가 취소되었거나 권한이 거부되었습니다.";
        hostErrorEl.hidden = false;
      });
  });

  stopBtn.addEventListener("click", stopBroadcast);

  /* ---- 시청 모드 (뷰어) ---- */

  var viewSocket = null;
  var viewPeer = null;

  function leaveView() {
    if (viewPeer) {
      viewPeer.close();
      viewPeer = null;
    }
    if (viewSocket) {
      viewSocket.close();
      viewSocket = null;
    }
    videoEl.srcObject = null;
    showSection(listSection);
  }

  function joinChannel(channelId, label) {
    viewErrorEl.hidden = true;
    viewLabelEl.textContent = label || "";
    showSection(viewSection);

    viewPeer = new RTCPeerConnection();
    viewPeer.addEventListener("track", function (event) {
      videoEl.srcObject = event.streams[0];
    });
    viewPeer.addEventListener("icecandidate", function (event) {
      if (event.candidate && viewSocket) {
        viewSocket.send(
          JSON.stringify({ type: "ice", channel_id: channelId, candidate: event.candidate })
        );
      }
    });

    viewSocket = new WebSocket(wsUrl());
    viewSocket.addEventListener("open", function () {
      viewSocket.send(JSON.stringify({ type: "join", channel_id: channelId }));
    });
    viewSocket.addEventListener("message", function (event) {
      var msg = JSON.parse(event.data);
      if (msg.type === "error") {
        viewErrorEl.textContent = msg.message || "방송에 참여할 수 없습니다.";
        viewErrorEl.hidden = false;
      } else if (msg.type === "offer") {
        viewPeer
          .setRemoteDescription(msg.sdp)
          .then(function () {
            return viewPeer.createAnswer();
          })
          .then(function (answer) {
            return viewPeer.setLocalDescription(answer);
          })
          .then(function () {
            viewSocket.send(
              JSON.stringify({
                type: "answer",
                channel_id: channelId,
                sdp: viewPeer.localDescription,
              })
            );
          });
      } else if (msg.type === "ice") {
        if (msg.candidate) viewPeer.addIceCandidate(msg.candidate);
      } else if (msg.type === "channel_closed") {
        viewErrorEl.textContent = "방송이 종료되었습니다.";
        viewErrorEl.hidden = false;
        if (viewPeer) {
          viewPeer.close();
          viewPeer = null;
        }
        setTimeout(leaveView, 1500);
      }
    });
  }

  backBtn.addEventListener("click", leaveView);
})();
```

- [ ] **Step 2: 서버 기동**

```bash
cd cloud/Codes/Cloud
uvicorn main:app --reload --port 8123
```

(브로커 없이도 뜬다 — `mqtt_bridge` 연결은 비차단이라 화면 송출 기능과 무관하다.)

- [ ] **Step 3: 단일 채널 · 마스터 1 · 학생 1 수동 확인**

브라우저 탭 2개(또는 별도 브라우저 창)를 같은 PC에서 `http://localhost:8123/broadcast` 로 연다.

1. 탭 A: "화면 공유 시작" → 채널 이름 입력(예: "테스트 방송") → "공유 시작" → 브라우저가 화면/창/탭 선택 프롬프트를 띄우면 아무 창이나 선택.
2. 탭 A에 "0명 시청 중"과 "방송 종료" 버튼이 뜨는지 확인.
3. 탭 B: 목록에 "테스트 방송" 채널이 나타나는지 확인(수동 새로고침 없이 자동으로 떠야 한다) → 클릭.
4. 탭 B에 탭 A가 공유 중인 화면이 실시간으로 보이는지 확인.
5. 탭 A의 시청자 수가 "1명"으로 바뀌는지 확인.
6. 탭 B에서 "‹ 목록으로" 클릭 → 탭 A의 시청자 수가 "0명"으로 돌아오는지 확인.
7. 탭 A에서 "방송 종료" 클릭 → 탭 B(다시 목록을 보고 있는 상태)에서 채널이 목록에서 사라지는지 확인.

- [ ] **Step 4: 채널 종료 중 시청 중이던 학생 처리 확인**

1. 탭 A: 새 채널로 다시 "화면 공유 시작".
2. 탭 B: 목록에서 클릭해 시청 시작(영상이 보이는지 확인).
3. 탭 A: "방송 종료" 클릭.
4. 탭 B: "방송이 종료되었습니다" 메시지가 잠깐 보이고, 약 1.5초 뒤 자동으로 목록 화면으로 돌아오는지 확인.

- [ ] **Step 5: 여러 마스터 · 여러 채널 동시 확인** (스펙의 핵심 요구사항)

1. 탭 A: "화면 공유 시작" → 채널 이름 "채널 1" 로 공유 시작.
2. 탭 C(새 탭): "화면 공유 시작" → 채널 이름 "채널 2" 로 공유 시작.
3. 탭 B: 목록에 "채널 1"과 "채널 2"가 둘 다 보이는지 확인.
4. 탭 B에서 "채널 1"을 클릭해 시청 → 탭 A의 화면이 보이는지, 탭 A의 시청자 수만 "1명"으로 바뀌고 탭 C는 "0명"인지 확인(채널끼리 서로 간섭하지 않아야 한다).
5. 탭 A만 "방송 종료" → 탭 B는 "방송이 종료되었습니다" 후 목록으로 복귀, 목록에는 "채널 2"만 남아 있는지 확인.

- [ ] **Step 6: 회귀 테스트 확인** (JS 변경은 테스트에 영향 없지만, 전체 스위트가 여전히 통과하는지 확인)

Run: `pytest cloud/Codes/Cloud/tests -v`
Expected: PASS

- [ ] **Step 7: 커밋**

```bash
git add cloud/Codes/Cloud/static/js/broadcast.js
git commit -m "feat(broadcast): 클라이언트 WebRTC 로직(목록/방송 시작/시청) 추가"
```

---

## Self-Review 요약

- **스펙 커버리지**: 아키텍처(WebRTC 메시 + WS 시그널링) → Task 2, 채널 수명주기(생성/참여/오퍼-앤서-ICE/종료/뷰어 이탈) → Task 2, UI(목록·방송 시작·시청 3모드) → Task 3+4, 에러 처리(미지원 브라우저·존재하지 않는 채널·재연결 없음) → Task 4, 테스트 전략(자동 = 시그널링 상태 전이, 수동 = 실제 영상) → Task 1/2(자동) + Task 4(수동). 빠짐없이 다룬다.
- **타입/시그니처 일관성**: `BroadcastRegistry`의 메서드 이름·반환값(Task 1)을 `handle_connection`(Task 2)이 그대로 쓰고, `handle_connection`이 만드는 메시지 `type` 값들을 `broadcast.js`(Task 4)가 그대로 소비하도록 맞춰 두었다.
- **플레이스홀더 없음**: 모든 단계에 실제 코드/명령을 넣었다.
