"""ur3.uds_payload 단위 테스트. UR3_RCI_기능명세서.md §4.2~4.5 기준."""
import json

import pytest

from ur3 import uds_payload


def test_encode_hex_produces_uppercase_space_separated_no_prefix():
    assert uds_payload.encode_hex(bytes([0x22, 0x01, 0x07])) == "22 01 07"


def test_encode_hex_empty_bytes():
    assert uds_payload.encode_hex(b"") == ""


def test_decode_hex_round_trip():
    assert uds_payload.decode_hex("22 01 07") == bytes([0x22, 0x01, 0x07])


def test_decode_hex_lowercase_input_also_accepted():
    # 사양서는 발행 시 대문자를 요구하지만, 파싱은 대소문자에 관용적이어야 한다
    # (웹앱이 보내는 요청 payload를 우리가 통제할 수 없기 때문).
    assert uds_payload.decode_hex("AB CD") == uds_payload.decode_hex("ab cd") == bytes([0xAB, 0xCD])


def test_classify_type_positive():
    assert uds_payload.classify_type(bytes([0x62, 0x01, 0x07, 0x07])) == "positive"


def test_classify_type_negative():
    assert uds_payload.classify_type(bytes([0x7F, 0x22, 0x31])) == "negative"


def test_classify_type_empty_raw_is_positive():
    # 빈 바이트열은 0x7F로 시작할 수 없으므로 positive로 분류한다.
    assert uds_payload.classify_type(b"") == "positive"


def test_parse_request_full_payload():
    result = uds_payload.parse_request('{"id":"u-0001","raw":"22 01 01","timeout_ms":1000}')
    assert result == {"id": "u-0001", "raw": bytes([0x22, 0x01, 0x01]), "timeout_ms": 1000}


def test_parse_request_without_timeout_ms():
    result = uds_payload.parse_request('{"id":"u-0002","raw":"3E 00"}')
    assert result == {"id": "u-0002", "raw": bytes([0x3E, 0x00]), "timeout_ms": None}


def test_build_response_positive():
    result = uds_payload.build_response("u-0001", bytes([0x62, 0x01, 0x07, 0x07]))
    assert json.loads(result) == {"id": "u-0001", "type": "positive", "raw": "62 01 07 07"}


def test_build_response_negative_extracts_nrc():
    result = uds_payload.build_response("u-0001", bytes([0x7F, 0x22, 0x31]))
    assert json.loads(result) == {
        "id": "u-0001",
        "type": "negative",
        "raw": "7F 22 31",
        "nrc": "31",
    }


def test_build_response_negative_too_short_raises():
    with pytest.raises(ValueError):
        uds_payload.build_response("u-0001", bytes([0x7F, 0x22]))


def test_build_error_valid_reason():
    result = uds_payload.build_error("u-0003", "robot_unreachable", "로봇 무응답")
    assert json.loads(result) == {
        "id": "u-0003",
        "type": "error",
        "reason": "robot_unreachable",
        "message": "로봇 무응답",
    }


def test_build_error_invalid_reason_raises():
    with pytest.raises(ValueError):
        uds_payload.build_error("u-0003", "not_a_real_reason", "x")


def test_build_status_valid():
    result = uds_payload.build_status("online", "connected")
    assert json.loads(result) == {"state": "online", "robot": "connected"}


def test_build_status_invalid_robot_value_raises():
    with pytest.raises(ValueError):
        uds_payload.build_status("online", "not_a_real_state")


def test_build_error_keeps_korean_message_unescaped():
    # json.loads()로 비교하면 \uXXXX 이스케이프 여부를 놓친다(디코드하면 같아지므로).
    # MQTT로 나가는 실제 문자열(raw string)에 한글이 그대로 있는지 직접 확인해야 한다.
    result = uds_payload.build_error("u-0003", "robot_unreachable", "로봇 무응답")
    assert "로봇 무응답" in result
    assert "\\u" not in result
