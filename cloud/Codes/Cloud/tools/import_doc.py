"""Confluence '.doc'(실은 MHTML) 내보내기 → 이론 교육 md + 이미지 로 변환하는 저작 도구.

배경
  사내 위키(Confluence)가 'Word .doc' 로 내보내지만 실체는 MHTML 이다 —
  multipart/related 안에 HTML 본문 한 개와 base64 로 박힌 이미지들이 함께 들어 있다.
  이 도구는 **Word 로 열지 않고** 파일 바이트를 직접 파싱한다. 그래서 더블클릭으로
  Word 에서 여는 동안 민감도 라벨이 붙어 '보안문서'가 되는 일이 없다.

  ⚠ 단, AIP/Purview 로 **암호화**된 파일은 평문이 아니라 이 도구로 열 수 없다. 그런
  파일은 사내 정식 절차(그룹웨어 문서해제센터)를 거쳐야 한다 — 이 도구는 복호화를
  하지 않는다. (Confluence 평문 내보내기는 암호화 대상이 아니라 그대로 변환된다.)

사용
  python tools/import_doc.py "<파일.doc>" [--id can-advanced] [--difficulty 심화] [--order 10] [--title "CAN 통신 심화"]

  --id/--title/--difficulty 를 안 주면 파일명에서 추론한다(파일명에 (기초|기본|심화)가
  있으면 난이도로 잡는다). 결과:
    content/theory/<id>.md                 frontmatter + 본문 markdown
    content/theory/assets/<id>/<이미지들>   문서에 내장돼 있던 그림
"""
import argparse
import email
import re
from email import policy
from pathlib import Path

from bs4 import BeautifulSoup
from markdownify import markdownify as html_to_md

THEORY_DIR = Path(__file__).resolve().parent.parent / "content" / "theory"
DIFFICULTIES = ("기초", "기본", "심화")


def _img_ext(data):
    """이미지 payload 의 매직 바이트로 확장자를 판별한다.

    Confluence MHTML 은 그림을 Content-Type application/octet-stream · 확장자 없는
    Content-Location(file:///C:/<해시>)으로 담는다 — 그래서 헤더가 아니라 내용으로
    형식을 알아내야 한다. 이미지가 아니면 None.
    """
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data[:2] == b"BM":
        return "bmp"
    head = data.lstrip()[:5].lower()
    if head[:4] == b"<svg" or head == b"<?xml":
        return "svg"
    return None


def derive_meta(path, args):
    """파일명에서 id·제목·난이도를 추론하고, CLI 인자가 있으면 그걸 우선한다.

    Confluence 파일명 예: '[1]+CAN+통신+(심화) (1) - 복사본.doc'
      → '+' 는 공백, 대괄호 번호·(난이도)·(1)·복사본·확장자는 떼어낸다.
    """
    raw = path.stem
    difficulty = args.difficulty or next((d for d in DIFFICULTIES if d in raw), "")
    name = raw.replace("+", " ")
    name = re.sub(r"^\s*\[\d+\]\s*", "", name)               # 앞머리 [1]
    name = re.sub(r"\((?:%s)\)" % "|".join(DIFFICULTIES), "", name)  # (심화)
    name = re.sub(r"\(\d+\)|복사본|-\s*복사본", "", name)     # (1) · 복사본
    title = args.title or re.sub(r"\s+", " ", name).strip()
    doc_id = args.id or _slugify(title)
    return doc_id, title, difficulty


def _slugify(title):
    """제목 → URL 안전한 소문자 슬러그. 한글은 남기되 공백·기호만 하이픈으로."""
    s = title.strip().lower()
    s = re.sub(r"[^\w가-힣]+", "-", s, flags=re.UNICODE).strip("-")
    return s or "doc"


def parse_mhtml(path):
    """MHTML(.doc) 을 (html: str, images: [bytes]) 로 가른다.

    이미지는 '파트 순서 그대로' 담는다 — Confluence 내보내기는 img src(서버 URL)와
    파트의 Content-Location(file:///C:/<해시>)이 서로 맞지 않아 이름으로는 못 잇는다.
    대신 본문의 N번째 <img> 가 N번째 이미지 파트에 대응한다(문서 순서 일치).
    """
    with path.open("rb") as fp:
        msg = email.message_from_binary_file(fp, policy=policy.default)
    html, images = None, []
    for part in msg.walk():
        ctype = part.get_content_type()
        if ctype == "text/html" and html is None:
            html = part.get_content()
        elif ctype.startswith("image/") or ctype == "application/octet-stream":
            data = part.get_payload(decode=True)
            if data and _img_ext(data):                       # 매직바이트로 진짜 이미지만
                images.append(data)
    if html is None:
        raise SystemExit(f"HTML 본문을 찾지 못했습니다(정상 MHTML 이 아님): {path.name}")
    return html, images


