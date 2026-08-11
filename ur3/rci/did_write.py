"""0x2E WriteDataByIdentifier 서비스 모듈"""
import struct

from . import codec
from .frames import (
    NRCError,
    NRC_INCORRECT_LENGTH_OR_FORMAT,
    NRC_REQUEST_OUT_OF_RANGE,
    NRC_SECURITY_ACCESS_DENIED,
    NRC_SERVICE_NOT_SUPPORTED_IN_SESSION,
    positive,
)
from .state import SESSION_EXTENDED


class DidWrite:
    """DID 쓰기 요청(0x2E)을 처리한다"""

    def __init__(self, state, settings_store, on_ip_changed=None):
        self.state = state
        self.settings_store = settings_store
        self.on_ip_changed = on_ip_changed

    def handle(self, sid, payload):
        """세션, 보안 상태를 확인하고 DID 데이터를 저장소에 반영한다"""
        if self.state.session != SESSION_EXTENDED:
            raise NRCError(sid, NRC_SERVICE_NOT_SUPPORTED_IN_SESSION)
        if not self.state.security_unlocked:
            raise NRCError(sid, NRC_SECURITY_ACCESS_DENIED)
        if len(payload) < 2:
            raise NRCError(sid, NRC_INCORRECT_LENGTH_OR_FORMAT)
        did = struct.unpack(">H", payload[0:2])[0]
        data = payload[2:]
        self._write(sid, did, data)
        return positive(sid, struct.pack(">H", did))

    def _write(self, sid, did, data):
        """DID 값에 맞게 데이터를 디코딩해 설정 저장소에 반영한다"""
        if did == 0xF199:
            yy, mm, dd = codec.unpack_bcd_date(data)
            self.settings_store.set("sw_update_date", f"{yy:02d}{mm:02d}{dd:02d}")
            return
        if did == 0xF18C:
            self.settings_store.set("serial_number", codec.unpack_ascii(data))
            return
        if did == 0xF1A0:
            ip = ".".join(str(b) for b in data)
            self.settings_store.set("robot_ip", ip)
            if self.on_ip_changed is not None:
                self.on_ip_changed(ip)
            return
        raise NRCError(sid, NRC_REQUEST_OUT_OF_RANGE)
