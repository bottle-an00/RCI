"""UDS 페이로드 바이트 인코딩, 디코딩 유틸리티"""
import struct


def pack_int16_list(values, scale):
    """실수 리스트를 정수 스케일 후 int16 빅엔디안 바이트로 변환한다"""
    out = b""
    for v in values:
        out += struct.pack(">h", round(v * scale))
    return out


def unpack_int16_list(data, scale):
    """int16 빅엔디안 바이트를 실수 리스트로 변환한다"""
    count = len(data) // 2
    values = struct.unpack(f">{count}h", data)
    return [v / scale for v in values]


def pack_uint16(value, scale=1):
    """정수를 스케일 적용 후 uint16 빅엔디안 바이트로 변환한다"""
    return struct.pack(">H", round(value * scale))


def unpack_uint16(data, scale=1):
    """uint16 빅엔디안 바이트를 스케일 적용된 실수로 변환한다"""
    return struct.unpack(">H", data)[0] / scale


def pack_uint8(value):
    """정수를 1바이트로 변환한다"""
    return struct.pack(">B", int(value))


def unpack_uint8(data):
    """1바이트를 정수로 변환한다"""
    return struct.unpack(">B", data)[0]


def pack_ascii(text):
    """문자열을 ASCII 바이트로 변환한다"""
    return text.encode("ascii")


def unpack_ascii(data):
    """ASCII 바이트를 문자열로 변환한다"""
    return data.decode("ascii")


def pack_bcd_date(yy, mm, dd):
    """YYMMDD 값을 BCD 3바이트로 인코딩한다"""
    return bytes([
        (yy // 10) << 4 | (yy % 10),
        (mm // 10) << 4 | (mm % 10),
        (dd // 10) << 4 | (dd % 10),
    ])


def unpack_bcd_date(data):
    """BCD 3바이트를 (yy, mm, dd) 튜플로 디코딩한다"""
    def bcd(b):
        return (b >> 4) * 10 + (b & 0x0F)
    return bcd(data[0]), bcd(data[1]), bcd(data[2])
