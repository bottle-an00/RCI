"""UR_Robot.glb 의 기본 자세(홈 포즈)를 지정하고, 애니메이션도 그 자세에서 시작하게 옮긴다.

왜 두 가지를 함께 하는가
    바인드 포즈만 바꾸면 tools/fix_ur3_pose.py 가 고친 문제가 되살아난다. 모델에는
    자세가 두 벌 있다 — 노드에 박힌 바인드 포즈(로드 직후)와 애니메이션 첫 키
    (강제구동 뒤 resetMotion() 이 currentTime=0 으로 되돌린 자세). 둘이 어긋나면
    첫 구동에서 관절이 툭 튀고 그 뒤로는 다른 자세로 서 있는다.

    그래서 바인드를 새 자세로 박고, 그 관절을 겨냥하는 애니메이션 채널의 **모든 키를
    같은 각도만큼 평행이동**한다. 움직임의 모양(진폭·타이밍)은 그대로 유지되고 시작·끝
    자세만 새 홈 포즈로 옮겨진다. 기존 클립들은 첫 키와 끝 키가 같아서(Shoulder
    56.49°→…→56.49°) 평행이동 뒤에도 제자리로 돌아온다.

각도는 어디서 왔는가
    UR 홈페이지 홍보 사진의 접힌 자세를 참조로 삼아, 링크 방향을 역산해 맞췄다.
    Shoulder·Elbow·Wrist02 가 모두 같은 축(로컬 −Z)을 돌아 팔이 한 평면에서 접히므로,
    평면 3관절 문제로 풀린다 — 목표 링크 방향(어깨→엘보우 +33°, 엘보우→손목 +136°,
    손목→툴 −152°)을 순차 1차원 탐색으로 맞춘 결과가 아래 기본값이다.

      θ 는 로컬 +Z 축 기준 부호 있는 각도다. 기존 값은 −56.49 / −85.22 / −37.79 였다
      (즉 −Z 로 56.49° 등). 바뀌는 양은 어깨 −0.52° · 엘보우 +188.24° · 손목2 +81.13°
      로, 사실상 '엘보우를 접어 팔을 위로 세우는' 변경이다.

사용
    python tools/set_ur3_home_pose.py                   # 기본 홈 포즈 적용
    python tools/set_ur3_home_pose.py --dry-run         # 무엇이 바뀔지만 본다
    python tools/set_ur3_home_pose.py --shoulder -57.01 --elbow 103.02 --wrist2 43.34
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

# 참조 자세를 역산한 값 (로컬 +Z 기준 부호 있는 각도).
HOME = {"Shoulder": -57.01, "Elbow": 103.02, "Wrist02": 43.34}


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


def theta_z(q) -> float:
    """순수 Z 회전 쿼터니언 → 부호 있는 각도(도). 이 모델의 팔 관절은 모두 Z 축이다."""
    return math.degrees(2 * math.atan2(q[2], q[3]))


def q_from_theta_z(deg: float):
    h = math.radians(deg) / 2
    return [0.0, 0.0, math.sin(h), math.cos(h)]


def layout(gltf: dict, accessor_index: int):
    acc = gltf["accessors"][accessor_index]
    if acc["type"] != "VEC4" or acc["componentType"] != 5126:
        raise SystemExit(f"rotation accessor 가 float VEC4 가 아니다: {acc['type']}")
    view = gltf["bufferViews"][acc["bufferView"]]
    start = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
    return start, (view.get("byteStride") or 16), acc["count"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", type=Path, default=MODEL)
    ap.add_argument("--shoulder", type=float, default=HOME["Shoulder"])
    ap.add_argument("--elbow", type=float, default=HOME["Elbow"])
    ap.add_argument("--wrist2", type=float, default=HOME["Wrist02"])
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    want = {"Shoulder": args.shoulder, "Elbow": args.elbow, "Wrist02": args.wrist2}

    raw = args.model.read_bytes()
    version, gltf, bin_data = unpack(raw)
    nodes = gltf["nodes"]
    index = {n.get("name"): i for i, n in enumerate(nodes)}

    print(f"{args.model.name} · 홈 포즈 적용")
    for name, new_theta in want.items():
        ni = index.get(name)
        if ni is None:
            raise SystemExit(f"'{name}' 노드가 없다")
        old_theta = theta_z(nodes[ni].get("rotation", [0, 0, 0, 1]))
        delta = new_theta - old_theta

        # 이 노드의 rotation 을 겨냥하는 채널의 출력 accessor (클립 간 공유될 수 있다)
        accs = {}
        for anim in gltf.get("animations", []):
            for chn in anim["channels"]:
                t = chn["target"]
                if t.get("node") == ni and t["path"] == "rotation":
                    accs.setdefault(anim["samplers"][chn["sampler"]]["output"], set()).add(
                        anim.get("name", "?"))

        print(f"\n  {name}")
        print(f"    바인드 {old_theta:+8.2f}° → {new_theta:+8.2f}°   (Δ {delta:+.2f}°)")
        if not args.dry_run:
            nodes[ni]["rotation"] = [round(v, 7) for v in q_from_theta_z(new_theta)]

        for acc_out, clips in accs.items():
            start, stride, count = layout(gltf, acc_out)
            before = [theta_z(struct.unpack_from("<ffff", bin_data, start + i * stride))
                      for i in range(count)]
            print(f"    acc{acc_out} · 키 {count}개 · 클립 {', '.join(sorted(clips))}")
            print(f"      지금  {min(before):+8.2f}° ~ {max(before):+8.2f}°  "
                  f"(첫 {before[0]:+.2f}° / 끝 {before[-1]:+.2f}°)")
            after = [t + delta for t in before]
            print(f"      이후  {min(after):+8.2f}° ~ {max(after):+8.2f}°  "
                  f"(첫 {after[0]:+.2f}° / 끝 {after[-1]:+.2f}°)")
            if args.dry_run:
                continue
            for i, th in enumerate(after):
                struct.pack_into("<ffff", bin_data, start + i * stride, *q_from_theta_z(th))

    if args.dry_run:
        print("\n--dry-run · 쓰지 않았다.")
        return 0

    out = pack(version, gltf, bin_data)
    args.model.write_bytes(out)
    _, again, bin2 = unpack(args.model.read_bytes())
    assert len(again.get("animations", [])) == len(gltf.get("animations", [])), "클립 수가 달라졌다"
    # 바인드와 첫 키가 실제로 일치하는지 되읽어 확인 — 이게 이 도구의 핵심 불변식이다.
    bad = []
    for name in want:
        ni = index[name]
        bind = theta_z(again["nodes"][ni]["rotation"])
        for anim in again.get("animations", []):
            for chn in anim["channels"]:
                t = chn["target"]
                if t.get("node") == ni and t["path"] == "rotation":
                    s, st, _ = layout(again, anim["samplers"][chn["sampler"]]["output"])
                    first = theta_z(struct.unpack_from("<ffff", bin2, s))
                    if abs((bind - first + 180) % 360 - 180) > 0.02:
                        bad.append(f"{name}/{anim.get('name')}: 바인드 {bind:.2f}° ≠ 첫 키 {first:.2f}°")
    if bad:
        raise SystemExit("불변식 깨짐 —\n  " + "\n  ".join(bad))
    print(f"\n수정 완료 · {len(raw):,}B → {len(out):,}B · 클립 {len(again['animations'])}개 유지")
    print("바인드 == 애니메이션 첫 키 검증 OK (로드 직후와 구동 후 자세가 같다)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
