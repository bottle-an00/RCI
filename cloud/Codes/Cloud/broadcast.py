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
