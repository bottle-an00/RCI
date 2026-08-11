"""motion_ctrl.MotionCtrl(0x31 RoutineControl) 동작 검증"""
import pytest

from ur3.rci import codec, frames
from ur3.rci.motion_ctrl import MotionCtrl, RID_MOVE_JOINT, RID_MOVE_LINEAR
from ur3.rci.state import BUSY_MOTION_ROUTINE, BUSY_NONE, BUSY_URP_PROGRAM, SESSION_EXTENDED

SID = 0x31


def _rid(rid):
    """RID를 2바이트로 변환한다"""
    return bytes([(rid >> 8) & 0xFF, rid & 0xFF])


def _joint_params(angles_deg, speed_pct, accel_pct):
    """MoveJoint 파라미터 14바이트를 조립한다"""
    return codec.pack_int16_list(angles_deg, 10) + codec.pack_uint8(speed_pct) + codec.pack_uint8(accel_pct)


def _linear_params(pos_mm, orient_rad, speed_pct, accel_pct):
    """MoveLinear 파라미터 14바이트를 조립한다"""
    return (
        codec.pack_int16_list(pos_mm, 10)
        + codec.pack_int16_list(orient_rad, 1000)
        + codec.pack_uint8(speed_pct)
        + codec.pack_uint8(accel_pct)
    )


def _start_payload(rid, params):
    """startRoutine 요청 페이로드를 조립한다"""
    return bytes([0x01]) + _rid(rid) + params


def _stop_payload(rid):
    """stopRoutine 요청 페이로드를 조립한다"""
    return bytes([0x02]) + _rid(rid) + b""


def _results_payload(rid):
    """requestRoutineResults 요청 페이로드를 조립한다"""
    return bytes([0x03]) + _rid(rid) + b""


def _unlocked_extended(state):
    """확장 세션과 보안 해제 상태로 만든다"""
    state.session = SESSION_EXTENDED
    state.security_unlocked = True


def test_move_joint_start_success(state, rtde_link):
    _unlocked_extended(state)
    ctrl = MotionCtrl(state, rtde_link)
    angles = [10.0, -20.0, 30.0, 0.0, 90.0, -90.0]
    payload = _start_payload(RID_MOVE_JOINT, _joint_params(angles, 50, 50))

    resp = ctrl.handle(SID, payload)

    assert resp == bytes([0x71, 0x01, 0x03, 0x01, 0x00])
    assert state.robot_busy_owner == BUSY_MOTION_ROUTINE
    assert len(rtde_link.moves) == 1
    kind, q, speed, accel = rtde_link.moves[0]
    assert kind == "j"
    assert speed == pytest.approx(50 / 100 * 3.14)
    assert accel == pytest.approx(50 / 100 * 3.14)
    for got, want in zip(q, angles):
        assert got == pytest.approx(want * 3.14159265358979 / 180, abs=1e-3)


def test_move_linear_start_success(state, rtde_link):
    _unlocked_extended(state)
    ctrl = MotionCtrl(state, rtde_link)
    pos = [100.0, -50.0, 200.0]
    orient = [1.0, -2.0, 3.0]
    payload = _start_payload(RID_MOVE_LINEAR, _linear_params(pos, orient, 20, 40))

    resp = ctrl.handle(SID, payload)

    assert resp == bytes([0x71, 0x01, 0x03, 0x02, 0x00])
    assert state.robot_busy_owner == BUSY_MOTION_ROUTINE
    kind, pose, speed, accel = rtde_link.moves[0]
    assert kind == "l"
    assert speed == pytest.approx(20 / 100 * 0.25)
    assert accel == pytest.approx(40 / 100 * 1.2)
    assert pose[0:3] == pytest.approx([p / 1000 for p in pos])
    assert pose[3:6] == pytest.approx(orient)


def test_request_results_success_after_completion(state, rtde_link):
    _unlocked_extended(state)
    ctrl = MotionCtrl(state, rtde_link)
    angles = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0]
    ctrl.handle(SID, _start_payload(RID_MOVE_JOINT, _joint_params(angles, 50, 50)))

    rtde_link.progress = 1.0
    resp = ctrl.handle(SID, _results_payload(RID_MOVE_JOINT))

    assert resp[0:4] == bytes([0x71, 0x03, 0x03, 0x01])
    status = resp[4]
    values = codec.unpack_int16_list(resp[5:17], 10)
    exec_time = codec.unpack_uint16(resp[17:19])
    assert status == 1
    assert values == pytest.approx(angles)
    assert exec_time >= 0
    assert state.robot_busy_owner == BUSY_NONE


