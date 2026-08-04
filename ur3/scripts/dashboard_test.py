"""
UR3 Dashboard Server(TCP 29999)에 텍스트 명령을 보내 상태를 확인하는 테스트.
로봇을 움직이지 않는 조회성 명령만 사용한다.

실행: python scripts/dashboard_test.py

주의: ur_rtde 버전에 따라 DashboardClient의 메서드 이름/반환값 형식이 조금씩
다를 수 있다. 아래 호출이 실패하면 파이썬에서 `help(DashboardClient)`로
설치된 버전의 실제 메서드 목록을 확인할 것.
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import ROBOT_IP

from dashboard_client import DashboardClient


def main():
    print(f"[연결 시도] UR3 Dashboard -> {ROBOT_IP}:29999")
    client = DashboardClient(ROBOT_IP)
    client.connect()

    if not client.isConnected():
        print("[실패] Dashboard 연결 실패.")
        return

    print("[성공] Dashboard 연결됨")
    try:
        print("robotmode      :", client.robotmode())
        print("safetymode     :", client.safetymode())
        print("loaded program :", client.getLoadedProgram())
    except Exception as e:
        print(f"[오류] 명령 실행 중 예외 발생: {e}")
        print("설치된 ur_rtde 버전의 DashboardClient 메서드명을 확인하세요.")
    finally:
        client.disconnect()
        print("[종료] Dashboard 연결 해제")


if __name__ == "__main__":
    main()
