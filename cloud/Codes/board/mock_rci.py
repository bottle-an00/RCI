"""목(mock) RCI 게이트웨이 — 사양서(minigit 계약) 이행.

RCI 실물 도착 전, 실물과 '같은 인터페이스'(= Documents/MQTT_Interface_Contract.md,
출처: UR3 클라우드 기능개발 요청서 §3/§5)를 이행하는 소프트웨어 스탠드인.
minigit/req/{device} 를 구독하다가 UDS 요청이 오면 응답 raw 를 만들어
minigit/resp/{device} 로 되돌린다.

책임 경계: 게이트웨이는 raw 바이트만 다룬다. 물리값 디코딩·NRC 이름 매핑은 웹앱(클라이언트)
몫이므로 여기서 하지 않는다.

주의(학습용 단순화): 세션/보안/제어권 상태를 실제로 게이팅하지 않고, 사양서의 예시 프레임을
그대로 돌려주는 수준이다. 상태 머신은 실 RCI 구현에서 채운다.

실행 전제: dev_broker.py 가 127.0.0.1:1883 에서 떠 있어야 한다.
실행:      python mock_rci.py
"""

import contextlib
import json
import sys
import time

import paho.mqtt.client as mqtt

with contextlib.suppress(Exception):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BROKER_HOST = "127.0.0.1"
BROKER_PORT = 1883
REQ_TOPIC = "minigit/req/+"          # urrobot·rccar 동시 구독
STATUS = {"urrobot": "minigit/status/rci-ur", "rccar": "minigit/status/rci-rc"}

# 대상·DID → 0x22 읽기 응답 데이터 바이트(hex). 값은 사양서 예시/인코딩표 기준.
#   빅엔디안, int16 음수는 2의 보수. (디코딩은 클라이언트가 수행)
DIDS = {
    "urrobot": {
        "0101": "FC 7C FC AB 03 F9 FB C6 FC 7E 00 03",  # 조인트각 6축 0.1도
        "0102": "00 00 00 00 00 00 00 00 00 00 00 00",  # 조인트속도 (정지)
        "0103": "01 F4 01 EC 02 08 01 F0 01 FA 02 12",  # 조인트온도 0.1도
        "0104": "00 64 00 5A 00 78 00 46 00 50 00 3C",  # 조인트전류 mA
        "0107": "07",              # 로봇 모드 = RUNNING
        "0108": "01",              # 안전 모드 = NORMAL
        "0109": "01",              # 프로그램 상태 = STOPPED
        "010A": "BB E4",           # 로봇 전압 48100mV = 48.1V
        "010B": "03 E8",           # 로봇 전류 1000mA
        "010F": "32",              # 그리퍼 50%
        "0110": "01",              # 카메라 연결됨
        "F199": "26 07 27",        # SW 날짜 2026-07-27
        "F195": "33 2E 31 35 2E 38",  # "3.15.8"
        "F1A0": "C0 A8 01 65",     # 로봇 IP 192.168.1.101
    },
    "rccar": {
        "0101": "00 EB",           # 초음파 거리 235mm
        "0102": "12 8E",           # 배터리 전압 4750mV
        "0103": "00 FA",           # 온도 250 = 25.0도
        "0104": "02 49",           # 습도 585 = 58.5%RH
        "0105": "01 56",           # 조도 342 lux
        "0106": "5A",              # 서보 각도 90도
        "0107": "05",              # LED bitfield (적+백)
        "0108": "00",              # 부저 OFF
        "F199": "26 07 23",        # SW 날짜 2026-07-23
        "F195": "56 31 2E 32",     # "V1.2"
        "F1A0": "07 E0",           # 제어기 CAN ID 0x07E0
    },
}

# 대상별 고정 Seed/Key (학습용 — 실제 보안 아님).
SECURITY = {
    "urrobot": {"seed": "11 22 33 44", "key": "55 66 77 88"},
    "rccar": {"seed": "12 34", "key": "56 78"},
}

# DTC 읽기(0x19 02) 캔드 응답 — confirmed(0x08).
DTC = {
    "urrobot": "59 02 B1 00 02 08",              # 보호정지
    "rccar": "59 02 90 00 01 08 C1 01 01 08",    # 버스단선 + 초음파 이상
}


