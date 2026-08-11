"""SecurityMgr(0x27) 단위 테스트"""
import time

import pytest

from ur3.rci import frames
from ur3.rci.security_mgr import KEY, SecurityMgr


@pytest.fixture
def mgr(state):
    return SecurityMgr(state, delay_sec=0.05)


def test_request_seed(mgr):
    res = mgr.handle(0x27, bytes([0x01]))
    assert res == bytes.fromhex("67 01 11 22 33 44")


def test_send_key_success(mgr, state):
    mgr.handle(0x27, bytes([0x01]))
    res = mgr.handle(0x27, bytes([0x02]) + KEY)
    assert res == bytes.fromhex("67 02")
    assert state.security_unlocked is True


def test_send_key_without_seed_is_sequence_error(mgr):
    with pytest.raises(frames.NRCError) as exc:
        mgr.handle(0x27, bytes([0x02]) + KEY)
    assert exc.value.nrc == frames.NRC_REQUEST_SEQUENCE_ERROR


def test_send_key_wrong_key_invalid(mgr):
    mgr.handle(0x27, bytes([0x01]))
    with pytest.raises(frames.NRCError) as exc:
        mgr.handle(0x27, bytes([0x02]) + bytes.fromhex("00000000"))
    assert exc.value.nrc == frames.NRC_INVALID_KEY


def test_third_failure_locks_and_exceeds_attempts(mgr):
    for _ in range(2):
        mgr.handle(0x27, bytes([0x01]))
        with pytest.raises(frames.NRCError) as exc:
            mgr.handle(0x27, bytes([0x02]) + bytes.fromhex("00000000"))
        assert exc.value.nrc == frames.NRC_INVALID_KEY

    mgr.handle(0x27, bytes([0x01]))
    with pytest.raises(frames.NRCError) as exc:
        mgr.handle(0x27, bytes([0x02]) + bytes.fromhex("00000000"))
    assert exc.value.nrc == frames.NRC_EXCEEDED_NUMBER_OF_ATTEMPTS


def test_locked_rejects_request_seed_and_send_key(mgr):
    for _ in range(3):
        mgr.handle(0x27, bytes([0x01]))
        with pytest.raises(frames.NRCError):
            mgr.handle(0x27, bytes([0x02]) + bytes.fromhex("00000000"))

    with pytest.raises(frames.NRCError) as exc:
        mgr.handle(0x27, bytes([0x01]))
    assert exc.value.nrc == frames.NRC_REQUIRED_TIME_DELAY_NOT_EXPIRED

    with pytest.raises(frames.NRCError) as exc:
        mgr.handle(0x27, bytes([0x02]) + KEY)
    assert exc.value.nrc == frames.NRC_REQUIRED_TIME_DELAY_NOT_EXPIRED


def test_lock_auto_expires(mgr, state):
    for _ in range(3):
        mgr.handle(0x27, bytes([0x01]))
        with pytest.raises(frames.NRCError):
            mgr.handle(0x27, bytes([0x02]) + bytes.fromhex("00000000"))

    time.sleep(0.1)

    mgr.handle(0x27, bytes([0x01]))
    res = mgr.handle(0x27, bytes([0x02]) + KEY)
    assert res == bytes.fromhex("67 02")
    assert state.security_unlocked is True


def test_unsupported_sub_function(mgr):
    with pytest.raises(frames.NRCError) as exc:
        mgr.handle(0x27, bytes([0x05]))
    assert exc.value.nrc == frames.NRC_SUB_FUNCTION_NOT_SUPPORTED


def test_reset_to_default_clears_internal_state(mgr, state):
    mgr.handle(0x27, bytes([0x01]))
    state.reset_to_default()
    with pytest.raises(frames.NRCError) as exc:
        mgr.handle(0x27, bytes([0x02]) + KEY)
    assert exc.value.nrc == frames.NRC_REQUEST_SEQUENCE_ERROR
