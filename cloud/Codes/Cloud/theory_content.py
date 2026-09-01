"""이론 교육 자료 로더 — content/theory/*.md (frontmatter + 본문)를 목록·본문 HTML 로 만든다.

자료 추가 = 이 폴더에 .md 파일 하나를 떨어뜨리는 것. main.py 의 하드코딩 목록
(THEORY_MATERIALS)을 대신한다 — quiz.json 이 "파일만 갈아끼우면 되도록" 한 것과 같은
철학의, 더 분산된 형태(목록 관리 파일조차 없음. 파일 자체가 목록의 원천).

렌더 분담
  서버(여기)  md → HTML. 이미지·표·인라인 <svg> 는 그대로 통과시킨다.
  브라우저    ```mermaid 블록만 그린다 — 다이어그램 그리기는 브라우저 전용이라
              여기서는 <div class="mermaid"> 로 뽑아만 두고, mermaid.min.js 가 그린다
              (static/js/theory-mermaid.js). model-viewer 를 브라우저에 맡긴 것과 같은 이유.

페이지 분할
  한 자료를 통째로 스크롤하지 않고 소제목(h1/h2) 단위로 끊어 한 화면씩 넘겨 본다
  (split_pages). load_material 은 요청한 페이지 하나만 변환해 돌려주므로, 이동은
  ?doc=…&page=N 주소 이동으로 이뤄진다 — mermaid 가 '보이는 요소'에서만 제대로
  그려지기 때문에, 감춰 두고 JS 로 갈아 끼우는 방식은 쓰지 않는다.

제외 규칙
  영상(mp4 등)을 참조하는 자료는 목록·본문 모두에서 빠진다 (has_video).

frontmatter 규약 (각 .md 상단)
  ---
  title: CAN 통신 기초      # 좌측 목록·뷰어 헤더 표기 (없으면 파일명 slug)
  difficulty: 기초          # 기초 | 기본 | 심화 (없으면 배지 생략)
  order: 10                # 같은 난이도 안에서의 정렬 키 (없으면 맨 뒤)
  ---
  # 본문 markdown...
"""
from pathlib import Path
import html
import re

import markdown

# 자료 루트. 서버가 도는 경로(BASE_DIR) 아래 content/theory 에 둔다.
CONTENT_DIR = Path(__file__).resolve().parent / "content" / "theory"

# md 안의 상대 자산 참조(assets/foo.png)를 이 절대 URL 로 바꾼다. main.py 가 content 폴더를
# /content 로 마운트하므로 실제 파일은 /content/theory/assets/foo.png 로 서빙된다.
ASSET_URL_BASE = "/content/theory/"

# 난이도 정렬 순위. 목록은 (난이도 순위 → order → 제목) 으로 정렬한다.
DIFFICULTY_RANK = {"기초": 0, "기본": 1, "심화": 2}

# 상단 `--- ... ---` frontmatter 블록과 본문을 가르는 정규식 (parse_frontmatter 에서 사용).
_FM_RE = re.compile(r"^---[ \t]*\n(.*?)\n---[ \t]*\n?(.*)$", re.DOTALL)

# 페이지를 가르는 소제목. 기본은 `# `/`## ` (h1·h2) 이고, 자료에 따라 `### ` 까지
# 내려간다 (split_pages 주석). 뒤따르는 `#` 는 닫는 표기(`## 제목 ##`)라 떼어낸다.
_HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")

# 코드펜스 여닫이. 펜스 **안**의 `#` 는 주석이지 소제목이 아니므로 나누면 안 된다.
_FENCE_RE = re.compile(r"^[ \t]*(```|~~~)")

# 페이지가 이만큼도 안 나오면 한 단계 더 깊은 소제목까지 내려가 다시 나눈다 (split_pages).
_MIN_PAGES = 3
# 내려갈 수 있는 가장 깊은 소제목 레벨. h5·h6 는 절 제목으로 쓰이지 않는다고 본다.
_MAX_SPLIT_LEVEL = 4

# 영상이 걸린 자료는 이론 교육 목록에서 제외한다 — 오프라인·태블릿 환경에서 재생을
# 보장할 수 없어 학습 흐름이 끊긴다. md 안의 파일 참조(.mp4 …)와 <video> 둘 다 본다.
_VIDEO_RE = re.compile(r"<video\b|\.(?:mp4|m4v|webm|mov|avi|mkv)\b", re.IGNORECASE)