def save_images(images, doc_id):
    """이미지 파트들을 assets/<id>/ 에 순서대로 저장하고 상대경로 리스트(순서 유지)를 돌려준다."""
    if not images:
        return []
    asset_dir = THEORY_DIR / "assets" / doc_id
    asset_dir.mkdir(parents=True, exist_ok=True)
    rels = []
    for i, data in enumerate(images, start=1):
        fname = f"img{i:02d}.{_img_ext(data)}"
        (asset_dir / fname).write_bytes(data)
        rels.append(f"assets/{doc_id}/{fname}")
    return rels


def _promote_heading_images(soup):
    """제목(h1~h6) 안에 박힌 이미지를 제목 바로 뒤 문단으로 끌어낸다.

    Confluence 내보내기가 그림을 <h3> 안에 넣어버리는 경우가 있는데, 그대로 두면
    markdownify 가 제목을 '### 텍스트'로만 바꾸면서 텍스트 없는 이미지를 통째로 버린다.
    제목 뒤 문단으로 옮기면 그 자리(섹션 제목 아래)에 그대로 렌더된다.
    """
    for heading in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        imgs = heading.find_all("img")
        if not imgs:
            continue
        holder = soup.new_tag("p")
        for img in imgs:
            holder.append((img.find_parent("span") or img).extract())
        heading.insert_after(holder)
        if not heading.get_text(strip=True):              # 이미지뿐이던 빈 제목은 버린다
            heading.decompose()


def rewrite_and_extract(html, rels):
    """본문 노드를 골라, N번째 <img> 의 src 를 N번째 이미지 경로로 바꾼 HTML 을 돌려준다.

    Confluence 내보내기는 본문을 #main-content 에 담는다 — 있으면 그것만, 없으면 body.
    파트보다 <img> 가 많으면(짝 없는 UI 아이콘 등) 남는 것은 제거한다.
    """
    soup = BeautifulSoup(html, "html.parser")
    for i, img in enumerate(soup.find_all("img")):
        if i < len(rels):
            img["src"] = rels[i]
        else:
            img.decompose()
    _promote_heading_images(soup)
    node = soup.select_one("#main-content") or soup.body or soup
    return str(node)


def to_markdown(html):
    body = html_to_md(html, heading_style="ATX", strong_em_symbol="*", bullets="-")
    return re.sub(r"\n{3,}", "\n\n", body).strip() + "\n"     # 빈 줄 3개 이상 → 2개


def main():
    ap = argparse.ArgumentParser(description="Confluence .doc(MHTML) → 이론 교육 md")
    ap.add_argument("file", help=".doc(MHTML) 파일 경로")
    ap.add_argument("--id", help="문서 id(=URL 슬러그, 파일명). 미지정 시 제목에서 생성")
    ap.add_argument("--title", help="frontmatter 제목. 미지정 시 파일명에서 추론")
    ap.add_argument("--difficulty", choices=DIFFICULTIES, help="난이도. 미지정 시 파일명에서 추론")
    ap.add_argument("--order", type=int, default=10, help="같은 난이도 안 정렬 키(기본 10)")
    args = ap.parse_args()

    path = Path(args.file)
    if not path.is_file():
        raise SystemExit(f"파일이 없습니다: {path}")

    doc_id, title, difficulty = derive_meta(path, args)
    html, images = parse_mhtml(path)
    rels = save_images(images, doc_id)
    body = to_markdown(rewrite_and_extract(html, rels))

    fm = [f"title: {title}"]
    if difficulty:
        fm.append(f"difficulty: {difficulty}")
    fm.append(f"order: {args.order}")
    out = THEORY_DIR / f"{doc_id}.md"
    out.write_text("---\n" + "\n".join(fm) + "\n---\n\n" + body, encoding="utf-8")

    print(f"✔ {out.relative_to(THEORY_DIR.parent.parent)}  (제목='{title}', 난이도='{difficulty or '-'}', 이미지 {len(rels)}개)")


if __name__ == "__main__":
    main()
