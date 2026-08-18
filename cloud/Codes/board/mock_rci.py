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
REQ_PREFIX = "minigit/req/"
REQ_TOPIC = REQ_PREFIX + "+"         # urrobot·rccar 동시 구독
STATUS = {"urrobot": "minigit/status/rci-ur", "rccar": "minigit/status/rci-rc"}

# 목 억제 채널 (계약 밖 · 개발 편의용).
#
# 실물 RCI 가 브로커에 붙으면 같은 minigit/req/{device} 를 둘이 구독해 **응답이 두 개**
# 나온다. 웹은 먼저 온 것을 채택하므로, 실물을 시험하는데 목의 답을 보고 있을 수 있다.
# 그래서 웹의 'RCI(MQTT)' 모드가 이 토픽으로 "이 device 는 실물이 맡는다"를 선언하고,
# 목은 그 device 만 응답을 접는다.
#
# device 마다 토픽을 따로 두는 이유: 한 토픽에 목록(["urrobot"])을 담으면 UR 탭과
# RC 탭이 각자 전체 목록을 다시 쓰면서 서로의 설정을 지운다(read-modify-write 경합).
# 토픽을 쪼개면 각 페이지가 자기 device 만 건드리므로 경합 자체가 없다.
#
# retained 라 목이 나중에 떠도 마지막 선언을 그대로 물려받는다.
CTRL_PREFIX = "minigit/control/mock/"
CTRL_TOPIC = CTRL_PREFIX + "+"

# 응답을 접은 device 들. paho 네트워크 스레드에서만 건드리므로 락은 필요 없다
# (on_message 는 단일 스레드에서 순차 실행된다).
_suppressed: set[str] = set()

# 목이 **자기 손으로** status 를 쓴 device 들. 회수(retained 삭제)는 여기 있는 것만
# 한다 — retained 삭제는 누가 썼든 지워버리므로, 이 기록이 없으면 실물 RCI 가 올린
# online 까지 목이 날린다.
_announced: set[str] = set()

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
        "0111": "00 2A",           # 진동 RMS 42 = 0.42 m/s²
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

# DTC 읽기(0x19 02) 캔드 응답.
# 구조: 59 <서브펑션> <statusAvailabilityMask> [DTC 3바이트 + 상태 1바이트] × n
# 마스크 0x08 = confirmedDTC. 실차 로그(BDC-BCM.txt)의 `03 59 02 08` 이 '마스크만 =
# 고장 없음' 형태이므로, 마스크 바이트를 반드시 포함해야 소거 전/후를 같은 규칙으로 읽는다.
DTC_MASK = "08"
DTC = {
    "urrobot": "B1 00 02 08",                    # 보호정지
    "rccar": "90 00 01 08 C1 01 01 08",          # 버스단선 + 초음파 이상
}
# 0x14 로 소거된 device. 0x19 재조회 시 레코드 없이 마스크만 돌려준다 —
# '소거 검증' 실습이 성립하려면 이 한 조각의 상태는 목도 들고 있어야 한다.
# 세션 오픈(0x10)마다 초기화해서 실습을 반복할 수 있게 한다.
_cleared: set[str] = set()


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
        _cleared.discard(device)               # 새 세션 = 실습 초기화 (DTC 되살림)
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
        sf = up[1] if len(up) > 1 else "02"
        records = "" if device in _cleared else DTC.get(device, "")
        return f"59 {sf} {DTC_MASK}" + (f" {records}" if records else "")
    if sid == 0x14:  # ClearDiagnosticInformation
        _cleared.add(device)
        return "54"
    # --- 리프로그래밍 3종 (0x34/0x36/0x37) --------------------------------
    # ECU 업그레이드 자동 시퀀스(main.py _seq_ecu)가 실제로 왕복하려면 목도 답해야 한다.
    # 블록을 저장하지는 않는다 — 카운터 흐름만 사실대로 되돌려준다.
    if sid == 0x34:  # RequestDownload
        # 0x20 = 길이 필드가 2바이트라는 뜻 · 0x0FFF = 한 블록 최대 길이.
        return "74 20 0F FF"
    if sid == 0x36:  # TransferData
        return f"76 {up[1]}" if len(up) > 1 else "7F 36 13"
    if sid == 0x37:  # RequestTransferExit
        return "77"
    return f"7F {up[0]} 11"                      # serviceNotSupported


def to_response_msg(req_id, raw):
    """응답 raw → 계약 페이로드({id, type, raw, nrc?})."""
    parts = raw.split()
    negative = bool(parts) and parts[0] == "7F"
    msg = {"id": req_id, "type": "negative" if negative else "positive", "raw": raw}
    if negative and len(parts) >= 3:
        msg["nrc"] = parts[2]
    return msg


def publish_status(client, device, state="online"):
    """생존 상태(retained). 목이 실제로 맡는 device 에 대해서만 발행한다."""
    robot = "connected" if state == "online" else "disconnected"
    client.publish(STATUS[device], json.dumps({"state": state, "robot": robot}),
                   qos=1, retain=True)
    _announced.add(device)


