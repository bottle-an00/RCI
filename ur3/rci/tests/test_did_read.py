"""DidRead(0x22) 단위 테스트"""
import pytest

from ur3.rci.did_read import DidRead
from ur3.rci.frames import NRCError, parse_hex, to_hex
from ur3.rci.settings_store import SettingsStore


@pytest.fixture
def settings_store(tmp_path):
    return SettingsStore(path=str(tmp_path / "settings.json"))


@pytest.fixture
def did_read(state, rtde_link, dashboard_link, camera_link, settings_store):
    return DidRead(state, rtde_link, dashboard_link, camera_link, settings_store)


def _handle(did_read, request_hex):
    """요청 hex 문자열을 SID, payload로 나눠 handle을 호출하고 응답 hex를 반환한다"""
    raw = parse_hex(request_hex)
    sid, payload = raw[0], raw[1:]
    return to_hex(did_read.handle(sid, payload))


def test_robot_mode(did_read, rtde_link):
    """0x0107 로봇 모드는 int8로 인코딩된다"""
    rtde_link.cache["robot_mode"] = 7
    assert _handle(did_read, "22 01 07") == "62 01 07 07"


def test_robot_mode_negative(did_read, rtde_link):
    """0x0107 로봇 모드는 음수도 struct int8로 인코딩된다"""
    rtde_link.cache["robot_mode"] = -1
    assert _handle(did_read, "22 01 07") == "62 01 07 FF"


def test_gripper_status_echo(did_read, state):
    """0x010F 그리퍼 상태는 마지막 명령값을 echo한다"""
    state.last_gripper_cmd = 50
    assert _handle(did_read, "22 01 0F") == "62 01 0F 32"


def test_sw_update_date(did_read, settings_store):
    """0xF199 SW 업데이트 날짜는 BCD 3바이트로 인코딩된다"""
    settings_store.set("sw_update_date", "260727")
    assert _handle(did_read, "22 F1 99") == "62 F1 99 26 07 27"


def test_joint_angles(did_read, rtde_link):
    """0x0101 조인트 각도는 rad를 deg로 변환 후 scale 10 int16로 인코딩된다"""
    import math

    rtde_link.cache["actual_q"] = [math.radians(10.0)] * 6
    assert _handle(did_read, "22 01 01") == "62 01 01 00 64 00 64 00 64 00 64 00 64 00 64"


def test_joint_velocities(did_read, rtde_link):
    """0x0102 조인트 속도는 rad/s를 deg/s로 변환 후 scale 10 int16로 인코딩된다"""
    import math

    rtde_link.cache["actual_qd"] = [math.radians(1.0)] * 6
    resp = _handle(did_read, "22 01 02")
    assert resp.startswith("62 01 02")


def test_joint_temperatures(did_read, rtde_link):
    """0x0103 조인트 온도는 scale 10 int16로 인코딩된다"""
    rtde_link.cache["joint_temperatures"] = [30.0] * 6
    assert _handle(did_read, "22 01 03") == "62 01 03 01 2C 01 2C 01 2C 01 2C 01 2C 01 2C"


def test_joint_currents(did_read, rtde_link):
    """0x0104 조인트 전류는 A를 mA scale 1000 int16로 인코딩된다"""
    rtde_link.cache["actual_current"] = [0.5] * 6
    assert _handle(did_read, "22 01 04") == "62 01 04 01 F4 01 F4 01 F4 01 F4 01 F4 01 F4"


def test_tcp_position(did_read, rtde_link):
    """0x0105 TCP 위치는 m을 0.1mm scale 10000 int16로 인코딩된다"""
    rtde_link.cache["actual_TCP_pose"] = [0.1, 0.2, 0.3, 0.0, 0.0, 0.0]
    assert _handle(did_read, "22 01 05") == "62 01 05 03 E8 07 D0 0B B8"


def test_tcp_orientation(did_read, rtde_link):
    """0x0106 TCP 자세는 rad를 scale 1000 int16로 인코딩된다"""
    rtde_link.cache["actual_TCP_pose"] = [0.0, 0.0, 0.0, 0.1, 0.2, 0.3]
    assert _handle(did_read, "22 01 06") == "62 01 06 00 64 00 C8 01 2C"


def test_safety_mode(did_read, rtde_link):
    """0x0108 안전 모드는 uint8로 인코딩된다"""
    rtde_link.cache["safety_mode"] = 1
    assert _handle(did_read, "22 01 08") == "62 01 08 01"


def test_runtime_state(did_read, rtde_link):
    """0x0109 실행 상태는 uint8로 인코딩된다"""
    rtde_link.cache["runtime_state"] = 2
    assert _handle(did_read, "22 01 09") == "62 01 09 02"


def test_robot_voltage(did_read, rtde_link):
    """0x010A 로봇 전압은 scale 1000 uint16로 인코딩된다"""
    rtde_link.cache["actual_robot_voltage"] = 48.0
    assert _handle(did_read, "22 01 0A") == "62 01 0A BB 80"


def test_robot_current(did_read, rtde_link):
    """0x010B 로봇 전류는 scale 1000 uint16로 인코딩된다"""
    rtde_link.cache["actual_robot_current"] = 1.5
    assert _handle(did_read, "22 01 0B") == "62 01 0B 05 DC"


def test_speed_scaling(did_read, rtde_link):
    """0x010C 속도 스케일링은 scale 1000 uint16로 인코딩된다"""
    rtde_link.cache["speed_scaling"] = 1.0
    assert _handle(did_read, "22 01 0C") == "62 01 0C 03 E8"


