"""선화 PNG → UI 아이콘(static/img/icons/*.png) 변환기.

왜 있는가
    새로 받은 아이콘은 흰 바탕에 검은 선이 그려진 1254x1254 PNG 다. 이 앱의 아이콘은
    모두 인라인 SVG 라 `currentColor` 를 물려받는다 — 파란 타일 위에서는 흰 선,
    흰 카드 위에서는 남색 선으로 **같은 파일이 다른 색**으로 그려진다. 받은 PNG 를
    그대로 넣으면 흰 사각형이 뜨고 색도 고정된다.

    그래서 그림을 '알파 마스크' 로 바꾼다. 흰 바탕은 투명으로 되돌리고, 선은 알파에만
    남긴다. 화면에서는 CSS `mask-image` 로 찍어 색을 `currentColor` 가 채운다 —
    결과적으로 기존 SVG 아이콘과 똑같이 문맥에 따라 색이 따라온다(styles.css .icon--art).

    선 굵기도 맞춘다. 받은 6장은 굵기가 제각각이라(ECU 는 두껍고 차량은 가늘다) 나란히
    놓으면 무게가 어긋나 보인다. 기존 SVG 들의 규칙 — 아이콘 상자의 5%(viewBox 48 에
    stroke-width 2.4) — 를 목표로 삼아, 선이 굵으면 깎고 가늘면 불려 통일한다.

무엇을 하는가
    1) 회색조 → 알파. 바탕 밝기를 0, 가장 짙은 선을 255 로 늘여 경계의 안티에일리어싱을
       그대로 살린다(이진화하면 계단이 진다).
    2) 선 굵기 측정. 거리 변환의 평균을 쓴다 — 굵기 w 인 선의 거리값 평균은 w/4 다.
    3) 굵기 보정. 목표보다 가늘면 팽창(MaxFilter), 굵으면 침식(MinFilter). 알파 위에서
       하므로 안티에일리어싱이 유지된다.
    4) 선이 그려진 영역만 잘라 정사각 캔버스 가운데에 여백을 두고 앉히고, 최종 크기로
       줄인다. 잘라내기 덕분에 원본마다 다른 여백이 사라져 타일에서 크기가 고르게 보인다.

사용
    pip install -r tools/requirements.txt
    python tools/make_icon_art.py                        # 기본 원본 폴더 → static/img/icons
    python tools/make_icon_art.py --src <폴더> --list     # 변환 없이 측정값만 출력
"""
from __future__ import annotations

import argparse
import sys
import unicodedata
from pathlib import Path

from PIL import Image, ImageFilter

BASE_DIR = Path(__file__).resolve().parent.parent
OUT_DIR = BASE_DIR / "static" / "img" / "icons"
# 원본은 리포 루트 바깥의 작업 폴더에 있다(변환 결과만 리포에 들어간다).
DEFAULT_SRC = BASE_DIR.parents[2] / "새롭게 적용할 아이콘과 사운드"

# 원본 파일명 → 내보낼 아이콘 이름. 이름은 화면이 부르는 이름(main.py 의 icon 값)과
# 맞춘다 — 템플릿 icon_any() 가 이 이름으로 그림과 SVG 중 하나를 고른다.
#
# 이름 뒤에 -car/-cycle 을 붙인 것은 templates/icons 의 같은 이름 SVG 와 겹치지 않게
# 하기 위해서다. 겹치면 그림이 SVG 를 가려, UR 로봇 화면에서 자동차 그림을 피해 SVG 로
# 되돌릴 길이 없어진다(main._CAR_ICON_ALT).
#
# stroke 를 따로 적은 것은 예외다. 기본값(5%)은 선이 몇 개 없는 납작한 기호에 맞춘
# 굵기라, 차량 일러스트처럼 선이 촘촘한 그림에 그대로 적용하면 선끼리 붙어 검은
# 덩어리가 된다. 그런 그림은 굵기를 낮추고 대신 크게 내보내 해상도로 버틴다.
NAMES = [
    {"src": "이론교육 아이콘", "name": "theory"},
    {"src": "실습 준비 아이콘", "name": "prep-car"},
    {"src": "진단 아이콘", "name": "diag-car"},
    {"src": "강제구동 아이콘", "name": "force-car"},
    {"src": "ECU 업그레이드 아이콘", "name": "ecu-cycle"},
    {"src": "진단모사차량 아이콘", "name": "rc-car", "stroke": 0.013, "size": 384,
     "square": False},
]

