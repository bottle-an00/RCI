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