def announce(client):
    """맡고 있는 device 들의 online 을 선언한다. 억제된 것은 건너뛴다.

    억제된 device 까지 online 을 쓰면 **실물 RCI 가 방금 쓴 retained status 를
    목이 덮어쓴다.** 그러면 웹의 /api/health 는 실물이 붙었는데도 목의 상태를
    보게 된다.
    """
    served = [d for d in STATUS if d not in _suppressed]
    for device in served:
        publish_status(client, device)
    print(f"[mock-rci] 담당 device: {', '.join(served) or '없음'}"
          + (f"  (억제: {', '.join(sorted(_suppressed))})" if _suppressed else ""),
          flush=True)


def apply_control(client, device, payload):
    """목 억제 제어 메시지 한 건을 반영한다.

    payload 는 웹이 보낸 `{"suppress": true|false}`. 이 device 를 _suppressed 에
    넣거나 빼고, 그에 맞춰 status(retained)를 정리한다.
    """
    want = bool(payload.get("suppress"))
    if want == (device in _suppressed):
        # 웹은 재접속할 때마다 같은 선언을 다시 발행한다(다른 탭이 뒤집어 놨을 수
        # 있어서). 상태가 그대로면 조용히 넘긴다 — 안 그러면 로그가 도배된다.
        return

    if want:
        _suppressed.add(device)
        # status 를 offline 으로 쓰지 **않는다.** 실물 RCI 가 방금 올린 online 을
        # "목이 죽었다"로 덮어쓰는 꼴이 된다. 대신 빈 페이로드 + retain 으로
        # 자기 주장을 회수한다(MQTT 의 retained 삭제 관용구).
        #
        # 단 자기가 쓴 적 있을 때만. retained 삭제는 누가 썼는지 안 가리므로,
        # 목이 한 번도 안 쓴 토픽을 지우면 실물 RCI 의 online 을 대신 날린다.
        if device in _announced:
            client.publish(STATUS[device], b"", qos=1, retain=True)
            _announced.discard(device)
            note = "응답·status 모두 회수"
        else:
            note = "응답 회수 · status 는 목이 쓴 적 없어 그대로 둠"
        print(f"[mock-rci] {device}: 억제 ON — 실물 RCI 담당 · {note}", flush=True)
    else:
        _suppressed.discard(device)
        publish_status(client, device)
        print(f"[mock-rci] {device}: 억제 OFF — 목이 다시 응답합니다", flush=True)


def on_connect(client, userdata, flags, reason_code, properties):
    # 제어 토픽을 요청 토픽과 함께 구독한다. retained 제어 상태는 SUBACK 직후
    # 도착하므로, status 선언은 main() 이 그 도착을 기다렸다가 한다.
    client.subscribe(REQ_TOPIC, qos=1)
    client.subscribe(CTRL_TOPIC, qos=1)
    print(f"[mock-rci] connected → subscribed {REQ_TOPIC}, {CTRL_TOPIC}", flush=True)


def on_message(client, userdata, msg):
    # 접두어로 먼저 가른다. 예전처럼 split("/")[2] 로 device 를 뽑으면 제어 토픽
    # (minigit/control/mock/urrobot)에서 'mock' 이 device 로 잡힌다.
    if msg.topic.startswith(CTRL_PREFIX):
        device = msg.topic[len(CTRL_PREFIX):]
        if device not in STATUS:
            return
        try:
            payload = json.loads(msg.payload.decode())
        except (ValueError, UnicodeDecodeError):
            print(f"[mock-rci] 제어 페이로드 무시: {msg.payload[:60]!r}", flush=True)
            return
        apply_control(client, device, payload)
        return

    if not msg.topic.startswith(REQ_PREFIX):
        return
    device = msg.topic[len(REQ_PREFIX):]

    # 실물 RCI 가 맡은 device 는 조용히 지나간다. 다만 '조용히'가 지나치면 목이
    # 죽은 줄 알게 되므로, 무엇을 왜 넘겼는지는 한 줄 남긴다.
    if device in _suppressed:
        print(f"[mock-rci] {device}: 억제됨 — 실물 RCI 에 맡김 (요청 무시)", flush=True)
        return

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


# retained 제어 상태가 도착할 때까지 기다리는 시간. 이 창을 두지 않고 접속 즉시
# status 를 내면, 억제 상태를 알기 전이라 실물 RCI 의 online 을 덮어쓰고 시작한다.
CTRL_SETTLE_SECONDS = 1.0


def main():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="mock-rci")
    client.on_connect = on_connect
    client.on_message = on_message
    # LWT: 비정상 종료 시 브로커가 offline 을 대신 발행 (요청서 §3.3).
    #
    # 한계: will 은 접속 전에 고정되므로 억제 상태를 따라가지 못한다. RCI(MQTT)
    # 모드에서 목이 비정상 종료하면 실물이 살아있는데도 rci-ur 가 offline 으로
    # 덮인다. 목은 브로커와 같은 PC 에 있어 죽으면 바로 보이는 개발 도구라
    # 감수하고 두지만, 실물만 쓸 거면 애초에 -NoMock 으로 띄우는 편이 낫다.
    client.will_set(STATUS["urrobot"], json.dumps({"state": "offline"}), qos=1, retain=True)
    client.connect(BROKER_HOST, BROKER_PORT, 60)
    client.loop_start()
    print("[mock-rci] running (Ctrl+C to stop)", flush=True)

    time.sleep(CTRL_SETTLE_SECONDS)
    announce(client)

    with contextlib.suppress(KeyboardInterrupt):
        while True:
            time.sleep(1)
    client.loop_stop()


if __name__ == "__main__":
    main()
