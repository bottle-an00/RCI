"""진단 세션 제어(0x10)와 TesterPresent(0x3E) 처리"""
import threading

from . import frames
from .state import SESSION_EXTENDED

SID_DIAGNOSTIC_SESSION_CONTROL = 0x10
SID_TESTER_PRESENT = 0x3E

SF_DEFAULT_SESSION = 0x01
SF_EXTENDED_DIAGNOSTIC_SESSION = 0x03

SF_TESTER_PRESENT_ZERO_SUB_FUNCTION = 0x00

P2_P2STAR_PAYLOAD = bytes([0x00, 0x32, 0x01, 0xF4])


class SessionMgr:
    """세션 전환과 S3 타이머를 관리한다"""

    def __init__(self, state, s3_timeout_sec=5.0):
        self.state = state
        self.s3_timeout_sec = s3_timeout_sec
        self._s3_timer = None
        self._timer_lock = threading.Lock()

    def handle(self, sid, payload):
        """SID 0x10 또는 0x3E 요청을 처리해 긍정 응답 바이트를 반환한다"""
        if sid == SID_DIAGNOSTIC_SESSION_CONTROL:
            return self._handle_session_control(payload)
        if sid == SID_TESTER_PRESENT:
            return self._handle_tester_present(payload)
        raise frames.NRCError(sid, frames.NRC_SERVICE_NOT_SUPPORTED)

    def _handle_session_control(self, payload):
        """0x10 요청의 서브펑션에 따라 세션을 전환한다"""
        sf = payload[0]
        if sf == SF_DEFAULT_SESSION:
            self.state.reset_to_default()
            self._stop_s3_timer()
        elif sf == SF_EXTENDED_DIAGNOSTIC_SESSION:
            with self.state.lock:
                self.state.session = SESSION_EXTENDED
            self._restart_s3_timer()
        else:
            raise frames.NRCError(SID_DIAGNOSTIC_SESSION_CONTROL, frames.NRC_SUB_FUNCTION_NOT_SUPPORTED)
        return frames.positive(SID_DIAGNOSTIC_SESSION_CONTROL, bytes([sf]) + P2_P2STAR_PAYLOAD)

    def _handle_tester_present(self, payload):
        """0x3E 요청에 응답하고 extended 세션이면 S3 타이머를 리셋한다"""
        with self.state.lock:
            is_extended = self.state.session == SESSION_EXTENDED
        if is_extended:
            self._restart_s3_timer()
        return frames.positive(SID_TESTER_PRESENT, bytes([SF_TESTER_PRESENT_ZERO_SUB_FUNCTION]))

    def _restart_s3_timer(self):
        """S3 타이머를 새로 시작한다 (기존 타이머는 취소 후 재시작)"""
        with self._timer_lock:
            if self._s3_timer is not None:
                self._s3_timer.cancel()
            self._s3_timer = threading.Timer(self.s3_timeout_sec, self._on_s3_timeout)
            self._s3_timer.daemon = True
            self._s3_timer.start()

    def _stop_s3_timer(self):
        """S3 타이머를 취소하고 정리한다"""
        with self._timer_lock:
            if self._s3_timer is not None:
                self._s3_timer.cancel()
                self._s3_timer = None

    def _on_s3_timeout(self):
        """S3 타임아웃 시 상태를 기본값으로 리셋한다"""
        self.state.reset_to_default()
        with self._timer_lock:
            self._s3_timer = None

    def stop(self):
        """S3 타이머를 종료한다 (에이전트 종료 시 호출)"""
        self._stop_s3_timer()
