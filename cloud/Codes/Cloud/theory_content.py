"""이론 교육 자료 로더 — content/theory/*.md (frontmatter + 본문)를 목록·본문 HTML 로 만든다.

자료 추가 = 이 폴더에 .md 파일 하나를 떨어뜨리는 것. main.py 의 하드코딩 목록
(THEORY_MATERIALS)을 대신한다 — quiz.json 이 "파일만 갈아끼우면 되도록" 한 것과 같은
철학의, 더 분산된 형태(목록 관리 파일조차 없음. 파일 자체가 목록의 원천).

렌더 분담
  서버(여기)  md → HTML. 이미지·표·인라인 <svg> 는 그대로 통과시킨다.
  브라우저    ```mermaid 블록만 그린다 — 다이어그램 그리기는 브라우저 전용이라
              여기서는 <div class="mermaid"> 로 뽑아만 두고, mermaid.min.js 가 그린다
              (static/js/theory-mermaid.js). model-viewer 를 브라우저에 맡긴 것과 같은 이유.

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


def _rewrite_assets(html_text):
    """md 의 상대 자산 참조(src/href="assets/…" · "./assets/…")를 마운트 절대경로로 바꾼다."""
    return re.sub(
        r'(src|href)="\.?/?assets/',
        rf'\1="{ASSET_URL_BASE}assets/',
        html_text,
    )


def render_markdown(md_text):
    """본문 md → 뷰어에 넣을 안전한 HTML. mermaid 추출·복원과 자산 경로 재작성을 포함."""
    stripped, blocks = _extract_mermaid(md_text)
    _MD.reset()
    body = _MD.convert(stripped)
    body = _restore_mermaid(body, blocks)
    return _rewrite_assets(body)


def load_materials():
    """content/theory/*.md 를 스캔해 좌측 목록 메타를 만든다(본문 HTML 은 제외).

    정렬: 난이도(기초→기본→심화, 미지정은 맨 뒤) → order → 제목. 폴더가 없으면 빈 목록.
    """
    out = []
    if CONTENT_DIR.is_dir():
        for path in CONTENT_DIR.glob("*.md"):
            meta, _ = parse_frontmatter(path.read_text(encoding="utf-8"))
            out.append({
                "id": _slug(path),
                "title": meta.get("title") or _slug(path),
                "difficulty": meta.get("difficulty", ""),
                "order": meta.get("order", 10_000),
            })
    out.sort(key=lambda m: (DIFFICULTY_RANK.get(m["difficulty"], 99), m["order"], m["title"]))
    return out


def load_material(doc_id):
    """단일 자료: 목록 메타 + 본문 HTML. doc_id 에 해당하는 .md 가 없으면 None."""
    if not doc_id:
        return None
    path = CONTENT_DIR / f"{doc_id}.md"
    if not path.is_file():
        return None
    meta, body = parse_frontmatter(path.read_text(encoding="utf-8"))
    return {
        "id": doc_id,
        "title": meta.get("title") or doc_id,
        "difficulty": meta.get("difficulty", ""),
        "html": render_markdown(body),
    }
