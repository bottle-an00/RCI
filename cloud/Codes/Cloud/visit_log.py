"""방문 집계 — "몇 명이 우리 시스템에 들어왔는가" 를 날짜별 JSON 로그로 남긴다.

왜 필요한가: 지금까지 서버에 사람 단위로 남는 기록은 퀴즈 결과(TEST_RESULT)뿐이었다.
그래서 이론 교육만 보고 나간 교육생은 통계에 아예 존재하지 않는다 — 교육을 몇 명이
받았는지 물으면 답할 근거가 없다. 여기서는 화면 진입 자체를 센다.

세는 단위는 '사람' 이 아니라 **방문(세션)** 이다
  방문자ID  브라우저에 심는 쿠키(rci_vid). 1년 유지되므로 같은 브라우저로 다시 오면
            같은 방문자로 이어진다. 실습실 공용 PC 를 여럿이 쓰면 한 방문자로 뭉치는
            한계가 있다 — 사람 수의 하한선으로 읽어야 한다.
  세션ID    쿠키(rci_sid)에 담고 **응답마다 수명을 1시간으로 다시 설정**한다. 그래서
            마지막 클릭 후 1시간 조용하면 쿠키가 저절로 사라지고, 다음 진입은 새 방문이
            된다(유휴 만료). 서버가 만료 시각을 들고 있지 않아도 브라우저가 알아서
            잊어 주는 구조라, 서버를 재시작해도 집계가 어긋나지 않는다.
            → "같은 사람이 1시간 뒤에 들어오면 다른 방문으로 센다" 가 이 한 줄이다.

기록 위치·방식은 퀴즈 결과(main.RESULT_DIR)의 선례를 그대로 따른다 — 날짜 파일 하나,
락으로 직렬화, 임시 파일에 쓰고 교체. DB 없이 붙고, 파일을 열어 눈으로 확인할 수 있다.

기록은 한 방문에 한 줄이고, 같은 방문 안에서 화면을 넘기면 그 줄의 페이지수·마지막시각만
갱신한다(= 체류 시간을 되계산할 수 있다). 방문마다 줄이 하나씩만 늘므로 교육장 규모
(하루 수십 명)에서는 파일이 수십 KB 를 넘지 않는다.
"""
from datetime import datetime, timedelta
from pathlib import Path
import json
import logging
import re
import threading
import uuid

# 로그가 쌓이는 기본 폴더. main.py 도 이 값을 쓴다 — 경로가 두 곳에 적히면 한쪽만
# 고쳐져서 "기록은 되는데 조회가 빈다" 가 된다.
DEFAULT_DIR = Path(__file__).resolve().parent / "VISIT_LOG"

# 이름 대조에 쓰는 다른 로그들. 방문 로그 자체에는 이름이 없다(쿠키뿐) — 퀴즈·설문을
# 낸 사람만 IP·시각으로 되짚어 이름을 붙일 수 있다 (_names_by_ip).
_NAMED_LOG_DIRS = (
    Path(__file__).resolve().parent / "TEST_RESULT",
    Path(__file__).resolve().parent / "SURVEY_RESULT",
)

# 쿠키 이름. 다른 쿠키와 섞이지 않게 접두사를 붙인다.
VISITOR_COOKIE = "rci_vid"
SESSION_COOKIE = "rci_sid"

# 방문자 쿠키 수명 1년 — '재방문' 을 알아보기 위한 것이라 길게 잡는다.
VISITOR_MAX_AGE = 365 * 24 * 60 * 60
# 세션 쿠키 수명 1시간. 응답마다 다시 설정하므로 '마지막 활동 후 1시간' 이 된다.
SESSION_IDLE_SEC = 60 * 60

# 집계에서 뺄 경로. 정적 자산·API·SSE 는 사람이 '화면을 봤다' 는 뜻이 아니다
# (이미지 하나가 방문 하나로 세어지면 숫자가 무의미해진다).
_SKIP_PREFIXES = ("/static/", "/content/", "/api/")
_SKIP_EXACT = ("/favicon.ico", "/robots.txt")

_DAY_RE = re.compile(r"\d{4}-\d{2}-\d{2}")

_LOCK = threading.Lock()
_log = logging.getLogger("visit")

