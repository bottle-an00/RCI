"""IoControl(0x2F) 서비스 테스트"""
import pytest

from ur3.rci.io_control import IoControl
from ur3.rci.frames import NRCError, parse_hex, to_hex
from ur3.rci.state import SESSION_EXTENDED, BUSY_MOTION_ROUTINE, BUSY_URP_PROGRAM, BUSY_NONE


@pytest.fixture
def io_control(state, dashboard_link, rtde_link):
    return IoControl(state, dashboard_link, rtde_link)


def run(io_control, request_hex):
    """요청 hex 문자열에서 SID를 분리해 handle을 호출하고 응답 hex를 돌려준다"""
    raw = parse_hex(request_hex)
    sid = raw[0]
    payload = raw[1:]
    return to_hex(io_control.handle(sid, payload))


def test_program_control_play_echoes_request(io_control, state, dashboard_link):
    """확장 세션에서 재생 요청은 그대로 echo 응답되고 dashboard에 play가 전달된다"""
    state.session = SESSION_EXTENDED
    resp = run(io_control, "2F 02 01 03 01")
    assert resp == "6F 02 01 03 01"
    assert dashboard_link.sent == ["play"]
    assert state.robot_busy_owner == BUSY_URP_PROGRAM


def test_speed_slider_50_percent(io_control, state, rtde_link):
    """속도 슬라이더 50%(0x32) 설정 예시"""
    state.session = SESSION_EXTENDED
    resp = run(io_control, "2F 02 02 03 32")
    assert resp == "6F 02 02 03 32"
    assert rtde_link.speed_slider == 0x32


def test_gripper_value_over_range_rejected(io_control, state):
    """그리퍼 값이 100 초과(0x65=101)면 NRC 0x31"""
    state.session = SESSION_EXTENDED
    with pytest.raises(NRCError) as exc_info:
        run(io_control, "2F 02 06 03 65")
    assert exc_info.value.nrc == 0x31


def test_not_extended_session_rejected(io_control, state):
    """확장 세션이 아니면 NRC 0x7F"""
    with pytest.raises(NRCError) as exc_info:
        run(io_control, "2F 02 01 03 01")
    assert exc_info.value.nrc == 0x7F


def test_play_while_motion_routine_busy_rejected(io_control, state):
    """모션 루틴 실행 중 재생 요청 시 NRC 0x22"""
    state.session = SESSION_EXTENDED
    state.robot_busy_owner = BUSY_MOTION_ROUTINE
    with pytest.raises(NRCError) as exc_info:
        run(io_control, "2F 02 01 03 01")
    assert exc_info.value.nrc == 0x22


def test_program_control_stop_resets_busy_owner(io_control, state, dashboard_link):
    """정지 요청 시 dashboard에 stop이 전달되고 busy owner가 NONE이 된다"""
    state.session = SESSION_EXTENDED
    state.robot_busy_owner = BUSY_URP_PROGRAM
    resp = run(io_control, "2F 02 01 03 00")
    assert resp == "6F 02 01 03 00"
    assert dashboard_link.sent == ["stop"]
    assert state.robot_busy_owner == BUSY_NONE


def test_program_control_return_control_acts_like_stop(io_control, state, dashboard_link):
    """returnControlToECU(0x00)는 정지와 동일하게 처리된다"""
    state.session = SESSION_EXTENDED
    resp = run(io_control, "2F 02 01 00")
    assert resp == "6F 02 01 00"
    assert dashboard_link.sent == ["stop"]
    assert state.robot_busy_owner == BUSY_NONE


def test_speed_slider_return_control_sets_100(io_control, state, rtde_link):
    """속도 슬라이더 returnControl은 100으로 설정한다"""
    state.session = SESSION_EXTENDED
    resp = run(io_control, "2F 02 02 00")
    assert resp == "6F 02 02 00"
    assert rtde_link.speed_slider == 100


