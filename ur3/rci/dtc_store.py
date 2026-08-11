"""DTC(고장코드) 저장과 SID 0x19/0x14 처리를 담당하는 저장소"""
from . import logger
from .frames import (
    NRCError,
    NRC_INCORRECT_LENGTH_OR_FORMAT,
    NRC_SERVICE_NOT_SUPPORTED,
    NRC_SUB_FUNCTION_NOT_SUPPORTED,
    positive,
)

DTC_STATUS_CONFIRMED = 0x08

SID_READ_DTC_INFORMATION = 0x19
SID_CLEAR_DIAGNOSTIC_INFORMATION = 0x14

SF_REPORT_DTC_BY_STATUS_MASK = 0x02

CLEAR_ALL_GROUP = b"\xff\xff\xff"


class DtcStore:
    """state.dtc_map을 기반으로 DTC를 등록/삭제/조회한다"""

    def __init__(self, state):
        self.state = state

    def set(self, code):
        """등록되지 않은 DTC를 confirmedDTC 상태로 추가한다"""
        with self.state.lock:
            is_new = code not in self.state.dtc_map
            if is_new:
                self.state.dtc_map[code] = DTC_STATUS_CONFIRMED
        if is_new:
            logger.log_dtc("SET", code)

    def clear(self, codes=None):
        """codes가 None이면 전체 삭제, 아니면 해당 코드만 삭제한다"""
        with self.state.lock:
            if codes is None:
                removed = list(self.state.dtc_map.keys())
                self.state.dtc_map.clear()
            else:
                removed = [code for code in codes if code in self.state.dtc_map]
                for code in codes:
                    self.state.dtc_map.pop(code, None)
        for code in removed:
            logger.log_dtc("CLEAR", code)

    def handle(self, sid, payload):
        """SID 0x19, 0x14 요청을 분기 처리한다"""
        if sid == SID_READ_DTC_INFORMATION:
            return self._handle_read(payload)
        if sid == SID_CLEAR_DIAGNOSTIC_INFORMATION:
            return self._handle_clear(payload)
        raise NRCError(sid, NRC_SERVICE_NOT_SUPPORTED)

    def _handle_read(self, payload):
        """reportDTCByStatusMask 서브펑션으로 마스크에 걸리는 DTC를 응답한다"""
        if len(payload) < 1:
            raise NRCError(SID_READ_DTC_INFORMATION, NRC_INCORRECT_LENGTH_OR_FORMAT)
        sub_function = payload[0]
        if sub_function != SF_REPORT_DTC_BY_STATUS_MASK:
            raise NRCError(SID_READ_DTC_INFORMATION, NRC_SUB_FUNCTION_NOT_SUPPORTED)
        if len(payload) < 2:
            raise NRCError(SID_READ_DTC_INFORMATION, NRC_INCORRECT_LENGTH_OR_FORMAT)
        mask = payload[1]
        with self.state.lock:
            items = list(self.state.dtc_map.items())
        entries = b""
        for code, status in items:
            if status & mask:
                entries += code.to_bytes(3, "big") + bytes([status])
        return positive(SID_READ_DTC_INFORMATION, bytes([SF_REPORT_DTC_BY_STATUS_MASK]) + entries)

    def _handle_clear(self, payload):
        """3바이트 그룹코드에 해당하는 DTC를 삭제한다"""
        if len(payload) != 3:
            raise NRCError(SID_CLEAR_DIAGNOSTIC_INFORMATION, NRC_INCORRECT_LENGTH_OR_FORMAT)
        if payload == CLEAR_ALL_GROUP:
            self.clear(None)
        else:
            self.clear([int.from_bytes(payload, "big")])
        return positive(SID_CLEAR_DIAGNOSTIC_INFORMATION)