# 세션ID → 그 세션의 기록이 들어 있는 날짜 파일 키("YYYY-MM-DD"). 자정을 넘겨 계속
# 보고 있는 방문의 줄을 어느 파일에서 찾을지 알기 위한 것. 서버가 살아 있는 동안만
# 유지되고, 없으면 오늘·어제 파일을 뒤져 찾는다(_find_day).
_session_day: dict[str, str] = {}


def is_page_path(path: str) -> bool:
    """이 경로가 '사람이 본 화면' 인가. 정적 자산·API 는 세지 않는다."""
    if path in _SKIP_EXACT:
        return False
    return not path.startswith(_SKIP_PREFIXES)


def new_id() -> str:
    """쿠키에 담을 불투명 id. 개인정보가 섞이지 않게 난수만 쓴다."""
    return uuid.uuid4().hex


def _path_for(base_dir: Path, day: str) -> Path:
    return base_dir / f"{day}.json"


def _load(path: Path) -> list:
    """날짜 파일을 배열로 읽는다. 깨져 있으면 옆으로 치우고 새로 시작한다.

    퀴즈 결과 로더(main._load_records)와 같은 판단이다 — 한 건이 깨졌다고 그날의
    이후 집계 전부를 잃는 쪽이 훨씬 나쁘다. 다만 방문 기록은 잃어도 교육 진행을
    막지 않으므로, 실패는 로그로만 남기고 조용히 넘어간다.
    """
    if not path.exists():
        return []
    try:
        with path.open(encoding="utf-8") as fp:
            records = json.load(fp)
        if isinstance(records, list):
            return records
        raise ValueError("최상위가 배열이 아님")
    except (json.JSONDecodeError, ValueError, OSError) as exc:
        backup = path.parent / f"{path.stem}.corrupt-{datetime.now():%H%M%S}.json"
        _log.error("방문 로그 %s 를 읽을 수 없어 %s 로 옮깁니다: %s", path.name, backup.name, exc)
        try:
            path.replace(backup)
        except OSError:
            pass
        return []


