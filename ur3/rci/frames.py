"""UDS 요청/응답 프레임 조립과 NRC 상수"""

NRC_GENERAL_REJECT = 0x10
NRC_SERVICE_NOT_SUPPORTED = 0x11
NRC_SUB_FUNCTION_NOT_SUPPORTED = 0x12
NRC_INCORRECT_LENGTH_OR_FORMAT = 0x13
NRC_RESPONSE_TOO_LONG = 0x14
NRC_BUSY_REPEAT_REQUEST = 0x21
NRC_CONDITIONS_NOT_CORRECT = 0x22
NRC_REQUEST_SEQUENCE_ERROR = 0x24
NRC_REQUEST_OUT_OF_RANGE = 0x31
NRC_SECURITY_ACCESS_DENIED = 0x33
NRC_INVALID_KEY = 0x35
NRC_EXCEEDED_NUMBER_OF_ATTEMPTS = 0x36
NRC_REQUIRED_TIME_DELAY_NOT_EXPIRED = 0x37
NRC_RESPONSE_PENDING = 0x78
NRC_SUB_FUNCTION_NOT_SUPPORTED_IN_SESSION = 0x7E
NRC_SERVICE_NOT_SUPPORTED_IN_SESSION = 0x7F


class NRCError(Exception):
    """부정 응답이 필요할 때 발생시키는 예외"""

    def __init__(self, sid, nrc):
        self.sid = sid
        self.nrc = nrc
        super().__init__(f"SID {sid:02X} NRC {nrc:02X}")


def parse_hex(raw_hex):
    """공백 구분 hex 문자열을 바이트로 변환한다"""
    return bytes.fromhex(raw_hex.replace(" ", ""))


def to_hex(data):
    """바이트를 공백 구분 대문자 hex 문자열로 변환한다"""
    return " ".join(f"{b:02X}" for b in data)


def positive(sid, data=b""):
    """긍정 응답 프레임을 조립한다 (SID+0x40)"""
    return bytes([sid + 0x40]) + data


def negative(sid, nrc):
    """부정 응답 프레임을 조립한다 (7F SID NRC)"""
    return bytes([0x7F, sid, nrc])
