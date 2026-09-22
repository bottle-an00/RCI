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

from fastapi import WebSocket, WebSocketDisconnect

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
