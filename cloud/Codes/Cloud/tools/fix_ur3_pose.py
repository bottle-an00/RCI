"""UR_Robot.glb 의 '시작 관절 위치' 교정 — 바인드 포즈를 애니메이션 첫 키에 맞춘다.

왜 필요한가
    모델에는 자세가 두 벌 들어 있다. 하나는 노드에 박힌 **바인드 포즈**(애니메이션을
    한 번도 재생하지 않은 로드 직후에 보이는 자세), 다른 하나는 **애니메이션 첫
    키프레임**(강제구동을 한 번 하고 rci-live.js 의 resetMotion() 이 currentTime=0
    으로 되돌린 뒤의 자세)이다. 이 둘이 다르면 첫 강제구동 순간 관절이 툭 튀고,
    그 뒤로는 계속 다른 자세로 서 있는다.

    UR_Robot.glb 는 Wrist02 가 바인드 0°인데 UR3Track 첫 키는 37.79°(−Z)여서
    말단 툴이 로드 직후에만 위로 45° 젖혀져 있었다. model-viewer 는 머티리얼만
    공개하고 노드 변환은 손댈 수 없어(rci-live.js 주석) JS 로는 고칠 수 없다 —
    그래서 파일을 직접 고친다.

무엇을 하는가
    기준 클립(기본 UR3Track)의 rotation 채널마다 첫 키 값을 읽어, 그 채널이 겨냥한
    노드의 바인드 rotation 을 같은 값으로 덮는다. 이미 같으면 건드리지 않는다 —
    몇 번 돌려도 결과가 같다(idempotent).

    glTF 2.0 의 GLB 는 [헤더 12B][JSON 청크][BIN 청크] 다. 노드 변환은 JSON 청크에
    쿼터니언 배열로 들어 있어 Blender 없이 바꿀 수 있다. 메시·키프레임은 BIN 청크에
    그대로 두므로 이 도구는 기하를 손대지 않는다.

사용
    python tools/fix_ur3_pose.py                      # 실제로 고친다(백업 .bak 생성)
    python tools/fix_ur3_pose.py --dry-run            # 무엇이 바뀔지만 본다
    python tools/fix_ur3_pose.py --clip JointWrist2   # 기준 클립을 바꾼다
"""
from __future__ import annotations

import argparse
import json
import math
import struct
import sys
from pathlib import Path

# 한글·em-dash 를 찍는다. 윈도우 기본 콘솔(cp949)에서는 인코딩 에러로 죽으므로
# 출력 스트림을 UTF-8 로 돌린다 — 리포의 다른 tools 도 같은 약점이 있다.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

MODEL = Path(__file__).resolve().parent.parent / "static" / "models" / "UR_Robot.glb"
JSON_CHUNK, BIN_CHUNK = 0x4E4F534A, 0x004E4942

# 쿼터니언이 '같은 회전'인지 보는 허용오차. q 와 −q 는 같은 회전이므로 둘 다 본다.
EPS = 1e-4


def unpack_glb(raw: bytes) -> tuple[int, dict, bytes]:
    magic, version, total = struct.unpack_from("<III", raw, 0)
    if magic != 0x46546C67:
        raise SystemExit(f"GLB 가 아니다 (magic={magic:#x})")
    off, chunks = 12, {}
    while off < total:
        length, ctype = struct.unpack_from("<II", raw, off)
        chunks[ctype] = raw[off + 8: off + 8 + length]
        off += 8 + length + (-length % 4)
    if JSON_CHUNK not in chunks:
        raise SystemExit("JSON 청크가 없다")
    return version, json.loads(chunks[JSON_CHUNK].decode("utf-8")), chunks.get(BIN_CHUNK, b"")


def pack_glb(version: int, gltf: dict, bin_data: bytes) -> bytes:
    """JSON 은 공백(0x20), BIN 은 0x00 으로 4바이트 경계까지 채운다(glTF 2.0 §4.4.1)."""
    js = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    js += b" " * (-len(js) % 4)
    out = bytearray()
    body = bytearray()
    body += struct.pack("<II", len(js), JSON_CHUNK) + js
    if bin_data:
        bn = bin_data + b"\x00" * (-len(bin_data) % 4)
        body += struct.pack("<II", len(bn), BIN_CHUNK) + bn
    out += struct.pack("<III", 0x46546C67, version, 12 + len(body)) + body
    return bytes(out)


