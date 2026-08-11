"""UR3 RTDE 연결과 텔레메트리 캐시를 다루는 링크"""
import socket
import threading

from .. import logger

DEFAULT_CONNECT_TIMEOUT_SEC = 5.0
PROBE_TIMEOUT_SEC = 2.0


class RTDELink:
    """RTDE Receive/Control 인터페이스를 감싸는 클래스"""

    def __init__(self, ip, port=30004):
        self.ip = ip
        self.port = port
        self.receive_if = None
        self.control_if = None
        self._lock = threading.RLock()
        self._generation = 0

    def connect(self, timeout=DEFAULT_CONNECT_TIMEOUT_SEC):
        """백그라운드 스레드로 연결을 시도하고, 시간 안에 안 끝나면 포기하고 False를 반환한다"""
        with self._lock:
            self._generation += 1
            generation = self._generation

        worker = threading.Thread(target=self._connect_worker, args=(generation,), daemon=True)
        worker.start()
        worker.join(timeout)

        with self._lock:
            return generation == self._generation and self.is_connected()

    def _connect_worker(self, generation):
        """실제 연결 시도. 시간이 오래 걸릴 수 있어 별도 스레드에서 실행된다"""
        receive_if, control_if = self._open_interfaces()
        with self._lock:
            if generation != self._generation:
                self._discard(receive_if, control_if)
                return
            self.receive_if = receive_if
            self.control_if = control_if
        ok = receive_if is not None and control_if is not None
        logger.log_robot_event("RTDE_CONNECT", f"ip={self.ip} ok={ok}")

    def _open_interfaces(self):
        """rtde_receive/rtde_control 라이브러리로 실제 연결을 시도한다"""
        if not self._probe_reachable():
            return None, None
        try:
            import rtde_receive
            import rtde_control

            return (
                rtde_receive.RTDEReceiveInterface(self.ip),
                rtde_control.RTDEControlInterface(self.ip),
            )
        except Exception:
            return None, None

    def _probe_reachable(self):
        """rtde_receive/rtde_control 생성자는 GIL을 쥔 채 응답 없는 IP에 수십 초간 멈출 수 있어, 그 전에 순수 소켓으로 포트가 열려 있는지 짧게 확인한다"""
        try:
            with socket.create_connection((self.ip, self.port), timeout=PROBE_TIMEOUT_SEC):
                return True
        except OSError:
            return False

    def _discard(self, receive_if, control_if):
        """더 이상 최신이 아닌 연결 시도 결과를 정리한다"""
        if receive_if is not None:
            try:
                receive_if.disconnect()
            except Exception:
                pass
        if control_if is not None:
            try:
                control_if.disconnect()
            except Exception:
                pass

    def disconnect(self):
        """RTDE 연결을 해제한다 (진행 중인 연결 시도가 있으면 그 결과도 무효화한다)"""
        with self._lock:
            self._generation += 1
            receive_if, control_if = self.receive_if, self.control_if
            self.receive_if = None
            self.control_if = None
        self._discard(receive_if, control_if)
        if receive_if is not None or control_if is not None:
            logger.log_robot_event("RTDE_DISCONNECT", f"ip={self.ip}")

    def is_connected(self):
        """RTDE 연결 여부를 반환한다"""
        with self._lock:
            return self.receive_if is not None and self.control_if is not None

    def get_cache(self):
        """최신 텔레메트리를 딕셔너리로 반환한다"""
        with self._lock:
            receive_if = self.receive_if
        cache = {}
        getters = {
            "actual_q": lambda: receive_if.getActualQ(),
            "actual_qd": lambda: receive_if.getActualQd(),
            "actual_current": lambda: receive_if.getActualCurrent(),
            "joint_temperatures": lambda: receive_if.getJointTemperatures(),
            "actual_TCP_pose": lambda: receive_if.getActualTCPPose(),
            "robot_mode": lambda: receive_if.getRobotMode(),
            "safety_mode": lambda: receive_if.getSafetyMode(),
            "runtime_state": lambda: receive_if.getRuntimeState(),
            "speed_scaling": lambda: receive_if.getSpeedScaling(),
            "actual_robot_voltage": lambda: receive_if.getActualRobotVoltage(),
            "actual_robot_current": lambda: receive_if.getActualRobotCurrent(),
            "safety_status_bits": lambda: receive_if.getSafetyStatusBits(),
        }
        for key, getter in getters.items():
            try:
                cache[key] = getter()
            except Exception:
                cache[key] = None
        return cache

    def move_j(self, q_rad_list, speed, accel):
        """관절 좌표로 비동기 moveJ를 실행한다"""
        self.control_if.moveJ(q_rad_list, speed, accel, asynchronous=True)

    def move_l(self, pose_list, speed, accel):
        """직선 좌표로 비동기 moveL을 실행한다"""
        self.control_if.moveL(pose_list, speed, accel, asynchronous=True)

    def stop_j(self):
        """moveJ 동작을 정지한다"""
        self.control_if.stopJ()

    def stop_l(self):
        """moveL 동작을 정지한다"""
        self.control_if.stopL()

    def get_async_progress(self):
        """비동기 동작 진행률을 반환한다"""
        return self.control_if.getAsyncOperationProgress()

    def set_speed_slider(self, percent_0_100):
        """속도 슬라이더 비율을 설정한다 (응답 없는 IP에 오래 멈추지 않도록 먼저 포트를 확인한다)"""
        if not self._probe_reachable():
            return
        try:
            import rtde_io

            io_if = rtde_io.RTDEIOInterface(self.ip)
            try:
                io_if.setSpeedSlider(percent_0_100 / 100)
            finally:
                io_if.disconnect()
        except Exception:
            pass

    def reconnect(self, ip=None, timeout=DEFAULT_CONNECT_TIMEOUT_SEC):
        """연결을 끊고 (IP가 주어지면 바꾼 뒤) 다시 연결한다"""
        self.disconnect()
        if ip is not None:
            self.ip = ip
        return self.connect(timeout=timeout)

    def health_check_and_reconnect(self):
        """좀비 스크립트 여부를 확인하고 필요시 재업로드한다"""
        # TODO 실기 미확인, 문서 5.7절 정책 반영 필요
        if self.control_if is not None and not self.control_if.isProgramRunning():
            self.control_if.reuploadScript()
