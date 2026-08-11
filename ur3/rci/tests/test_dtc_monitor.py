"""DtcMonitor._check_once의 조건별 DTC 등록 검증"""
from ur3.rci.dtc_store import DtcStore
from ur3.rci.dtc_monitor import DtcMonitor


def make_monitor(state, rtde_link, camera_link, dashboard_link=None):
    dtc_store = DtcStore(state)
    return DtcMonitor(rtde_link, camera_link, dtc_store, dashboard_link=dashboard_link)


def test_rtde_disconnected_sets_dtc(state, rtde_link, camera_link):
    rtde_link.connected = False
    monitor = make_monitor(state, rtde_link, camera_link)
    monitor._check_once()
    assert 0x900002 in state.dtc_map


def test_safety_mode_protective_stop(state, rtde_link, camera_link):
    rtde_link.cache["safety_mode"] = 6
    monitor = make_monitor(state, rtde_link, camera_link)
    monitor._check_once()
    assert 0xB10001 in state.dtc_map


def test_safety_mode_reduced(state, rtde_link, camera_link):
    rtde_link.cache["safety_mode"] = 3
    monitor = make_monitor(state, rtde_link, camera_link)
    monitor._check_once()
    assert 0xB10002 in state.dtc_map


def test_safety_mode_safeguard_stop(state, rtde_link, camera_link):
    rtde_link.cache["safety_mode"] = 5
    monitor = make_monitor(state, rtde_link, camera_link)
    monitor._check_once()
    assert 0xB10003 in state.dtc_map


def test_safety_mode_recovery(state, rtde_link, camera_link):
    rtde_link.cache["safety_mode"] = 8
    monitor = make_monitor(state, rtde_link, camera_link)
    monitor._check_once()
    assert 0xB10004 in state.dtc_map


def test_joint_over_temperature(state, rtde_link, camera_link):
    rtde_link.cache["joint_temperatures"] = [30.0, 51.0, 20.0]
    monitor = make_monitor(state, rtde_link, camera_link)
    monitor._check_once()
    assert 0xC20101 in state.dtc_map


def test_under_voltage(state, rtde_link, camera_link):
    rtde_link.cache["actual_robot_voltage"] = 40.0
    monitor = make_monitor(state, rtde_link, camera_link)
    monitor._check_once()
    assert 0xC20201 in state.dtc_map


def test_camera_disconnected(state, rtde_link, camera_link):
    camera_link.connected = False
    monitor = make_monitor(state, rtde_link, camera_link)
    monitor._check_once()
    assert 0xC20301 in state.dtc_map


def test_dashboard_disconnected_sets_dtc(state, rtde_link, camera_link, dashboard_link):
    dashboard_link.connected = False
    monitor = make_monitor(state, rtde_link, camera_link, dashboard_link)
    monitor._check_once()
    assert 0x900002 in state.dtc_map


def test_none_cache_values_are_skipped(state, rtde_link, camera_link):
    monitor = make_monitor(state, rtde_link, camera_link)
    monitor._check_once()
    assert state.dtc_map == {}


def test_normal_conditions_do_not_set_dtc(state, rtde_link, camera_link):
    rtde_link.cache["safety_mode"] = 1
    rtde_link.cache["joint_temperatures"] = [30.0, 30.0]
    rtde_link.cache["actual_robot_voltage"] = 48.0
    monitor = make_monitor(state, rtde_link, camera_link)
    monitor._check_once()
    assert state.dtc_map == {}
