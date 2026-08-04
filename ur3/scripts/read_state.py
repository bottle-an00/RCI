"""
UR3 로봇 상태를 RTDE로 읽어오는 최소 연결 테스트.
로봇을 전혀 움직이지 않으므로, 가장 먼저 실행해서 라즈베리파이 <-> UR3 간
네트워크 통신이 되는지 확인하는 용도다.

실행: python scripts/read_state.py
"""
import os
import sys
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import ROBOT_IP

from rtde_receive import RTDEReceiveInterface


def main():
    print(f"[연결 시도] UR3 RTDE(읽기 전용) -> {ROBOT_IP}:30004")
    rtde_r = RTDEReceiveInterface(ROBOT_IP)

    if not rtde_r.isConnected():
        print("[실패] RTDE 연결 실패. IP/네트워크/방화벽을 확인하세요.")
        return

    print("[성공] RTDE 연결됨. 상태를 5초간 출력합니다 (Ctrl+C로 중단)")
    try:
        for _ in range(10):
            joint_deg = [round(v * 180.0 / 3.14159265, 1) for v in rtde_r.getActualQ()]
            tcp_pose = rtde_r.getActualTCPPose()
            robot_mode = rtde_r.getRobotMode()
            safety_mode = rtde_r.getSafetyMode()

            print(f"joint(deg)   : {joint_deg}")
            print(f"tcp(x,y,z,m) : {[round(v, 4) for v in tcp_pose[:3]]}")
            print(f"robot_mode   : {robot_mode}   safety_mode: {safety_mode}")
            print("-" * 50)
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        rtde_r.disconnect()
        print("[종료] RTDE 연결 해제")


if __name__ == "__main__":
    main()
