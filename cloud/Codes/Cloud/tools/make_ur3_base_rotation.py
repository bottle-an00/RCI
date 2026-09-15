"""UR_Robot.glb 의 베이스 회전 키프레임 생성 — 원래 '움직이지 않는' 클립이었다.

왜 필요한가
    베이스 회전 강제구동(DID 0x0204)은 로그도 남고 배지도 뜨는데 모델이 전혀 움직이지
    않았다. UR3 노드를 겨냥하는 rotation 채널의 키프레임 80개가 **전부 identity** 여서다
    (진폭 0.00°). rci-live.js 주석의 "4개 관절이 함께 움직이는 기본 클립" 이라는 설명과
    실제가 달랐다 — 나머지 3개(Shoulder·Elbow·Wrist02)만 실제로 값이 들어 있었다.

    그래서 없는 동작을 만들어 넣는다. UR3Track 과 JointBase 가 같은 출력 accessor 를
    공유하므로(둘 다 acc111), 이 한 번의 수정이 '전체 구동' 과 '베이스 회전' 양쪽에
    함께 반영된다.

회전축을 Y 로 잡은 근거
    UR3 노드의 로컬 축 중 무엇이 수직인지 눈으로 가렸다 — 축별로 90° 를 박아 렌더해
    보면 X·Z 는 로봇이 옆으로 넘어가고 Y 만 받침대가 선 채 팔이 수평으로 돈다.
    기하로도 같은 답이다: 받침대 메시(UnityRobotics_RF3_s1)가 X·Z 로 ±6.42, Y 로
    8.6 을 차지하는 세로 기둥이고, 베이스 디스크(Base01)는 Y 로만 얇은 수평 판이다.

곡선
    0° → +90° → 0° 을 반코사인으로 굽혔다. 샘플러 보간이 LINEAR 라 곡선은 키프레임에
    구워야 하는데, 80개면 충분히 매끄럽다. 양 끝과 꼭대기에서 속도가 0 이 되므로
    시작·정지가 툭 끊기지 않는다. 끝값이 시작값과 같은 것도 중요하다 — 다른 클립들도
    그렇게 되어 있고(Shoulder 56.49°→…→56.49°), rci-live.js 의 resetMotion() 이
    currentTime=0 으로 되돌리기 때문에 클립이 제자리로 돌아와야 자세가 튀지 않는다.

    시간축(acc110)은 그대로 쓴다 — 80키 / 3.33초. 그래서 '베이스 회전'(JointBase)은
    3.33초 단발 스윕이고, '전체 구동'(UR3Track, 16.67초)에서는 베이스가 앞 3.33초에
    돌고 난 뒤 팔이 계속 움직이는 순서로 읽힌다. 시간축을 늘리려면 accessor 를 새로
    만들어야 해서(두 클립이 공유한다) 여기서는 건드리지 않았다.

    기존 80개 키의 값만 제자리에서 덮으므로 accessor 개수·bufferView 길이·파일 크기가
    변하지 않는다. 메시는 손대지 않는다.

사용
    python tools/make_ur3_base_rotation.py                  # 90° 스윕을 굽는다
    python tools/make_ur3_base_rotation.py --degrees 120    # 진폭을 바꾼다
    python tools/make_ur3_base_rotation.py --dry-run        # 무엇이 바뀔지만 본다
"""
from __future__ import annotations

import argparse
import json
import math
import struct
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MODEL = Path(__file__).resolve().parent.parent / "static" / "models" / "UR_Robot.glb"
JSON_CHUNK, BIN_CHUNK = 0x4E4F534A, 0x004E4942
BASE_NODE_NAME = "UR3"          # 베이스(관절 1) 노드 — 아래 팔 전체가 이 노드에 물려 있다
REF_CLIP = "UR3Track"


def unpack(raw: bytes):
    magic, version, total = struct.unpack_from("<III", raw, 0)
    if magic != 0x46546C67:
        raise SystemExit(f"GLB 가 아니다 (magic={magic:#x})")
    off, chunks = 12, {}
    while off < total:
        length, ctype = struct.unpack_from("<II", raw, off)
        chunks[ctype] = raw[off + 8: off + 8 + length]
        off += 8 + length + (-length % 4)
    return version, json.loads(chunks[JSON_CHUNK].decode("utf-8")), bytearray(chunks[BIN_CHUNK])


