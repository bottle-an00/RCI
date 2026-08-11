"""AgentReset(0x11) 단위 테스트"""
import pytest

from ur3.rci import frames
from ur3.rci.agent_reset import AgentReset
from ur3.rci.state import BUSY_NONE, BUSY_URP_PROGRAM, SESSION_DEFAULT, SESSION_EXTENDED


@pytest.fixture
def mgr(state):
    return AgentReset(state)


def test_hard_reset(mgr, state):
    state.session = SESSION_EXTENDED
    state.security_unlocked = True
    state.robot_busy_owner = BUSY_URP_PROGRAM

    res = mgr.handle(0x11, bytes([0x01]))

    assert res == bytes.fromhex("51 01")
    assert state.session == SESSION_DEFAULT
    assert state.security_unlocked is False
    assert state.robot_busy_owner == BUSY_NONE


def test_hard_reset_runs_registered_hooks(mgr, state):
    calls = []
    state.add_reset_hook(lambda: calls.append(1))

    mgr.handle(0x11, bytes([0x01]))

    assert calls == [1]


def test_unsupported_sub_function(mgr):
    with pytest.raises(frames.NRCError) as exc:
        mgr.handle(0x11, bytes([0x02]))
    assert exc.value.nrc == frames.NRC_SUB_FUNCTION_NOT_SUPPORTED


def test_unsupported_sid(mgr):
    with pytest.raises(frames.NRCError) as exc:
        mgr.handle(0x22, bytes([0x01]))
    assert exc.value.nrc == frames.NRC_SERVICE_NOT_SUPPORTED
