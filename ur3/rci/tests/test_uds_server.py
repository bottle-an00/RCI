"""UdsServer 조립 통합 테스트. 문서 부록 A, D 흐름을 실제 raw hex로 검증한다"""
import math

import pytest

from ur3.rci.agent_reset import AgentReset
from ur3.rci.did_read import DidRead
from ur3.rci.did_write import DidWrite
from ur3.rci.dtc_store import DtcStore
from ur3.rci.io_control import IoControl
from ur3.rci.motion_ctrl import MotionCtrl
from ur3.rci.security_mgr import SecurityMgr
from ur3.rci.session_mgr import SessionMgr
from ur3.rci.settings_store import SettingsStore
from ur3.rci.state import SESSION_EXTENDED
from ur3.rci.uds_server import UdsServer


@pytest.fixture
def settings_store(tmp_path):
    return SettingsStore(path=str(tmp_path / "settings.json"))


@pytest.fixture
def server(state, rtde_link, dashboard_link, camera_link, settings_store):
    """개별 서비스 모듈을 실제로 조립해 UdsServer를 만든다"""
    session_mgr = SessionMgr(state)
    security_mgr = SecurityMgr(state)
    agent_reset = AgentReset(state)
    did_read = DidRead(state, rtde_link, dashboard_link, camera_link, settings_store)
    did_write = DidWrite(state, settings_store)
    io_control = IoControl(state, dashboard_link, rtde_link)
    motion_ctrl = MotionCtrl(state, rtde_link)
    dtc_store = DtcStore(state)

    handlers = {
        0x10: session_mgr,
        0x3E: session_mgr,
        0x27: security_mgr,
        0x11: agent_reset,
        0x22: did_read,
        0x2E: did_write,
        0x2F: io_control,
        0x31: motion_ctrl,
        0x19: dtc_store,
        0x14: dtc_store,
    }
    return UdsServer(handlers)


def test_read_joint_angles(server, rtde_link):
    """부록 A: DID 0x0101 조인트 각도 읽기 흐름을 검증한다"""
    rtde_link.cache = {"actual_q": [-math.pi / 2, 0.0, 0.0, 0.0, 0.0, 0.0]}
    response = server.handle_request("22 01 01")
    assert response == "62 01 01 FC 7C 00 00 00 00 00 00 00 00 00 00"


def test_move_joint_start_pending_complete(server, state, rtde_link):
    """부록 D: 모션 실행 시작, 진행중, 완료 흐름을 검증한다"""
    state.session = SESSION_EXTENDED
    state.security_unlocked = True

    rtde_link.progress = 0.0
    start_response = server.handle_request(
        "31 01 03 01 00 00 FC 7C 00 00 FC 7C 00 00 00 00 1E 1E"
    )
    assert start_response == "71 01 03 01 00"

    pending_response = server.handle_request("31 03 03 01")
    assert pending_response == "7F 31 78"

    rtde_link.progress = 1.0
    complete_response = server.handle_request("31 03 03 01")
    parts = complete_response.split(" ")
    assert parts[0:7] == ["71", "03", "03", "01", "01", "00", "00"]
    assert parts[7:11] == ["FC", "7C", "00", "00"]
    assert parts[11:13] == ["FC", "7C"]
    assert parts[13:15] == ["00", "00"]


def test_unknown_sid_returns_negative():
    """등록되지 않은 SID는 serviceNotSupported로 응답한다"""
    empty_server = UdsServer({})
    response = empty_server.handle_request("99 00")
    assert response == "7F 99 11"


def test_unexpected_exception_returns_general_reject():
    """핸들러가 NRCError가 아닌 예외를 던져도 루프가 죽지 않고 generalReject로 응답한다"""

    class BoomHandler:
        def handle(self, sid, payload):
            raise RuntimeError("boom")

    server = UdsServer({0x22: BoomHandler()})
    response = server.handle_request("22 01 01")
    assert response == "7F 22 10"
