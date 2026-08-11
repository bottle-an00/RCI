"""RCI 진입점. config를 읽어 UR3Robot을 생성하고 실행한다. repo 루트에서 `python -m ur3.rci.main`으로 실행할 것"""
from .. import config
from .robot import UR3Robot


def main():
    """UR3Robot을 생성해 run()을 호출한다"""
    robot = UR3Robot(
        config.ROBOT_IP,
        dashboard_port=config.DASHBOARD_PORT,
        rtde_port=config.RTDE_PORT,
        broker_host=config.BROKER_HOST,
        broker_port=config.BROKER_PORT,
        broker_username=config.BROKER_USERNAME,
        broker_password=config.BROKER_PASSWORD,
        broker_tls=config.BROKER_TLS,
    )
    robot.run()


if __name__ == "__main__":
    main()
