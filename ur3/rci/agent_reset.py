"""ECUReset(0x11) 처리, RCI 진단 에이전트 자체의 소프트 리셋"""
from . import frames

SID_ECU_RESET = 0x11

SF_HARD_RESET = 0x01


class AgentReset:
    """에이전트 리셋 요청을 처리한다"""

    def __init__(self, state):
        self.state = state

    def handle(self, sid, payload):
        """SID 0x11 요청을 처리해 긍정 응답 바이트를 반환한다"""
        if sid != SID_ECU_RESET:
            raise frames.NRCError(sid, frames.NRC_SERVICE_NOT_SUPPORTED)
        sf = payload[0]
        if sf != SF_HARD_RESET:
            raise frames.NRCError(SID_ECU_RESET, frames.NRC_SUB_FUNCTION_NOT_SUPPORTED)
        self.state.reset_to_default()
        return frames.positive(SID_ECU_RESET, bytes([SF_HARD_RESET]))
