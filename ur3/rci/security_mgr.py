"""보안 접근(0x27) 처리, 학습용 고정 Seed/Key"""
import time

from . import frames

SID_SECURITY_ACCESS = 0x27

SF_REQUEST_SEED = 0x01
SF_SEND_KEY = 0x02

SEED = bytes.fromhex("11223344")
KEY = bytes.fromhex("55667788")

MAX_ATTEMPTS = 3


class SecurityMgr:
    """시드 발급, 키 검증, 실패 시 지연잠금을 관리한다"""

    def __init__(self, state, delay_sec=10.0):
        self.state = state
        self.delay_sec = delay_sec
        self._seed_issued = False
        self._fail_count = 0
        self._locked_until = None
        self.state.add_reset_hook(self._reset_internal)

    def handle(self, sid, payload):
        """SID 0x27 요청을 처리해 긍정 응답 바이트를 반환한다"""
        if sid != SID_SECURITY_ACCESS:
            raise frames.NRCError(sid, frames.NRC_SERVICE_NOT_SUPPORTED)
        sf = payload[0]
        if self._is_locked():
            raise frames.NRCError(SID_SECURITY_ACCESS, frames.NRC_REQUIRED_TIME_DELAY_NOT_EXPIRED)
        if sf == SF_REQUEST_SEED:
            return self._handle_request_seed()
        if sf == SF_SEND_KEY:
            return self._handle_send_key(payload)
        raise frames.NRCError(SID_SECURITY_ACCESS, frames.NRC_SUB_FUNCTION_NOT_SUPPORTED)

    def _handle_request_seed(self):
        """시드를 발급하고 발급 상태를 기록한다"""
        self._seed_issued = True
        return frames.positive(SID_SECURITY_ACCESS, bytes([SF_REQUEST_SEED]) + SEED)

    def _handle_send_key(self, payload):
        """전달된 키를 검증하고 결과에 따라 잠금/실패횟수를 처리한다"""
        if not self._seed_issued:
            raise frames.NRCError(SID_SECURITY_ACCESS, frames.NRC_REQUEST_SEQUENCE_ERROR)
        key = payload[1:]
        if key == KEY:
            with self.state.lock:
                self.state.security_unlocked = True
            self._fail_count = 0
            self._seed_issued = False
            return frames.positive(SID_SECURITY_ACCESS, bytes([SF_SEND_KEY]))
        self._seed_issued = False
        self._fail_count += 1
        if self._fail_count < MAX_ATTEMPTS:
            raise frames.NRCError(SID_SECURITY_ACCESS, frames.NRC_INVALID_KEY)
        self._locked_until = time.monotonic() + self.delay_sec  # 가정: 10초
        raise frames.NRCError(SID_SECURITY_ACCESS, frames.NRC_EXCEEDED_NUMBER_OF_ATTEMPTS)

    def _is_locked(self):
        """지연잠금 중인지 확인하고 시간이 지났으면 자동 해제한다"""
        if self._locked_until is None:
            return False
        if time.monotonic() < self._locked_until:
            return True
        self._locked_until = None
        self._fail_count = 0
        return False

    def _reset_internal(self):
        """에이전트 리셋 시 시드발급여부와 실패횟수를 초기화한다"""
        self._seed_issued = False
        self._fail_count = 0
        self._locked_until = None
