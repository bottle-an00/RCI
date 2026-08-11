"""0x2F InputOutputControlByIdentifier(강제 구동) 서비스"""
from . import logger
from .state import SESSION_EXTENDED, BUSY_NONE, BUSY_URP_PROGRAM, BUSY_MOTION_ROUTINE
from .frames import (
    NRCError,
    NRC_SERVICE_NOT_SUPPORTED_IN_SESSION,
    NRC_SECURITY_ACCESS_DENIED,
    NRC_CONDITIONS_NOT_CORRECT,
    NRC_REQUEST_OUT_OF_RANGE,
    NRC_REQUIRED_TIME_DELAY_NOT_EXPIRED,
    NRC_INCORRECT_LENGTH_OR_FORMAT,
    positive,
)

IO_PARAM_RETURN_CONTROL = 0x00
IO_PARAM_ADJUSTMENT = 0x03

DID_PROGRAM_CONTROL = 0x0201
DID_SPEED_SLIDER = 0x0202
DID_POWER_BRAKE = 0x0203
DID_SAFETY_RECOVERY = 0x0204
DID_GRIPPER = 0x0206

SECURITY_REQUIRED_DIDS = (DID_POWER_BRAKE, DID_SAFETY_RECOVERY)


class IoControl:
    """DID 기반 강제 구동 요청을 처리한다"""

    def __init__(self, state, dashboard_link, rtde_link, unlock_ready_check=None):
        self.state = state
        self.dashboard_link = dashboard_link
        self.rtde_link = rtde_link
        self.unlock_ready_check = unlock_ready_check
        state.add_reset_hook(self._on_reset)

    def _on_reset(self):
        """세션종료, 타임아웃, 리셋 시 연결돼 있으면 강제구동 값을 기본값(속도 100퍼센트)으로 되돌린다"""
        if self.rtde_link.is_connected():
            self.rtde_link.set_speed_slider(100)

    def handle(self, sid, payload):
        """요청 payload를 검증하고 DID별 강제 구동을 실행한 뒤 echo 응답을 반환한다"""
        if len(payload) < 3:
            raise NRCError(sid, NRC_INCORRECT_LENGTH_OR_FORMAT)

        did = (payload[0] << 8) | payload[1]
        io_param = payload[2]
        control_data = payload[3:]

        with self.state.lock:
            if self.state.session != SESSION_EXTENDED:
                raise NRCError(sid, NRC_SERVICE_NOT_SUPPORTED_IN_SESSION)

            if did in SECURITY_REQUIRED_DIDS and not self.state.security_unlocked:
                raise NRCError(sid, NRC_SECURITY_ACCESS_DENIED)

            if did == DID_PROGRAM_CONTROL:
                self._program_control(sid, io_param, control_data)
            elif did == DID_SPEED_SLIDER:
                self._speed_slider(sid, io_param, control_data)
            elif did == DID_POWER_BRAKE:
                self._power_brake(sid, io_param, control_data)
            elif did == DID_SAFETY_RECOVERY:
                self._safety_recovery(sid, io_param, control_data)
            elif did == DID_GRIPPER:
                self._gripper(sid, io_param, control_data)
            else:
                raise NRCError(sid, NRC_REQUEST_OUT_OF_RANGE)

        return positive(sid, payload)

    def _program_control(self, sid, io_param, control_data):
        """0x0201 프로그램 실행 제어(정지/재생/일시정지)를 처리한다"""
        if not self.dashboard_link.is_connected():
            raise NRCError(sid, NRC_CONDITIONS_NOT_CORRECT)
        if io_param == IO_PARAM_RETURN_CONTROL:
            value = 0
        elif io_param == IO_PARAM_ADJUSTMENT:
            if len(control_data) < 1:
                raise NRCError(sid, NRC_INCORRECT_LENGTH_OR_FORMAT)
            value = control_data[0]
        else:
            raise NRCError(sid, NRC_REQUEST_OUT_OF_RANGE)

        if value == 0:
            self.dashboard_link.send("stop")
            self._set_busy_owner(BUSY_NONE)
        elif value == 1:
            if self.state.robot_busy_owner == BUSY_MOTION_ROUTINE:
                raise NRCError(sid, NRC_CONDITIONS_NOT_CORRECT)
            self.dashboard_link.send("play")
            self._set_busy_owner(BUSY_URP_PROGRAM)
        elif value == 2:
            self.dashboard_link.send("pause")
            self._set_busy_owner(BUSY_NONE)
        else:
            raise NRCError(sid, NRC_REQUEST_OUT_OF_RANGE)

    def _set_busy_owner(self, new_owner):
        """robot_busy_owner를 바꾸고 전이를 로그로 남긴다"""
        old_owner = self.state.robot_busy_owner
        self.state.robot_busy_owner = new_owner
        if old_owner != new_owner:
            logger.log_robot_event("BUSY_OWNER", f"{old_owner}->{new_owner}")

    def _speed_slider(self, sid, io_param, control_data):
        """0x0202 속도 슬라이더 값을 설정한다"""
        if not self.rtde_link.is_connected():
            raise NRCError(sid, NRC_CONDITIONS_NOT_CORRECT)
        if io_param == IO_PARAM_RETURN_CONTROL:
            value = 100
        elif io_param == IO_PARAM_ADJUSTMENT:
            if len(control_data) < 1:
                raise NRCError(sid, NRC_INCORRECT_LENGTH_OR_FORMAT)
            value = control_data[0]
            if value > 100:
                raise NRCError(sid, NRC_REQUEST_OUT_OF_RANGE)
        else:
            raise NRCError(sid, NRC_REQUEST_OUT_OF_RANGE)

        self.rtde_link.set_speed_slider(value)

    def _power_brake(self, sid, io_param, control_data):
        """0x0203 전원/브레이크 제어를 처리한다"""
        if not self.dashboard_link.is_connected():
            raise NRCError(sid, NRC_CONDITIONS_NOT_CORRECT)
        if io_param != IO_PARAM_ADJUSTMENT:
            raise NRCError(sid, NRC_REQUEST_OUT_OF_RANGE)
        if len(control_data) < 1:
            raise NRCError(sid, NRC_INCORRECT_LENGTH_OR_FORMAT)

        value = control_data[0]
        if value == 0:
            self.dashboard_link.send("power off")
        elif value == 1:
            self.dashboard_link.send("power on")
        elif value == 2:
            self.dashboard_link.send("brake release")
        else:
            raise NRCError(sid, NRC_REQUEST_OUT_OF_RANGE)

    def _safety_recovery(self, sid, io_param, control_data):
        """0x0204 안전 복구 제어를 처리한다"""
        if not self.dashboard_link.is_connected():
            raise NRCError(sid, NRC_CONDITIONS_NOT_CORRECT)
        if io_param != IO_PARAM_ADJUSTMENT:
            raise NRCError(sid, NRC_REQUEST_OUT_OF_RANGE)
        if len(control_data) < 1:
            raise NRCError(sid, NRC_INCORRECT_LENGTH_OR_FORMAT)

        value = control_data[0]
        if value == 1:
            if self.unlock_ready_check is not None and not self.unlock_ready_check():
                raise NRCError(sid, NRC_REQUIRED_TIME_DELAY_NOT_EXPIRED)
            self.dashboard_link.send("unlock protective stop")
        elif value == 2:
            self.dashboard_link.send("close safety popup")
        elif value == 3:
            self.dashboard_link.send("restart safety")
        else:
            raise NRCError(sid, NRC_REQUEST_OUT_OF_RANGE)

    def _gripper(self, sid, io_param, control_data):
        """0x0206 그리퍼 목표값을 상태에 저장한다"""
        if io_param != IO_PARAM_ADJUSTMENT:
            raise NRCError(sid, NRC_REQUEST_OUT_OF_RANGE)
        if len(control_data) < 1:
            raise NRCError(sid, NRC_INCORRECT_LENGTH_OR_FORMAT)

        value = control_data[0]
        if value > 100:
            raise NRCError(sid, NRC_REQUEST_OUT_OF_RANGE)

        self.state.last_gripper_cmd = value
        # TODO: 그리퍼 인터페이스 미확정으로 실제 I/O 신호 전송은 구현하지 않음
