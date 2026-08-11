"""요청/응답, 로봇 이벤트, DTC 변경 이력을 기록하는 로거"""
import logging
import os

LOG_PATH = os.path.join(os.path.dirname(__file__), "rci.log")

logger = logging.getLogger("rci")
logger.setLevel(logging.INFO)


def setup_logging(log_path=LOG_PATH):
    """파일과 콘솔에 로그를 남기도록 핸들러를 붙인다 (앱 시작 시 한 번만 호출)"""
    if logger.handlers:
        return
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)


def log_request(request_id, raw, elapsed_ms, result_type, nrc=None):
    """요청/응답 처리 결과(id, raw, 처리시간, 결과)를 기록한다"""
    if nrc is not None:
        logger.info(
            "REQ id=%s raw=%s elapsed_ms=%.1f result=%s nrc=%s",
            request_id, raw, elapsed_ms, result_type, nrc,
        )
    else:
        logger.info(
            "REQ id=%s raw=%s elapsed_ms=%.1f result=%s",
            request_id, raw, elapsed_ms, result_type,
        )


def log_robot_event(event, detail=""):
    """RTDE 접속/두절, safety_mode 변화, robot_busy_owner 전이 등 로봇 이벤트를 기록한다"""
    logger.info("EVENT %s %s", event, detail)


def log_dashboard(command, response):
    """Dashboard 명령과 응답 원문을 기록한다"""
    logger.info("DASHBOARD cmd=%s resp=%s", command, response)


def log_dtc(action, code):
    """DTC 설정/소거 이력을 기록한다"""
    logger.info("DTC %s code=0x%06X", action, code)


def log_error(message):
    """예외/에러 상황을 기록한다"""
    logger.error(message)
