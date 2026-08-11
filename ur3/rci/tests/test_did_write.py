"""DidWrite(0x2E) 단위 테스트"""
import pytest

from ur3.rci.did_write import DidWrite
from ur3.rci.frames import NRCError, negative, parse_hex, to_hex
from ur3.rci.settings_store import SettingsStore
from ur3.rci.state import SESSION_DEFAULT, SESSION_EXTENDED


@pytest.fixture
def settings_store(tmp_path):
    return SettingsStore(path=str(tmp_path / "settings.json"))


@pytest.fixture
def unlocked_state(state):
    """세션을 extended로, 보안을 해제 상태로 만든다"""
    state.session = SESSION_EXTENDED
    state.security_unlocked = True
    return state


def _handle(did_write, request_hex):
    """요청 hex 문자열을 SID, payload로 나눠 handle을 호출하고 응답 hex를 반환한다"""
    raw = parse_hex(request_hex)
    sid, payload = raw[0], raw[1:]
    return to_hex(did_write.handle(sid, payload))


def test_write_robot_ip(unlocked_state, settings_store):
    """0xF1A0 IP 쓰기는 4바이트를 a.b.c.d 문자열로 저장한다"""
    did_write = DidWrite(unlocked_state, settings_store)
    assert _handle(did_write, "2E F1 A0 C0 A8 01 66") == "6E F1 A0"
    assert settings_store.get("robot_ip") == "192.168.1.102"


def test_write_robot_ip_calls_on_ip_changed(unlocked_state, settings_store):
    """0xF1A0 IP 쓰기는 on_ip_changed 콜백에 새 IP를 전달한다"""
    changed = []
    did_write = DidWrite(unlocked_state, settings_store, on_ip_changed=changed.append)
    _handle(did_write, "2E F1 A0 C0 A8 01 66")
    assert changed == ["192.168.1.102"]


def test_write_serial_number(unlocked_state, settings_store):
    """0xF18C 시리얼번호 쓰기는 ascii를 그대로 저장한다"""
    did_write = DidWrite(unlocked_state, settings_store)
    payload_hex = "2E F1 8C " + to_hex(b"SN99887")
    assert _handle(did_write, payload_hex) == "6E F1 8C"
    assert settings_store.get("serial_number") == "SN99887"


def test_write_sw_update_date(unlocked_state, settings_store):
    """0xF199 SW 업데이트 날짜 쓰기는 BCD 3바이트를 YYMMDD 문자열로 저장한다"""
    did_write = DidWrite(unlocked_state, settings_store)
    assert _handle(did_write, "2E F1 99 26 07 27") == "6E F1 99"
    assert settings_store.get("sw_update_date") == "260727"


def test_write_sw_version_not_writable(unlocked_state, settings_store):
    """0xF195 SW버전은 쓰기 불가로 NRC 0x31을 발생시킨다"""
    did_write = DidWrite(unlocked_state, settings_store)
    with pytest.raises(NRCError) as exc:
        did_write.handle(0x2E, parse_hex("F1 95 01"))
    assert exc.value.nrc == 0x31


def test_write_undefined_did(unlocked_state, settings_store):
    """정의되지 않은 DID 쓰기는 NRC 0x31을 발생시킨다"""
    did_write = DidWrite(unlocked_state, settings_store)
    with pytest.raises(NRCError) as exc:
        did_write.handle(0x2E, parse_hex("00 01 FF"))
    assert exc.value.nrc == 0x31


def test_write_without_security_unlocked_raises_error(state, settings_store):
    """보안 미완료 상태에서 쓰기 요청시 NRC 0x33을 발생시킨다"""
    state.session = SESSION_EXTENDED
    state.security_unlocked = False
    did_write = DidWrite(state, settings_store)
    with pytest.raises(NRCError) as exc:
        did_write.handle(0x2E, parse_hex("F1 A0 C0 A8 01 66"))
    assert exc.value.nrc == 0x33
    assert to_hex(negative(exc.value.sid, exc.value.nrc)) == "7F 2E 33"


def test_write_in_default_session_raises_error(state, settings_store):
    """default 세션에서 쓰기 요청시 NRC 0x7F를 발생시킨다"""
    state.session = SESSION_DEFAULT
    state.security_unlocked = True
    did_write = DidWrite(state, settings_store)
    with pytest.raises(NRCError) as exc:
        did_write.handle(0x2E, parse_hex("F1 A0 C0 A8 01 66"))
    assert exc.value.nrc == 0x7F