def test_request_results_pending_while_in_progress(state, rtde_link):
    _unlocked_extended(state)
    ctrl = MotionCtrl(state, rtde_link)
    angles = [0.0] * 6
    ctrl.handle(SID, _start_payload(RID_MOVE_JOINT, _joint_params(angles, 50, 50)))

    rtde_link.progress = 0.5
    with pytest.raises(frames.NRCError) as exc:
        ctrl.handle(SID, _results_payload(RID_MOVE_JOINT))

    assert exc.value.nrc == frames.NRC_RESPONSE_PENDING
    assert state.robot_busy_owner == BUSY_MOTION_ROUTINE


def test_stop_routine_always_succeeds_without_start(state, rtde_link):
    ctrl = MotionCtrl(state, rtde_link)
    resp = ctrl.handle(SID, _stop_payload(RID_MOVE_JOINT))

    assert resp == bytes([0x71, 0x02, 0x03, 0x01, 0x00])
    assert rtde_link.stopped is True
    assert state.robot_busy_owner == BUSY_NONE


def test_stop_routine_stops_active_motion(state, rtde_link):
    _unlocked_extended(state)
    ctrl = MotionCtrl(state, rtde_link)
    angles = [0.0] * 6
    ctrl.handle(SID, _start_payload(RID_MOVE_JOINT, _joint_params(angles, 50, 50)))

    resp = ctrl.handle(SID, _stop_payload(RID_MOVE_JOINT))

    assert resp == bytes([0x71, 0x02, 0x03, 0x01, 0x00])
    assert rtde_link.stopped is True
    assert state.robot_busy_owner == BUSY_NONE


def test_start_rejected_when_session_not_extended(state, rtde_link):
    ctrl = MotionCtrl(state, rtde_link)
    angles = [0.0] * 6
    payload = _start_payload(RID_MOVE_JOINT, _joint_params(angles, 50, 50))

    with pytest.raises(frames.NRCError) as exc:
        ctrl.handle(SID, payload)

    assert exc.value.nrc == frames.NRC_SERVICE_NOT_SUPPORTED_IN_SESSION


def test_start_rejected_when_security_locked(state, rtde_link):
    state.session = SESSION_EXTENDED
    ctrl = MotionCtrl(state, rtde_link)
    angles = [0.0] * 6
    payload = _start_payload(RID_MOVE_JOINT, _joint_params(angles, 50, 50))

    with pytest.raises(frames.NRCError) as exc:
        ctrl.handle(SID, payload)

    assert exc.value.nrc == frames.NRC_SECURITY_ACCESS_DENIED


def test_start_rejected_when_busy_urp_program(state, rtde_link):
    _unlocked_extended(state)
    state.robot_busy_owner = BUSY_URP_PROGRAM
    ctrl = MotionCtrl(state, rtde_link)
    angles = [0.0] * 6
    payload = _start_payload(RID_MOVE_JOINT, _joint_params(angles, 50, 50))

    with pytest.raises(frames.NRCError) as exc:
        ctrl.handle(SID, payload)

    assert exc.value.nrc == frames.NRC_CONDITIONS_NOT_CORRECT


def test_start_rejected_when_already_running_motion(state, rtde_link):
    _unlocked_extended(state)
    ctrl = MotionCtrl(state, rtde_link)
    angles = [0.0] * 6
    ctrl.handle(SID, _start_payload(RID_MOVE_JOINT, _joint_params(angles, 50, 50)))

    with pytest.raises(frames.NRCError) as exc:
        ctrl.handle(SID, _start_payload(RID_MOVE_LINEAR, _linear_params([0, 0, 0], [0, 0, 0], 50, 50)))

    assert exc.value.nrc == frames.NRC_BUSY_REPEAT_REQUEST


def test_start_rejected_for_unsupported_rid(state, rtde_link):
    _unlocked_extended(state)
    ctrl = MotionCtrl(state, rtde_link)
    payload = _start_payload(0x0303, b"\x00" * 14)

    with pytest.raises(frames.NRCError) as exc:
        ctrl.handle(SID, payload)

    assert exc.value.nrc == frames.NRC_REQUEST_OUT_OF_RANGE


def test_start_rejected_for_wrong_param_length(state, rtde_link):
    _unlocked_extended(state)
    ctrl = MotionCtrl(state, rtde_link)
    payload = _start_payload(RID_MOVE_JOINT, b"\x00" * 10)

    with pytest.raises(frames.NRCError) as exc:
        ctrl.handle(SID, payload)

    assert exc.value.nrc == frames.NRC_INCORRECT_LENGTH_OR_FORMAT


