"""퀴즈 원문(.doc, 실은 MHTML) → data/quiz.json 변환기.

이론 교육의 tools/import_doc.py 와 같은 자리·같은 방식이다 — 사내 위키(Confluence)
가 'Word .doc' 로 내보내지만 실체는 MHTML 이라, Word 로 열지 않고 파일 바이트를
직접 파싱한다(민감도 라벨이 붙지 않는다).

담당자에게 받은 .doc 를 `content/quiz/` 에 그대로 떨어뜨린 뒤 이 도구를 돌리면
`data/quiz.json` 이 통째로 다시 만들어진다. 즉 **원문이 원천**이고 quiz.json 은
산출물이다 — 이론 교육이 .md 를 원천으로 삼는 것과 같은 철학이되, 퀴즈는 서버가
파일 하나(quiz.json)만 읽도록 되어 있어 이 빌드 단계를 둔다.

사용
    python tools/import_quiz.py            # content/quiz/*.doc → data/quiz.json

원문 규약 (Confluence 내보내기 형태 그대로)
    h1              "1) 사전 퀴즈 - DoIP (기초)"  → 차수·과목·난이도
    ul              대상 / 시점 / 선수 학습 / 문항  (머리말 메타 — `키 : 값` 목록)
    h2              "(1) DoIP 개요" 또는 "1장. DoIP 개요"  → 문항 묶음(섹션) 제목
    p               "Q1. ..."                          → 문항 지문
    pre             (선택) 지문에 딸린 바이트열·코드 블록
    ol > li × 4     보기 A~D (원문 순서 유지)
    h2 "정답 및 해설"
    table           번호 | 정답(1~4) | 해설 | (선택) 참조

출력 스키마는 main.py `_load_quiz_topics` 주석과 같다.
    topics[]    id / title / subject / level / phase / subtitle / meta / source / questions[]
    questions[] id / text / code? / section? / choices[4] / answer(0~3) / explain? / ref?
정답을 문구가 아닌 **인덱스**로 두어 보기 문구가 바뀌어도 채점이 깨지지 않는다.
"""
from pathlib import Path
import email
import json
import re
import sys

from bs4 import BeautifulSoup

BASE_DIR = Path(__file__).resolve().parent.parent
DOC_DIR = BASE_DIR / "content" / "quiz"
OUT_PATH = BASE_DIR / "data" / "quiz.json"

# 좌측 목록 정렬 = 커리큘럼 순서. 이론 교육 폴더의 `[n]` 번호와 같은 순서를 쓴다.
SUBJECT_ORDER = {"디지털 통신": 0, "CAN": 1, "CAN 통신": 1, "UDS": 2,
                 "차량용 이더넷": 3, "DoIP": 4}
SUBJECT_SLUG = {"디지털 통신": "digital", "CAN": "can", "CAN 통신": "can",
                "UDS": "uds", "차량용 이더넷": "eth", "DoIP": "doip"}
LEVEL_SLUG = {"기초": "basic", "심화": "adv"}
PHASE_SLUG = {"사전": "pre", "사후": "post"}

# h1 예: "1) 사전 퀴즈 - DoIP (기초)"
_TITLE_RE = re.compile(r"^\d\)\s*(사전|사후)\s*퀴즈\s*[-–—]\s*(.+?)\s*\((기초|심화)\)\s*$")
# 문항 지문 예: "Q1. DoIP를 한 문장으로 설명하면?"
_Q_RE = re.compile(r"^Q\s*(\d+)\s*[.)]\s*(.*)$", re.DOTALL)
# 해설 표의 번호 칸 예: "Q1"
_ANS_NO_RE = re.compile(r"^Q\s*(\d+)$")


def _norm(text):
    """연속 공백·개행을 한 칸으로 접는다. 원문 태그 사이 줄바꿈이 그대로 들어오기 때문."""
    return " ".join(text.split())


def _text(node):
    """태그 안 텍스트. 구분자를 넣지 않는다 — <strong>아닌</strong> 앞뒤 공백이 원문에 이미 있다."""
    return _norm(node.get_text(""))


def read_html(path):
    """MHTML(.doc) 에서 text/html 파트를 꺼낸다. Confluence 내보내기는 quoted-printable."""
    with path.open("rb") as fp:
        msg = email.message_from_binary_file(fp)
    for part in msg.walk():
        if part.get_content_type() == "text/html":
            return part.get_payload(decode=True).decode("utf-8", "replace")
    raise ValueError(f"{path.name}: text/html 파트가 없다")


def parse_head(soup, path):
    """h1 에서 (phase, subject, level) 을 얻는다. 파일명이 아니라 원문 제목이 원천."""
    h1 = soup.find("h1")
    match = _TITLE_RE.match(_text(h1)) if h1 else None
    if not match:
        raise ValueError(f"{path.name}: h1 제목 형식이 아니다 — {_text(h1) if h1 else '없음'}")
    return match.group(1), match.group(2), match.group(3)


def parse_meta(soup):
    """머리말 ul 의 `키 : 값` 목록 (대상 / 시점 / 선수 학습 / 문항). 문서마다 키가 다르므로 그대로 담는다."""
    meta = {}
    ul = soup.find("ul")
    if not ul:
        return meta
    for li in ul.find_all("li"):
        line = _text(li)
        if ":" in line:
            key, value = line.split(":", 1)
            meta[key.strip()] = value.strip()
    return meta


