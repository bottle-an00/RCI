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


# ── 폴더(=큰 주제) 일괄 변환 ────────────────────────────────────────────────
# 이론 자료를 '큰 주제(폴더) ▸ 소제목(파일)' 2단으로 반영하기 위한 확장.
# content/theory/<[n] 제목 (난이도)>/ 안에 .doc 를 넣어두면, 같은 폴더에 md 를 만든다.
GROUP_NUM_RE = re.compile(r"^\s*\[(\d+)\]\s*")   # 폴더명 앞머리 [n]
FILE_NUM_RE = re.compile(r"^\s*\((\d+)\)\s*")    # 파일명 앞머리 (k)


def parse_folder_meta(folder):
    """하위 폴더명 `[n] 제목 (난이도)` → (group_order, group_title, difficulty)."""
    raw = folder.name.replace("+", " ")
    m = GROUP_NUM_RE.match(raw)
    group_order = int(m.group(1)) if m else 9999
    difficulty = next((d for d in DIFFICULTIES if d in raw), "")
    name = GROUP_NUM_RE.sub("", raw)
    name = re.sub(r"\((?:%s)\)" % "|".join(DIFFICULTIES), "", name)   # (난이도)
    group_title = re.sub(r"\s+", " ", name).strip()
    return group_order, group_title, difficulty


def parse_file_meta(path, folder_difficulty):
    """폴더 안 .doc 파일명 `(k)+제목.doc` → (order, title, difficulty, doc_id).

    order 는 파일명 앞 (k). 난이도는 파일명에 있으면 그걸, 없으면 폴더 난이도를 물려받는다.
    """
    raw = path.stem.replace("+", " ")
    m = FILE_NUM_RE.match(raw)
    order = int(m.group(1)) if m else 10
    difficulty = next((d for d in DIFFICULTIES if d in raw), folder_difficulty)
    name = FILE_NUM_RE.sub("", raw)                              # 앞머리 (k)
    name = re.sub(r"^\s*\[\d+\]\s*", "", name)                   # 앞머리 [n]
    name = re.sub(r"\((?:%s)\)" % "|".join(DIFFICULTIES), "", name)  # (난이도)
    name = re.sub(r"\(\d+\)|복사본|-\s*복사본", "", name)         # (1)·복사본
    title = re.sub(r"\s+", " ", name).strip() or path.stem
    return order, title, difficulty, _slugify(title)


def convert_one(doc_path, out_dir, doc_id, title, difficulty, order, group, group_order):
    """단일 .doc(MHTML) → out_dir/<doc_id>.md (+ out_dir/assets/<doc_id>/ 이미지)."""
    html, images = parse_mhtml(doc_path)
    by_key = save_images(images, doc_id, base_dir=out_dir)
    body = to_markdown(rewrite_and_extract(html, by_key))
    fm = [f"title: {title}"]
    if group:
        fm.append(f"group: {group}")
        fm.append(f"group_order: {group_order}")
    if difficulty:
        fm.append(f"difficulty: {difficulty}")
    fm.append(f"order: {order}")
    out = out_dir / f"{doc_id}.md"
    out.write_text("---\n" + "\n".join(fm) + "\n---\n\n" + body, encoding="utf-8")
    return out, len(images)


def process_folder(folder):
    """폴더(=그룹) 안의 모든 .doc 를 변환한다. 산출물은 같은 폴더."""
    group_order, group_title, folder_diff = parse_folder_meta(folder)
    docs = sorted(p for p in folder.glob("*.doc") if "복사본" not in p.name)
    results = []
    seen = {}
    for doc in docs:
        order, title, difficulty, doc_id = parse_file_meta(doc, folder_diff)
        seen[doc_id] = seen.get(doc_id, 0) + 1
        if seen[doc_id] > 1:                       # 같은 슬러그 충돌 방지
            doc_id = f"{doc_id}-{seen[doc_id]}"
        out, n = convert_one(doc, folder, doc_id, title, difficulty, order,
                             group_title, group_order)
        results.append((out, title, difficulty, n))
    return group_title, results


def process_dir(root):
    """content/theory 아래 하위 폴더(=그룹)를 모두 훑어 변환한다."""
    total = 0
    for folder in sorted(p for p in root.iterdir() if p.is_dir() and p.name != "assets"):
        if not any(folder.glob("*.doc")):
            continue
        group_title, results = process_folder(folder)
        print(f"■ 그룹 '{group_title}'  ({folder.name})")
        for out, title, difficulty, n in results:
            print(f"   ✔ {out.name}  (제목='{title}', 난이도='{difficulty or '-'}', 이미지 {n}개)")
            total += 1
    print(f"\n총 {total}개 자료 변환 완료.")


def _loc_key(value):
    """Content-Location / img src → 매칭에 쓸 basename 키.

    파트는 `file:///C:/<해시>`, 본문 img 는 `<해시>` 로 같은 이름을 쓴다. 경로·쿼리·
    프래그먼트를 떼고 소문자 basename 만 남겨 둘을 같은 기준으로 비교한다.
    """
    if not value:
        return ""
    v = value.split("?", 1)[0].split("#", 1)[0].rstrip("/")
    return v.replace("\\", "/").rsplit("/", 1)[-1].strip().lower()


