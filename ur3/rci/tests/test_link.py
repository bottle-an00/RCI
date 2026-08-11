"""링크 계층(RTDELink, DashboardLink, CameraLink) 경량 단위 테스트"""
import threading
import time

from ur3.rci.link.rtde_link import RTDELink
from ur3.rci.link.dashboard_link import DashboardLink
from ur3.rci.link.camera_link import CameraLink


def test_rtde_link_instantiation():
    link = RTDELink("192.168.1.101")
    assert link.is_connected() is False


def test_rtde_link_connect_without_library_returns_false():
    """실제 연결시도가 오래 걸려도 짧은 timeout 안에 포기하고 돌아온다"""
    link = RTDELink("192.168.1.101")
    start = time.time()
    assert link.connect(timeout=0.3) is False
    assert time.time() - start < 1.0
    assert link.is_connected() is False


def test_rtde_link_get_cache_without_connection_does_not_raise():
    link = RTDELink("192.168.1.101")
    cache = link.get_cache()
    expected_keys = {
        "actual_q", "actual_qd", "actual_current", "joint_temperatures",
        "actual_TCP_pose", "robot_mode", "safety_mode", "runtime_state",
        "speed_scaling", "actual_robot_voltage", "actual_robot_current",
        "safety_status_bits",
    }
    assert set(cache.keys()) == expected_keys
    assert all(v is None for v in cache.values())


def test_rtde_link_disconnect_without_connection_does_not_raise():
    link = RTDELink("192.168.1.101")
    link.disconnect()
    assert link.is_connected() is False


def test_rtde_link_connect_returns_within_timeout_even_if_worker_is_slow(monkeypatch):
    """연결 시도가 오래 걸려도 connect()는 timeout만큼만 기다리고 돌아온다"""

    def slow_open():
        time.sleep(1.0)
        return None, None

    link = RTDELink("192.168.1.101")
    monkeypatch.setattr(link, "_open_interfaces", slow_open)

    start = time.time()
    result = link.connect(timeout=0.1)
    elapsed = time.time() - start

    assert result is False
    assert elapsed < 0.5


def test_rtde_link_stale_connect_result_is_discarded(monkeypatch):
    """timeout으로 포기한 뒤 disconnect가 먼저 일어나면, 늦게 끝난 연결 시도 결과는 버려진다"""

    class FakeInterface:
        def __init__(self):
            self.disconnected = False

        def disconnect(self):
            self.disconnected = True

    fake_receive = FakeInterface()
    fake_control = FakeInterface()
    release = threading.Event()

    def slow_open():
        release.wait(timeout=2)
        return fake_receive, fake_control

    link = RTDELink("192.168.1.101")
    monkeypatch.setattr(link, "_open_interfaces", slow_open)

    assert link.connect(timeout=0.1) is False

    link.disconnect()
    release.set()
    time.sleep(0.2)

    assert fake_receive.disconnected is True
    assert fake_control.disconnected is True
    assert link.is_connected() is False


def test_set_speed_slider_skips_quickly_when_unreachable(monkeypatch):
    """포트가 안 열려 있으면 실제 RTDEIOInterface 생성을 시도하지 않고 바로 반환한다"""
    link = RTDELink("192.168.1.101")
    monkeypatch.setattr(link, "_probe_reachable", lambda: False)

    start = time.time()
    link.set_speed_slider(50)
    elapsed = time.time() - start

    assert elapsed < 0.5


def test_dashboard_link_instantiation():
    link = DashboardLink("192.168.1.101")
    assert link.is_connected() is False


def test_dashboard_link_connect_without_server_returns_false():
    link = DashboardLink("127.0.0.1", port=1, timeout=0.2)
    assert link.connect() is False
    assert link.is_connected() is False


def test_dashboard_link_disconnect_without_connection_does_not_raise():
    link = DashboardLink("192.168.1.101")
    link.disconnect()
    assert link.is_connected() is False


def test_rtde_link_reconnect_updates_ip_and_returns_quickly():
    link = RTDELink("192.168.1.101")
    start = time.time()
    result = link.reconnect("192.168.1.102", timeout=0.2)
    elapsed = time.time() - start
    assert link.ip == "192.168.1.102"
    assert result is False
    assert elapsed < 1.0


def test_dashboard_link_reconnect_updates_ip_without_raising():
    link = DashboardLink("127.0.0.1", port=1, timeout=0.2)
    result = link.reconnect("127.0.0.2")
    assert link.ip == "127.0.0.2"
    assert result is False
    assert link.is_connected() is False


def test_camera_link_default_not_connected():
    link = CameraLink()
    assert link.is_connected() is False
