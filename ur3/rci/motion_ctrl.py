"""모션 실행(0x31 RoutineControl) 서비스 모듈. MoveJoint/MoveLinear만 지원한다"""
import math
import threading
import time

from . import codec
from . import frames
from . import logger
from .frames import NRCError
from .state import BUSY_MOTION_ROUTINE, BUSY_NONE, BUSY_URP_PROGRAM, SESSION_EXTENDED

SF_START = 0x01
SF_STOP = 0x02
SF_RESULTS = 0x03

RID_MOVE_JOINT = 0x0301
RID_MOVE_LINEAR = 0x0302
SUPPORTED_RIDS = (RID_MOVE_JOINT, RID_MOVE_LINEAR)

PARAM_LEN = 14

JOINT_ANGLE_SCALE = 10      # 0.1도 단위
TCP_POS_SCALE = 10          # 0.1mm 단위
TCP_ORIENT_SCALE = 1000     # 0.001rad 단위
EXEC_TIME_SCALE = 10        # 0.1초 단위

JOINT_ANGLE_LIMIT_DEG = 360.0
TCP_POS_LIMIT_MM = 1000.0
TCP_ORIENT_LIMIT_RAD = 6.283
PERCENT_MIN = 1
PERCENT_MAX = 100

RESULT_SUCCESS = 1
RESULT_FAILURE = 2


def _rid_bytes(rid):
    """RID를 2바이트 빅엔디안으로 변환한다"""
    return bytes([(rid >> 8) & 0xFF, rid & 0xFF])


def _in_range(values, low, high):
    """모든 값이 [low, high] 범위 안에 있는지 검사한다"""
    return all(low <= v <= high for v in values)