def read_first_key(gltf: dict, bin_data: bytes, accessor_index: int) -> list[float]:
    """rotation 출력 accessor 의 첫 원소(VEC4 float)를 꺼낸다."""
    acc = gltf["accessors"][accessor_index]
    if acc["type"] != "VEC4" or acc["componentType"] != 5126:
        raise SystemExit(f"rotation 샘플러가 float VEC4 가 아니다: {acc['type']}/{acc['componentType']}")
    view = gltf["bufferViews"][acc["bufferView"]]
    base = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
    return list(struct.unpack_from("<ffff", bin_data, base))


def same_rotation(a: list[float], b: list[float]) -> bool:
    d = math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))
    dn = math.sqrt(sum((x + y) ** 2 for x, y in zip(a, b)))   # q 와 −q 는 같은 회전
    return min(d, dn) < EPS


def axis_angle(q: list[float]) -> str:
    x, y, z, w = q
    n = math.sqrt(x * x + y * y + z * z + w * w) or 1.0
    x, y, z, w = x / n, y / n, z / n, w / n
    if w < 0:
        x, y, z, w = -x, -y, -z, -w
    deg = 2 * math.degrees(math.acos(max(-1.0, min(1.0, w))))
    s = math.sqrt(max(0.0, 1 - w * w))
    if s < 1e-6:
        return f"{deg:6.2f}°"
    return f"{deg:6.2f}° 축({x / s:+.2f},{y / s:+.2f},{z / s:+.2f})"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", type=Path, default=MODEL)
    ap.add_argument("--clip", default="UR3Track", help="기준 클립 이름 (기본 UR3Track)")
    ap.add_argument("--dry-run", action="store_true", help="고치지 않고 차이만 보여준다")
    args = ap.parse_args()

    raw = args.model.read_bytes()
    version, gltf, bin_data = unpack_glb(raw)

    clip = next((a for a in gltf.get("animations", []) if a.get("name") == args.clip), None)
    if clip is None:
        names = [a.get("name") for a in gltf.get("animations", [])]
        raise SystemExit(f"클립 '{args.clip}' 이 없다. 있는 것: {names}")

    nodes = gltf["nodes"]
    changed = []
    print(f"{args.model.name} · 기준 클립 '{args.clip}'")
    for ch in clip["channels"]:
        if ch["target"]["path"] != "rotation":
            continue
        ni = ch["target"]["node"]
        node = nodes[ni]
        bind = node.get("rotation", [0.0, 0.0, 0.0, 1.0])
        first = read_first_key(gltf, bin_data, clip["samplers"][ch["sampler"]]["output"])
        name = node.get("name", f"node{ni}")
        if same_rotation(bind, first):
            print(f"  {name:<10} 일치      {axis_angle(bind)}")
            continue
        print(f"  {name:<10} 불일치    바인드 {axis_angle(bind)}  →  첫 키 {axis_angle(first)}")
        node["rotation"] = [round(v, 7) for v in first]
        changed.append(name)

    if not changed:
        print("\n모두 일치 — 바꿀 것이 없다.")
        return 0
    if args.dry_run:
        print(f"\n--dry-run · 바뀔 노드 {len(changed)}개: {', '.join(changed)}")
        return 0

    backup = args.model.with_suffix(args.model.suffix + ".bak")
    if not backup.exists():           # 첫 실행의 원본만 남긴다(재실행이 백업을 덮지 않게)
        backup.write_bytes(raw)
        print(f"\n원본 백업 → {backup.name}")
    out = pack_glb(version, gltf, bin_data)
    args.model.write_bytes(out)
    print(f"수정 완료 · 노드 {len(changed)}개({', '.join(changed)}) · "
          f"{len(raw):,}B → {len(out):,}B")
    # 되읽어 확인 — 쓰고 나서 깨지지 않았는지 여기서 걸러낸다.
    _, again, _ = unpack_glb(args.model.read_bytes())
    assert len(again["nodes"]) == len(nodes), "재파싱 결과가 다르다"
    print("재파싱 검증 OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
