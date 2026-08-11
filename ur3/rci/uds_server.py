"""SID별 핸들러로 UDS 요청을 라우팅하는 서버"""
from . import frames
from . import logger


class UdsServer:
    """handlers 매핑을 이용해 요청 hex를 응답 hex로 변환한다"""

    def __init__(self, handlers):
        self.handlers = handlers

    def handle_request(self, raw_hex):
        """hex 문자열 요청을 처리해 응답 hex 문자열을 반환한다"""
        try:
            payload = frames.parse_hex(raw_hex)
        except ValueError as exc:
            logger.log_error(f"[UdsServer] hex 파싱 실패: {exc}")
            return None
        if not payload:
            logger.log_error("[UdsServer] 빈 요청 무시")
            return None

        sid = payload[0]
        data = payload[1:]
        handler = self.handlers.get(sid)
        if handler is None:
            return frames.to_hex(frames.negative(sid, frames.NRC_SERVICE_NOT_SUPPORTED))

        try:
            response = handler.handle(sid, data)
        except frames.NRCError as exc:
            response = frames.negative(exc.sid, exc.nrc)
        except Exception as exc:
            logger.log_error(f"[UdsServer] SID {sid:02X} 처리 중 예외 발생: {exc}")
            response = frames.negative(sid, frames.NRC_GENERAL_REJECT)

        return frames.to_hex(response)
