"""로봇 상태를 주기적으로 감시해 DTC를 등록하는 모듈"""
import threading

from . import logger

DTC_RTDE_DISCONNECTED = 0x900002
DTC_SAFETY_EMERGENCY_STOP = 0xB10001
DTC_SAFETY_PROTECTIVE_STOP = 0xB10002
DTC_SAFETY_SAFEGUARD_STOP = 0xB10003
DTC_SAFETY_VIOLATION_FAULT = 0xB10004
DTC_JOINT_OVER_TEMPERATURE = 0xC20101
DTC_UNDER_VOLTAGE = 0xC20201
DTC_CAMERA_DISCONNECTED = 0xC20301

JOINT_TEMPERATURE_LIMIT = 50.0
VOLTAGE_LOWER_LIMIT = 44.0


class DtcMonitor:
    """RTDE/카메라 상태를 주기적으로 검사해 DtcStore에 등록한다"""

    def __init__(self, rtde_link, camera_link, dtc_store, dashboard_link=None, interval_sec=0.5):
        self.rtde_link = rtde_link
        self.camera_link = camera_link
        self.dtc_store = dtc_store
        self.dashboard_link = dashboard_link
        self.interval_sec = interval_sec
        self._thread = None
        self._stop_event = threading.Event()
        self._last_safety_mode = None

    def start(self):
        """백그라운드 감시 스레드를 시작한다"""
        if self._thread is not None:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        """백그라운드 감시 스레드를 정지한다"""
        if self._thread is None:
            return
        self._stop_event.set()
        self._thread.join()
        self._thread = None

    def _run(self):
        """정지 신호가 올 때까지 주기적으로 검사를 반복한다"""
        while not self._stop_event.is_set():
            self._check_once()
            self._stop_event.wait(self.interval_sec)

    def _check_once(self):
        """한 번의 상태 검사를 수행하고 조건에 맞는 DTC를 등록한다"""
        dashboard_lost = self.dashboard_link is not None and not self.dashboard_link.is_connected()
        if not self.rtde_link.is_connected() or dashboard_lost:
            self.dtc_store.set(DTC_RTDE_DISCONNECTED)
        cache = self.rtde_link.get_cache()
        self._check_safety_mode(cache)
        self._check_joint_temperatures(cache)
        self._check_voltage(cache)
        if not self.camera_link.is_connected():
            self.dtc_store.set(DTC_CAMERA_DISCONNECTED)

    def _check_safety_mode(self, cache):
        """safety_mode 값에 따라 해당하는 DTC를 등록한다"""
        safety_mode = cache.get("safety_mode")
        if safety_mode is None:
            return
        if safety_mode != self._last_safety_mode:
            logger.log_robot_event("SAFETY_MODE", f"{self._last_safety_mode}->{safety_mode}")
            self._last_safety_mode = safety_mode
        if safety_mode in (6, 7):
            self.dtc_store.set(DTC_SAFETY_EMERGENCY_STOP)
        elif safety_mode == 3:
            self.dtc_store.set(DTC_SAFETY_PROTECTIVE_STOP)
        elif safety_mode == 5:
            self.dtc_store.set(DTC_SAFETY_SAFEGUARD_STOP)
        elif safety_mode in (8, 9):
            self.dtc_store.set(DTC_SAFETY_VIOLATION_FAULT)

    def _check_joint_temperatures(self, cache):
        """관절 온도가 임계값을 넘으면 DTC를 등록한다"""
        temperatures = cache.get("joint_temperatures")
        if temperatures is None:
            return
        if any(t > JOINT_TEMPERATURE_LIMIT for t in temperatures):
            self.dtc_store.set(DTC_JOINT_OVER_TEMPERATURE)

    def _check_voltage(self, cache):
        """로봇 전압이 하한값보다 낮으면 DTC를 등록한다"""
        voltage = cache.get("actual_robot_voltage")
        if voltage is None:
            return
        if voltage < VOLTAGE_LOWER_LIMIT:
            self.dtc_store.set(DTC_UNDER_VOLTAGE)
