"""UR_Robot.glb 에 책상(다리 있는 작업대)을 붙인다 — 회색 무광 + 검정 모서리.

왜 필요한가
    로봇이 공중에 떠 있는 것처럼 보였다. 받침대 기둥만 있고 바닥이 없어 크기 감각이
    잡히지 않는다. 더 중요한 이유는 **베이스 회전이 잘 읽히지 않는다**는 것이다 —
    UR3 는 세로축에 대해 거의 대칭이라, 배경이 빈 공간이면 베이스가 90° 돌아도
    '돌았는지' 판단하기 어렵다. 고정된 판이 있으면 상대 운동이 즉시 보인다.

    모서리를 검정으로 두는 이유: 배경색을 화면에서 바꿀 수 있게 했으므로
    (static/js/view3d-bg.js), 회색 배경을 고르면 회색 책상이 배경에 묻힌다. 상판
    테두리에 검정 띠를 두면 어떤 배경에서도 책상의 윤곽이 남는다.

무엇을 하는가
    상판 1개 + 다리 4개를 박스로 만들어 GLB 에 주입한다. 정점·법선은 한 벌만 올리고,
    인덱스를 둘로 갈라 프리미티브 2개로 나눈다 — 회색(상판 위·아래면 + 다리 전체)과
    검정(상판 측면 4면). glTF 프리미티브는 attribute accessor 를 공유할 수 있어
    정점을 두 번 올릴 필요가 없다.

    다리는 상판 모서리에 맞춘다 — 바깥 두 면이 상판 측면과 같은 평면에 놓여, 다리의
    바깥 수직 모서리가 상판 코너와 한 선으로 이어진다(--inset 0). 검정 테두리 띠가
    다리 모서리까지 그대로 내려가 보이므로 윤곽이 끊기지 않는다.

    노드는 **씬 루트에 직접** 붙인다(UR3 아래가 아니다). 그래서 베이스가 돌 때 책상은
    가만히 있는다 — 그게 이 판을 두는 목적이다. 씬 루트가 월드 좌표계이므로 아래
    치수는 그대로 월드 값이다.

    받침대 밑면이 정확히 Y=0 이라 상판 윗면을 Y=0 에 둔다. 상판은 팔이 뻗는 쪽으로
    조금 넘치게 잡았다 — 실제 작업대에 얹힌 UR3 도 팔이 모서리를 넘어간다.

    책상을 넣으면 바운딩 박스가 커져 model-viewer 가 조금 물러나 잡는다(로봇이 그만큼
    작아진다). 그래서 다리를 실물 비율보다 짧게 두어 높이 증가를 0.2 로 묶었다.

    이미 책상이 있으면 아무 것도 하지 않는다. 치수를 바꾸려면 GLB 를 git 에서 되돌린
    뒤(git checkout -- static/models/UR_Robot.glb) 다른 옵션으로 다시 돌릴 것 —
    accessor 를 지우면 뒤 인덱스가 전부 밀려 다른 메시가 깨진다.

사용
    python tools/add_ur3_desk.py
    python tools/add_ur3_desk.py --width 0.50 --depth 0.38 --leg-height 0.22
    python tools/add_ur3_desk.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MODEL = Path(__file__).resolve().parent.parent / "static" / "models" / "UR_Robot.glb"
JSON_CHUNK, BIN_CHUNK = 0x4E4F534A, 0x004E4942
NODE_NAME = MESH_NAME = "Desk"
MAT_GRAY, MAT_EDGE = "DeskGrayMatte", "DeskEdgeBlack"

# 회색 무광. metallic 0 / roughness 0.9 — 로봇의 rep_WhitePlastic(0.13/0.25)과 달리
# 반사를 거의 없애 배경 판처럼 가라앉게 한다.
GRAY = [0.451, 0.459, 0.475, 1.0]
# 모서리 띠. 완전한 0 은 조명이 없는 듯 죽어 보여 아주 살짝 띄운다.
BLACK = [0.055, 0.059, 0.067, 1.0]

SIDE_FACES = ("+X", "-X", "+Z", "-Z")


def unpack(raw: bytes):
    magic, version, total = struct.unpack_from("<III", raw, 0)
    if magic != 0x46546C67:
        raise SystemExit("GLB 가 아니다 (magic=%#x)" % magic)
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


def box_faces(x0, y0, z0, x1, y1, z1):
    """박스를 면 6개로 돌려준다 — (면 이름, 법선, 사각형 정점 4개).

    면마다 정점을 따로 두는 이유는 법선이 면별로 달라 공유할 수 없기 때문이고,
    면 이름을 함께 돌려주는 이유는 어느 면을 검정으로 칠할지 고르기 위해서다.
    """
    return [
        ("+Z", [0, 0, 1], [(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]),
        ("-Z", [0, 0, -1], [(x1, y0, z0), (x0, y0, z0), (x0, y1, z0), (x1, y1, z0)]),
        ("+X", [1, 0, 0], [(x1, y0, z1), (x1, y0, z0), (x1, y1, z0), (x1, y1, z1)]),
        ("-X", [-1, 0, 0], [(x0, y0, z0), (x0, y0, z1), (x0, y1, z1), (x0, y1, z0)]),
        ("+Y", [0, 1, 0], [(x0, y1, z1), (x1, y1, z1), (x1, y1, z0), (x0, y1, z0)]),
        ("-Y", [0, -1, 0], [(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)]),
    ]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", type=Path, default=MODEL)
    ap.add_argument("--width", type=float, default=0.44, help="상판 X 폭 (기본 0.44)")
    ap.add_argument("--depth", type=float, default=0.34, help="상판 Z 깊이 (기본 0.34)")
    ap.add_argument("--top-thickness", type=float, default=0.022)
    ap.add_argument("--leg-height", type=float, default=0.18)
    ap.add_argument("--leg", type=float, default=0.028, help="다리 단면 한 변")
    # 0 이면 다리의 바깥 두 면이 상판 측면과 같은 평면에 놓인다 — 다리의 바깥 수직
    # 모서리가 상판 코너와 정확히 한 선으로 이어진다. 안으로 물리려면 값을 준다.
    ap.add_argument("--inset", type=float, default=0.0,
                    help="다리를 상판 모서리에서 안으로 물리는 양 (기본 0 = 모서리에 맞춤)")
    ap.add_argument("--top-y", type=float, default=0.0, help="상판 윗면 Y (받침대 밑면)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    raw = args.model.read_bytes()
    version, gltf, bin_data = unpack(raw)

    if any(n.get("name") == NODE_NAME for n in gltf["nodes"]):
        print("'%s' 노드가 이미 있다 — 아무 것도 하지 않는다." % NODE_NAME)
        return 0

    hw, hd = args.width / 2, args.depth / 2
    ty = args.top_y
    lt = ty - args.top_thickness                                          # 다리 상단
    lb = lt - args.leg_height                                             # 다리 하단

    # (면 목록, 측면을 검정으로 칠할지) — 상판만 테두리를 검정으로 둔다.
    groups = [(box_faces(-hw, lt, -hd, hw, ty, hd), True)]
    for sx in (-1, 1):
        for sz in (-1, 1):
            cx = sx * (hw - args.inset - args.leg / 2)
            cz = sz * (hd - args.inset - args.leg / 2)
            groups.append((box_faces(cx - args.leg / 2, lb, cz - args.leg / 2,
                                     cx + args.leg / 2, lt, cz + args.leg / 2), False))

    pos, nrm, idx_gray, idx_edge = [], [], [], []
    for faces, edge_sides in groups:
        for name, normal, quad in faces:
            b = len(pos)
            pos.extend(quad)
            nrm.extend([tuple(normal)] * 4)
            tris = [b, b + 1, b + 2, b, b + 2, b + 3]
            if edge_sides and name in SIDE_FACES:
                idx_edge.extend(tris)
            else:
                idx_gray.extend(tris)

    print("%s · 책상 주입" % args.model.name)
    print("  상판 %.3f x %.3f x %.3f  윗면 Y=%+.3f"
          % (args.width, args.top_thickness, args.depth, ty))
    print("  다리 %.3f 각 x %.3f x 4개  밑면 Y=%+.3f" % (args.leg, args.leg_height, lb))
    print("  정점 %d개 · 회색 삼각형 %d개 · 검정 모서리 삼각형 %d개"
          % (len(pos), len(idx_gray) // 3, len(idx_edge) // 3))
    print("  회색 baseColor %s (metallic 0 / roughness 0.9) · 모서리 %s"
          % (GRAY[:3], BLACK[:3]))
    if args.dry_run:
        print("\n--dry-run · 쓰지 않았다.")
        return 0

    # --- BIN 에 덧붙인다. bufferView 는 4바이트 경계에 맞춘다. ---
    def append(payload: bytes) -> int:
        bin_data.extend(b"\x00" * (-len(bin_data) % 4))
        start = len(bin_data)
        bin_data.extend(payload)
        return start

    pos_off = append(b"".join(struct.pack("<fff", *v) for v in pos))
    nrm_off = append(b"".join(struct.pack("<fff", *v) for v in nrm))
    gray_off = append(b"".join(struct.pack("<H", v) for v in idx_gray))
    edge_off = append(b"".join(struct.pack("<H", v) for v in idx_edge))

    bv = gltf["bufferViews"]
    base_bv = len(bv)
    bv.append({"buffer": 0, "byteOffset": pos_off, "byteLength": len(pos) * 12, "target": 34962})
    bv.append({"buffer": 0, "byteOffset": nrm_off, "byteLength": len(nrm) * 12, "target": 34962})
    bv.append({"buffer": 0, "byteOffset": gray_off,
               "byteLength": len(idx_gray) * 2, "target": 34963})
    bv.append({"buffer": 0, "byteOffset": edge_off,
               "byteLength": len(idx_edge) * 2, "target": 34963})
    bv_pos, bv_nrm, bv_gray, bv_edge = base_bv, base_bv + 1, base_bv + 2, base_bv + 3

    acc = gltf["accessors"]
    base_acc = len(acc)
    # POSITION 은 min/max 가 필수다(glTF 2.0) — 뷰어가 바운딩을 이걸로 잡는다.
    acc.append({"bufferView": bv_pos, "componentType": 5126, "count": len(pos), "type": "VEC3",
                "min": [min(v[k] for v in pos) for k in range(3)],
                "max": [max(v[k] for v in pos) for k in range(3)]})
    acc.append({"bufferView": bv_nrm, "componentType": 5126, "count": len(nrm), "type": "VEC3"})
    acc.append({"bufferView": bv_gray, "componentType": 5123,
                "count": len(idx_gray), "type": "SCALAR"})
    acc.append({"bufferView": bv_edge, "componentType": 5123,
                "count": len(idx_edge), "type": "SCALAR"})
    a_pos, a_nrm, a_gray, a_edge = base_acc, base_acc + 1, base_acc + 2, base_acc + 3

    def material(name, color):
        gltf["materials"].append({
            "name": name,
            "pbrMetallicRoughness": {"baseColorFactor": color,
                                     "metallicFactor": 0.0, "roughnessFactor": 0.9},
            "emissiveFactor": [0.0, 0.0, 0.0], "alphaMode": "OPAQUE", "doubleSided": False,
        })
        return len(gltf["materials"]) - 1

    mat_gray = material(MAT_GRAY, GRAY)
    mat_edge = material(MAT_EDGE, BLACK)

    # 프리미티브 2개가 POSITION·NORMAL accessor 를 공유하고 인덱스만 다르다.
    attrs = {"POSITION": a_pos, "NORMAL": a_nrm}
    gltf["meshes"].append({"name": MESH_NAME, "primitives": [
        {"attributes": attrs, "indices": a_gray, "material": mat_gray},
        {"attributes": attrs, "indices": a_edge, "material": mat_edge},
    ]})
    mesh_i = len(gltf["meshes"]) - 1

    gltf["nodes"].append({"name": NODE_NAME, "mesh": mesh_i})
    node_i = len(gltf["nodes"]) - 1
    # 씬 루트에 직접 — UR3 아래에 넣으면 베이스와 함께 돌아 버린다.
    gltf["scenes"][gltf["scene"]]["nodes"].append(node_i)

    gltf["buffers"][0]["byteLength"] = len(bin_data)

    out = pack(version, gltf, bin_data)
    args.model.write_bytes(out)

    _, again, _ = unpack(args.model.read_bytes())
    assert any(n.get("name") == NODE_NAME for n in again["nodes"]), "책상 노드가 없다"
    assert len(again.get("animations", [])) == len(gltf.get("animations", [])), "클립 수가 달라졌다"
    assert again["buffers"][0]["byteLength"] == len(bin_data), "buffer 길이가 안 맞는다"
    desk = next(m for m in again["meshes"] if m.get("name") == MESH_NAME)
    assert len(desk["primitives"]) == 2, "프리미티브가 2개가 아니다"
    print("\n수정 완료 · %s B -> %s B · 노드 %d개 · 클립 %d개 유지 · 프리미티브 2개 · 재파싱 OK"
          % (format(len(raw), ","), format(len(out), ","),
             len(again["nodes"]), len(again["animations"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
