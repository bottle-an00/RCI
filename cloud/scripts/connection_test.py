"""RCI ↔ 브로커 ↔ FastAPI 전 구간 연결 테스트 (웹 → RCI 방향 발행 포함).

`Codes/board/test_roundtrip.py` 는 MQTT 에 **직접** 붙어 파이프만 본다. 이 스크립트는
한 단계 위, **FastAPI 를 통해** 발행/수신해서 실제 서비스 경로 전체를 검증한다.

    [이 스크립트] --HTTP--> [FastAPI :8123] --MQTT--> [브로커] --MQTT--> [RCI]
                        <--          응답을 id 로 상관지어 되돌림          --

RCI 담당자 사용법 (RCI 를 라즈베리파이에서 띄운 상태로, PC 에서 실행):

    python scripts/connection_test.py                          # 로컬 기본값
    python scripts/connection_test.py --base-url http://192.168.x.y:8123
    python scripts/connection_test.py --device urrobot --stub  # 실물 RCI 스텁(3E 00 만 구현)

`--stub` 은 UDS 디스패처가 아직 없는 RCI(= ur3/scripts/mqtt_echo_test.py) 상대일 때
쓴다. 이 경우 TesterPresent(3E 00) 외 서비스는 에러 회신이 정상이므로 실패로 세지 않는다.

표준 라이브러리만 쓴다(설치 불필요). 종료 코드: 전부 통과 0, 하나라도 실패 1.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
import urllib.error
import urllib.request

with contextlib.suppress(Exception):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"


class Http:
    """최소 HTTP 클라이언트. (status, body) 를 돌려주고 4xx/5xx 도 예외 없이 반환한다."""

    def __init__(self, base_url: str, timeout: float):
        self.base = base_url.rstrip("/")
        self.timeout = timeout

    def request(self, method: str, path: str, body: dict | None = None):
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Content-Type": "application/json"} if data else {}
        req = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.status, json.loads(resp.read().decode() or "null")
        except urllib.error.HTTPError as exc:               # 4xx/5xx 도 검증 대상
            raw = exc.read().decode(errors="replace")
            with contextlib.suppress(ValueError):
                return exc.code, json.loads(raw)
            return exc.code, {"detail": raw}
        except urllib.error.URLError as exc:
            raise SystemExit(
                f"✗ FastAPI 에 접속할 수 없습니다: {self.base} ({exc.reason})\n"
                f"  웹 서버를 먼저 띄우세요:  python -m uvicorn main:app "
                f"--app-dir Codes/Cloud --port 8123") from None


class Report:
    """검사 결과 누적기. 실패는 원인까지 남긴다 — 통과/실패만으론 디버깅이 안 된다."""

    def __init__(self):
        self.rows = []

    def add(self, verdict: str, name: str, detail: str = ""):
        self.rows.append((verdict, name, detail))
        mark = {PASS: "PASS", FAIL: "FAIL", SKIP: "SKIP"}[verdict]
        print(f"  [{mark}] {name}" + (f"\n         {detail}" if detail else ""))

    @property
    def failed(self):
        return [r for r in self.rows if r[0] == FAIL]

    def summary(self):
        counts = {v: sum(1 for r in self.rows if r[0] == v) for v in (PASS, FAIL, SKIP)}
        print(f"\n결과: 통과 {counts[PASS]} · 실패 {counts[FAIL]} · 건너뜀 {counts[SKIP]}")
        return 1 if counts[FAIL] else 0


def check_health(http: Http, rep: Report) -> dict:
    status, body = http.request("GET", "/api/health")
    if status != 200:
        rep.add(FAIL, "FastAPI /api/health", f"HTTP {status} — {body}")
        raise SystemExit(rep.summary())
    rep.add(PASS, "FastAPI 응답", f"{http.base}")

    if body.get("connected"):
        rep.add(PASS, "FastAPI → 브로커 연결", body.get("broker", ""))
    else:
        rep.add(FAIL, "FastAPI → 브로커 연결",
                f"미연결 — {body.get('broker')}. 브로커가 떠 있는지, "
                f"RCI_BROKER_HOST/PORT 환경변수가 맞는지 확인하세요.")
        raise SystemExit(rep.summary())
    return body


def check_rci_alive(http: Http, rep: Report, device: str, health: dict):
    """RCI 생존 상태(retained)를 받았는지. 없으면 RCI 가 안 떴거나 토픽이 어긋난 것."""
    status, body = http.request("GET", f"/api/status/{device}")
    if status == 200:
        rep.add(PASS, f"RCI 생존 상태 ({device})", json.dumps(body, ensure_ascii=False))
    else:
        rep.add(FAIL, f"RCI 생존 상태 ({device})",
                "retained status 미수신 — RCI 가 minigit/status/rci-{ur|rc} 에 "
                "발행하는지, 같은 브로커에 붙었는지 확인하세요.")


def diag(http: Http, device: str, raw: str, timeout_ms: int = 1000):
    return http.request("POST", f"/api/diag/{device}/request",
                        {"raw": raw, "timeout_ms": timeout_ms})


def check_roundtrip(http: Http, rep: Report, device: str, stub: bool):
    """웹 → RCI 발행 → 응답 수신. 여기가 이 스크립트의 본체."""
    # 1) TesterPresent — 세션·상태에 의존하지 않아 실물/목/스텁 어디서나 통과해야 한다.
    status, body = diag(http, device, "3E 00")
    if status == 200 and body.get("type") == "positive" and body.get("raw") == "7E 00":
        rep.add(PASS, "왕복 3E 00 (TesterPresent)", f"← {body['raw']}  id={body.get('id')}")
    elif status == 504:
        rep.add(FAIL, "왕복 3E 00 (TesterPresent)",
                "RCI 무응답 — 요청은 브로커까지 갔으나 회신이 없습니다. RCI 가 "
                f"minigit/req/{device} 를 구독 중인지 확인하세요.")
    else:
        rep.add(FAIL, "왕복 3E 00 (TesterPresent)", f"HTTP {status} — {body}")

    # 2) 0x22 읽기 — UDS 디스패처가 있어야 한다. 스텁 상대면 에러 회신이 정상.
    status, body = diag(http, device, "22 01 07")
    if status == 200 and body.get("type") == "positive":
        rep.add(PASS, "왕복 22 01 07 (ReadDataByIdentifier)", f"← {body.get('raw')}")
    elif stub:
        rep.add(SKIP, "왕복 22 01 07 (ReadDataByIdentifier)",
                f"스텁 모드 — UDS 디스패처 미구현이 정상. 회신: {body}")
    else:
        rep.add(FAIL, "왕복 22 01 07 (ReadDataByIdentifier)", f"HTTP {status} — {body}")

    # 3) id 상관 — 연속 요청의 응답이 서로 뒤바뀌지 않는지(응답 id = 요청 id).
    ids = []
    for _ in range(3):
        status, body = diag(http, device, "3E 00")
        if status == 200 and body.get("id"):
            ids.append(body["id"])
    if len(ids) == 3 and len(set(ids)) == 3:
        rep.add(PASS, "요청-응답 id 상관", " · ".join(ids))
    else:
        rep.add(FAIL, "요청-응답 id 상관", f"응답 id 가 중복/누락: {ids}")


def check_input_validation(http: Http, rep: Report, device: str):
    """계약 표기 정규화·거부. RCI 쪽이 아니라 웹 쪽 계약 준수를 본다."""
    status, body = diag(http, device, "3e00")          # 소문자·공백 없음 → 정규화되어야
    if status == 200:
        rep.add(PASS, "raw 표기 정규화 (3e00 → 3E 00)", f"← {body.get('raw')}")
    else:
        rep.add(FAIL, "raw 표기 정규화 (3e00 → 3E 00)", f"HTTP {status} — {body}")

    status, body = diag(http, device, "ZZ")            # hex 아님 → 400
    if status == 400:
        rep.add(PASS, "잘못된 raw 거부 (400)", str(body.get("detail", ""))[:80])
    else:
        rep.add(FAIL, "잘못된 raw 거부 (400)", f"HTTP {status} 로 응답 — 400 이어야 합니다")

    status, body = diag(http, "nosuchdevice", "3E 00")  # 계약 밖 device → 400
    if status == 400:
        rep.add(PASS, "알 수 없는 device 거부 (400)", str(body.get("detail", ""))[:80])
    else:
        rep.add(FAIL, "알 수 없는 device 거부 (400)", f"HTTP {status} 로 응답 — 400 이어야 합니다")


def main():
    parser = argparse.ArgumentParser(description="RCI ↔ 브로커 ↔ FastAPI 연결 테스트")
    parser.add_argument("--base-url", default="http://0.0.0.0:8123",
                        help="FastAPI 주소 (기본 http://0.0.0.0:8123)")
    parser.add_argument("--device", default="urrobot", choices=["urrobot", "rccar"])
    parser.add_argument("--timeout", type=float, default=10.0, help="HTTP 타임아웃(초)")
    parser.add_argument("--stub", action="store_true",
                        help="RCI 가 UDS 미구현 스텁(3E 00 만 처리)일 때 — 0x22 실패를 건너뜀")
    args = parser.parse_args()

    http = Http(args.base_url, args.timeout)
    rep = Report()

    print(f"\n■ 1단계 · 웹 서버와 브로커 연결   ({args.base_url})")
    health = check_health(http, rep)

    print(f"\n■ 2단계 · RCI 생존 확인   (device={args.device})")
    check_rci_alive(http, rep, args.device, health)

    print("\n■ 3단계 · 웹 → RCI 메시지 왕복")
    check_roundtrip(http, rep, args.device, args.stub)

    print("\n■ 4단계 · 계약 표기 검증")
    check_input_validation(http, rep, args.device)

    code = rep.summary()
    if code:
        print("\n실패한 항목:")
        for _, name, detail in rep.failed:
            print(f"  · {name} — {detail}")
    else:
        print("전 구간 정상. 실시간 메시지를 보려면:  curl -N " + args.base_url + "/api/events")
    return code


if __name__ == "__main__":
    sys.exit(main())
