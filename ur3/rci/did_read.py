"""0x22 ReadDataByIdentifier 서비스 모듈"""
import struct
import time

from . import codec
from .frames import (
    NRCError,
    NRC_CONDITIONS_NOT_CORRECT,
    NRC_INCORRECT_LENGTH_OR_FORMAT,
    NRC_REQUEST_OUT_OF_RANGE,
    positive,
)

CACHE_TTL_SEC = 5.0
RAD_TO_DEG = 180.0 / 3.141592653589793


class DidRead:
    """DID 조회 요청(0x22)을 처리한다"""

    def __init__(self, state, rtde_link, dashboard_link, camera_link, settings_store):
        self.state = state
        self.rtde_link = rtde_link
        self.dashboard_link = dashboard_link
        self.camera_link = camera_link
        self.settings_store = settings_store
        self._program_name = None
        self._program_name_ts = 0.0
        self._sw_version = None
        self._sw_version_ts = 0.0

    def handle(self, sid, payload):
        """DID를 파싱해 데이터를 조회하고 긍정 응답 바이트를 반환한다"""
        if len(payload) != 2:
            raise NRCError(sid, NRC_INCORRECT_LENGTH_OR_FORMAT)
        did = struct.unpack(">H", payload)[0]
        data = self._read(sid, did)
        return positive(sid, struct.pack(">H", did) + data)

    def _read(self, sid, did):
        """DID 값에 맞는 인코딩된 데이터 바이트를 반환한다"""
        if 0x0101 <= did <= 0x010D:
            return self._read_rtde_band(sid, did)
        if did == 0x010E:
            return codec.pack_ascii(self._loaded_program_name(sid))
        if did == 0x010F:
            return codec.pack_uint8(self.state.last_gripper_cmd)
        if did == 0x0110:
            return codec.pack_uint8(1 if self.camera_link.is_connected() else 0)
        if did == 0xF199:
            return self._read_sw_update_date()
        if did == 0xF195:
            return self._read_sw_version(sid)
        if did == 0xF18C:
            return codec.pack_ascii(self.settings_store.get("serial_number"))
        if did == 0xF1A0:
            return self._read_robot_ip()
        raise NRCError(sid, NRC_REQUEST_OUT_OF_RANGE)

    def _read_rtde_band(self, sid, did):
        """RTDE 텔레메트리에 의존하는 0x01xx 대역(0x0101~0x010D)을 캐시에서 읽어 인코딩한다"""
        if not self.rtde_link.is_connected():
            raise NRCError(sid, NRC_CONDITIONS_NOT_CORRECT)
        cache = self.rtde_link.get_cache()
        if did == 0x0101:
            return codec.pack_int16_list([v * RAD_TO_DEG for v in cache["actual_q"]], 10)
        if did == 0x0102:
            return codec.pack_int16_list([v * RAD_TO_DEG for v in cache["actual_qd"]], 10)
        if did == 0x0103:
            return codec.pack_int16_list(cache["joint_temperatures"], 10)
        if did == 0x0104:
            return codec.pack_int16_list(cache["actual_current"], 1000)
        if did == 0x0105:
            return codec.pack_int16_list(cache["actual_TCP_pose"][0:3], 10000)
        if did == 0x0106:
            return codec.pack_int16_list(cache["actual_TCP_pose"][3:6], 1000)
        if did == 0x0107:
            return struct.pack(">b", cache["robot_mode"])
        if did == 0x0108:
            return codec.pack_uint8(cache["safety_mode"])
        if did == 0x0109:
            return codec.pack_uint8(cache["runtime_state"])
        if did == 0x010A:
            return codec.pack_uint16(cache["actual_robot_voltage"], 1000)
        if did == 0x010B:
            return codec.pack_uint16(cache["actual_robot_current"], 1000)
        if did == 0x010C:
            return codec.pack_uint16(cache["speed_scaling"], 1000)
        # 0x010D: TODO 안전 상태 비트 캐시 키 이름은 실기 미확인 가안값
        value = cache.get("safety_status_bits") or 0
        return struct.pack(">H", value)

    def _loaded_program_name(self, sid):
        """로드된 프로그램명을 5초 TTL로 캐시해 Dashboard에서 조회한다"""
        now = time.time()
        if self._program_name is None or now - self._program_name_ts > CACHE_TTL_SEC:
            if not self.dashboard_link.is_connected():
                raise NRCError(sid, NRC_CONDITIONS_NOT_CORRECT)
            self._program_name = self.dashboard_link.send("get loaded program")
            self._program_name_ts = now
        return self._program_name

    def _read_sw_version(self, sid):
        """SW버전을 5초 TTL로 캐시해 Dashboard에서 조회한다"""
        now = time.time()
        if self._sw_version is None or now - self._sw_version_ts > CACHE_TTL_SEC:
            if not self.dashboard_link.is_connected():
                raise NRCError(sid, NRC_CONDITIONS_NOT_CORRECT)
            self._sw_version = self.dashboard_link.send("PolyscopeVersion")
            self._sw_version_ts = now
        return codec.pack_ascii(self._sw_version)

    def _read_sw_update_date(self):
        """SW 업데이트 날짜 문자열을 BCD 3바이트로 인코딩한다"""
        text = self.settings_store.get("sw_update_date")
        yy, mm, dd = int(text[0:2]), int(text[2:4]), int(text[4:6])
        return codec.pack_bcd_date(yy, mm, dd)

    def _read_robot_ip(self):
        """로봇 IP 문자열을 4바이트로 인코딩한다"""
        parts = self.settings_store.get("robot_ip").split(".")
        return bytes(int(p) for p in parts)
