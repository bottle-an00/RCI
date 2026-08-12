"""테스트용 가짜 링크 객체와 공통 픽스처"""
import pytest

from ur3.rci.state import RciState


class FakeRtdeLink:
    def __init__(self):
        self.connected = True
        self.cache = {"actual_q": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]}
        self.moves = []
        self.stopped = False
        self.progress = 1.0
        self.speed_slider = 100

    def is_connected(self):
        return self.connected

    def get_cache(self):
        return self.cache

    def move_j(self, q, speed, accel):
        self.moves.append(("j", q, speed, accel))

    def move_j_blocking(self, q, speed, accel):
        self.moves.append(("j_blocking", q, speed, accel))

    def move_l(self, pose, speed, accel):
        self.moves.append(("l", pose, speed, accel))

    def move_l_blocking(self, pose, speed, accel):
        self.moves.append(("l_blocking", pose, speed, accel))

    def stop_j(self):
        self.stopped = True

    def stop_l(self):
        self.stopped = True

    def get_async_progress(self):
        return self.progress

    def set_speed_slider(self, fraction_percent):
        self.speed_slider = fraction_percent


class FakeDashboardLink:
    def __init__(self):
        self.connected = True
        self.sent = []
        self.responses = {}

    def is_connected(self):
        return self.connected

    def send(self, command):
        self.sent.append(command)
        return self.responses.get(command, "ok")


class FakeCameraLink:
    def __init__(self):
        self.connected = True

    def is_connected(self):
        return self.connected


@pytest.fixture
def state():
    return RciState()


@pytest.fixture
def rtde_link():
    return FakeRtdeLink()


@pytest.fixture
def dashboard_link():
    return FakeDashboardLink()


@pytest.fixture
def camera_link():
    return FakeCameraLink()
