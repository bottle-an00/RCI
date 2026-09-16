"""UR_Robot.glb 에 배경 공간(바닥 + 뒷벽 + 입체 GIT 로고 간판)을 붙인다.

왜 필요한가
    화면의 정비소 배경(static/js/view3d-bg.js 의 .view3d__scene)은 CSS 로 그린
    평평한 2D 판이라 model-viewer 의 카메라(드래그 회전)와 무관하게 화면에
    고정돼 있다. 로봇을 돌려 보면 배경은 그대로고 모델만 도는 부자연스러움이
    드러난다. 바닥·벽·로고를 GLB 안에 실제 geometry 로 넣으면 카메라가 도는 대로
    같이 돌아 진짜 3D 공간처럼 보인다 — 책상(add_ur3_desk.py)과 같은 원리다.

    GIT 로고는 텍스트를 새로 그리지 않는다 — static/img/git-logo.png(실제 제공된
    파일)를 그대로 텍스처로 입힌 raised plaque(두께가 있는 판)로 만든다. 폰트로
    다시 그리면 실제 로고체(기울어진 획)와 달라지고, 이미지 윤곽을 벡터로 추적해
    직접 압출하는 것은 지나치게 복잡하다 — 판에 실제 이미지를 입히고 판 자체에
    두께를 줘 옆면이 보이게 하는 편이 브랜드를 그대로 지키면서도 입체감을 낸다.

    로고 PNG 는 투명 영역의 RGB 가 검정으로 박혀 있다(실측) — OPAQUE 로 그리면
    투명이어야 할 자리가 새까맣게 나온다. 그래서 로고 앞면만 alphaMode=BLEND 로
    그린다 — 알파 0 인 자리는 이미 그려진 벽(흰색)이 그대로 비쳐 보인다.

무엇을 하는가
    1) 바닥 — 책상 다리 밑면 높이에 맞춘 큰 사각 평면.
    2) 뒷벽 — 바닥 뒤쪽 가장자리에서 수직으로 올라가는 평면.
    3) GIT 로고 — 벽 앞면에서 --logo-depth 만큼 튀어나온 판. 앞면엔 실제
       git-logo.png 를 텍스처로(alphaMode BLEND), 옆면(테두리 두께)엔 흰 무광을
       입힌다 — 카메라를 돌리면 이 옆면이 보여 '튀어나와 있다' 는 것이 읽힌다.
    노드는 전부 **씬 루트에 직접** 붙인다(UR3 아래가 아니다) — 베이스가 돌 때
    바닥·벽·로고는 가만히 있어야 한다(책상과 같은 이유).

    이미지는 GLB 안에 다시 담지 않는다 — static/models/ 기준 상대경로
    (../img/git-logo.png)로 참조해 static/img/git-logo.png 원본을 그대로 가리킨다.
    파일이 두 자리에 따로 있으면 나중에 로고를 바꿀 때 하나만 바뀌고 하나는
    안 바뀌는 사고가 나기 때문이다.

    이미 'SceneRoom' 노드가 있으면 아무 것도 하지 않는다.

사용
    python add_scene_room.py --model <path-to-UR_Robot.glb>
    python add_scene_room.py --model <path> --dry-run
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

from PIL import Image

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

JSON_CHUNK, BIN_CHUNK = 0x4E4F534A, 0x004E4942
NODE_NAME = "SceneRoom"

# 바닥·벽 — 책상보다 밝은 회색 무광(배경이라 책상보다 더 물러나 보여야 한다).
FLOOR_COLOR = [0.694, 0.706, 0.725, 1.0]
WALL_COLOR = [0.925, 0.933, 0.945, 1.0]
# 로고 판 옆면(테두리 두께) — 벽과 같은 흰 무광. 판이 벽에서 튀어나온 것처럼
# 보이게 하는 것은 이 옆면이지, 색이 아니다.
LOGO_RIM_COLOR = [0.965, 0.968, 0.972, 1.0]

LOGO_IMAGE_REL_URI = "../img/git-logo.png"       # static/models/ 기준 상대경로
LOGO_IMAGE_ABS = Path(__file__).resolve().parent.parent / "static" / "img" / "git-logo.png"


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


def quad(pos_list, nrm_list, idx_list, normal, quad4, uv_list=None, uv4=None):
    """사각형 하나(정점 4개, 삼각형 2개)를 리스트에 얹는다 — 면마다 법선이 달라
    공유할 수 없으므로(add_ur3_desk.py 와 같은 이유) 정점을 따로 둔다."""
    b = len(pos_list)
    pos_list.extend(quad4)
    nrm_list.extend([tuple(normal)] * 4)
    idx_list.extend([b, b + 1, b + 2, b, b + 2, b + 3])
    if uv_list is not None:
        uv_list.extend(uv4)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", type=Path, required=True)
    ap.add_argument("--floor-half", type=float, default=0.42, help="바닥 한 변의 절반")
    ap.add_argument("--floor-y", type=float, default=-0.202, help="바닥 높이(책상 다리 밑면)")
    ap.add_argument("--wall-z", type=float, default=-0.38, help="벽 위치(월드 Z)")
    ap.add_argument("--wall-height", type=float, default=0.72)
    ap.add_argument("--logo-width", type=float, default=0.30, help="로고 판 가로 폭")
    ap.add_argument("--logo-depth", type=float, default=0.016, help="로고 판이 벽에서 튀어나오는 두께")
    ap.add_argument("--logo-y", type=float, default=0.55, help="로고 판 세로 중심")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    raw = args.model.read_bytes()
    version, gltf, bin_data = unpack(raw)

    if any(n.get("name") == NODE_NAME for n in gltf["nodes"]):
        print("'%s' 노드가 이미 있다 — 아무 것도 하지 않는다." % NODE_NAME)
        return 0

    img_w, img_h = Image.open(LOGO_IMAGE_ABS).size
    logo_w = args.logo_width
    logo_h = logo_w * img_h / img_w

    fh = args.floor_half
    fy = args.floor_y
    wz = args.wall_z
    wtop = fy + args.wall_height

    # --- 바닥 · 벽 (UV 없음 — 단색 재질) ---
    room_pos, room_nrm, idx_floor, idx_wall = [], [], [], []
    quad(room_pos, room_nrm, idx_floor, [0, 1, 0],
         [(-fh, fy, fh), (fh, fy, fh), (fh, fy, wz), (-fh, fy, wz)])
    quad(room_pos, room_nrm, idx_wall, [0, 0, 1],
         [(-fh, fy, wz), (fh, fy, wz), (fh, wtop, wz), (-fh, wtop, wz)])

    # --- 로고 판 (앞면만 UV 가 필요하다 — 옆면은 단색) ---
    hw, hh = logo_w / 2, logo_h / 2
    z0, z1 = wz, wz + args.logo_depth
    cy = args.logo_y

    logo_face_pos, logo_face_nrm, logo_face_uv, idx_logo_face = [], [], [], []
    # 앞면 — +Z(방 쪽)를 향한다. UV: glTF 는 V=0 이 이미지 위쪽이다.
    quad(logo_face_pos, logo_face_nrm, idx_logo_face, [0, 0, 1],
         [(-hw, cy - hh, z1), (hw, cy - hh, z1), (hw, cy + hh, z1), (-hw, cy + hh, z1)],
         logo_face_uv, [(0, 1), (1, 1), (1, 0), (0, 0)])

    logo_rim_pos, logo_rim_nrm, idx_logo_rim = [], [], []
    # 옆면(테두리 두께) 4장 — 이게 튀어나온 느낌을 만든다. 뒷면은 벽에 붙어
    # 보이지 않으므로 만들지 않는다.
    edges = [
        ([0, -1, 0], [(-hw, cy - hh, z0), (hw, cy - hh, z0), (hw, cy - hh, z1), (-hw, cy - hh, z1)]),
        ([0, 1, 0], [(hw, cy + hh, z0), (-hw, cy + hh, z0), (-hw, cy + hh, z1), (hw, cy + hh, z1)]),
        ([-1, 0, 0], [(-hw, cy + hh, z0), (-hw, cy - hh, z0), (-hw, cy - hh, z1), (-hw, cy + hh, z1)]),
        ([1, 0, 0], [(hw, cy - hh, z0), (hw, cy + hh, z0), (hw, cy + hh, z1), (hw, cy - hh, z1)]),
    ]
    for normal, q in edges:
        quad(logo_rim_pos, logo_rim_nrm, idx_logo_rim, normal, q)

    print("%s · 배경 공간 주입" % args.model.name)
    print("  바닥 %.2f x %.2f  Y=%+.3f" % (fh * 2, fh * 2, fy))
    print("  벽   %.2f x %.2f  Z=%+.3f" % (fh * 2, args.wall_height, wz))
    print("  로고 판 %.3f x %.3f (원본 %dx%d) · 두께 %.3f · 중심 Y=%+.3f"
          % (logo_w, logo_h, img_w, img_h, args.logo_depth, cy))
    print("  이미지 %s (참조, GLB 에 재복사하지 않음)" % LOGO_IMAGE_REL_URI)
    if args.dry_run:
        print("\n--dry-run · 쓰지 않았다.")
        return 0

    def append(payload: bytes) -> int:
        bin_data.extend(b"\x00" * (-len(bin_data) % 4))
        start = len(bin_data)
        bin_data.extend(payload)
        return start

    room_pos_off = append(b"".join(struct.pack("<fff", *v) for v in room_pos))
    room_nrm_off = append(b"".join(struct.pack("<fff", *v) for v in room_nrm))
    floor_off = append(b"".join(struct.pack("<I", v) for v in idx_floor))
    wall_off = append(b"".join(struct.pack("<I", v) for v in idx_wall))

    face_pos_off = append(b"".join(struct.pack("<fff", *v) for v in logo_face_pos))
    face_nrm_off = append(b"".join(struct.pack("<fff", *v) for v in logo_face_nrm))
    face_uv_off = append(b"".join(struct.pack("<ff", *v) for v in logo_face_uv))
    face_idx_off = append(b"".join(struct.pack("<I", v) for v in idx_logo_face))

    rim_pos_off = append(b"".join(struct.pack("<fff", *v) for v in logo_rim_pos))
    rim_nrm_off = append(b"".join(struct.pack("<fff", *v) for v in logo_rim_nrm))
    rim_idx_off = append(b"".join(struct.pack("<I", v) for v in idx_logo_rim))

    bv = gltf["bufferViews"]

    def add_bv(offset, length, target):
        bv.append({"buffer": 0, "byteOffset": offset, "byteLength": length, "target": target})
        return len(bv) - 1

    bv_room_pos = add_bv(room_pos_off, len(room_pos) * 12, 34962)
    bv_room_nrm = add_bv(room_nrm_off, len(room_nrm) * 12, 34962)
    bv_floor = add_bv(floor_off, len(idx_floor) * 4, 34963)
    bv_wall = add_bv(wall_off, len(idx_wall) * 4, 34963)
    bv_face_pos = add_bv(face_pos_off, len(logo_face_pos) * 12, 34962)
    bv_face_nrm = add_bv(face_nrm_off, len(logo_face_nrm) * 12, 34962)
    bv_face_uv = add_bv(face_uv_off, len(logo_face_uv) * 8, 34962)
    bv_face_idx = add_bv(face_idx_off, len(idx_logo_face) * 4, 34963)
    bv_rim_pos = add_bv(rim_pos_off, len(logo_rim_pos) * 12, 34962)
    bv_rim_nrm = add_bv(rim_nrm_off, len(logo_rim_nrm) * 12, 34962)
    bv_rim_idx = add_bv(rim_idx_off, len(idx_logo_rim) * 4, 34963)

    acc = gltf["accessors"]

    def add_acc(bufferview, comp_type, count, typ, minmax=None):
        entry = {"bufferView": bufferview, "componentType": comp_type, "count": count, "type": typ}
        if minmax:
            entry["min"], entry["max"] = minmax
        acc.append(entry)
        return len(acc) - 1

    a_room_pos = add_acc(bv_room_pos, 5126, len(room_pos), "VEC3",
                         ([min(v[k] for v in room_pos) for k in range(3)],
                          [max(v[k] for v in room_pos) for k in range(3)]))
    a_room_nrm = add_acc(bv_room_nrm, 5126, len(room_nrm), "VEC3")
    a_floor = add_acc(bv_floor, 5125, len(idx_floor), "SCALAR")
    a_wall = add_acc(bv_wall, 5125, len(idx_wall), "SCALAR")

    a_face_pos = add_acc(bv_face_pos, 5126, len(logo_face_pos), "VEC3",
                         ([min(v[k] for v in logo_face_pos) for k in range(3)],
                          [max(v[k] for v in logo_face_pos) for k in range(3)]))
    a_face_nrm = add_acc(bv_face_nrm, 5126, len(logo_face_nrm), "VEC3")
    a_face_uv = add_acc(bv_face_uv, 5126, len(logo_face_uv), "VEC2")
    a_face_idx = add_acc(bv_face_idx, 5125, len(idx_logo_face), "SCALAR")

    a_rim_pos = add_acc(bv_rim_pos, 5126, len(logo_rim_pos), "VEC3",
                        ([min(v[k] for v in logo_rim_pos) for k in range(3)],
                         [max(v[k] for v in logo_rim_pos) for k in range(3)]))
    a_rim_nrm = add_acc(bv_rim_nrm, 5126, len(logo_rim_pos), "VEC3")
    a_rim_idx = add_acc(bv_rim_idx, 5125, len(idx_logo_rim), "SCALAR")

    # --- 이미지 · 샘플러 · 텍스처 — GLB 에 바이트를 담지 않고 상대경로로만 가리킨다 ---
    gltf.setdefault("images", []).append({"uri": LOGO_IMAGE_REL_URI})
    img_i = len(gltf["images"]) - 1
    gltf.setdefault("samplers", []).append({
        "magFilter": 9729, "minFilter": 9987,   # LINEAR / LINEAR_MIPMAP_LINEAR
        "wrapS": 33071, "wrapT": 33071,          # CLAMP_TO_EDGE
    })
    smp_i = len(gltf["samplers"]) - 1
    gltf.setdefault("textures", []).append({"sampler": smp_i, "source": img_i})
    tex_i = len(gltf["textures"]) - 1

    def material(name, color, rough=0.9, texture=None, alpha_blend=False):
        pbr = {"baseColorFactor": color, "metallicFactor": 0.0, "roughnessFactor": rough}
        if texture is not None:
            pbr["baseColorTexture"] = {"index": texture}
        gltf["materials"].append({
            "name": name, "pbrMetallicRoughness": pbr,
            "emissiveFactor": [0.0, 0.0, 0.0],
            "alphaMode": "BLEND" if alpha_blend else "OPAQUE",
            "doubleSided": False,
        })
        return len(gltf["materials"]) - 1

    mat_floor = material("SceneFloor", FLOOR_COLOR)
    mat_wall = material("SceneWall", WALL_COLOR)
    mat_logo_face = material("SceneLogoFace", [1.0, 1.0, 1.0, 1.0], rough=0.35,
                              texture=tex_i, alpha_blend=True)
    mat_logo_rim = material("SceneLogoRim", LOGO_RIM_COLOR, rough=0.6)

    gltf["meshes"].append({"name": NODE_NAME, "primitives": [
        {"attributes": {"POSITION": a_room_pos, "NORMAL": a_room_nrm},
         "indices": a_floor, "material": mat_floor},
        {"attributes": {"POSITION": a_room_pos, "NORMAL": a_room_nrm},
         "indices": a_wall, "material": mat_wall},
        {"attributes": {"POSITION": a_face_pos, "NORMAL": a_face_nrm, "TEXCOORD_0": a_face_uv},
         "indices": a_face_idx, "material": mat_logo_face},
        {"attributes": {"POSITION": a_rim_pos, "NORMAL": a_rim_nrm},
         "indices": a_rim_idx, "material": mat_logo_rim},
    ]})
    mesh_i = len(gltf["meshes"]) - 1

    gltf["nodes"].append({"name": NODE_NAME, "mesh": mesh_i})
    node_i = len(gltf["nodes"]) - 1
    gltf["scenes"][gltf["scene"]]["nodes"].append(node_i)

    gltf["buffers"][0]["byteLength"] = len(bin_data)

    out = pack(version, gltf, bin_data)
    args.model.write_bytes(out)

    _, again, _ = unpack(args.model.read_bytes())
    assert any(n.get("name") == NODE_NAME for n in again["nodes"]), "노드가 없다"
    assert len(again.get("animations", [])) == len(gltf.get("animations", [])), "클립 수가 달라졌다"
    assert again["buffers"][0]["byteLength"] == len(bin_data), "buffer 길이가 안 맞는다"
    room = next(m for m in again["meshes"] if m.get("name") == NODE_NAME)
    assert len(room["primitives"]) == 4, "프리미티브가 4개가 아니다"
    assert again["images"][img_i]["uri"] == LOGO_IMAGE_REL_URI, "이미지 참조가 안 맞는다"
    print("\n수정 완료 · %s B -> %s B · 노드 %d개 · 클립 %d개 유지 · 프리미티브 4개 · 재파싱 OK"
          % (format(len(raw), ","), format(len(out), ","),
             len(again["nodes"]), len(again["animations"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