SIZE = 256            # 내보낼 정사각 크기(px). 화면 표시는 60~84px 라 2~4배 여유.
MARGIN = 0.06         # 캔버스 대비 상하좌우 여백 비율
STROKE_RATIO = 0.05   # 선 굵기 / 캔버스 — 기존 SVG 규칙(viewBox 48 · stroke-width 2.4)
MAX_DT = 60           # 거리 변환 반복 상한(원본 해상도 기준 안전장치)
# 바탕으로 볼 밝기 폭(0~1). 받은 그림의 흰 바탕은 고르지 않아서(종이 질감·JPEG 흔적으로
# 240~255 사이를 오간다) 가장 밝은 값만 0 으로 눕히면 나머지가 알파 1~30 짜리 옅은
# 안개로 남는다. 눈에는 선으로 안 보여도 상자 전체가 아주 옅게 칠해져 **타일 바탕과
# 미묘하게 다른 사각형**이 드러난다. 이 폭 아래는 전부 완전한 투명으로 눌러 없앤다.
NOISE_FLOOR = 0.18


def to_alpha(img, floor=NOISE_FLOOR):
    """흰 바탕 선화 → 알파(선=255, 바탕=0). 안티에일리어싱을 살려 늘인다.

    바탕 얼룩은 floor 아래로 깔고 잘라 낸다 — 자르지 않으면 상자 전체에 옅은 안개가
    남아 타일 바탕과 다른 사각형으로 보인다(NOISE_FLOOR). 자른 뒤 남은 구간을 다시
    0~255 로 펴서, 선 가장자리의 부드러운 계조는 그대로 둔다.
    """
    g = img.convert("L")
    lo, hi = g.getextrema()          # lo=가장 짙은 선, hi=바탕
    if hi <= lo:
        raise ValueError("단색 이미지입니다 — 선을 찾을 수 없습니다")
    cut = floor * (hi - lo)          # 바탕으로 칠 밝기 폭(원본 눈금)
    span = (hi - lo) - cut
    # 바탕(hi)을 0, 선(lo)을 255 로. 바탕이 완전한 흰색이 아니어도(247 등) 맞춰진다.
    return g.point(lambda v: min(255, max(0, int(round((hi - v - cut) * 255.0 / span)))))


def stroke_width(alpha, thresh=128):
    """선 굵기(px) 추정. 거리 변환 평균 × 4 — 굵기 w 인 띠의 평균 거리값이 w/4 다."""
    b = alpha.point(lambda v: 255 if v >= thresh else 0)
    ink = sum(b.histogram()[1:])
    if not ink:
        return 0.0
    total = ink                      # k=0 (자기 자신) 몫
    cur = b
    for _ in range(MAX_DT):
        cur = cur.filter(ImageFilter.MinFilter(3))   # 3x3 침식
        n = sum(cur.histogram()[1:])
        if not n:
            break
        total += n
    return 4.0 * total / ink


def resize_stroke(alpha, delta_px):
    """선을 delta_px 만큼 굵게(+)/가늘게(-) 한다. 알파 위 형태 연산이라 경계가 살아 있다."""
    r = int(round(abs(delta_px) / 2.0))   # 반경 r 이면 굵기는 2r 만큼 변한다
    if r < 1:
        return alpha
    f = ImageFilter.MaxFilter if delta_px > 0 else ImageFilter.MinFilter
    out = alpha
    # MaxFilter/MinFilter 는 커널이 홀수 크기여야 한다. 큰 반경은 3x3 을 반복해 만든다
    # (한 번에 큰 커널을 쓰는 것보다 느리지만 모서리가 덜 뭉개진다).
    for _ in range(r):
        out = out.filter(f(3))
    return out


