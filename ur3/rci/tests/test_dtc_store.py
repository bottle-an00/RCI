"""DtcStore의 set/clear/handle 동작 검증"""
from ur3.rci.dtc_store import DtcStore
from ur3.rci.frames import NRCError, parse_hex, to_hex


def test_set_adds_new_code_with_confirmed_status(state):
    store = DtcStore(state)
    store.set(0xB10002)
    assert state.dtc_map == {0xB10002: 0x08}


def test_set_keeps_existing_status(state):
    store = DtcStore(state)
    state.dtc_map[0xB10002] = 0x08
    store.set(0xB10002)
    assert state.dtc_map == {0xB10002: 0x08}


def test_clear_all_when_codes_none(state):
    store = DtcStore(state)
    state.dtc_map[0xB10002] = 0x08
    state.dtc_map[0xC20101] = 0x08
    store.clear(None)
    assert state.dtc_map == {}


def test_clear_specific_codes(state):
    store = DtcStore(state)
    state.dtc_map[0xB10002] = 0x08
    state.dtc_map[0xC20101] = 0x08
    store.clear([0xB10002])
    assert state.dtc_map == {0xC20101: 0x08}


def test_handle_read_dtc_by_status_mask(state):
    store = DtcStore(state)
    state.dtc_map[0xB10002] = 0x08
    state.dtc_map[0xC20101] = 0x08
    response = store.handle(0x19, parse_hex("02 08"))
    assert to_hex(response) == "59 02 B1 00 02 08 C2 01 01 08"


def test_handle_clear_specific_group(state):
    store = DtcStore(state)
    state.dtc_map[0xB10002] = 0x08
    state.dtc_map[0xC20101] = 0x08
    response = store.handle(0x14, parse_hex("B1 00 02"))
    assert to_hex(response) == "54"
    assert state.dtc_map == {0xC20101: 0x08}


def test_handle_clear_all(state):
    store = DtcStore(state)
    state.dtc_map[0xB10002] = 0x08
    state.dtc_map[0xC20101] = 0x08
    response = store.handle(0x14, parse_hex("FF FF FF"))
    assert to_hex(response) == "54"
    assert state.dtc_map == {}


def test_handle_read_unsupported_sub_function_raises(state):
    store = DtcStore(state)
    try:
        store.handle(0x19, parse_hex("01"))
        assert False, "NRCError가 발생해야 한다"
    except NRCError as e:
        assert e.sid == 0x19


def test_handle_clear_invalid_length_raises(state):
    store = DtcStore(state)
    try:
        store.handle(0x14, parse_hex("B1 00"))
        assert False, "NRCError가 발생해야 한다"
    except NRCError as e:
        assert e.sid == 0x14