def _save(path: Path, records: list) -> None:
    """임시 파일에 다 쓴 뒤 교체 — 도중에 죽어도 반쪽 JSON 이 남지 않는다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as fp:
        json.dump(records, fp, ensure_ascii=False, indent=2)
    tmp.replace(path)


def _find_day(base_dir: Path, sid: str, now: datetime) -> str | None:
    """세션의 기록이 어느 날짜 파일에 있는지 — 메모리에 없으면 오늘·어제를 뒤진다.

    어제까지 보는 이유: 자정을 넘겨 이어 보는 방문이 있고, 서버를 재시작하면 메모리
    색인이 비기 때문이다. 그보다 오래된 세션은 이미 쿠키(1시간)로 만료됐다.
    """
    known = _session_day.get(sid)
    if known:
        return known
    for delta in (0, 1):
        day = f"{datetime.fromtimestamp(now.timestamp() - delta * 86400):%Y-%m-%d}"
        records = _load(_path_for(base_dir, day))
        if any(r.get("세션ID") == sid for r in records):
            _session_day[sid] = day
            return day
    return None


def track(base_dir: Path, *, visitor_id: str, session_id: str, new_session: bool,
          now: datetime, path: str, ip: str, agent: str, returning: bool) -> None:
    """방문 한 건을 기록한다 — 새 세션이면 줄을 추가, 이어 보는 중이면 그 줄을 갱신.

    호출자(main 의 미들웨어)는 쿠키를 읽어 new_session 을 판정하고, 파일 I/O 인 이
    함수를 스레드풀에서 부른다. 여기서 예외가 나가도 화면은 이미 그려진 뒤이므로,
    집계 실패가 교육을 막지 않게 로그만 남긴다.
    """
    try:
        with _LOCK:
            if new_session:
                day = f"{now:%Y-%m-%d}"
                file = _path_for(base_dir, day)
                records = _load(file)
                records.append({
                    "세션ID": session_id,
                    "방문자ID": visitor_id,
                    "방문시각": now.isoformat(timespec="seconds"),
                    "마지막시각": now.isoformat(timespec="seconds"),
                    "페이지수": 1,
                    "첫화면": path,
                    "재방문": returning,
                    "IP": ip,
                    "브라우저": agent[:200],      # UA 는 길다 — 식별에 쓸 만큼만 남긴다
                })
                _save(file, records)
                _session_day[session_id] = day
                _log.info("새 방문 · %s · %s · %s (오늘 %d번째)",
                          path, ip, "재방문" if returning else "첫방문", len(records))
                return

            day = _find_day(base_dir, session_id, now)
            if day is None:
                # 쿠키는 있는데 기록이 없다 — 로그를 지웠거나 다른 서버에서 받은
                # 쿠키다. 없는 줄을 새로 만들면 방문 수가 부풀어 오르므로 세지 않는다.
                return
            file = _path_for(base_dir, day)
            records = _load(file)
            for record in records:
                if record.get("세션ID") != session_id:
                    continue
                record["마지막시각"] = now.isoformat(timespec="seconds")
                record["페이지수"] = int(record.get("페이지수", 0)) + 1
                _save(file, records)
                return
    except OSError as exc:
        _log.warning("방문 기록 실패 (%s): %s", path, exc)


def summary(base_dir: Path, day: str) -> dict:
    """그 날짜의 집계 — 방문 수(세션), 방문자 수(고유 브라우저), 기록 전체.

    방문수 ≥ 방문자수 다. 한 사람이 오전·오후에 각각 들어오면 방문 2 · 방문자 1 로
    잡힌다 — "1시간 뒤에 들어오면 다른 것으로 센다" 는 방문 쪽 숫자다.
    """
    records = _load(_path_for(base_dir, day))
    visitors = {r.get("방문자ID") for r in records if r.get("방문자ID")}
    return {
        "날짜": day,
        "방문수": len(records),
        "방문자수": len(visitors),
        "재방문수": sum(1 for r in records if r.get("재방문")),
        "페이지조회수": sum(int(r.get("페이지수", 0)) for r in records),
        "기록": records,
    }


def is_day(value: str) -> bool:
    """조회 파라미터가 YYYY-MM-DD 형식인가 (경로 이탈 방지 겸 검증)."""
    return bool(_DAY_RE.fullmatch(value))


# --------------------------------------------------------------------------- #
# 단독 실행 리포트 — `python visit_log.py` 로 "언제부터 언제, 몇 명이, 누가" 를 본다.
#
# 서버를 띄우지 않고 로그 파일만 읽는다(읽기 전용). 교육이 끝난 뒤 담당자가 서버 PC
# 에서 그대로 돌려 볼 수 있어야 하므로, 인수 없이 실행하면 오늘치를 보여준다.
# --------------------------------------------------------------------------- #


def _days_between(start: str, end: str) -> list[str]:
    """start~end(포함) 날짜 문자열 목록. 순서가 뒤집혀 오면 바로잡는다."""
    a = datetime.strptime(start, "%Y-%m-%d")
    b = datetime.strptime(end, "%Y-%m-%d")
    if a > b:
        a, b = b, a
    return [f"{a + timedelta(days=i):%Y-%m-%d}" for i in range((b - a).days + 1)]


def _names_by_ip(day: str) -> dict[str, list[tuple[str, str]]]:
    """그날 이름을 남긴 기록(퀴즈·설문)을 IP 별로 모은다. {IP: [(시각, 이름), …]}

    방문 로그는 익명이다 — 쿠키 id 와 IP 만 있고 이름이 없다. 그래서 '누가' 는
    이름을 남긴 다른 로그와 **대조해 추정**할 수밖에 없다. 같은 IP 라도 공용 PC 면
    여러 사람일 수 있으므로, 붙는 이름은 어디까지나 참고값이다(리포트에 그렇게 적는다).
    """
    found: dict[str, list[tuple[str, str]]] = {}
    for base in _NAMED_LOG_DIRS:
        for record in _load(base / f"{day}.json"):
            ip = record.get("제출IP") or record.get("IP") or "-"
            name = record.get("이름") or record.get("성함")
            when = (record.get("제출시각") or "")[11:16]
            if name:
                found.setdefault(ip, []).append((when, name))
    return found


def _report(base_dir: Path, days: list[str], detail: bool) -> str:
    lines = []
    totals = {"방문": 0, "페이지": 0, "재방문": 0}
    visitors: set[str] = set()
    first_seen = last_seen = None
    rows = []

    for day in days:
        s = summary(base_dir, day)
        if not s["방문수"]:
            continue
        totals["방문"] += s["방문수"]
        totals["페이지"] += s["페이지조회수"]
        totals["재방문"] += s["재방문수"]
        visitors.update(r["방문자ID"] for r in s["기록"] if r.get("방문자ID"))
        # ISO 문자열은 자리수가 고정이라 문자열 비교가 곧 시각 비교다.
        stamps = [r["방문시각"] for r in s["기록"] if r.get("방문시각")]
        if stamps:
            first = min(stamps)
            last = max(r.get("마지막시각") or r["방문시각"] for r in s["기록"])
            first_seen = first if first_seen is None else min(first_seen, first)
            last_seen = last if last_seen is None else max(last_seen, last)
        rows.append((day, s))

    lines.append(f"방문 로그 · {base_dir}")
    if not rows:
        lines.append(f"기간 {days[0]} ~ {days[-1]} · 기록 없음")
        return "\n".join(lines)

    lines.append(f"기간 {days[0]} ~ {days[-1]}"
                 f" (실제 기록 {first_seen.replace('T', ' ')} ~ {last_seen.replace('T', ' ')})")
    lines.append(f"방문 {totals['방문']}건 · 방문자 {len(visitors)}명(브라우저 기준)"
                 f" · 페이지조회 {totals['페이지']}회 · 재방문 {totals['재방문']}건")
    lines.append("")
    # 한글은 터미널에서 두 칸을 차지한다 — 숫자 열이 한글 머리글과 어긋나지 않게
    # 머리글 쪽 자리수를 줄여 맞춘다(폭 계산 대신 눈으로 맞춘 표라 단순하다).
    lines.append(f"{'날짜':<10}{'방문':>4}{'방문자':>7}{'페이지':>7}{'재방문':>7}")
    for day, s in rows:
        lines.append(f"{day:<12}{s['방문수']:>4}{s['방문자수']:>7}"
                     f"{s['페이지조회수']:>8}{s['재방문수']:>8}")

    if detail:
        lines.append("")
        lines.append("방문 상세 (이름은 같은 IP·시각의 퀴즈·설문 기록에서 붙인 추정값)")
        for day, s in rows:
            names = _names_by_ip(day)
            for r in s["기록"]:
                ip = r.get("IP", "-")
                hint = ", ".join(f"{t} {n}" for t, n in names.get(ip, [])) or "-"
                lines.append(
                    f"  {day} {r['방문시각'][11:16]}~{(r.get('마지막시각') or r['방문시각'])[11:16]}"
                    f" · {r.get('방문자ID', '-')[:8]}"
                    f" · {r.get('페이지수', 0):>3}페이지"
                    f" · {'재방문' if r.get('재방문') else '첫방문'}"
                    f" · {ip:<15} · {hint}")
    return "\n".join(lines)


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="방문 로그 리포트 — 언제부터 언제, 몇 명이, 누가 들어왔는지 (읽기 전용)")
    parser.add_argument("--from", dest="start", help="시작 날짜 YYYY-MM-DD")
    parser.add_argument("--to", dest="end", help="끝 날짜 YYYY-MM-DD (기본: 오늘)")
    parser.add_argument("--days", type=int, help="오늘까지 최근 N일")
    parser.add_argument("--detail", action="store_true", help="방문 한 건씩 자세히")
    parser.add_argument("--dir", default=str(DEFAULT_DIR), help="로그 폴더")
    args = parser.parse_args(argv)

    today = f"{datetime.now():%Y-%m-%d}"
    end = args.end or today
    if args.days:
        start = f"{datetime.strptime(end, '%Y-%m-%d') - timedelta(days=args.days - 1):%Y-%m-%d}"
    else:
        start = args.start or end
    for value in (start, end):
        if not is_day(value):
            parser.error(f"날짜는 YYYY-MM-DD 형식입니다: {value}")

    print(_report(Path(args.dir), _days_between(start, end), args.detail))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
