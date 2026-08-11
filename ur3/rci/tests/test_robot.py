"""UR3Robot 요청 처리 루프의 예외 안전성 검증"""
import threading
import time

from ur3.rci.robot import UR3Robot


class BoomUdsServer:
    """항상 예외를 던지는 가짜 uds_server"""

    def handle_request(self, raw_hex):
        raise RuntimeError("boom")


class RecordingMqttClient:
    """publish_error 호출을 기록하는 가짜 mqtt_client"""

    def __init__(self):
        self.errors = []

    def publish_error(self, id, reason, message):
        self.errors.append((id, reason, message))


class BoomOnPublishMqttClient:
    """publish_error 호출 시 예외를 던지는 가짜 mqtt_client"""

    def publish_error(self, id, reason, message):
        raise RuntimeError("mqtt down")


def _make_robot(**kwargs):
    return UR3Robot("127.0.0.1", **kwargs)


class FlakyThenOkMqttClient:
    """처음 N번은 연결에 실패하고 그 다음부터는 성공하는 가짜 mqtt_client"""

    def __init__(self, fail_times):
        self.fail_times = fail_times
        self.attempts = 0

    def connect(self):
        self.attempts += 1
        if self.attempts <= self.fail_times:
            raise ConnectionRefusedError("broker not up yet")


def test_process_request_safe_reports_internal_error_without_raising():
    robot = _make_robot()
    robot.uds_server = BoomUdsServer()
    robot.mqtt_client = RecordingMqttClient()

    robot._process_request_safe({"id": "u-0001", "raw_bytes": b"\x22\x01\x01"})

    assert robot.mqtt_client.errors == [("u-0001", "internal_error", "boom")]


def test_process_request_safe_swallows_publish_failure():
    robot = _make_robot()
    robot.uds_server = BoomUdsServer()
    robot.mqtt_client = BoomOnPublishMqttClient()

    robot._process_request_safe({"id": "u-0002", "raw_bytes": b"\x22\x01\x01"})


class FakeReconnectLink:
    """reconnect 호출만 기록하는 가짜 링크. RECONNECT_DELAY_SEC만큼 일부러 오래 걸리게 한다"""

    RECONNECT_DELAY_SEC = 0.5

    def __init__(self):
        self.ip = None
        self.reconnect_calls = []
        self.done = threading.Event()

    def reconnect(self, ip=None):
        time.sleep(self.RECONNECT_DELAY_SEC)
        self.reconnect_calls.append(ip)
        self.ip = ip
        self.done.set()
        return True


def test_ip_write_does_not_block_on_slow_reconnect():
    """0xF1A0 쓰기 처리는 재접속이 오래 걸려도 그 시간만큼 기다리지 않고 바로 반환한다"""
    robot = _make_robot()
    robot.rtde_link = FakeReconnectLink()
    robot.dashboard_link = FakeReconnectLink()
    robot.state.session = "extended"
    robot.state.security_unlocked = True

    start = time.time()
    robot.did_write.handle(0x2E, bytes.fromhex("F1 A0 0A 00 00 05"))
    elapsed = time.time() - start

    assert elapsed < FakeReconnectLink.RECONNECT_DELAY_SEC

    assert robot.dashboard_link.done.wait(timeout=2)
    assert robot.rtde_link.ip == "10.0.0.5"
    assert robot.dashboard_link.ip == "10.0.0.5"


def test_connect_mqtt_with_retry_succeeds_after_failures():
    """연결이 실패해도 재시도 간격 후 다시 시도해 결국 성공한다"""
    robot = _make_robot(mqtt_retry_interval_sec=0.01)
    robot.mqtt_client = FlakyThenOkMqttClient(fail_times=3)

    robot._connect_mqtt_with_retry()

    assert robot.mqtt_client.attempts == 4


def test_concurrent_ip_changes_do_not_run_reconnect_at_the_same_time():
    """재접속이 겹치면 락으로 직렬화되어 동시에 실행되지 않는다"""
    robot = _make_robot()
    overlap_detected = threading.Event()
    in_progress = threading.Event()

    class BlockingLink:
        def __init__(self):
            self.ip = None

        def reconnect(self, ip=None):
            if in_progress.is_set():
                overlap_detected.set()
            in_progress.set()
            time.sleep(0.2)
            self.ip = ip
            in_progress.clear()
            return True

    robot.rtde_link = BlockingLink()
    robot.dashboard_link = BlockingLink()

    t1 = threading.Thread(target=robot._reconnect_links, args=("10.0.0.5",))
    t2 = threading.Thread(target=robot._reconnect_links, args=("10.0.0.6",))
    t1.start()
    t2.start()
    t1.join(timeout=2)
    t2.join(timeout=2)

    assert overlap_detected.is_set() is False