def test_start_rejected_for_out_of_range_angle(state, rtde_link):
    _unlocked_extended(state)
    ctrl = MotionCtrl(state, rtde_link)
    angles = [400.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    payload = _start_payload(RID_MOVE_JOINT, _joint_params(angles, 50, 50))

    with pytest.raises(frames.NRCError) as exc:
        ctrl.handle(SID, payload)

    assert exc.value.nrc == frames.NRC_REQUEST_OUT_OF_RANGE


def test_start_rejected_for_out_of_range_percent(state, rtde_link):
    _unlocked_extended(state)
    ctrl = MotionCtrl(state, rtde_link)
    angles = [0.0] * 6
    payload = _start_payload(RID_MOVE_JOINT, _joint_params(angles, 0, 50))

    with pytest.raises(frames.NRCError) as exc:
        ctrl.handle(SID, payload)

    assert exc.value.nrc == frames.NRC_REQUEST_OUT_OF_RANGE


def test_request_results_without_start_is_sequence_error(state, rtde_link):
    ctrl = MotionCtrl(state, rtde_link)

    with pytest.raises(frames.NRCError) as exc:
        ctrl.handle(SID, _results_payload(RID_MOVE_JOINT))

    assert exc.value.nrc == frames.NRC_REQUEST_SEQUENCE_ERROR


def test_start_rejected_when_rtde_disconnected(state, rtde_link):
    _unlocked_extended(state)
    rtde_link.connected = False
    ctrl = MotionCtrl(state, rtde_link)
    angles = [0.0] * 6
    payload = _start_payload(RID_MOVE_JOINT, _joint_params(angles, 50, 50))

    with pytest.raises(frames.NRCError) as exc:
        ctrl.handle(SID, payload)

    assert exc.value.nrc == frames.NRC_CONDITIONS_NOT_CORRECT


def test_reset_hook_stops_motion_and_clears_state(state, rtde_link):
    _unlocked_extended(state)
    ctrl = MotionCtrl(state, rtde_link)
    angles = [0.0] * 6
    ctrl.handle(SID, _start_payload(RID_MOVE_JOINT, _joint_params(angles, 50, 50)))

    state.reset_to_default()

    assert rtde_link.stopped is True
    with pytest.raises(frames.NRCError) as exc:
        ctrl.handle(SID, _results_payload(RID_MOVE_JOINT))
    assert exc.value.nrc == frames.NRC_REQUEST_SEQUENCE_ERROR


def test_stop_routine_rejected_when_rtde_disconnected(state, rtde_link):
    """통신이 두절된 상태에서는 stopRoutine도 정직하게 실패를 알린다"""
    rtde_link.connected = False
    ctrl = MotionCtrl(state, rtde_link)

    with pytest.raises(frames.NRCError) as exc:
        ctrl.handle(SID, _stop_payload(RID_MOVE_JOINT))

    assert exc.value.nrc == frames.NRC_CONDITIONS_NOT_CORRECT
    assert rtde_link.stopped is False


def test_runaway_timeout_does_not_crash_when_rtde_disconnected(state, rtde_link):
    """런어웨이 타임아웃은 통신이 끊겨도 예외 없이 제어권을 해제한다"""
    _unlocked_extended(state)
    ctrl = MotionCtrl(state, rtde_link)
    angles = [0.0] * 6
    ctrl.handle(SID, _start_payload(RID_MOVE_JOINT, _joint_params(angles, 50, 50)))

    rtde_link.connected = False
    ctrl._on_runaway_timeout()

    assert state.robot_busy_owner == BUSY_NONE
    assert rtde_link.stopped is False


def test_reset_hook_does_not_crash_when_rtde_disconnected(state, rtde_link):
    """리셋 훅은 통신이 끊겨도 예외 없이 내부 상태를 초기화한다"""
    _unlocked_extended(state)
    ctrl = MotionCtrl(state, rtde_link)
    angles = [0.0] * 6
    ctrl.handle(SID, _start_payload(RID_MOVE_JOINT, _joint_params(angles, 50, 50)))

    rtde_link.connected = False
    state.reset_to_default()

    assert rtde_link.stopped is False
    with pytest.raises(frames.NRCError) as exc:
        ctrl.handle(SID, _results_payload(RID_MOVE_JOINT))
    assert exc.value.nrc == frames.NRC_REQUEST_SEQUENCE_ERROR
