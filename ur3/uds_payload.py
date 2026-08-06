"""UR3 진단 MQTT 페이로드 인코딩/봉투 구성.

UR3_RCI_기능명세서.md §4.2~4.5 (확정) 기준. 물리값 디코딩·NRC 이름 매핑은
웹앱 담당이므로, 이 모듈은 raw 바이트만 다루고 절대 값을 해석하지 않는다.
"""
import json


def encode_hex(data: bytes) -> str:
    """바이트열을 사양서 §4.5 표기로 인코딩한다: 대문자, 공백 구분, 0x 없음."""
    return " ".join(f"{b:02X}" for b in data)


def decode_hex(text: str) -> bytes:
    """§4.5 표기(또는 대소문자 관용 입력)를 바이트열로 디코딩한다."""
    tokens = text.split()
    return bytes(int(tok, 16) for tok in tokens)


def classify_type(raw: bytes) -> str:
    """§4.5: raw 첫 바이트가 0x7F면 negative, 그 외 positive."""
    if raw and raw[0] == 0x7F:
        return "negative"
    return "positive"


def parse_request(payload: str) -> dict:
    """§4.2 요청 페이로드를 파싱한다: {"id", "raw"(hex str), "timeout_ms"?}."""
    obj = json.loads(payload)
    return {
        "id": obj["id"],
        "raw": decode_hex(obj["raw"]),
        "timeout_ms": obj.get("timeout_ms"),
    }


def build_response(request_id: str, raw: bytes) -> str:
    """§4.3 응답 페이로드를 조립한다. negative면 raw[2]를 NRC로 추출한다."""
    response_type = classify_type(raw)
    response = {"id": request_id, "type": response_type, "raw": encode_hex(raw)}
    if response_type == "negative":
        if len(raw) < 3:
            raise ValueError(
                f"negative response raw too short to contain NRC: {encode_hex(raw)!r}"
            )
        response["nrc"] = f"{raw[2]:02X}"
    return json.dumps(response, ensure_ascii=False)


VALID_ERROR_REASONS = {"robot_unreachable", "dashboard_error", "internal_error"}
VALID_ROBOT_STATES = {"connected", "disconnected"}


def build_error(request_id: str, reason: str, message: str) -> str:
    """§4.4 에러 페이로드를 조립한다."""
    if reason not in VALID_ERROR_REASONS:
        raise ValueError(f"invalid error reason: {reason!r} (allowed: {VALID_ERROR_REASONS})")
    return json.dumps(
        {"id": request_id, "type": "error", "reason": reason, "message": message},
        ensure_ascii=False,
    )


def build_status(state: str, robot: str) -> str:
    """§4.4 상태 페이로드를 조립한다."""
    if robot not in VALID_ROBOT_STATES:
        raise ValueError(f"invalid robot state: {robot!r} (allowed: {VALID_ROBOT_STATES})")
    return json.dumps({"state": state, "robot": robot}, ensure_ascii=False)