def test_reset_hook_skips_speed_slider_when_rtde_disconnected(io_control, state, rtde_link):
    """리셋 훅은 RTDE 미연결 상태에서 속도 슬라이더 설정을 시도하지 않는다"""
    rtde_link.speed_slider = 42
    rtde_link.connected = False

    state.reset_to_default()

    assert rtde_link.speed_slider == 42


def test_power_brake_requires_security_unlock(io_control, state):
    """0x0203은 보안 잠금 해제 안 되어 있으면 NRC 0x33"""
    state.session = SESSION_EXTENDED
    state.security_unlocked = False
    with pytest.raises(NRCError) as exc_info:
        run(io_control, "2F 02 03 03 01")
    assert exc_info.value.nrc == 0x33


def test_power_brake_power_on(io_control, state, dashboard_link):
    """보안 해제 후 0x0203 값 1은 power on을 전송한다"""
    state.session = SESSION_EXTENDED
    state.security_unlocked = True
    resp = run(io_control, "2F 02 03 03 01")
    assert resp == "6F 02 03 03 01"
    assert dashboard_link.sent == ["power on"]


def test_power_brake_return_control_rejected(io_control, state):
    """0x0203은 returnControl 개념이 없어 NRC 0x31"""
    state.session = SESSION_EXTENDED
    state.security_unlocked = True
    with pytest.raises(NRCError) as exc_info:
        run(io_control, "2F 02 03 00")
    assert exc_info.value.nrc == 0x31


def test_safety_recovery_requires_security_unlock(io_control, state):
    """0x0204는 보안 잠금 해제 안 되어 있으면 NRC 0x33"""
    state.session = SESSION_EXTENDED
    state.security_unlocked = False
    with pytest.raises(NRCError) as exc_info:
        run(io_control, "2F 02 04 03 02")
    assert exc_info.value.nrc == 0x33


def test_safety_recovery_close_popup(io_control, state, dashboard_link):
    """0x0204 값 2는 safety popup 닫기를 전송한다"""
    state.session = SESSION_EXTENDED
    state.security_unlocked = True
    resp = run(io_control, "2F 02 04 03 02")
    assert resp == "6F 02 04 03 02"
    assert dashboard_link.sent == ["close safety popup"]


def test_safety_recovery_unlock_blocked_by_ready_check(state, dashboard_link, rtde_link):
    """unlock_ready_check가 False면 보호정지 해제는 NRC 0x37"""
    io_control = IoControl(state, dashboard_link, rtde_link, unlock_ready_check=lambda: False)
    state.session = SESSION_EXTENDED
    state.security_unlocked = True
    with pytest.raises(NRCError) as exc_info:
        run(io_control, "2F 02 04 03 01")
    assert exc_info.value.nrc == 0x37


def test_safety_recovery_unlock_allowed_by_ready_check(state, dashboard_link, rtde_link):
    """unlock_ready_check가 True면 보호정지 해제가 진행된다"""
    io_control = IoControl(state, dashboard_link, rtde_link, unlock_ready_check=lambda: True)
    state.session = SESSION_EXTENDED
    state.security_unlocked = True
    resp = run(io_control, "2F 02 04 03 01")
    assert resp == "6F 02 04 03 01"
    assert dashboard_link.sent == ["unlock protective stop"]


def test_gripper_saves_last_command(io_control, state):
    """그리퍼 값은 state.last_gripper_cmd에 저장된다"""
    state.session = SESSION_EXTENDED
    resp = run(io_control, "2F 02 06 03 32")
    assert resp == "6F 02 06 03 32"
    assert state.last_gripper_cmd == 0x32


def test_gripper_return_control_rejected(io_control, state):
    """그리퍼는 returnControl 개념이 없어 NRC 0x31"""
    state.session = SESSION_EXTENDED
    with pytest.raises(NRCError) as exc_info:
        run(io_control, "2F 02 06 00")
    assert exc_info.value.nrc == 0x31


def test_undefined_did_rejected(io_control, state):
    """정의되지 않은 DID는 NRC 0x31"""
    state.session = SESSION_EXTENDED
    with pytest.raises(NRCError) as exc_info:
        run(io_control, "2F 09 99 03 01")
    assert exc_info.value.nrc == 0x31
