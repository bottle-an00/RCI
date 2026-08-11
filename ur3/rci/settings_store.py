"""사양/식별 정보(0xF1xx)를 JSON 파일로 영속화하는 저장소"""
import json
import os

DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "settings.json")

DEFAULTS = {
    "sw_update_date": "260727",   # YYMMDD, DID 0xF199
    "serial_number": "UNKNOWN",   # DID 0xF18C
    "robot_ip": "192.168.1.101",  # DID 0xF1A0
}


class SettingsStore:
    def __init__(self, path=DEFAULT_PATH):
        self.path = path
        self._data = dict(DEFAULTS)
        self._load()

    def _load(self):
        """파일이 있으면 읽어서 기본값 위에 덮어쓴다"""
        if os.path.exists(self.path):
            with open(self.path, "r", encoding="utf-8") as f:
                self._data.update(json.load(f))

    def _save(self):
        """현재 값을 파일에 기록한다"""
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def get(self, key):
        return self._data[key]

    def set(self, key, value):
        """값을 갱신하고 즉시 파일에 저장한다"""
        self._data[key] = value
        self._save()