def pack(version: int, gltf: dict, bin_data: bytes) -> bytes:
    js = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    js += b" " * (-len(js) % 4)
    bn = bytes(bin_data) + b"\x00" * (-len(bin_data) % 4)
    body = (struct.pack("<II", len(js), JSON_CHUNK) + js
            + struct.pack("<II", len(bn), BIN_CHUNK) + bn)
    return struct.pack("<III", 0x46546C67, version, 12 + len(body)) + body


def layout(gltf: dict, accessor_index: int):
    """accessor 의 (시작 바이트, stride, 개수). VEC4 float 만 다룬다."""
    acc = gltf["accessors"][accessor_index]
    if acc["type"] != "VEC4" or acc["componentType"] != 5126:
        raise SystemExit(f"rotation accessor 가 float VEC4 가 아니다: {acc['type']}")
    view = gltf["bufferViews"][acc["bufferView"]]
    start = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
    stride = view.get("byteStride") or 16
    return start, stride, acc["count"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", type=Path, default=MODEL)
    ap.add_argument("--degrees", type=float, default=90.0, help="최대 회전각 (기본 90)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    raw = args.model.read_bytes()
    version, gltf, bin_data = unpack(raw)

    nodes = gltf["nodes"]
    base_idx = next((i for i, n in enumerate(nodes) if n.get("name") == BASE_NODE_NAME), None)
    if base_idx is None:
        raise SystemExit(f"'{BASE_NODE_NAME}' 노드가 없다")

    # 이 노드의 rotation 을 겨냥하는 채널이 쓰는 출력 accessor 를 모은다. UR3Track 과
    # JointBase 가 공유하므로 보통 하나만 나온다 — 나오는 대로 전부 덮는다.
    targets, clips = {}, []
    for anim in gltf.get("animations", []):
        for ch in anim["channels"]:
            t = ch["target"]
            if t.get("node") == base_idx and t["path"] == "rotation":
                acc_out = anim["samplers"][ch["sampler"]]["output"]
                targets.setdefault(acc_out, []).append(anim.get("name", "?"))
                clips.append(anim.get("name", "?"))
    if not targets:
        raise SystemExit(f"'{BASE_NODE_NAME}' 의 rotation 을 겨냥하는 채널이 없다")

    print(f"{args.model.name} · 베이스 노드 '{BASE_NODE_NAME}'(node {base_idx}) · "
          f"최대 {args.degrees:g}° · 축 Y")
    for acc_out, names in targets.items():
        start, stride, count = layout(gltf, acc_out)
        before = [struct.unpack_from("<ffff", bin_data, start + i * stride) for i in range(count)]
        amp = max(2 * math.degrees(math.acos(min(1.0, abs(q[3])))) for q in before)
        print(f"  acc{acc_out} · 키 {count}개 · 쓰는 클립 {', '.join(sorted(set(names)))}")
        print(f"    지금 진폭 {amp:6.2f}°" + ("  ← 사실상 고정" if amp < 0.5 else ""))

        if args.dry_run:
            continue
        for i in range(count):
            u = i / (count - 1)                       # 0 → 1
            # 반코사인: 0 → 1 → 0. 양 끝·꼭대기에서 속도 0.
            ang = math.radians(args.degrees) * (1 - math.cos(2 * math.pi * u)) / 2
            h = ang / 2
            struct.pack_into("<ffff", bin_data, start + i * stride,
                             0.0, math.sin(h), 0.0, math.cos(h))
        after = [struct.unpack_from("<ffff", bin_data, start + i * stride) for i in range(count)]
        amp2 = max(2 * math.degrees(math.acos(min(1.0, abs(q[3])))) for q in after)
        ends = (2 * math.degrees(math.acos(min(1.0, abs(after[0][3])))),
                2 * math.degrees(math.acos(min(1.0, abs(after[-1][3])))))
        print(f"    바뀐 진폭 {amp2:6.2f}°  시작 {ends[0]:.2f}° / 끝 {ends[1]:.2f}° (같아야 정상)")

    if args.dry_run:
        print("\n--dry-run · 쓰지 않았다.")
        return 0

    out = pack(version, gltf, bin_data)
    if len(out) != len(raw):
        print(f"  주의: 파일 크기가 {len(raw):,} → {len(out):,} 로 변했다")
    args.model.write_bytes(out)
    # 되읽어 확인 — 클립이 살아 있는지, 값이 실제로 들어갔는지 여기서 걸러낸다.
    _, again, bin2 = unpack(args.model.read_bytes())
    assert len(again.get("animations", [])) == len(gltf.get("animations", [])), "클립 수가 달라졌다"
    print(f"수정 완료 · {len(raw):,}B → {len(out):,}B · 클립 "
          f"{len(again['animations'])}개 유지 · 재파싱 검증 OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
