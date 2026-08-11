"""logger 모듈의 로그 포맷 검증"""
import logging

from ur3.rci import logger


def test_log_request_without_nrc(caplog):
    with caplog.at_level(logging.INFO, logger="rci"):
        logger.log_request("u-0001", "22 01 07", 3.5, "positive")
    assert "id=u-0001" in caplog.text
    assert "raw=22 01 07" in caplog.text
    assert "result=positive" in caplog.text
    assert "nrc=" not in caplog.text


def test_log_request_with_nrc(caplog):
    with caplog.at_level(logging.INFO, logger="rci"):
        logger.log_request("u-0002", "31 01 03 01", 1.2, "negative", nrc="31")
    assert "result=negative" in caplog.text
    assert "nrc=31" in caplog.text


def test_log_robot_event(caplog):
    with caplog.at_level(logging.INFO, logger="rci"):
        logger.log_robot_event("BUSY_OWNER", "NONE->MOTION_ROUTINE")
    assert "EVENT BUSY_OWNER NONE->MOTION_ROUTINE" in caplog.text


def test_log_dashboard(caplog):
    with caplog.at_level(logging.INFO, logger="rci"):
        logger.log_dashboard("play", "Starting program")
    assert "cmd=play" in caplog.text
    assert "resp=Starting program" in caplog.text


def test_log_dtc(caplog):
    with caplog.at_level(logging.INFO, logger="rci"):
        logger.log_dtc("SET", 0xB10002)
    assert "DTC SET code=0xB10002" in caplog.text


def test_log_error(caplog):
    with caplog.at_level(logging.ERROR, logger="rci"):
        logger.log_error("문제 발생")
    assert "문제 발생" in caplog.text