# ```mermaid 코드펜스. 변환 전에 본문에서 들어내 화살표(-->)·괄호가 마크다운에 훼손되지
# 않게 한다(MULTILINE: ^$ 가 줄 단위, DOTALL: . 가 개행 포함).
_MERMAID_RE = re.compile(r"^```mermaid[ \t]*\n(.*?)\n```[ \t]*$", re.MULTILINE | re.DOTALL)

# 재사용 변환기. reset() 으로 문서 간 상태(각주·toc 등)를 비우고 재사용한다.
_MD = markdown.Markdown(
    extensions=["fenced_code", "tables", "attr_list", "sane_lists", "toc"],
    output_format="html5",
)


def parse_frontmatter(text):
    """md 원문에서 상단 `--- ... ---` frontmatter 를 떼어 (meta: dict, body: str) 로 나눈다.

    meta 는 평면 매핑이다 — title / difficulty 는 문자열, order 는 정수. frontmatter 가
    아예 없으면 meta={} 이고 body 는 원문 그대로여야 한다(뒤의 로더가 기본값으로 메운다).

    참고: 위 _FM_RE 로 `---` 블록과 본문을 한 번에 가를 수 있다(그룹1=블록, 그룹2=본문).
    블록 안은 `key: value` 가 한 줄씩. 되도록 관대하게 — 빈 줄·모르는 키는 흘려보내고,
    order 처럼 숫자로 써야 할 값이 숫자가 아니면 정렬이 깨지지 않게 방어한다.
    """
    match = _FM_RE.match(text)
    if not match:                       # frontmatter 없음 — 원문 그대로 본문
        return {}, text
    meta = {}
    for line in match.group(1).splitlines():
        if ":" not in line:             # 빈 줄·구분 불가한 줄은 흘려보낸다
            continue
        key, value = line.split(":", 1)  # 첫 콜론만 기준 — 값 안의 콜론은 보존
        meta[key.strip()] = value.strip()
    if "order" in meta:                 # 정렬 키는 정수여야 한다 — 아니면 맨 뒤로
        try:
            meta["order"] = int(meta["order"])
        except ValueError:
            meta["order"] = 10_000
    return meta, match.group(2)


def _slug(path):
    """파일명(확장자 제외)을 자료 id 로 쓴다 — URL ?doc= 값이자 좌측 목록 키."""
    return path.stem


def _extract_mermaid(md_text):
    """```mermaid 블록을 빼내고 자리표시자 문단으로 치환. (치환된_텍스트, [raw블록…]) 반환.

    자리표시자는 앞뒤 빈 줄을 둘러 그 자체로 한 문단이 되게 한다. 변환 뒤 `<p>…</p>` 로
    감싸이는데, _restore_mermaid 가 그 문단을 통째로 <div class="mermaid"> 로 되돌린다.
    """
    blocks = []

    def stash(match):
        blocks.append(match.group(1))
        return f"\n\nMERMAIDSLOT{len(blocks) - 1}ENDSLOT\n\n"

    return _MERMAID_RE.sub(stash, md_text), blocks


def _restore_mermaid(html_text, blocks):
    """자리표시자 문단을 mermaid div 로 되돌린다.

    raw 다이어그램 텍스트는 escape 해 넣는다 — HTML 을 깨지 않으면서도, 브라우저가 요소의
    textContent 를 읽을 때 엔티티를 자동 복원하므로 mermaid 는 원문 그대로를 받는다.
    """
    for i, raw in enumerate(blocks):
        html_text = html_text.replace(
            f"<p>MERMAIDSLOT{i}ENDSLOT</p>",
            f'<div class="mermaid">{html.escape(raw)}</div>',
        )
    return html_text


def _rewrite_assets(html_text, base_url=ASSET_URL_BASE):
    """md 의 상대 자산 참조(src/href="assets/…" · "./assets/…")를 마운트 절대경로로 바꾼다.

    base_url 은 그 md 가 놓인 폴더의 마운트 URL — 하위 폴더(그룹)에 있는 자료는
    자산도 그 폴더 아래(assets/…)에 있으므로, 폴더 경로를 접두로 붙여야 한다.
    """
    return re.sub(
        r'(src|href)="\.?/?assets/',
        rf'\1="{base_url}assets/',
        html_text,
    )


def render_markdown(md_text, base_url=ASSET_URL_BASE):
    """본문 md → 뷰어에 넣을 안전한 HTML. mermaid 추출·복원과 자산 경로 재작성을 포함."""
    stripped, blocks = _extract_mermaid(md_text)
    _MD.reset()
    body = _MD.convert(stripped)
    body = _restore_mermaid(body, blocks)
    return _rewrite_assets(body, base_url)


