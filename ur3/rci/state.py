"""RCI 상태 저장소. 세션/보안/제어권/그리퍼 마지막 값/DTC를 보관한다"""
import threading

SESSION_DEFAULT = "default"
SESSION_EXTENDED = "extended"

BUSY_NONE = "NONE"
BUSY_URP_PROGRAM = "URP_PROGRAM"
BUSY_MOTION_ROUTINE = "MOTION_ROUTINE"


class RciState:
    def __init__(self):
        self.lock = threading.RLock()
        self.session = SESSION_DEFAULT
        self.security_unlocked = False
        self.robot_busy_owner = BUSY_NONE
        self.last_gripper_cmd = 0
        self.dtc_map = {}
        self.reset_hooks = []

    def add_reset_hook(self, hook):
        """S3 타임아웃, 에이전트 리셋 시 호출할 콜백 등록"""
        self.reset_hooks.append(hook)

    def reset_to_default(self):
        """세션, 보안, 제어권을 초기화하고 등록된 훅을 실행한다"""
        with self.lock:
            self.session = SESSION_DEFAULT
            self.security_unlocked = False
            self.robot_busy_owner = BUSY_NONE
            hooks = list(self.reset_hooks)
        for hook in hooks:
            hook()
