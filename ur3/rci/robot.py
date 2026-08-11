"""RCI composition root. 링크/상태/서비스 모듈을 조립하고 실행 루프를 돈다"""
import threading
import time

from .. import uds_payload
from ..mqtt_handler import UR3MqttHandler
from . import frames
from . import logger
from .agent_reset import AgentReset
from .did_read import DidRead
from .did_write import DidWrite
from .dtc_monitor import DtcMonitor
from .dtc_store import DtcStore
from .io_control import IoControl
from .link.camera_link import CameraLink
from .link.dashboard_link import DashboardLink
from .link.rtde_link import RTDELink
from .motion_ctrl import MotionCtrl
from .request_queue import RequestQueue
from .security_mgr import SecurityMgr
from .session_mgr import SessionMgr
from .settings_store import SettingsStore
from .state import RciState
from .uds_server import UdsServer

MQTT_RETRY_INTERVAL_SEC = 5.0


class UR3Robot:
    """UR3 RCI 전체 구성을 조립하고 요청 처리 루프를 실행한다"""

    def __init__(self, robot_ip, dashboard_port=29999, rtde_port=30004,
                 broker_host="localhost", broker_port=1883,
                 broker_username=None, broker_password=None, broker_tls=False,
                 mqtt_retry_interval_sec=MQTT_RETRY_INTERVAL_SEC):
        self.mqtt_retry_interval_sec = mqtt_retry_interval_sec
        self.rtde_link = RTDELink(robot_ip, rtde_port)
        self.dashboard_link = DashboardLink(robot_ip, dashboard_port)
        self.camera_link = CameraLink()

        self.state = RciState()
        self.settings_store = SettingsStore()

        self.session_mgr = SessionMgr(self.state)
        self.security_mgr = SecurityMgr(self.state)
        self.agent_reset = AgentReset(self.state)
        self.did_read = DidRead(
            self.state, self.rtde_link, self.dashboard_link, self.camera_link, self.settings_store
        )
        self.did_write = DidWrite(self.state, self.settings_store, on_ip_changed=self._on_robot_ip_changed)
        self.io_control = IoControl(self.state, self.dashboard_link, self.rtde_link)
        self.motion_ctrl = MotionCtrl(self.state, self.rtde_link)
        self.dtc_store = DtcStore(self.state)
        self.dtc_monitor = DtcMonitor(
            self.rtde_link, self.camera_link, self.dtc_store, dashboard_link=self.dashboard_link
        )

        handlers = {
            0x10: self.session_mgr,
            0x3E: self.session_mgr,
            0x27: self.security_mgr,
            0x11: self.agent_reset,
            0x22: self.did_read,
            0x2E: self.did_write,
            0x2F: self.io_control,
            0x31: self.motion_ctrl,
            0x19: self.dtc_store,
            0x14: self.dtc_store,
        }
        self.uds_server = UdsServer(handlers)

        self.request_queue = RequestQueue()
        self.mqtt_client = UR3MqttHandler(
            broker_host, broker_port, client_id="ur3-rci",
            username=broker_username, password=broker_password, tls=broker_tls,
        )
        self.mqtt_client.on_request = self._on_request
        self._reconnect_lock = threading.Lock()

    def _on_robot_ip_changed(self, ip):
        """0xF1A0 쓰기 시 요청 처리 스레드를 막지 않도록 백그라운드 스레드에서 재접속한다"""
        threading.Thread(target=self._reconnect_links, args=(ip,), daemon=True).start()

    def _reconnect_links(self, ip):
        """실제 재접속 작업. 동시에 여러 재접속이 겹치지 않도록 락으로 직렬화한다"""
        with self._reconnect_lock:
            self.rtde_link.reconnect(ip)
            self.dashboard_link.reconnect(ip)

    def _on_request(self, request):
        """mqtt_handler가 이미 파싱한 요청({"id", "raw"(bytes), "timeout_ms"})을 큐에 담는다"""
        self.request_queue.put({"id": request["id"], "raw_bytes": request["raw"]})

    def run(self):
        """감시 스레드를 시작하고 MQTT 연결이 될 때까지 재시도한 뒤 요청 처리 루프를 돈다"""
        logger.setup_logging()
        self.dtc_monitor.start()
        self._connect_mqtt_with_retry()
        while True:
            request = self.request_queue.get()
            self._process_request_safe(request)

    def _connect_mqtt_with_retry(self):
        """MQTT 브로커 연결을 될 때까지 일정 간격으로 무한 재시도한다"""
        while True:
            try:
                self.mqtt_client.connect()
                return
            except Exception as exc:
                logger.log_error(
                    f"[UR3Robot] MQTT 브로커 연결 실패, {self.mqtt_retry_interval_sec}초 후 재시도: {exc}"
                )
                time.sleep(self.mqtt_retry_interval_sec)

    def _process_request_safe(self, request):
        """요청 하나를 처리하고, 예외가 나도 루프가 죽지 않게 막는다"""
        try:
            self._process_request(request)
        except Exception as exc:
            logger.log_error(f"[UR3Robot] 요청 처리 중 예외 발생: {exc}")
            self._publish_internal_error(request, exc)

    def _publish_internal_error(self, request, exc):
        """요청 처리 실패를 error 토픽으로 알린다 (발행 자체 실패는 무시)"""
        try:
            self.mqtt_client.publish_error(request.get("id"), "internal_error", str(exc))
        except Exception:
            pass

    def _process_request(self, request):
        """요청 하나를 UdsServer로 처리하고 결과를 응답 토픽에 발행한 뒤 로그로 남긴다"""
        raw_hex = frames.to_hex(request["raw_bytes"])
        started_at = time.time()
        response_hex = self.uds_server.handle_request(raw_hex)
        elapsed_ms = (time.time() - started_at) * 1000

        if response_hex is None:
            logger.log_request(request["id"], raw_hex, elapsed_ms, "ignored")
            return

        response_bytes = frames.parse_hex(response_hex)
        self.mqtt_client.publish_response(request["id"], response_bytes)
        result_type = uds_payload.classify_type(response_bytes)
        nrc = f"{response_bytes[2]:02X}" if result_type == "negative" else None
        logger.log_request(request["id"], raw_hex, elapsed_ms, result_type, nrc=nrc)

    def stop(self):
        """감시 스레드를 정지하고 MQTT 연결을 해제한다"""
        self.dtc_monitor.stop()
        self.mqtt_client.disconnect()
