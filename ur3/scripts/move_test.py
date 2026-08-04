"""
UR3에 아주 작은 안전 이동을 한 번 지시해보는 테스트.

!!! 경고: 이 스크립트는 실제로 로봇을 움직인다 !!!
- 로봇 주변에 사람/장애물이 없는지 반드시 확인할 것
- 비상정지 버튼에 손이 닿는 위치에서 실행할 것
- 처음 실행할 때는 로봇의 Safety Configuration에서 속도/힘 제한을
  충분히 낮게 설정해두는 것을 권장함

기본값은 TCP(Tool Center Point)를 Z축으로 2cm만 직선 이동시키는 매우 작은 동작이다.

실행: python scripts/move_test.py
"""
import os
import sys
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import ROBOT_IP

from rtde_control import RTDEControlInterface
from rtde_receive import RTDEReceiveInterface

SPEED_M_S = 0.02    # 매우 느린 속도
ACCEL_M_S2 = 0.2
AXIS_INDEX = 2      # 0=X, 1=Y, 2=Z (base 좌표계 기준 TCP 이동 축)
DELTA_M = 0.02      # 2cm


def confirm() -> bool:
    print("!!! 경고: 이 스크립트는 실제로 UR3를 움직입니다 !!!")
    print("- 로봇 주변에 사람/장애물이 없는지 확인하세요.")
    print("- 비상정지 버튼에 손이 닿는 위치에서 실행하세요.")
    answer = input("계속하려면 'yes'를 입력하세요: ")
    return answer.strip().lower() == "yes"


def main():
    if not confirm():
        print("[취소됨]")
        return

    rtde_c = RTDEControlInterface(ROBOT_IP)
    rtde_r = RTDEReceiveInterface(ROBOT_IP)

    if not rtde_c.isConnected():
        print("[실패] RTDEControlInterface 연결 실패.")
        return

    try:
        current_pose = rtde_r.getActualTCPPose()
        print("이동 전 TCP pose:", current_pose)

        target_pose = list(current_pose)
        target_pose[AXIS_INDEX] += DELTA_M

        print("목표 TCP pose   :", target_pose)
        rtde_c.moveL(target_pose, SPEED_M_S, ACCEL_M_S2)
        print("[완료] moveL 실행됨")

        time.sleep(1)
        print("이동 후 TCP pose:", rtde_r.getActualTCPPose())
    finally:
        rtde_c.stopScript()
        rtde_c.disconnect()
        rtde_r.disconnect()
        print("[종료] 연결 해제")


if __name__ == "__main__":
    main()