def test_safety_status_bits_default_zero(did_read, rtde_link):
    """0x010D 안전 상태 비트는 캐시에 없으면 0으로 인코딩된다"""
    assert _handle(did_read, "22 01 0D") == "62 01 0D 00 00"


def test_loaded_program_name(did_read, dashboard_link):
    """0x010E 로드된 프로그램명은 dashboard 명령 결과를 ascii로 인코딩한다"""
    dashboard_link.responses["get loaded program"] = "test.urp"
    resp = _handle(did_read, "22 01 0E")
    assert resp == "62 01 0E " + to_hex(b"test.urp")
    assert dashboard_link.sent.count("get loaded program") == 1


def test_loaded_program_name_cached(did_read, dashboard_link):
    """0x010E는 5초 TTL 이내 재조회 시 dashboard에 재전송하지 않는다"""
    dashboard_link.responses["get loaded program"] = "test.urp"
    _handle(did_read, "22 01 0E")
    _handle(did_read, "22 01 0E")
    assert dashboard_link.sent.count("get loaded program") == 1


def test_camera_status_connected(did_read, camera_link):
    """0x0110 카메라 상태는 연결시 1로 인코딩된다"""
    camera_link.connected = True
    assert _handle(did_read, "22 01 10") == "62 01 10 01"


def test_camera_status_disconnected(did_read, camera_link):
    """0x0110 카메라 상태는 미연결시 0으로 인코딩된다"""
    camera_link.connected = False
    assert _handle(did_read, "22 01 10") == "62 01 10 00"


def test_rtde_band_not_connected_raises_conditions_not_correct(did_read, rtde_link):
    """rtde 미연결 상태에서 0x01xx 대역 조회시 NRC 0x22를 발생시킨다"""
    rtde_link.connected = False
    with pytest.raises(NRCError) as exc:
        did_read.handle(0x22, parse_hex("01 07"))
    assert exc.value.nrc == 0x22


def test_gripper_status_readable_without_rtde(did_read, rtde_link, state):
    """0x010F 그리퍼 상태는 RTDE 미연결이어도 정상 조회된다"""
    rtde_link.connected = False
    state.last_gripper_cmd = 50
    assert _handle(did_read, "22 01 0F") == "62 01 0F 32"


def test_camera_status_readable_without_rtde(did_read, rtde_link, camera_link):
    """0x0110 카메라 상태는 RTDE 미연결이어도 정상 조회된다"""
    rtde_link.connected = False
    camera_link.connected = True
    assert _handle(did_read, "22 01 10") == "62 01 10 01"


def test_loaded_program_name_readable_without_rtde(did_read, rtde_link, dashboard_link):
    """0x010E 프로그램명은 RTDE 미연결이어도 Dashboard가 연결돼 있으면 조회된다"""
    rtde_link.connected = False
    dashboard_link.responses["get loaded program"] = "test.urp"
    resp = _handle(did_read, "22 01 0E")
    assert resp == "62 01 0E " + to_hex(b"test.urp")


def test_loaded_program_name_requires_dashboard_connection(did_read, dashboard_link):
    """0x010E는 Dashboard 미연결 상태에서 NRC 0x22를 발생시킨다"""
    dashboard_link.connected = False
    with pytest.raises(NRCError) as exc:
        did_read.handle(0x22, parse_hex("01 0E"))
    assert exc.value.nrc == 0x22


def test_sw_version_requires_dashboard_connection(did_read, dashboard_link):
    """0xF195는 Dashboard 미연결 상태에서 NRC 0x22를 발생시킨다"""
    dashboard_link.connected = False
    with pytest.raises(NRCError) as exc:
        did_read.handle(0x22, parse_hex("F1 95"))
    assert exc.value.nrc == 0x22


def test_sw_version(did_read, dashboard_link):
    """0xF195 SW버전은 dashboard 명령 결과를 ascii로 인코딩한다"""
    dashboard_link.responses["PolyscopeVersion"] = "5.11.0"
    resp = _handle(did_read, "22 F1 95")
    assert resp == "62 F1 95 " + to_hex(b"5.11.0")


def test_serial_number(did_read, settings_store):
    """0xF18C 시리얼번호는 설정 저장소 값을 ascii로 인코딩한다"""
    settings_store.set("serial_number", "SN12345")
    resp = _handle(did_read, "22 F1 8C")
    assert resp == "62 F1 8C " + to_hex(b"SN12345")


def test_robot_ip(did_read, settings_store):
    """0xF1A0 로봇 IP는 설정 저장소 값을 4바이트로 인코딩한다"""
    settings_store.set("robot_ip", "192.168.1.102")
    assert _handle(did_read, "22 F1 A0") == "62 F1 A0 C0 A8 01 66"


def test_undefined_did_raises_request_out_of_range(did_read):
    """미정의 DID 조회시 NRC 0x31을 발생시킨다"""
    with pytest.raises(NRCError) as exc:
        did_read.handle(0x22, parse_hex("00 01"))
    assert exc.value.nrc == 0x31


def test_incorrect_payload_length_raises_error(did_read):
    """DID 페이로드 길이가 2바이트가 아니면 NRC 0x13을 발생시킨다"""
    with pytest.raises(NRCError) as exc:
        did_read.handle(0x22, parse_hex("01"))
    assert exc.value.nrc == 0x13
