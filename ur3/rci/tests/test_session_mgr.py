"""SessionMgr(0x10/0x3E) 단위 테스트"""
import time

import pytest

from ur3.rci import frames
from ur3.rci.session_mgr import SessionMgr
from ur3.rci.state import SESSION_DEFAULT, SESSION_EXTENDED


@pytest.fixture
def mgr(state):
    m = SessionMgr(state, s3_timeout_sec=0.05)
    yield m
    m.stop()


def test_default_session(mgr, state):
    res = mgr.handle(0x10, bytes([0x01]))
    assert res == bytes.fromhex("50 01 00 32 01 F4")
    assert state.session == SESSION_DEFAULT


def test_extended_session(mgr, state):
    res = mgr.handle(0x10, bytes([0x03]))
    assert res == bytes.fromhex("50 03 00 32 01 F4")
    assert state.session == SESSION_EXTENDED


def test_unsupported_sub_function(mgr):
    with pytest.raises(frames.NRCError) as exc:
        mgr.handle(0x10, bytes([0x02]))
    assert exc.value.nrc == frames.NRC_SUB_FUNCTION_NOT_SUPPORTED


def test_tester_present(mgr):
    res = mgr.handle(0x3E, bytes([0x00]))
    assert res == bytes.fromhex("7E 00")


def test_s3_timeout_resets_state(mgr, state):
    mgr.handle(0x10, bytes([0x03]))
    time.sleep(0.15)
    assert state.session == SESSION_DEFAULT


def test_tester_present_resets_s3_timer(mgr, state):
    mgr.handle(0x10, bytes([0x03]))
    time.sleep(0.03)
    mgr.handle(0x3E, bytes([0x00]))
    time.sleep(0.03)
    assert state.session == SESSION_EXTENDED
    time.sleep(0.1)
    assert state.session == SESSION_DEFAULT


def test_tester_present_in_default_session_no_timer(mgr, state):
    mgr.handle(0x3E, bytes([0x00]))
    time.sleep(0.1)
    assert state.session == SESSION_DEFAULT


def test_default_session_stops_timer(mgr, state):
    mgr.handle(0x10, bytes([0x03]))
    mgr.handle(0x10, bytes([0x01]))
    time.sleep(0.1)
    assert state.session == SESSION_DEFAULT