def has_video(md_text):
    """자료 본문이 영상(mp4 등)을 참조하는가. True 면 이론 교육에서 제외한다."""
    return bool(_VIDEO_RE.search(md_text))


def split_pages(md_body):
    """본문 md 를 소제목 단위 '페이지'로 나눈다.

    한 자료를 통째로 스크롤하는 대신, 소제목마다 한 화면씩 넘겨 보게 하기 위한 분할이다
    (templates/theory.html 의 이전·다음 버튼). 기본으로 나누는 자리는 h1 과 h2 다 —
    그보다 아래는 그 소제목에 딸린 내용이므로 같은 페이지에 남는다.

        # (1) 컴퓨터가 정보를 다루는 방식   → 1페이지 (첫 h2 직전까지)
        ## 1.1 왜 0과 1만 쓰는가            → 2페이지 (### 하위 항목들을 품은 채로)
        ## 1.2 비트와 바이트                → 3페이지

    다만 자료마다 절 제목의 깊이가 다르다. 어떤 심화 자료는 h2 를 문서 제목 되풀이에만
    쓰고 실제 절은 h3(`### 4.1 …`)나 h4 로 적는다 — 그런 자료를 h2 로만 나누면 한두
    페이지에 모든 내용이 몰린다. 그래서 h2 로 나눠 보고 페이지가 _MIN_PAGES 도 안 되면
    한 단계씩(_MAX_SPLIT_LEVEL 까지) 더 깊이 내려가며 다시 나눈다. 결과가 충분히
    나뉘는 순간 멈추므로, 위 예처럼 h2 로 잘 나뉘는 자료는 h3 로 더 쪼개지지 않는다.

    코드펜스(``` / ~~~) 안의 `#` 는 주석이지 소제목이 아니므로 세지 않는다.
    첫 소제목보다 앞에 오는 글은 첫 페이지에 붙는다. 소제목이 하나도 없으면 1페이지다.

    반환: [{"title": 소제목 텍스트, "md": 그 페이지의 md 원문}, …] (최소 1개)
    """
    pages = []
    for level in range(2, _MAX_SPLIT_LEVEL + 1):
        deeper = _split_at(md_body, level)
        if len(deeper) > len(pages):
            pages = deeper
        if len(pages) >= _MIN_PAGES:
            break
    return pages or [{"title": "", "md": md_body}]


def _iter_headings(md_body):
    """(레벨, 제목, 원문줄) 을 훑는다. 코드펜스 안은 건너뛴다.

    소제목이 아닌 줄은 (0, "", 줄) 로 흘려보낸다 — 호출부가 본문을 그대로 다시 쌓을 수
    있게 하기 위해서다(원문 손실 없이 자르기).
    """
    fence = None                       # 열려 있는 펜스 토큰 (``` 또는 ~~~)
    for line in md_body.splitlines():
        hit = _FENCE_RE.match(line)
        if hit:
            token = hit.group(1)
            # 여는 펜스와 같은 종류일 때만 닫는다 — ``` 안의 ~~~ 는 그냥 글자다.
            fence = token if fence is None else (None if token == fence else fence)
        elif fence is None:
            heading = _HEADING_RE.match(line)
            if heading:
                yield len(heading.group(1)), heading.group(2).strip(), line
                continue
        yield 0, "", line


def _split_at(md_body, max_level):
    """레벨 max_level 이하의 소제목마다 잘라 페이지 목록을 만든다."""
    pages = []
    title, buf = "", []

    def flush():
        if "".join(buf).strip():
            pages.append({"title": title, "md": "\n".join(buf)})

    for level, text, line in _iter_headings(md_body):
        if level and level <= max_level:
            flush()
            title, buf = text, [line]
            continue
        buf.append(line)

    flush()
    return pages


def _iter_material_files():
    """content/theory 아래 모든 .md 를 훑는다(assets 폴더는 제외). 하위 폴더까지 재귀.

    각 항목은 (path, rel_dir): rel_dir 은 CONTENT_DIR 기준 부모 폴더의 posix 경로
    (루트 직속이면 ""). id·자산 URL 산출에 쓴다.
    """
    if not CONTENT_DIR.is_dir():
        return
    for path in sorted(CONTENT_DIR.rglob("*.md")):
        rel = path.relative_to(CONTENT_DIR)
        if "assets" in rel.parts:                 # 자산 폴더 안 md 는 자료가 아니다
            continue
        rel_dir = rel.parent.as_posix()
        rel_dir = "" if rel_dir == "." else rel_dir
        yield path, rel_dir