def parse_questions(soup):
    """본문을 훑어 문항을 모은다.

    h2 를 섹션 제목으로 들고 다니다가 `Qn.` 인 p 를 만나면 문항을 열고, 뒤따르는
    pre(코드)·ol(보기)을 그 문항에 붙인다. "정답 및 해설" h2 를 만나면 멈춘다.
    """
    body = soup.find("body") or soup
    questions = []
    section = None
    current = None

    for node in body.find_all(["h2", "p", "pre", "ol"]):
        if node.name == "h2":
            title = _text(node)
            if title.startswith("정답"):
                break
            section = title
            continue
        if node.name == "p":
            match = _Q_RE.match(_text(node))
            if match:
                current = {"no": int(match.group(1)), "text": _norm(match.group(2)),
                           "section": section, "choices": []}
                questions.append(current)
            continue
        if current is None:
            continue
        if node.name == "pre":
            current["code"] = node.get_text("").strip("\n")
        elif node.name == "ol" and not current["choices"]:
            current["choices"] = [_text(li) for li in node.find_all("li", recursive=False)]
    return questions


def parse_answers(soup):
    """"정답 및 해설" 표 → {문항번호: (정답 1-based, 해설, 참조)}.

    문서 끝에는 '오답 항목별 복습 가이드' 표가 하나 더 있어서, 번호 칸이 `Qn` 인
    행만 골라 담는다(그 표는 `Q1~Q2` 처럼 범위라 정규식에 걸리지 않는다).
    """
    answers = {}
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = [_text(td) for td in row.find_all(["td", "th"])]
            if len(cells) < 2:
                continue
            match = _ANS_NO_RE.match(cells[0])
            if not match or not cells[1].isdigit():
                continue
            answers[int(match.group(1))] = (
                int(cells[1]),
                cells[2] if len(cells) > 2 else "",
                cells[3] if len(cells) > 3 else "",
            )
    return answers


def build_topic(path):
    """.doc 한 개 → topics[] 원소 한 개."""
    soup = BeautifulSoup(read_html(path), "html.parser")
    phase, subject, level = parse_head(soup, path)
    meta = parse_meta(soup)
    questions = parse_questions(soup)
    answers = parse_answers(soup)

    slug = f"{SUBJECT_SLUG.get(subject, 'etc')}-{LEVEL_SLUG[level]}-{PHASE_SLUG[phase]}"
    items = []
    for q in questions:
        if len(q["choices"]) != 4:
            raise ValueError(f"{path.name}: Q{q['no']} 보기가 4개가 아니다 ({len(q['choices'])}개)")
        if q["no"] not in answers:
            raise ValueError(f"{path.name}: Q{q['no']} 정답이 해설 표에 없다")
        answer, explain, ref = answers[q["no"]]
        if not 1 <= answer <= 4:
            raise ValueError(f"{path.name}: Q{q['no']} 정답 번호가 1~4 밖 ({answer})")
        item = {"id": f"{slug}-{q['no']:02d}", "text": q["text"]}
        if q.get("code"):
            item["code"] = q["code"]
        if q["section"]:
            item["section"] = q["section"]
        item["choices"] = q["choices"]
        item["answer"] = answer - 1        # 원문 1~4 → 채점용 0~3
        if explain:
            item["explain"] = explain
        if ref:
            item["ref"] = ref
        items.append(item)

    if not items:
        raise ValueError(f"{path.name}: 문항을 하나도 못 읽었다")

    # 머리말이 밝힌 문항 수와 실제로 읽은 수가 다르면 파싱이 샌 것이다.
    declared = re.search(r"(\d+)\s*문항", meta.get("문항", ""))
    if declared and int(declared.group(1)) != len(items):
        raise ValueError(f"{path.name}: 머리말은 {declared.group(1)}문항인데 {len(items)}개를 읽었다")

    return {
        "id": slug,
        "title": f"{subject} ({level}) · {phase}",
        "subject": subject,
        "level": level,
        "phase": PHASE_SLUG[phase],
        "subtitle": f"{phase} 퀴즈 · 객관식 4지선다",
        "meta": meta,
        "source": f"content/quiz/{path.name}",
        "questions": items,
    }


def sort_key(topic):
    """과목(커리큘럼 순) → 난이도(기초 먼저) → 차수(사전 먼저)."""
    return (SUBJECT_ORDER.get(topic["subject"], 99),
            0 if topic["level"] == "기초" else 1,
            0 if topic["phase"] == "pre" else 1)


def main():
    docs = sorted(DOC_DIR.glob("*.doc"))
    if not docs:
        print(f"원문이 없다: {DOC_DIR}", file=sys.stderr)
        return 1

    topics = sorted((build_topic(p) for p in docs), key=sort_key)

    payload = {
        "_note": "content/quiz/*.doc (담당자 제공 원문) 에서 tools/import_quiz.py 로 생성한다. "
                 "직접 고치지 말고 원문을 고친 뒤 다시 생성할 것.",
        "_schema": {
            "topics[]": "id(슬러그) / title(좌측 목록·헤더 표기) / subject / level(기초|심화) / "
                        "phase(pre|post) / subtitle / meta(원문 머리말) / source(원문 경로) / questions[]",
            "questions[]": "id / text(지문) / code?(지문에 딸린 바이트열) / section?(원문 묶음 제목) / "
                           "choices(보기 4개, 원문 순서 유지) / answer(정답 인덱스 0~3) / "
                           "explain?(해설) / ref?(교육자료 참조 절)",
        },
        "version": 3,
        "topics": topics,
    }
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")

    total = sum(len(t["questions"]) for t in topics)
    print(f"{OUT_PATH} — 주제 {len(topics)}개 / 문항 {total}개")
    for t in topics:
        print(f"  {t['id']:20s} {t['title']:24s} {len(t['questions'])}문항")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