def fit_canvas(alpha, size, margin, square=True):
    """선이 있는 영역만 잘라 캔버스 가운데에 여백을 두고 앉힌다.

    square=False 는 가로로 긴 그림(차량처럼)을 위한 것이다. 정사각으로 맞추면 위아래가
    죄다 빈 여백이 되는데, CSS 가 이 그림을 contain 으로 담을 때 그 여백까지 함께
    담아 버려 실제 그림은 상자보다 한참 작게 나온다. 여백을 남기지 않으면 상자 크기가
    곧 그림 크기가 된다.
    """
    box = alpha.point(lambda v: 255 if v >= 24 else 0).getbbox()
    if box:
        alpha = alpha.crop(box)
    inner = int(round(size * (1 - 2 * margin)))
    w, h = alpha.size
    s = min(inner / w, inner / h)
    alpha = alpha.resize((max(1, int(round(w * s))), max(1, int(round(h * s)))),
                         Image.LANCZOS)
    pad = int(round(size * margin))
    cw, ch = (size, size) if square else (alpha.size[0] + 2 * pad, alpha.size[1] + 2 * pad)
    canvas = Image.new("L", (cw, ch), 0)
    canvas.paste(alpha, ((cw - alpha.size[0]) // 2, (ch - alpha.size[1]) // 2))
    return canvas


def convert(src_path, out_path, report, size=SIZE, stroke=STROKE_RATIO, square=True):
    img = Image.open(src_path)
    alpha = to_alpha(img)

    # 굵기 보정은 **최종 크기로 줄이기 전** 원본 해상도에서 한다 — 픽셀이 많을수록
    # 형태 연산의 결과가 곱다. 그래서 목표 굵기도 원본 축척으로 환산해 둔다.
    box = alpha.point(lambda v: 255 if v >= 24 else 0).getbbox()
    content = max(box[2] - box[0], box[3] - box[1]) if box else alpha.size[0]
    scale = (size * (1 - 2 * MARGIN)) / content        # 원본 → 최종 축척
    now = stroke_width(alpha)
    target_src = (stroke * size) / scale
    alpha = resize_stroke(alpha, target_src - now)

    out_alpha = fit_canvas(alpha, size, MARGIN, square)
    out = Image.new("RGBA", out_alpha.size, (0, 0, 0, 0))
    out.putalpha(out_alpha)
    out.save(out_path, optimize=True)
    report.append((out_path.name, now * scale, stroke * size,
                   stroke_width(out.getchannel("A")), out_path.stat().st_size))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--src", type=Path, default=DEFAULT_SRC, help="원본 PNG 폴더")
    ap.add_argument("--out", type=Path, default=OUT_DIR, help="내보낼 폴더")
    ap.add_argument("--list", action="store_true", help="변환하지 않고 측정만")
    a = ap.parse_args(argv)

    if not a.src.is_dir():
        print(f"원본 폴더가 없습니다: {a.src}", file=sys.stderr)
        return 1
    a.out.mkdir(parents=True, exist_ok=True)

    # 한글 파일명은 자소 분리(NFD)로 들어오는 경우가 있어 정규화해 맞춘다.
    found = {unicodedata.normalize("NFC", p.stem): p for p in a.src.glob("*.png")}
    report = []
    for spec in NAMES:
        p = found.get(unicodedata.normalize("NFC", spec["src"]))
        if not p:
            print(f"! 원본을 찾지 못했습니다: {spec['src']}.png", file=sys.stderr)
            continue
        if a.list:
            alpha = to_alpha(Image.open(p))
            print(f"{spec['name']:8s} 굵기 {stroke_width(alpha):6.1f}px / {alpha.size[0]}px")
            continue
        convert(p, a.out / f"{spec['name']}.png", report,
                size=spec.get("size", SIZE), stroke=spec.get("stroke", STROKE_RATIO),
                square=spec.get("square", True))

    for name, before, target, after, size in report:
        print(f"{name:14s} 굵기 {before:5.1f} → {after:5.1f} (목표 {target:.1f}) "
              f"· {size // 1024}KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