def build_response(device: str, raw: str) -> str:
    """UDS 요청 raw(공백 hex) → 응답 raw hex. 서비스별로 분기한다."""
    parts = raw.split()
    if not parts:
        return "7F 10 13"  # 포맷 오류
    try:
        b = [int(x, 16) for x in parts]
    except ValueError:
        return "7F 10 13"
    up = [f"{x:02X}" for x in b]
    sid = b[0]
    dids = DIDS.get(device, {})

    if sid == 0x10:  # DiagnosticSessionControl
        sf = up[1] if len(up) > 1 else "01"
        return f"50 {sf} 00 32 01 F4"          # P2=50ms, P2*=5000ms
    if sid == 0x3E:  # TesterPresent
        return "7E 00"
    if sid == 0x11:  # ECUReset (가상 더미)
        return f"51 {up[1] if len(up) > 1 else '01'}"
    if sid == 0x27:  # SecurityAccess
        sub = up[1] if len(up) > 1 else "01"
        if sub == "01":
            return "67 01 " + SECURITY[device]["seed"]
        if sub == "02":
            key = " ".join(up[2:])
            return "67 02" if key == SECURITY[device]["key"] else "7F 27 35"
        return "7F 27 12"
    if sid == 0x22:  # ReadDataByIdentifier
        if len(up) < 3:
            return "7F 22 13"
        did = up[1] + up[2]
        data = dids.get(did)
        return f"62 {up[1]} {up[2]} {data}" if data else "7F 22 31"
    if sid == 0x2E:  # WriteDataByIdentifier
        if len(up) < 3:
            return "7F 2E 13"
        if up[1] + up[2] == "F195":
            return "7F 2E 31"                   # 쓰기 불가 항목
        return f"6E {up[1]} {up[2]}"
    if sid == 0x2F:  # InputOutputControlByIdentifier
        return "6F " + " ".join(up[1:])         # 요청 echo
    if sid == 0x31:  # RoutineControl
        return "71 " + " ".join(up[1:])         # 접수/결과 (단순화)
    if sid == 0x19:  # ReadDTCInformation
        return DTC.get(device, "59 02")
    if sid == 0x14:  # ClearDiagnosticInformation
        return "54"
    return f"7F {up[0]} 11"                      # serviceNotSupported


def to_response_msg(req_id, raw):
    """응답 raw → 계약 페이로드({id, type, raw, nrc?})."""
    parts = raw.split()
    negative = bool(parts) and parts[0] == "7F"
    msg = {"id": req_id, "type": "negative" if negative else "positive", "raw": raw}
    if negative and len(parts) >= 3:
        msg["nrc"] = parts[2]
    return msg


def on_connect(client, userdata, flags, reason_code, properties):
    client.subscribe(REQ_TOPIC, qos=1)
    for topic in STATUS.values():                # 생존 상태 (retained)
        client.publish(topic, json.dumps({"state": "online", "robot": "connected"}),
                       qos=1, retain=True)
    print(f"[mock-rci] connected → subscribed {REQ_TOPIC}", flush=True)


def on_message(client, userdata, msg):
    device = msg.topic.split("/")[2]             # minigit/req/{device}
    try:
        req = json.loads(msg.payload.decode())
    except (ValueError, UnicodeDecodeError):
        print(f"[mock-rci] {device}: 잘못된 페이로드 무시", flush=True)
        return

    raw = req.get("raw", "")
    resp_raw = build_response(device, raw)
    resp = to_response_msg(req.get("id"), resp_raw)
    client.publish(f"minigit/resp/{device}", json.dumps(resp), qos=1)
    print(f"[mock-rci] {device}  {raw}  →  {resp_raw}  ({resp['type']})", flush=True)


def main():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="mock-rci")
    client.on_connect = on_connect
    client.on_message = on_message
    # LWT: 비정상 종료 시 브로커가 offline 을 대신 발행 (요청서 §3.3).
    client.will_set(STATUS["urrobot"], json.dumps({"state": "offline"}), qos=1, retain=True)
    client.connect(BROKER_HOST, BROKER_PORT, 60)
    print("[mock-rci] running (Ctrl+C to stop)", flush=True)
    client.loop_forever()


if __name__ == "__main__":
    main()
