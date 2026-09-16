"""UR_Robot.glb 에 배경 공간(광택 바닥 + 코브(둥근 이음)로 이어지는 벽 + 입체
GIT 로고 간판)을 붙인다.

왜 필요한가
    화면의 정비소 배경(static/js/view3d-bg.js 의 .view3d__scene)은 CSS 로 그린
    평평한 2D 판이라 model-viewer 의 카메라(드래그 회전)와 무관하게 화면에
    고정돼 있다. 로봇을 돌려 보면 배경은 그대로고 모델만 도는 부자연스러움이
    드러난다. 바닥·벽·로고를 GLB 안에 실제 geometry 로 넣으면 카메라가 도는 대로
    같이 돌아 진짜 3D 공간처럼 보인다 — 책상(add_ur3_desk.py)과 같은 원리다.

    바닥과 벽은 사진관 무한배경(cyclorama)처럼 둥글게 이어 붙인다(--cove-radius).
    두 평면이 직각으로 만나면 그 모서리 선이 또렷하게 보여 '작은 무대 위에 있다'
    는 인상을 준다 — 사용자가 요청한 "내가 그 공간에 들어가 있는 것처럼" 은 그
    이음매가 없어야 나온다. 바닥·벽 자체도 --floor-half·--wall-height 를 넉넉히
    키워, 카메라가 어느 방향을 봐도 가장자리가 시야 밖으로 벗어나게 했다.

    표면은 전부 매끈하게(낮은 roughness) 두어 광이 나는 느낌을 낸다 —
    environment-image="neutral"(_model3d.html) 의 반사가 낮은 roughness 에서
    뚜렷하게 드러난다.

    GIT 로고는 텍스트를 새로 그리지 않는다 — static/img/git-logo.png(실제 제공된
    파일)를 그대로 텍스처로 입힌 raised plaque(두께가 있는 판)로 만든다. 폰트로
    다시 그리면 실제 로고체(기울어진 획)와 달라지고, 이미지 윤곽을 벡터로 추적해
    직접 압출하는 것은 지나치게 복잡하다 — 판에 실제 이미지를 입히고 판 자체에
    두께를 줘 옆면이 보이게 하는 편이 브랜드를 그대로 지키면서도 입체감을 낸다.

    로고 PNG 는 투명 영역의 RGB 가 검정으로 박혀 있다(실측) — OPAQUE 로 그리면
    투명이어야 할 자리가 새까맣게 나온다. 그래서 로고 앞면만 alphaMode=BLEND 로
    그린다 — 알파 0 인 자리는 이미 그려진 벽(흰색)이 그대로 비쳐 보인다.

무엇을 하는가
    1) 바닥 — 책상 다리 밑면 높이에 맞춘 큰 사각 평면. 뒤쪽 --cove-radius 만큼은
       코브에 내준다(그만큼 짧다).
    2) 코브 — 바닥과 벽을 잇는 1/4 원통 곡면(--cove-segments 등분). 두 평면에
       접하도록 반지름을 잡아 이음매가 매끄럽다.
    3) 뒷벽 — 코브 위쪽 가장자리에서 --wall-height 까지 올라가는 평면.
    4) GIT 로고 — 벽 앞면에서 --logo-depth 만큼 튀어나온 판. 앞면엔 실제
       git-logo.png 를 텍스처로(alphaMode BLEND), 옆면(테두리 두께)엔 흰 무광을
       입힌다 — 카메라를 돌리면 이 옆면이 보여 '튀어나와 있다' 는 것이 읽힌다.
    노드는 전부 **씬 루트에 직접** 붙인다(UR3 아래가 아니다) — 베이스가 돌 때
    바닥·벽·로고는 가만히 있어야 한다(책상과 같은 이유).

    이미지는 GLB 안에 다시 담지 않는다 — static/models/ 기준 상대경로
    (../img/git-logo.png)로 참조해 static/img/git-logo.png 원본을 그대로 가리킨다.

    이미 'SceneRoom' 노드가 있으면 아무 것도 하지 않는다.

사용
    python add_scene_room.py --model <path-to-UR_Robot.glb>
    python add_scene_room.py --model <path> --dry-run
"""
from __future__ import annotations