class MotionCtrl:
    """0x31 RoutineControl(MoveJoint/MoveLinear) 요청을 처리한다"""

    def __init__(self, state, rtde_link, runaway_timeout_sec=45):
        self.state = state
        self.rtde_link = rtde_link
        self.runaway_timeout_sec = runaway_timeout_sec
        self.active_rid = None
        self.active_kind = None
        self.target_values = None
        self.start_time = None
        self.timer = None
        state.add_reset_hook(self._on_reset)

    def handle(self, sid, payload):
        """SID 0x31 요청을 서브펑션별로 분기 처리한다"""
        if len(payload) < 3:
            raise NRCError(sid, frames.NRC_INCORRECT_LENGTH_OR_FORMAT)
        sf = payload[0]
        rid = (payload[1] << 8) | payload[2]
        params = payload[3:]
        if sf == SF_START:
            return self._start_routine(sid, rid, params)
        if sf == SF_STOP:
            return self._stop_routine(sid, rid)
        if sf == SF_RESULTS:
            return self._request_results(sid, rid)
        raise NRCError(sid, frames.NRC_SUB_FUNCTION_NOT_SUPPORTED)

    def _start_routine(self, sid, rid, params):
        """startRoutine 서브펑션. 검증 후 move_j/move_l을 호출한다"""
        with self.state.lock:
            if self.state.robot_busy_owner == BUSY_URP_PROGRAM:
                raise NRCError(sid, frames.NRC_CONDITIONS_NOT_CORRECT)
            if self.state.robot_busy_owner == BUSY_MOTION_ROUTINE:
                raise NRCError(sid, frames.NRC_BUSY_REPEAT_REQUEST)
            if self.state.session != SESSION_EXTENDED:
                raise NRCError(sid, frames.NRC_SERVICE_NOT_SUPPORTED_IN_SESSION)
            if not self.state.security_unlocked:
                raise NRCError(sid, frames.NRC_SECURITY_ACCESS_DENIED)
            if rid not in SUPPORTED_RIDS:
                raise NRCError(sid, frames.NRC_REQUEST_OUT_OF_RANGE)
            if len(params) != PARAM_LEN:
                raise NRCError(sid, frames.NRC_INCORRECT_LENGTH_OR_FORMAT)
            if not self.rtde_link.is_connected():
                raise NRCError(sid, frames.NRC_CONDITIONS_NOT_CORRECT)

            if rid == RID_MOVE_JOINT:
                self._start_move_joint(sid, params)
            else:
                self._start_move_linear(sid, params)

            self.active_rid = rid
            self.start_time = time.time()
            self.state.robot_busy_owner = BUSY_MOTION_ROUTINE
            self._start_runaway_timer()
        logger.log_robot_event("BUSY_OWNER", f"NONE->MOTION_ROUTINE rid={rid:04X}")
        return frames.positive(sid, bytes([SF_START]) + _rid_bytes(rid) + b"\x00")

    def _start_move_joint(self, sid, params):
        """MoveJoint 파라미터를 검증하고 move_j를 호출한다"""
        angles_deg = codec.unpack_int16_list(params[0:12], JOINT_ANGLE_SCALE)
        speed_pct = codec.unpack_uint8(params[12:13])
        accel_pct = codec.unpack_uint8(params[13:14])
        if not _in_range(angles_deg, -JOINT_ANGLE_LIMIT_DEG, JOINT_ANGLE_LIMIT_DEG):
            raise NRCError(sid, frames.NRC_REQUEST_OUT_OF_RANGE)
        if not _in_range([speed_pct, accel_pct], PERCENT_MIN, PERCENT_MAX):
            raise NRCError(sid, frames.NRC_REQUEST_OUT_OF_RANGE)

        # 가정: 속도/가속도 백분율을 각각 3.14 rad/s, 3.14 rad/s^2 만점 기준으로 환산
        speed_rad_s = speed_pct / 100 * 3.14
        accel_rad_s2 = accel_pct / 100 * 3.14
        angles_rad = [math.radians(a) for a in angles_deg]

        self.rtde_link.move_j(angles_rad, speed_rad_s, accel_rad_s2)
        self.active_kind = "joint"
        self.target_values = angles_deg

    def _start_move_linear(self, sid, params):
        """MoveLinear 파라미터를 검증하고 move_l을 호출한다"""
        pos_mm = codec.unpack_int16_list(params[0:6], TCP_POS_SCALE)
        orient_rad = codec.unpack_int16_list(params[6:12], TCP_ORIENT_SCALE)
        speed_pct = codec.unpack_uint8(params[12:13])
        accel_pct = codec.unpack_uint8(params[13:14])
        if not _in_range(pos_mm, -TCP_POS_LIMIT_MM, TCP_POS_LIMIT_MM):
            raise NRCError(sid, frames.NRC_REQUEST_OUT_OF_RANGE)
        if not _in_range(orient_rad, -TCP_ORIENT_LIMIT_RAD, TCP_ORIENT_LIMIT_RAD):
            raise NRCError(sid, frames.NRC_REQUEST_OUT_OF_RANGE)
        if not _in_range([speed_pct, accel_pct], PERCENT_MIN, PERCENT_MAX):
            raise NRCError(sid, frames.NRC_REQUEST_OUT_OF_RANGE)

        # 가정: 속도/가속도 백분율을 각각 0.25 m/s, 1.2 m/s^2 만점 기준으로 환산
        speed_m_s = speed_pct / 100 * 0.25
        accel_m_s2 = accel_pct / 100 * 1.2
        pos_m = [p / 1000 for p in pos_mm]

        self.rtde_link.move_l(pos_m + orient_rad, speed_m_s, accel_m_s2)
        self.active_kind = "linear"
        self.target_values = (pos_mm, orient_rad)

    def _stop_routine(self, sid, rid):
        """stopRoutine 서브펑션. 통신이 살아있으면 로봇을 정지시키고, 두절 중이면 정직하게 실패를 알린다"""
        with self.state.lock:
            if not self.rtde_link.is_connected():
                raise NRCError(sid, frames.NRC_CONDITIONS_NOT_CORRECT)
            self.rtde_link.stop_j()
            self.rtde_link.stop_l()
            self.state.robot_busy_owner = BUSY_NONE
            self._cancel_runaway_timer()
        logger.log_robot_event("BUSY_OWNER", f"MOTION_ROUTINE->NONE rid={rid:04X} (stopRoutine)")
        return frames.positive(sid, bytes([SF_STOP]) + _rid_bytes(rid) + b"\x00")

    def _request_results(self, sid, rid):
        """requestRoutineResults 서브펑션. 진행중이면 pending, 끝났으면 결과 반환"""
        with self.state.lock:
            if self.active_rid is None or rid != self.active_rid:
                raise NRCError(sid, frames.NRC_REQUEST_SEQUENCE_ERROR)

            progress = self.rtde_link.get_async_progress()
            if progress < 1.0 and self.state.robot_busy_owner == BUSY_MOTION_ROUTINE:
                raise NRCError(sid, frames.NRC_RESPONSE_PENDING)

            self._cancel_runaway_timer()
            self.state.robot_busy_owner = BUSY_NONE
            result_bytes = self._build_result_bytes(progress)
        logger.log_robot_event("BUSY_OWNER", f"MOTION_ROUTINE->NONE rid={rid:04X} (completed)")
        return frames.positive(sid, bytes([SF_RESULTS]) + _rid_bytes(rid) + result_bytes)

    def _build_result_bytes(self, progress):
        """완료 결과 바이트(상태+최종값+실행시간)를 조립한다"""
        status = RESULT_SUCCESS if progress >= 1.0 else RESULT_FAILURE
        if self.active_kind == "joint":
            values_bytes = codec.pack_int16_list(self.target_values, JOINT_ANGLE_SCALE)
        else:
            pos_mm, orient_rad = self.target_values
            values_bytes = (
                codec.pack_int16_list(pos_mm, TCP_POS_SCALE)
                + codec.pack_int16_list(orient_rad, TCP_ORIENT_SCALE)
            )
        elapsed_sec = time.time() - self.start_time if self.start_time else 0.0
        exec_time = max(0, min(65535, round(elapsed_sec * EXEC_TIME_SCALE)))
        return bytes([status]) + values_bytes + codec.pack_uint16(exec_time)

    def _start_runaway_timer(self):
        """완료 안내가 없을 때 자동 정지시키는 타이머를 시작한다"""
        self._cancel_runaway_timer()
        self.timer = threading.Timer(self.runaway_timeout_sec, self._on_runaway_timeout)
        self.timer.daemon = True
        self.timer.start()

    def _cancel_runaway_timer(self):
        """진행중인 런어웨이 타이머가 있으면 취소한다"""
        if self.timer is not None:
            self.timer.cancel()
            self.timer = None

    def _on_runaway_timeout(self):
        """타임아웃 시 연결돼 있으면 로봇을 정지시키고, 어떤 경우든 제어권을 해제한다"""
        with self.state.lock:
            if self.rtde_link.is_connected():
                self.rtde_link.stop_j()
                self.rtde_link.stop_l()
            self.state.robot_busy_owner = BUSY_NONE
            self.timer = None
        logger.log_robot_event("RUNAWAY_TIMEOUT", f"rid={self.active_rid}")

    def _on_reset(self):
        """세션 타임아웃/리셋 시 연결돼 있으면 진행중인 모션을 정지시키고, 어떤 경우든 내부 상태를 초기화한다"""
        with self.state.lock:
            self._cancel_runaway_timer()
            if self.rtde_link.is_connected():
                self.rtde_link.stop_j()
                self.rtde_link.stop_l()
            self.active_rid = None
            self.active_kind = None
            self.target_values = None
            self.start_time = None
