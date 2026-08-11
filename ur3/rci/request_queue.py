"""요청 큐. 정지, 취소 클래스 요청을 최우선으로 처리한다"""
import threading

STOP_CLASS_PREFIXES = (
    bytes([0x31, 0x02]),  # stopRoutine
    bytes([0x11]),        # ECUReset
)


class RequestQueue:
    def __init__(self):
        self._urgent = []
        self._normal = []
        self._cond = threading.Condition()

    def put(self, request):
        """raw 바이트 앞부분을 보고 긴급, 일반 큐에 나눠 담는다"""
        raw = request.get("raw_bytes", b"")
        with self._cond:
            if raw.startswith(STOP_CLASS_PREFIXES):
                self._urgent.append(request)
            else:
                self._normal.append(request)
            self._cond.notify()

    def get(self):
        """긴급 큐를 먼저 비우고 없으면 일반 큐에서 꺼낸다 (blocking)"""
        with self._cond:
            while not self._urgent and not self._normal:
                self._cond.wait()
            if self._urgent:
                return self._urgent.pop(0)
            return self._normal.pop(0)
