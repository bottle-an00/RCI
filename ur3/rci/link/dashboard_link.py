"""UR3 Dashboard Server 텍스트 라인 프로토콜 링크"""
import socket
import threading

from .. import logger


class DashboardLink:
    """Dashboard Server(포트 29999)에 라인 단위 명령을 보내는 클래스"""

    def __init__(self, ip, port=29999, timeout=5.0):
        self.ip = ip
        self.port = port
        self.timeout = timeout
        self.sock = None
        self.lock = threading.Lock()

    def connect(self):
        """소켓 연결 후 배너 라인을 읽는다"""
        try:
            sock = socket.create_connection((self.ip, self.port), timeout=self.timeout)
            sock.settimeout(self.timeout)
            self._recv_line(sock)
            self.sock = sock
            return True
        except Exception:
            self.sock = None
            return False

    def disconnect(self):
        """소켓 연결을 닫는다"""
        if self.sock is not None:
            try:
                self.sock.close()
            except Exception:
                pass
        self.sock = None

    def is_connected(self):
        """연결 여부를 반환한다"""
        return self.sock is not None

    def reconnect(self, ip=None):
        """연결을 끊고 (IP가 주어지면 바꾼 뒤) 다시 연결한다"""
        self.disconnect()
        if ip is not None:
            self.ip = ip
        return self.connect()

    def send(self, command):
        """명령을 보내고 응답 한 줄을 반환한다"""
        with self.lock:
            self.sock.sendall((command + "\n").encode("utf-8"))
            response = self._recv_line(self.sock)
        logger.log_dashboard(command, response)
        return response

    def _recv_line(self, sock):
        """소켓에서 개행까지 한 줄을 읽어 반환한다"""
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = sock.recv(1)
            if not chunk:
                break
            buf += chunk
        return buf.decode("utf-8").rstrip("\r\n")