def _material_id(path):
    """자료 id = CONTENT_DIR 기준 상대경로(확장자 제외, posix). URL ?doc= 값이 된다."""
    return path.relative_to(CONTENT_DIR).with_suffix("").as_posix()


def load_materials():
    """content/theory 를 재귀 스캔해 '큰 주제(그룹) ▸ 소제목' 트리를 만든다(본문 제외).

    그룹 = 하위 폴더(frontmatter group). 루트 직속 md 는 그룹 없이 '기타'로 묶는다.
    정렬: 그룹(group_order → 난이도 → 제목), 그룹 안(order → 제목).
    반환: [{"id","title","difficulty","order","items":[{"id","title","difficulty","order"}]}]
    """
    groups = {}
    for path, rel_dir in _iter_material_files():
        raw = path.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(raw)
        if has_video(body):          # 영상 자료는 목록에 올리지 않는다
            continue
        doc_id = _material_id(path)
        item = {
            "id": doc_id,
            "title": meta.get("title") or path.stem,
            "difficulty": meta.get("difficulty", ""),
            "order": meta.get("order", 10_000),
        }
        gtitle = meta.get("group", "")
        if gtitle:
            # 같은 [n]·같은 제목이라도 난이도(기초/심화)가 다르면 별개 그룹이다
            # (예: 'CAN 통신 (기초)' vs 'CAN 통신 (심화)' — group·group_order 가 같다).
            gorder = _as_int(meta.get("group_order"), 9_998)
            gdiff = item["difficulty"]
            gkey = f"{gorder:04d}|{gdiff}|{gtitle}"
        else:
            # 루트 직속 md(구 자료)는 그룹 없이 '기타'로 묶는다.
            gkey, gtitle, gorder, gdiff = "__misc__", "기타", 9_999, ""
        g = groups.get(gkey)
        if g is None:
            g = groups[gkey] = {
                "id": gkey, "title": gtitle, "difficulty": gdiff,
                "order": gorder, "docs": [],
            }
        g["docs"].append(item)

    out = []
    for g in groups.values():
        g["docs"].sort(key=lambda m: (m["order"], m["title"]))
        out.append(g)
    out.sort(key=lambda g: (g["order"], DIFFICULTY_RANK.get(g["difficulty"], 99), g["title"]))
    return out


def first_material_id(groups):
    """그룹 트리에서 가장 먼저 오는 자료 id (없으면 None). 선택 폴백용."""
    for g in groups:
        if g["docs"]:
            return g["docs"][0]["id"]
    return None


def _as_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def load_material(doc_id, page=1):
    """단일 자료의 **한 페이지**: 메타 + 그 페이지 본문 HTML + 페이지 위치.

    doc_id 는 CONTENT_DIR 기준 상대경로(하위 폴더 포함). 경로 이탈(..)은 막는다.
    해당 .md 가 없거나 영상 자료면 None.

    page 는 1기반이고 범위를 벗어나면 가장 가까운 쪽으로 당긴다 — 주소창을 손으로
    고쳐 들어와도 빈 화면이 나오지 않게. 본문 변환은 그 페이지 몫만 하므로,
    mermaid·이미지도 보이는 페이지의 것만 그려진다.
    """
    if not doc_id:
        return None
    path = (CONTENT_DIR / f"{doc_id}.md").resolve()
    root = CONTENT_DIR.resolve()
    if root not in path.parents or not path.is_file():
        return None
    meta, body = parse_frontmatter(path.read_text(encoding="utf-8"))
    if has_video(body):
        return None
    rel_dir = path.parent.relative_to(root).as_posix()
    base_url = ASSET_URL_BASE + ("" if rel_dir == "." else rel_dir + "/")

    pages = split_pages(body)
    total = len(pages)
    idx = min(max(_as_int(page, 1), 1), total)
    current = pages[idx - 1]

    return {
        "id": doc_id,
        "title": meta.get("title") or path.stem,
        "difficulty": meta.get("difficulty", ""),
        "html": render_markdown(current["md"], base_url),
        # 페이지 이동 UI 가 쓰는 값들 (templates/theory.html).
        "page": idx,
        "page_total": total,
        "page_title": current["title"],
        "prev_page": idx - 1 if idx > 1 else None,
        "next_page": idx + 1 if idx < total else None,
        "page_titles": [p["title"] for p in pages],
    }