import argparse
import json
import math
import struct
import sys
from pathlib import Path

from PIL import Image

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

JSON_CHUNK, BIN_CHUNK = 0x4E4F534A, 0x004E4942
NODE_NAME = "SceneRoom"

# 바닥·벽·코브 — 광택을 내려면 색만으로는 부족하고 재질의 roughness 를 낮춰야
# 한다(아래 material() 호출부의 rough= 인자). 색 자체는 책상보다 밝은 회색·흰색을
# 유지한다(배경이라 책상보다 더 물러나 보여야 한다).
FLOOR_COLOR = [0.694, 0.706, 0.725, 1.0]
COVE_COLOR = [0.82, 0.827, 0.84, 1.0]      # 바닥과 벽 사이 — 두 색의 중간 톤
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


def cove_strip(pos_list, nrm_list, idx_list, x0, x1, floor_y, wall_z, radius, segments):
    """바닥(Y=floor_y)과 벽(Z=wall_z) 을 잇는 1/4 원통 곡면 — 사진관 무한배경처럼
    이음매 없이 이어지게 한다.

    원의 중심은 (Y=floor_y+radius, Z=wall_z+radius) 에 둔다 — 그러면 각도 0 인
    점이 정확히 바닥의 안쪽 끝(Y=floor_y, Z=wall_z+radius)에서 바닥과 같은 접선
    (수평)을 갖고, 각도 90°인 점이 벽의 아래쪽 끝(Y=floor_y+radius, Z=wall_z)에서
    벽과 같은 접선(수직)을 갖는다 — 그래서 바닥·코브·벽 세 조각이 눈에 안 보이는
    이음매로 붙는다. 법선은 원의 중심을 향하는 안쪽 방향이다(오목한 곡면이라
    바닥의 +Y, 벽의 +Z 사이를 그대로 보간한다).
    """
    cy = floor_y + radius
    cz = wall_z + radius
    angles = [math.pi / 2 * i / segments for i in range(segments + 1)]
    rows = []
    for a in angles:
        y = cy - radius * math.cos(a)
        z = cz - radius * math.sin(a)
        ny, nz = math.cos(a), math.sin(a)
        rows.append((y, z, ny, nz))
    for i in range(segments):
        y0, z0, ny0, nz0 = rows[i]
        y1, z1, ny1, nz1 = rows[i + 1]
        # 각 구간을 사각형으로 — 앞뒤 행의 법선이 달라 정점을 두 번(사각형마다)
        # 새로 찍는다. 곡면이라 각도 구간이 좁으면(segments 를 늘리면) 사실상
        # 매끈해 보인다.
        quad(pos_list, nrm_list, idx_list, (0, (ny0 + ny1) / 2, (nz0 + nz1) / 2),
             [(x0, y0, z0), (x1, y0, z0), (x1, y1, z1), (x0, y1, z1)])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", type=Path, required=True)
    ap.add_argument("--floor-half", type=float, default=1.3, help="바닥 한 변의 절반")
    ap.add_argument("--floor-y", type=float, default=-0.202, help="바닥 높이(책상 다리 밑면)")
    ap.add_argument("--wall-z", type=float, default=-0.85, help="벽 위치(월드 Z, 코브 반영 전)")
    ap.add_argument("--wall-height", type=float, default=1.6)
    ap.add_argument("--cove-radius", type=float, default=0.35, help="바닥-벽 이음 곡면 반지름")
    ap.add_argument("--cove-segments", type=int, default=14)
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
    wz = args.wall_z                       # 벽의 평평한 부분 Z (코브가 시작되는 자리)
    r = args.cove_radius
    floor_back_z = wz + r                  # 바닥의 평평한 부분이 끝나는 자리(코브 시작)
    wall_base_y = fy + r                   # 벽의 평평한 부분이 시작되는 자리(코브 끝)
    wtop = fy + args.wall_height

    room_pos, room_nrm, idx_floor, idx_cove, idx_wall = [], [], [], [], []

    # 바닥 — 앞쪽(+fh, 카메라 쪽)에서 코브가 시작되는 자리(floor_back_z)까지만.
    quad(room_pos, room_nrm, idx_floor, [0, 1, 0],
         [(-fh, fy, fh), (fh, fy, fh), (fh, fy, floor_back_z), (-fh, fy, floor_back_z)])

    # 코브 — 바닥과 벽을 잇는 둥근 곡면.
    cove_strip(room_pos, room_nrm, idx_cove, -fh, fh, fy, wz, r, args.cove_segments)

    # 뒷벽 — 코브 위쪽 끝(wall_base_y)에서 wtop 까지.
    quad(room_pos, room_nrm, idx_wall, [0, 0, 1],
         [(-fh, wall_base_y, wz), (fh, wall_base_y, wz), (fh, wtop, wz), (-fh, wtop, wz)])

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

    if cy - hh <= wall_base_y + 0.02:
        print("경고: 로고 판이 코브 영역과 겹칠 수 있다 — --logo-y 를 올리거나 "
              "--cove-radius 를 줄이세요.")

    print("%s · 배경 공간 주입" % args.model.name)
    print("  바닥 %.2f x %.2f (평평한 구간, 코브 앞) Y=%+.3f" % (fh * 2, fh - floor_back_z, fy))
    print("  코브 반지름 %.2f · %d 등분  ·  벽 평평한 구간 Y=%.3f~%.3f" % (r, args.cove_segments, wall_base_y, wtop))
    print("  전체 폭 %.2f (좌우로 넉넉히 펼침)" % (fh * 2))
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
    cove_off = append(b"".join(struct.pack("<I", v) for v in idx_cove))
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
    bv_cove = add_bv(cove_off, len(idx_cove) * 4, 34963)
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
    a_cove = add_acc(bv_cove, 5125, len(idx_cove), "SCALAR")
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

    # roughness 를 낮게(0.12~0.2) 두어 광이 나는 느낌을 낸다 — 책상(0.9, 무광)과
    # 대비된다. 완전한 거울(0)은 아니다 — environment-image="neutral" 하나로만
    # 비추는 반사라 너무 낮추면 부자연스럽게 반짝인다.
    mat_floor = material("SceneFloor", FLOOR_COLOR, rough=0.15)
    mat_cove = material("SceneCove", COVE_COLOR, rough=0.15)
    mat_wall = material("SceneWall", WALL_COLOR, rough=0.18)
    mat_logo_face = material("SceneLogoFace", [1.0, 1.0, 1.0, 1.0], rough=0.3,
                              texture=tex_i, alpha_blend=True)
    mat_logo_rim = material("SceneLogoRim", LOGO_RIM_COLOR, rough=0.3)

    gltf["meshes"].append({"name": NODE_NAME, "primitives": [
        {"attributes": {"POSITION": a_room_pos, "NORMAL": a_room_nrm},
         "indices": a_floor, "material": mat_floor},
        {"attributes": {"POSITION": a_room_pos, "NORMAL": a_room_nrm},
         "indices": a_cove, "material": mat_cove},
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
    assert len(room["primitives"]) == 5, "프리미티브가 5개가 아니다"
    assert again["images"][img_i]["uri"] == LOGO_IMAGE_REL_URI, "이미지 참조가 안 맞는다"
    print("\n수정 완료 · %s B -> %s B · 노드 %d개 · 클립 %d개 유지 · 프리미티브 5개 · 재파싱 OK"
          % (format(len(raw), ","), format(len(out), ","),
             len(again["nodes"]), len(again["animations"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