def parse_mhtml(path):
    """MHTML(.doc) 을 (html: str, images: [(key, bytes)]) 로 가른다.

    key 는 파트의 Content-Location basename(보통 `file:///C:/<해시>` 의 <해시>) 이다.
    Confluence 내보내기는 본문 <img src> 에 **같은 해시**를 쓰므로 이걸로 정확히 잇는다.
    파트 순서와 본문 등장 순서는 일치하지 않으므로(첨부 순으로 나온다) 순서로 이으면
    안 된다 — 그림이 조용히 뒤바뀐다.
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
                images.append((_loc_key(part.get("Content-Location", "")), data))
    if html is None:
        raise SystemExit(f"HTML 본문을 찾지 못했습니다(정상 MHTML 이 아님): {path.name}")
    return html, images


def save_images(images, doc_id, base_dir=THEORY_DIR):
    """이미지 파트를 <base_dir>/assets/<id>/ 에 저장하고 {key: 상대경로} 를 돌려준다.

    파일명은 파트 순서(img01, img02 …) 그대로다 — 본문 배치는 key 매칭이 정하므로
    파일명 순서에 의미를 싣지 않는다.
    """
    if not images:
        return {}
    asset_dir = base_dir / "assets" / doc_id
    asset_dir.mkdir(parents=True, exist_ok=True)
    by_key = {}
    for i, (key, data) in enumerate(images, start=1):
        fname = f"img{i:02d}.{_img_ext(data)}"
        (asset_dir / fname).write_bytes(data)
        if key:
            by_key[key] = f"assets/{doc_id}/{fname}"
    return by_key


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


def rewrite_and_extract(html, by_key):
    """본문 노드를 골라, 각 <img> 의 src 를 **같은 키의** 저장 경로로 바꾼 HTML 을 돌려준다.

    Confluence 내보내기는 본문을 #main-content 에 담는다 — 있으면 그것만, 없으면 body.
    키가 by_key 에 없는 <img> 는 내장 파트가 없는 것(위키에 붙은 원격 이미지, UI 아이콘
    따위)이라 따로 처리한다 — _handle_unmatched_img 참고.
    """
    soup = BeautifulSoup(html, "html.parser")
    for img in soup.find_all("img"):
        rel = by_key.get(_loc_key(img.get("src", "")))
        if rel:
            img["src"] = rel
        else:
            _handle_unmatched_img(img)
    _promote_heading_images(soup)
    node = soup.select_one("#main-content") or soup.body or soup
    return str(node)


def _handle_unmatched_img(img):
    """내장 파트가 없는 <img> 를 어떻게 할지 정한다.

    예: 위키 본문이 외부 사이트 그림을 http(s) 주소로 직접 걸어둔 경우
    (`https://ars.els-cdn.com/…/f13-09.jpg`). 파일이 문서 안에 없으므로
    로컬 자산으로 저장할 수 없다.
    """
    src = (img.get("src") or "").strip()
    if src.lower().startswith(("http://", "https://")):
        # 운영 환경이 온라인이므로 원격 주소 그대로 두면 렌더된다. 지우면 교육자료에서
        # 그림 한 장이 말없이 사라지고, 그 빈자리를 뒤 이미지가 메우며 배치가 밀린다.
        img["alt"] = img.get("alt") or "외부 이미지"
        return
    # 내장 파트도 원격 주소도 아니면 위키 UI 아이콘(말머리·이모지) 이다 — 본문이 아니다.
    img.decompose()


def to_markdown(html):
    body = html_to_md(html, heading_style="ATX", strong_em_symbol="*", bullets="-")
    return re.sub(r"\n{3,}", "\n\n", body).strip() + "\n"     # 빈 줄 3개 이상 → 2개


def main():
    ap = argparse.ArgumentParser(description="Confluence .doc(MHTML) → 이론 교육 md")
    ap.add_argument("file", help=".doc(MHTML) 파일 또는 폴더(=큰 주제 묶음) 경로")
    ap.add_argument("--id", help="문서 id(=URL 슬러그, 파일명). 미지정 시 제목에서 생성")
    ap.add_argument("--title", help="frontmatter 제목. 미지정 시 파일명에서 추론")
    ap.add_argument("--difficulty", choices=DIFFICULTIES, help="난이도. 미지정 시 파일명에서 추론")
    ap.add_argument("--order", type=int, default=10, help="같은 난이도 안 정렬 키(기본 10)")
    args = ap.parse_args()

    path = Path(args.file)
    if path.is_dir():
        # 폴더 모드: 하위 폴더 하나 = 큰 주제, 그 안 .doc 하나 = 소제목.
        process_dir(path)
        return
    if not path.is_file():
        raise SystemExit(f"파일이 없습니다: {path}")

    doc_id, title, difficulty = derive_meta(path, args)
    html, images = parse_mhtml(path)
    by_key = save_images(images, doc_id)
    body = to_markdown(rewrite_and_extract(html, by_key))

    fm = [f"title: {title}"]
    if difficulty:
        fm.append(f"difficulty: {difficulty}")
    fm.append(f"order: {args.order}")
    out = THEORY_DIR / f"{doc_id}.md"
    out.write_text("---\n" + "\n".join(fm) + "\n---\n\n" + body, encoding="utf-8")

    print(f"✔ {out.relative_to(THEORY_DIR.parent.parent)}  (제목='{title}', 난이도='{difficulty or '-'}', 이미지 {len(images)}개)")


if __name__ == "__main__":
    main()
