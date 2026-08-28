"""RCI 진단 교육 플랫폼 — FastAPI + Jinja2 서버 렌더링 엔트리포인트.

정보구조 (target-first, §와이어프레임 확정):
  /                    Step1 대상 선택 (RC Car / UR Robot)
  /{target}            Step2 컨텐츠 그리드 (학습·준비 / 진단·실습 2섹션)
  /{target}/{content}  Step3 콘텐츠별 화면 (뷰어/상세/퀴즈/3분할 실행/ECU)
  /search              통합 검색 (플레이스홀더)

대상(rc-car/ur-robot)은 경로 접두사로 하위 전 화면에 물려 내려간다. 목록·타일·
트리는 하드코딩 마크업이 아니라 아래 데이터를 템플릿에서 렌더한다(§8, 더미 기반).

MQTT
  서버 자신도 브로커에 붙는다(`mqtt_bridge.MqttBridge`). 브라우저 직결 경로
  (`static/js/rci-live.js`, ws:8080)와 병존하며, 이쪽은 `/api/*` 로 노출돼
  브라우저 없이 RCI 와 왕복을 확인할 수 있다. 계약은
  `Documents/MQTT_Interface_Contract.md`.
"""

import asyncio
import json
import logging
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

import theory_content
from mqtt_bridge import BridgeError, BrokerConfig, MqttBridge, RequestTimeout

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")

BASE_DIR = Path(__file__).resolve().parent

bridge = MqttBridge(BrokerConfig.from_env())


@asynccontextmanager
async def lifespan(app: FastAPI):
    """웹 서버 수명과 MQTT 연결 수명을 묶는다.

    `start()` 는 비차단이라 브로커가 아직 안 떠 있어도 기동은 성공하고, 브로커가
    나중에 올라오면 자동으로 붙는다. 연결 여부는 `/api/health` 로 확인한다.
    """
    bridge.start(asyncio.get_running_loop())
    try:
        yield
    finally:
        bridge.stop()


app = FastAPI(title="RCI 진단 교육 플랫폼", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
# 이론 교육 자료(md 안에서 참조하는 이미지·SVG)를 /content 로 서빙한다.
# theory_content.ASSET_URL_BASE(/content/theory/) 와 짝을 이룬다.
app.mount("/content", StaticFiles(directory=BASE_DIR / "content"), name="content")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def asset(path: str) -> str:
    """정적 파일 URL + 내용이 바뀌면 함께 바뀌는 쿼리(mtime).

    개발 중 JS/CSS 를 고쳐도 브라우저가 디스크 캐시의 **옛 파일을 실행**하는 일이
    잦다(새로고침으로도 안 잡힐 때가 있다). mtime 을 URL 에 실어 파일이 바뀌면
    주소도 바뀌게 해서 그 혼란을 없앤다.
    """
    try:
        version = int((BASE_DIR / "static" / path).stat().st_mtime)
    except OSError:
        version = 0
    return f"/static/{path}?v={version}"


templates.env.globals["asset"] = asset


# --------------------------------------------------------------------------- #
# 데이터 (§8) — 추후 DB/백엔드 연동 시 이 계층만 교체.
# --------------------------------------------------------------------------- #

# 대상. tile_sub=타일 보조문구, status=상단 상태표시 라벨, transport=전송수단.
# device = MQTT 토픽 접미사 (minigit/req/{device}), 사양서 계약.
# model = 3D 뷰어 .glb 파일명(static/models/).
#   rc-car   아이오닉5 차량 모델을 대역으로 쓴다 (RC카 모델 준비 전까지).
#   ur-robot UR 로봇팔 실제 모델 (Blender glTF I/O · 메시 8 · 머티리얼 6 · 애니메이션 1).
# 조명 연동(rci-live.js blinkLights)은 RC카 전용이다 — 발광 머티리얼 이름을
# "M_Emission" 으로 고정해 두었고, UR 모델의 발광 머티리얼은 "rep_BluePlastic" 이다.
# UR 쪽에도 점등을 붙이려면 EMISSIVE_MAT 를 대상별로 갈라야 한다(조명 DID 0x0207 은
# 현재 RC카에만 있으므로 지금은 필요 없다).
_RC_MODEL = "hyundai_ioniq_5_lowpoly.glb"
_UR_MODEL = "UR_Robot.glb"
TARGETS = [
    # 표시 명칭은 "진단 모사 차량"(리뷰 피드백 §1). URL 슬러그 id="rc-car" 와 MQTT
    # device="rccar" 는 계약이라 그대로 둔다 — 바꾸면 라우트·토픽이 깨진다.
    {"id": "rc-car", "label": "진단 모사 차량", "status": "진단 모사 차량", "device": "rccar",
     "transport": "CAN", "tile_sub": "CAN · OBD", "icon": "car",
     "model": _RC_MODEL},
    {"id": "ur-robot", "label": "UR Robot", "status": "UR Robot", "device": "urrobot",
     "transport": "DoIP", "tile_sub": "DoIP · 이더넷", "icon": "robotarm",
     "model": _UR_MODEL},
]

# 하단 5메뉴 (GDS-SMART 라벨 그대로).
BOTTOM_NAV = [
    {"label": "GSW", "icon": "globe"},
    {"label": "사용자 지원", "icon": "headset"},
    {"label": "정비 매뉴얼", "icon": "book"},
    {"label": "e-Report", "icon": "ereport"},
    {"label": "환경 설정", "icon": "gear"},
]

# 이론 교육 자료는 더 이상 여기 하드코딩하지 않는다 — content/theory/*.md 를 스캔한다
# (theory_content). 자료 추가 = 그 폴더에 .md 파일 하나 떨어뜨리기.


def _load_quiz_topics():
    """퀴즈 주제·문항 (data/quiz.json). 대상 무관 공통.

    quiz.json 은 담당자가 준 원문(content/quiz/*.doc)에서 tools/import_quiz.py
    로 생성한다 — 퀴즈 갱신 = 그 폴더에 .doc 갈아끼우고 도구 한 번 돌리기.
    서버는 여기서만 읽는다. 스키마는 topics[] = {id, title, subtitle, questions[]},
    questions[] = {id, text, code?, choices[4], answer(정답 인덱스), explain?}.
    정답을 문구가 아닌 인덱스로 두어 보기 문구가 바뀌어도 채점이 깨지지 않는다.
    """
    with (BASE_DIR / "data" / "quiz.json").open(encoding="utf-8") as fp:
        return json.load(fp)["topics"]


QUIZ_TOPICS = _load_quiz_topics()

# 컨텐츠 그리드 정의. 섹션 2개 × 콘텐츠. view = Step3 화면 유형.
SECTIONS = ["학습·준비", "진단·실습"]
CONTENTS = [
    {"id": "theory", "section": "학습·준비", "title": "이론 교육", "icon": "doc", "view": "theory"},
    {"id": "prep", "section": "학습·준비", "title": "실습 준비", "icon": "prep", "view": "detail"},
    {"id": "quiz", "section": "학습·준비", "title": "퀴즈", "icon": "quiz", "view": "quiz"},
    {"id": "diag", "section": "진단·실습", "title": "진단", "icon": "sensor", "view": "run"},
    {"id": "force", "section": "진단·실습", "title": "강제구동", "icon": "force", "view": "run"},
    {"id": "ecu", "section": "진단·실습", "title": "ECU 업그레이드", "icon": "ecu", "view": "ecu"},
    {"id": "message", "section": "진단·실습", "title": "메시지 작성", "icon": "compose",
     "view": "run", "composer": True},
]


# --------------------------------------------------------------------------- #
# 실습 준비 — 세부 항목별 안내문
#
# 준비 탭은 '장비 체결'만 있었지만, 교육생이 실제로 먼저 부딪히는 것은 화면 사용법
# 이다(이론 교육·퀴즈가 어떤 규칙으로 도는지 모르면 자료를 훑고 지나간다). 그래서
# 준비 탭을 '실습 전에 읽는 것' 전반으로 넓히고, 안내문을 여기 데이터로 둔다.
#
# 템플릿(detail.html)은 이 구조만 그린다 — 항목을 늘리려면 여기 dict 하나를 더한다.
#   id/title       좌측 트리 (content_tree 가 여기서 만든다)
#   tag            우상단 배지
#   meta           제목 아래 회색 한 줄
#   sections[]     {heading, body?(문단) | steps?(번호 없는 줄 나열)}
#   action?        {label, url} 해당 탭으로 바로 보내는 버튼. url 은 아래 형식 문자열.
#
# 본문의 `{label}` `{transport}` 는 대상(TARGETS)에 따라 달라지는 자리다 —
# prep_guide() 가 채운다. 중괄호를 그대로 쓰려면 `{{ }}` 로 이스케이프할 것.
# --------------------------------------------------------------------------- #
PREP_GUIDES = [
    {
        "id": "prep-equip",
        "title": "실습 장비 체결",
        "tag": "준비",
        "meta": "대상 {label} · 사전 준비 · 전송 {transport}",
        "sections": [
            {"heading": "준비물",
             "body": "Mini VCI · {label} · 전원/통신 케이블 · 진단 PC (더미)"},
            {"heading": "체결 절차",
             "steps": ["1) 대상 전원 확인",
                       "2) Mini VCI ↔ 대상 커넥터 체결",
                       "3) Mini VCI ↔ PC 연결 ({transport})",
                       "4) 연결 상태 '연결됨' 확인"]},
            {"heading": "유의사항",
             "body": "체결 전 전원 상태를 반드시 확인하세요. 상단 바의 연결 표시가 "
                     "'연결됨'이 되어야 진단·강제구동·메시지 작성이 실제로 왕복합니다."},
        ],
    },
    {
        "id": "prep-theory",
        "title": "이론 교육 탭 활용 방법",
        "tag": "사용법",
        "meta": "학습·준비 · 이론 교육 화면 안내",
        "sections": [
            {"heading": "화면 구성",
             "body": "왼쪽은 교육 자료 목록, 오른쪽은 선택한 자료의 본문입니다. "
                     "목록은 '큰 주제 ▸ 소제목' 2단이며, 큰 주제 줄을 누르면 접거나 펼 수 있습니다."},
            {"heading": "보는 순서",
             "steps": ["1) 큰 주제를 고른다 — 디지털 통신 → CAN → UDS → 차량용 이더넷 → DoIP 순서로 쌓입니다",
                       "2) 같은 주제 안에서는 위에서 아래로 읽는다 — 소제목이 이미 학습 순서대로 정렬돼 있습니다",
                       "3) 오른쪽 배지로 난이도(기초·기본·심화)를 확인한다 — 기초를 건너뛰면 심화가 막힙니다",
                       "4) 한 주제를 끝내면 퀴즈 탭에서 같은 과목의 사후 퀴즈를 푼다"]},
            {"heading": "본문에서 볼 수 있는 것",
             "body": "그림·표는 물론 프레임 구조도, 통신 절차 다이어그램이 함께 들어 있습니다. "
                     "다이어그램은 화면에서 직접 그려지므로 로딩이 한 박자 늦을 수 있습니다."},
            {"heading": "실습과 이어보기",
             "body": "심화 자료의 바이트열 예시는 '메시지 작성' 실습에서 그대로 조립해 볼 수 있습니다. "
                     "읽고 끝내지 말고 해당 실습 코스를 한 번 밟아보세요."},
        ],
        "action": {"label": "이론 교육 열기", "url": "/{target_id}/theory"},
    },
    {
        "id": "prep-quiz",
        "title": "퀴즈 탭 활용 방법",
        "tag": "사용법",
        "meta": "학습·준비 · 퀴즈 화면 안내",
        "sections": [
            {"heading": "화면 구성",
             "body": "왼쪽은 퀴즈 주제 목록으로, 과목마다 '사전'과 '사후'가 한 쌍입니다. "
                     "주제 이름 옆 숫자가 그 퀴즈의 문항 수입니다. 오른쪽에서 한 문항씩 풉니다."},
            {"heading": "푸는 순서",
             "steps": ["1) 교육자료를 보기 '전'에 사전 퀴즈를 푼다 — 뭘 모르는지 먼저 드러내는 것이 목적입니다",
                       "2) 이론 교육 탭에서 해당 과목을 학습한다",
                       "3) 학습이 끝나면 사후 퀴즈를 푼다 — 사전 점수와 비교해 얼마나 올랐는지 봅니다",
                       "4) 틀린 문항 번호를 교육자료에서 다시 찾아 읽는다"]},
            {"heading": "진행 규칙",
             "steps": ["· 보기 순서는 응시할 때마다 새로 섞입니다 — 답의 위치를 외우는 것은 의미가 없습니다",
                       "· '이전 / 다음'으로 오갈 수 있고, 마지막 문항에서 '제출하기'로 채점합니다",
                       "· 고르지 않고 넘어간 문항은 오답 처리됩니다",
                       "· 점수는 100점 환산이며, 결과 화면의 O/X 칩으로 문항별 정오를 봅니다",
                       "· '다시 풀기'를 누르면 보기 순서까지 새로 섞여 처음부터 시작합니다"]},
            {"heading": "유의사항",
             "body": "채점 결과는 저장되지 않습니다. 화면을 벗어나면 사라지니 "
                     "사전·사후 점수는 따로 적어 두고 비교하세요."},
        ],
        "action": {"label": "퀴즈 열기", "url": "/{target_id}/quiz?item={first_quiz}"},
    },
]


def prep_guide(node_id, target):
    """실습 준비 세부 항목 id → 대상에 맞게 문구를 채운 안내문 (없으면 None).

    본문의 `{label}`·`{transport}` 는 대상마다 다르고, action.url 의 `{target_id}`·
    `{first_quiz}` 는 링크를 걸 주소라 여기서 한 번에 포맷한다. 원본(PREP_GUIDES)은
    건드리지 않도록 새 dict 로 만들어 돌려준다.
    """
    guide = next((g for g in PREP_GUIDES if g["id"] == node_id), None)
    if guide is None:
        return None

    fmt = {"label": target["label"], "transport": target["transport"],
           "target_id": target["id"],
           "first_quiz": QUIZ_TOPICS[0]["id"] if QUIZ_TOPICS else ""}

    def fill(text):
        return text.format(**fmt)

    sections = []
    for sec in guide["sections"]:
        item = {"heading": sec["heading"]}
        if "body" in sec:
            item["body"] = fill(sec["body"])
        if "steps" in sec:
            item["steps"] = [fill(s) for s in sec["steps"]]
        sections.append(item)

    out = {"id": guide["id"], "title": guide["title"], "tag": guide["tag"],
           "meta": fill(guide["meta"]), "sections": sections}
    if "action" in guide:
        out["action"] = {"label": guide["action"]["label"],
                         "url": fill(guide["action"]["url"])}
    return out


# --------------------------------------------------------------------------- #
# 메시지 작성 실습 — CAN/DoIP 프레임 조립 (주제별 코스)
#
# 좌측 트리는 UDS 서비스 분류표가 아니라 **실제 진단 순서**를 담는다. 주제마다
# 필요한 단계만 밟되, 규격·실차 로그상 빠뜨릴 수 없는 단계는 채워 넣는다:
#   센서 리딩   읽기(0x22) 자체가 없으면 코스가 성립하지 않음
#   DTC        소거(0x14) 뒤 재조회로 실제로 지워졌는지 확인해야 함
#   강제 구동   제어 반환(옵션 0x00)까지 해야 ECU 가 제어권을 되찾음
#              — BDC-BCM 로그의 `2F F0 88 03` / `2F F0 88 00` 쌍이 근거
#   데이터 쓰기 보안 접근(0x27) 없이는 NRC 0x33, 쓴 뒤 0x22 로 검증
#              — 로그에서도 `27 11`/`27 12` 직후에야 `2E 12 A0` 이 나온다
#
# 어드레싱: 응답 ID = 요청 ID + 8 (사양서·로그 공통). RC카 0x7E0/0x7E8 은
# mock_rci 의 F1A0(제어기 CAN ID = 07 E0) 기준. UR 은 DoIP 라 CAN 층이 없다.
# 필러 바이트는 방향에 따라 갈린다 — 요청 0x55 / 응답 0xAA (BDC-BCM 18,918줄 전량 일관).
# --------------------------------------------------------------------------- #

# CAN 층 어드레싱. transport != "CAN" 이면 프레임 조립기는 CAN 층을 접는다.
MSG_ADDR = {
    "rc-car": {"req": "000007E0", "resp": "000007E8", "fill_req": "55", "fill_resp": "AA"},
    "ur-robot": {"req": None, "resp": None, "fill_req": None, "fill_resp": None},
}


def _sp(did):
    """"0101" → "01 01" (조립 템플릿은 바이트 단위 공백 구분 — 계약 §표기 규칙)."""
    return f"{did[:2]} {did[2:]}"


def _did_opts(pairs):
    return [{"v": _sp(d), "t": f"0x{d} · {n}"} for d, n in pairs]


# 0x22 읽기 DID (mock_rci.DIDS 와 일치 — 실제로 응답이 돌아오는 값만).
_READ_DIDS = {
    "rc-car": [("0101", "초음파 거리"), ("0102", "배터리 전압"), ("0103", "온도"),
               ("0104", "습도"), ("0105", "조도"), ("0106", "서보 각도"),
               ("0107", "LED 상태"), ("0108", "부저 상태"),
               ("F195", "SW 버전"), ("F199", "SW 날짜"), ("F1A0", "제어기 CAN ID")],
    "ur-robot": [("0101", "조인트 각도"), ("0103", "조인트 온도"), ("0104", "조인트 전류"),
                 ("0107", "로봇 모드"), ("0108", "안전 모드"), ("010A", "전압"),
                 ("010B", "전류"), ("0111", "진동"), ("F195", "SW 버전"), ("F1A0", "로봇 IP")],
}
# 0x2F 강제구동 DID (0x02xx 대역 — 계약 §DID 대역).
_CTRL_DIDS = {
    "rc-car": [("0201", "모터"), ("0202", "서보"), ("0207", "조명"), ("0208", "부저"),
               ("0209", "MP3 사운드")],
    "ur-robot": [("0201", "조인트 구동"), ("0203", "그리퍼")],
}
# 0x2E 쓰기 DID. F195 는 mock 이 NRC 0x31 로 거부한다 — 거부 사례 시연용으로 남겨둔다.
_WRITE_DIDS = {
    "rc-car": [("F1A0", "제어기 CAN ID"), ("0106", "서보 각도"), ("F195", "SW 버전 · 쓰기 거부")],
    "ur-robot": [("F1A0", "로봇 IP"), ("F195", "SW 버전 · 쓰기 거부")],
}
# 학습용 Seed 길이 (mock_rci.SECURITY 와 일치).
_SEED_LEN = {"rc-car": 2, "ur-robot": 4}


def _choice(name, label, opts, default):
    return {"name": name, "label": label, "kind": "choice", "options": opts, "default": default}


def _hex(name, label, default, hint=""):
    return {"name": name, "label": label, "kind": "hex", "default": default, "hint": hint}


def _act(label, tpl, resp, primary=True):
    """전송 액션 1건. tpl/resp 의 `{필드명}` 은 브라우저에서 현재 필드값으로 치환된다."""
    return {"label": label, "tpl": tpl, "resp": resp, "primary": primary}


def _st_open():
    return {
        "sid": "10", "service": "DiagnosticSessionControl",
        "fields": [_choice("session", "세션 유형", [
            {"v": "01", "t": "기본 01 Default"},
            {"v": "02", "t": "프로그래밍 02 Programming"},
            {"v": "03", "t": "확장 03 Extended"}], "03")],
        "actions": [_act("세션 오픈 전송 →", "10 {session}", "50 {session} 00 32 01 F4")],
        "hint": "강제구동(0x2F)·쓰기(0x2E)는 확장 세션(03)에서만 허용된다. "
                "응답 뒤 4바이트는 타이밍 파라미터 — P2 = 0x0032 = 50ms, P2* = 0x01F4 × 10ms = 5000ms.",
        "ref": "실차 로그 · 02 10 03 → 06 50 03 00 32 01 F4",
    }


def _st_tp():
    return {
        "sid": "3E", "service": "TesterPresent", "keepalive": True,
        "fields": [_choice("sup", "응답 요구 여부", [
            {"v": "00", "t": "응답 요구 00"},
            {"v": "80", "t": "응답 억제 80"}], "00")],
        "actions": [_act("1회 전송 →", "3E {sup}", "7E 00")],
        "hint": "발행이 끊기면 5초 후 기본 세션으로 되돌아간다(계약 §표기·처리 규칙). "
                "서브펑션 0x80 은 suppressPosRspMsgIndicationBit — 응답을 보내지 않는다.",
        "ref": "실차 로그 · 7A0: 02 3E 00 → 02 7E 00 / BDC(5D0): 02 3E 80 (응답 없음)",
    }


def _st_close():
    return {
        "sid": "10", "service": "DiagnosticSessionControl",
        "fields": [],
        "actions": [_act("기본 세션 복귀 →", "10 01", "50 01 00 32 01 F4")],
        "hint": "실습을 끝낼 때는 기본 세션으로 되돌린다. 강제구동을 켜둔 채 종료하면 "
                "제어권이 ECU 로 돌아가지 않은 상태가 될 수 있다.",
        "ref": "요청 SID 0x10 · 서브펑션 0x01 Default",
    }


def _st_sec(target):
    n = _SEED_LEN[target["id"]]
    zeros = " ".join(["00"] * n)
    return {
        "sid": "27", "service": "SecurityAccess", "seedkey": True,
        "fields": [_hex("key", f"Key ({n}바이트)", zeros,
                        "Seed 응답이 오면 자동 계산되어 채워진다")],
        "actions": [
            _act("① Seed 요청 →", "27 01", "67 01 " + " ".join(["<Seed>"] * n)),
            _act("② Key 전송 →", "27 02 {key}", "67 02", primary=False),
        ],
        "hint": "Seed 를 받아 Key 를 계산해 되돌려야 잠금이 풀린다. Key 가 틀리면 NRC 0x35 "
                "invalidKey, 시도 횟수를 넘기면 0x36. 보안 없이 쓰기·강제구동을 시도하면 0x33.",
        "ref": "실차 로그 · 02 27 11 → 10 0A 67 11 C7 BB B8 E3 + 21 DE A6 DA 55 "
               "(레벨 0x11/0x12, Seed 8바이트, 멀티프레임)",
    }


def _st_read(target, name="센서"):
    return {
        "sid": "22", "service": "ReadDataByIdentifier",
        "fields": [_choice("did", f"{name} DID", _did_opts(_READ_DIDS[target["id"]]), "01 05"
                           if target["id"] == "rc-car" else "01 01")],
        "actions": [_act("읽기 요청 →", "22 {did}", "62 {did} <데이터>")],
        "hint": "응답 SID 0x62 뒤에 요청한 DID 가 그대로 되돌아오고, 그 뒤가 데이터다. "
                "다바이트 값은 빅엔디안이고 int16 음수는 2의 보수(계약 §표기 규칙).",
        "ref": "실차 로그 · 03 22 B0 01 → 10 22 62 B0 01 … (응답 34바이트 = 멀티프레임)",
    }


def _st_dtc_read(title_hint):
    return {
        "sid": "19", "service": "ReadDTCInformation",
        "fields": [
            _choice("sf", "서브펑션", [
                {"v": "01", "t": "01 개수만"},
                {"v": "02", "t": "02 상태마스크로 조회"}], "02"),
            _hex("mask", "상태 마스크", "08", "0x08 = confirmedDTC (확정 고장만)"),
        ],
        "actions": [_act("DTC 조회 →", "19 {sf} {mask}",
                         "59 {sf} <마스크> <DTC> <DTC> <DTC> <상태>")],
        "hint": title_hint,
        "ref": "실차 로그 · 03 19 02 08 → 03 7F 19 78 (처리 중) → 03 59 02 08 (고장 없음)",
    }


def _st_dtc_clear():
    return {
        "sid": "14", "service": "ClearDiagnosticInformation",
        "fields": [_hex("group", "고장 그룹", "FF FF FF", "0xFFFFFF = 전체 그룹")],
        "actions": [_act("DTC 소거 →", "14 {group}", "54")],
        "hint": "소거는 되돌릴 수 없다. 구동 조건이 맞지 않으면 NRC 0x22 conditionsNotCorrect 로 거부된다.",
        "ref": "BDC-BCM 로그에는 0x14 프레임이 없음 — ISO 14229 규격에서 유도한 프레임",
    }


def _st_force(target):
    return {
        "sid": "2F", "service": "InputOutputControlByIdentifier",
        "fields": [
            _choice("did", "제어 대상 DID", _did_opts(_CTRL_DIDS[target["id"]]), "02 07"
                    if target["id"] == "rc-car" else "02 01"),
            _hex("value", "강제값", "01", "옵션 0x03 일 때만 쓰인다"),
        ],
        "actions": [
            _act("강제 구동 (03 단기조정) →", "2F {did} 03 {value}", "6F {did} 03 {value}"),
            _act("제어 반환 (00) →", "2F {did} 00", "6F {did} 00", primary=False),
        ],
        "hint": "제어 옵션 — 00 제어권 반환 · 01 기본값 리셋 · 02 현재값 고정 · 03 단기 조정. "
                "구동 후 반드시 00 으로 제어권을 ECU 에 돌려줘야 한다. 주변 안전을 먼저 확인할 것.",
        "ref": "실차 로그 · 04 2F F0 88 03 → 04 6F F0 88 03, 반환 04 2F F0 88 00 → 04 6F F0 88 00 "
               "(지원하지 않는 옵션은 NRC 0x12 — 로그에 19회 등장)",
    }


def _st_write(target):
    return {
        "sid": "2E", "service": "WriteDataByIdentifier",
        "fields": [
            _choice("did", "쓰기 대상 DID", _did_opts(_WRITE_DIDS[target["id"]]), "F1 A0"),
            _hex("value", "쓸 값", "07 E0", "DID 별 데이터 길이에 맞춰 입력"),
        ],
        "actions": [_act("쓰기 요청 →", "2E {did} {value}", "6E {did}")],
        "hint": "긍정 응답은 SID 와 DID 만 돌아온다(데이터 없음). 보안 해제 전이면 NRC 0x33, "
                "쓰기 금지 항목이면 0x31 requestOutOfRange.",
        "ref": "실차 로그 · 05 2E 12 A0 0D 01 → 03 6E 12 A0",
    }


def message_scenarios(target):
    """주제별 실습 코스. 각 코스 = 세션 오픈부터 종료까지의 단계 목록."""
    return [
        {"id": "read", "title": "센서 리딩", "steps": [
            {"id": "read-open", "title": "① 세션 오픈 (10)", "spec": _st_open()},
            {"id": "read-tp", "title": "② 세션 유지 (3E)", "spec": _st_tp()},
            {"id": "read-did", "title": "③ 센서 데이터 읽기 (22)", "spec": _st_read(target)},
            {"id": "read-close", "title": "④ 세션 종료 (10 01)", "spec": _st_close()},
        ]},
        {"id": "dtc", "title": "DTC 조회·소거", "steps": [
            {"id": "dtc-open", "title": "① 세션 오픈 (10)", "spec": _st_open()},
            {"id": "dtc-tp", "title": "② 세션 유지 (3E)", "spec": _st_tp()},
            {"id": "dtc-read", "title": "③ DTC 조회 (19)", "spec": _st_dtc_read(
                "저장된 고장코드를 읽는다. 응답의 4바이트 레코드는 3바이트 DTC + 1바이트 상태다. "
                "NRC 0x78 이 먼저 오면 '처리 중'이고 같은 id 로 최종 응답이 뒤따른다.")},
            {"id": "dtc-clear", "title": "④ DTC 소거 (14)", "spec": _st_dtc_clear()},
            {"id": "dtc-verify", "title": "⑤ DTC 재조회 · 소거 검증 (19)", "spec": _st_dtc_read(
                "소거가 실제로 반영됐는지 같은 요청을 다시 보내 확인한다. 레코드 없이 "
                "마스크만 돌아오면(예 `59 02 08`) 남은 고장이 없다는 뜻이다.")},
            {"id": "dtc-close", "title": "⑥ 세션 종료 (10 01)", "spec": _st_close()},
        ]},
        {"id": "force", "title": "강제 구동", "steps": [
            {"id": "force-open", "title": "① 세션 오픈 (10)", "spec": _st_open()},
            {"id": "force-tp", "title": "② 세션 유지 (3E)", "spec": _st_tp()},
            {"id": "force-sec", "title": "③ 보안 접근 (27)", "spec": _st_sec(target)},
            {"id": "force-drive", "title": "④ 강제 구동 · 제어 반환 (2F)", "spec": _st_force(target)},
            {"id": "force-close", "title": "⑤ 세션 종료 (10 01)", "spec": _st_close()},
        ]},
        {"id": "write", "title": "데이터 쓰기", "steps": [
            {"id": "write-open", "title": "① 세션 오픈 (10)", "spec": _st_open()},
            {"id": "write-tp", "title": "② 세션 유지 (3E)", "spec": _st_tp()},
            {"id": "write-sec", "title": "③ 보안 접근 (27)", "spec": _st_sec(target)},
            {"id": "write-do", "title": "④ 데이터 쓰기 (2E)", "spec": _st_write(target)},
            {"id": "write-verify", "title": "⑤ 쓰기 검증 읽기 (22)", "spec": _st_read(target, "검증")},
            {"id": "write-close", "title": "⑥ 세션 종료 (10 01)", "spec": _st_close()},
        ]},
    ]


# --------------------------------------------------------------------------- #
# 진단·실습 자동 시퀀스 (진단 · 강제구동 · ECU 업그레이드)
#
# 이 세 카테고리는 버튼 하나로 끝나는 동작이 아니다. 실제로는 위 '메시지 작성' 코스에서
# 사람이 한 단계씩 밟는 순서 — 세션 오픈 → 세션 유지 → (보안 접근) → 본 동작 →
# 제어권·세션 정리 — 를 그대로 밟아야 한다. 여기서는 그 순서를 서버가 정의하고,
# 브라우저가 1초 간격으로 자동 수행하며 왕복을 통신 로그에 보여준다.
#
# 순서만 서버에 둔다. 실행·페이싱·실패 정책은 브라우저(static/js/auto-sequence.js) 몫이다
# — 응답은 서버를 거치지 않고 브라우저가 MQTT 로 직접 받기 때문이다(step-progress.js 가
# 단계 통과를 브라우저에서 판정하는 것과 같은 이유).
#
# 단계 필드
#   title    중앙 stepper 에 그려지는 이름
#   raw      보낼 UDS 페이로드. kind 가 "key"/"ka_stop" 이면 None (브라우저가 만든다)
#   expect   기대 응답 접두 hex ("50", "67 01", "76 02" …). 판정은 브라우저가 한다
#   note     왕복 뒤 로그에 덧붙일 한 줄 설명 (교육용 — 왜 이 단계가 필요한가)
#   kind     ka_start 세션 유지 반복 발행 시작 · ka_stop 중지
#            seed     보안 Seed 요청 (응답에서 Seed 를 꺼내 다음 단계에 넘긴다)
#            key      앞 단계 Seed 로 계산한 Key 전송 (raw 를 브라우저가 만든다)
#   critical True 면 실패 시 어느 모드에서든 중단한다 (뒤 단계가 성립하지 않으므로)
#   hold_ms  이 단계 뒤에 더 쉬는 시간 (구동 상태를 눈으로 확인하라고)
# --------------------------------------------------------------------------- #

# 진단 카테고리 — 트리 잎(센서) → 읽을 DID. mock_rci.DIDS 에 실제로 있는 값만.
_DIAG_DID = {
    "rc-cds": ("01 05", "CDS 조도"),
    "rc-ultra": ("01 01", "초음파 거리"),
    "rc-temp": ("01 03", "온도"),
    "ur-joint": ("01 01", "조인트 각도"),
    "ur-power": ("01 0A", "로봇 전압"),
    "ur-vib": ("01 11", "진동"),
}
# 강제구동 카테고리 — 트리 잎 → (제어 DID, 강제값, 표시 이름).
_FORCE_DID = {
    "rc-motor": ("02 01", "3C", "모터 60%"),
    "rc-servo": ("02 02", "5A", "서보 90도"),
    "rc-led": ("02 07", "01", "전조등 ON"),
    "rc-buzzer": ("02 08", "01", "부저 ON"),
    "rc-mp3": ("02 09", "01", "MP3 재생"),
    "ur-joint-drive": ("02 01", "3C", "조인트 구동"),
}
# ECU 업그레이드 — 전송할 더미 블록. 실제 펌웨어가 아니라 카운터 흐름을 보이는 용도다.
_ECU_BLOCKS = ["36 01 A5 5A 00 01", "36 02 A5 5A 00 02", "36 03 A5 5A 00 03"]


def _sq(title, raw, expect, note, **kw):
    step = {"title": title, "raw": raw, "expect": expect, "note": note}
    step.update(kw)
    return step


def _sq_open(session, why):
    """세션 오픈 + 세션 유지 발행 시작 — 모든 시퀀스의 앞머리."""
    return [
        _sq(f"진단 세션 오픈 (10 {session})", f"10 {session}", f"50 {session}",
            f"{why} 응답 뒤 4바이트는 타이밍 파라미터다 — P2 50ms · P2* 5000ms.",
            critical=True),
        _sq("세션 유지 발행 시작 (3E 00)", "3E 00", "7E",
            "여기서부터 2초 주기로 3E 를 계속 보낸다. 발행이 끊기면 5초 뒤 ECU 가 "
            "스스로 기본 세션으로 되돌아가 뒤 단계가 거부된다.",
            kind="ka_start"),
    ]


def _sq_sec(target):
    """보안 접근 Seed → Key. Key 계산은 브라우저가 한다(Seed 를 받아야 알 수 있으므로)."""
    n = _SEED_LEN[target["id"]]
    return [
        _sq("보안 Seed 요청 (27 01)", "27 01", "67 01",
            f"ECU 가 {n}바이트 Seed 를 준다. 실차에서는 매 세션 달라진다.", kind="seed"),
        _sq("보안 Key 전송 (27 02)", None, "67 02",
            "받은 Seed 로 Key 를 계산해 되돌린다(학습용 알고리즘: 각 바이트 + 0x44). "
            "틀리면 NRC 0x35, 이 단계를 건너뛰면 뒤 동작이 NRC 0x33 으로 거부된다.",
            kind="key", critical=True),
    ]


def _sq_close(what):
    """세션 유지 중지 + 기본 세션 복귀 — 모든 시퀀스의 마무리."""
    return [
        _sq("세션 유지 발행 중지", None, None,
            "반복 발행을 멈춘다. 이대로 두면 5초 뒤 자동으로 기본 세션이 된다.",
            kind="ka_stop"),
        _sq("기본 세션 복귀 (10 01)", "10 01", "50 01",
            f"{what} — 자동 복귀를 기다리지 않고 명시적으로 되돌린다."),
    ]


def _seq_diag(target, leaf):
    did, label = _DIAG_DID.get(
        leaf, ("01 05", "센서") if target["id"] == "rc-car" else ("01 01", "센서"))
    return {
        "id": "diag", "title": f"{label} 진단 시퀀스", "danger": False,
        "steps": _sq_open("03", "읽기(0x22) 자체는 기본 세션에서도 되지만, 진단은 확장 세션(03)을 "
                                "연 상태에서 진행하는 것이 실차 절차다.")
        + [
            # 요청한 DID 가 그대로 돌아왔는지까지 본다 — 엉뚱한 센서값을 읽고
            # 넘어가면 진단이 성립하지 않는다.
            _sq(f"{label} 값 읽기 (22 {did})", f"22 {did}", f"62 {did}",
                "응답 0x62 뒤에 요청한 DID 가 그대로 오고, 그 뒤가 데이터다. "
                "물리값 해석은 아래 ↳ 줄에 붙는다."),
            _sq("고장코드 조회 (19 02 08)", "19 02 08", "59 02",
                "센서값이 정상이어도 과거 고장이 남아 있을 수 있다. 마스크 0x08 = 확정 고장만."),
        ]
        + _sq_close("진단 종료"),
    }


def _seq_force(target, leaf):
    did, val, label = _FORCE_DID.get(
        leaf, ("02 01", "3C", "구동") if target["id"] == "rc-car" else ("02 01", "3C", "조인트 구동"))
    return {
        "id": "force", "title": f"{label} 강제구동 시퀀스", "danger": True,
        "steps": _sq_open("03", "강제구동(0x2F)은 확장 세션(03)에서만 허용된다.")
        + _sq_sec(target)
        + [
            # 제어 옵션까지 맞춰 본다 — 0x03 을 요청했는데 0x00 이 돌아오면
            # 구동된 것이 아니라 제어권이 반환된 것이다.
            _sq(f"강제 구동 (2F {did} 03)", f"2F {did} 03 {val}", f"6F {did} 03",
                f"{label} · 제어 옵션 0x03 단기 조정. 긍정 응답은 요청을 그대로 되돌려준다.",
                hold_ms=2000),
            _sq(f"제어권 반환 (2F {did} 00)", f"2F {did} 00", f"6F {did} 00",
                "옵션 0x00 으로 제어권을 ECU 에 돌려준다. 이 단계를 빠뜨리면 ECU 가 "
                "강제값을 계속 물고 있는다 — 실차 로그의 `2F F0 88 03` / `2F F0 88 00` 쌍이 그것이다."),
        ]
        + _sq_close("강제구동 종료"),
    }


def _seq_ecu(target):
    steps = (
        _sq_open("02", "리프로그래밍은 프로그래밍 세션(02)에서만 가능하다.")
        + _sq_sec(target)
        + [
            _sq("다운로드 요청 (34)", "34 00 44 00 00 10 00 00 00 20 00", "74",
                "형식 0x00(무압축·무암호) · 주소/길이 형식 0x44(각 4바이트). 응답 "
                "`74 20 0F FF` 의 0x0FFF 가 한 블록 최대 길이다.", critical=True),
        ]
    )
    for i, blk in enumerate(_ECU_BLOCKS, start=1):
        steps.append(_sq(
            f"블록 전송 {i}/{len(_ECU_BLOCKS)} (36 {i:02X})", blk, f"76 {i:02X}",
            "블록 카운터는 01 부터 1씩 오른다. 같은 번호로 응답이 와야 다음 블록을 보낸다.",
            critical=True))
    steps += [
        _sq("전송 종료 (37)", "37", "77", "더 보낼 블록이 없음을 알린다.", critical=True),
        _sq("무결성 검증 (31 01 FF 01)", "31 01 FF 01", "71 01 FF 01",
            "checkProgrammingDependencies — 체크섬·의존성 검사. 여기서 실패하면 "
            "리셋하면 안 된다(반쯤 쓰인 펌웨어로 부팅한다).", critical=True),
        _sq("세션 유지 발행 중지", None, None,
            "리셋 전에 멈춘다 — 어차피 리셋되면 세션은 사라진다.", kind="ka_stop"),
        _sq("ECU 리셋 (11 01)", "11 01", "51 01",
            "hardReset. 재기동하면 새 펌웨어로 올라온다.", hold_ms=1500),
    ]
    return {"id": "ecu", "title": "ECU 리프로그래밍 시퀀스", "danger": True, "steps": steps}


def auto_sequence(content_id, target, selected):
    """카테고리(+선택 잎)별 자동 시퀀스. 해당 없으면 None."""
    leaf = selected["id"] if selected else None
    if content_id == "diag":
        return _seq_diag(target, leaf)
    if content_id == "force":
        return _seq_force(target, leaf)
    if content_id == "ecu":
        return _seq_ecu(target)
    return None


# --------------------------------------------------------------------------- #
# 작성 참고 자료 (읽기 전용)
#
# 메시지 작성 화면의 주역은 '사용자가 직접 타이핑하는 프레임 입력창'이다. 아래 자료는
# 그 아래에 깔리는 참고표 — 무엇을 쓸 수 있는지 알려주기만 하고 조작하지 않는다.
# (칩을 눌러 프레임을 자동 조립하는 방식은 진단·강제구동 화면의 성격이다.)
# --------------------------------------------------------------------------- #

# 프레임 층. example 은 대상별 CAN ID 를 끼워 넣어 템플릿에서 완성한다.
MSG_LAYERS = [
    ("CAN ID", "식별자. 응답 = 요청 + 8", "{req} → {resp}"),
    ("DLC", "데이터 길이 코드. CAN Classic 이라 항상 8 (남는 칸은 패딩)", "8"),
    ("PCI", "ISO-TP 제어정보. 단일 0L · 첫 1L LL · 연속 2N · 흐름제어 30 BS STmin", "02"),
    ("UDS", "SID + 서브펑션·DID·데이터 — 이 부분만 실제로 전송된다", "10 03"),
    ("필러", "8칸을 채우는 패딩. 방향에 따라 값이 다르다", "요청 55 / 응답 AA"),
]

# NRC. 실차 로그(BDC-BCM.txt)에 실제로 등장한 것을 등장 횟수 순으로 앞세운다.
MSG_NRC = [
    ("12", "subFunctionNotSupported", "지원하지 않는 서브펑션·제어옵션", "로그 19회"),
    ("31", "requestOutOfRange", "DID·값이 범위 밖", "로그 11회"),
    ("22", "conditionsNotCorrect", "구동 조건 불충족", "로그 10회"),
    ("11", "serviceNotSupported", "지원하지 않는 서비스", "로그 1회"),
    ("78", "responsePending", "처리 중 — 같은 id 로 최종 응답이 뒤따름", "로그 1회"),
    ("33", "securityAccessDenied", "보안 해제 전 쓰기·강제구동 시도", ""),
    ("35", "invalidKey", "Key 불일치", ""),
    ("13", "incorrectMessageLengthOrInvalidFormat", "길이·포맷 오류", ""),
]

# 부정 응답 형식 (모든 서비스 공통).
MSG_NEGATIVE = "7F <요청 SID> <NRC>"


def _subst(tpl, values):
    """"22 {did}" + {did: "01 05"} → "22 01 05"."""
    return re.sub(r"\{(\w+)\}", lambda m: values.get(m.group(1), ""), tpl or "").strip()


def frame_text(payload, addr, resp=False):
    """UDS 페이로드 → 참고용 프레임 한 줄. CAN 층이 없으면(DoIP) 페이로드 그대로.

    8바이트를 넘기면 멀티프레임이라 한 줄로 못 적는다 — 첫 프레임만 보이고 뒤는 생략한다.
    """
    can_id = addr["resp"] if resp else addr["req"]
    filler = addr["fill_resp"] if resp else addr["fill_req"]
    if not can_id:
        return payload
    b = payload.split()
    if len(b) > 7:
        pci = f"1{len(b) >> 8:X} {len(b) & 0xFF:02X}"
        return f"{can_id}  8  {pci}  " + " ".join(b[:6]) + "  ⋯ 이후 연속 프레임"
    pad = " ".join([filler] * (7 - len(b)))
    return f"{can_id}  8  {len(b):02X}  " + " ".join(b) + (f"  {pad}" if pad else "")


def step_examples(spec, addr):
    """단계 규격의 액션 템플릿에 필드 기본값을 대입해 '이렇게 쓰면 된다' 예시로 바꾼다.

    자동 조립기였을 때는 전송 대상이었지만, 이제는 사용자가 입력창에 손으로 옮겨 적을
    본보기다. 그래서 UDS 만이 아니라 프레임 한 줄 전체를 보여준다.
    """
    values = {f["name"]: f["default"] for f in spec["fields"]}
    out = []
    for a in spec["actions"]:
        req = _subst(a["tpl"], values)
        resp = _subst(a["resp"], values)
        out.append({
            "label": a["label"].replace(" →", ""),
            "uds": req,
            "frame": frame_text(req, addr),
            "resp": resp,
            "resp_frame": frame_text(resp, addr, resp=True) if "<" not in resp else resp,
        })
    return out


def find_step(scenarios, item_id):
    """잎 id → (코스, 단계, 1기반 순번, 코스 단계수). 못 찾으면 첫 코스의 첫 단계."""
    for sc in scenarios:
        for i, st in enumerate(sc["steps"]):
            if st["id"] == item_id:
                return sc, st, i + 1, len(sc["steps"])
    sc = scenarios[0]
    return sc, sc["steps"][0], 1, len(sc["steps"])


# --------------------------------------------------------------------------- #
# 브라우저 직결 MQTT 접속 정보
#
# 브라우저는 서버측 브리지(mqtt_bridge)와 별개로 WebSocket 으로 브로커에 직접 붙는다.
# RCI 측과 연동 테스트할 때 브로커가 로컬이 아닐 수 있으므로 하드코딩하지 않는다.
# 자격증명(username/password)은 **의도적으로 내려보내지 않는다** — HTML 은 누구나
# 볼 수 있다. 인증이 필요한 브로커라면 서버측 경로(`/api/diag/{device}/request`,
# 환경변수 RCI_BROKER_USERNAME/PASSWORD)를 쓰거나 별도 제한 계정을 발급할 것.
# --------------------------------------------------------------------------- #


def browser_ws_url():
    """브라우저가 붙을 ws(s):// URL. RCI_WS_URL 이 있으면 그대로 쓴다."""
    override = os.environ.get("RCI_WS_URL")
    if override:
        return override
    tls = os.environ.get("RCI_BROKER_WS_TLS", "").lower() in ("1", "true", "yes", "on")
    port = os.environ.get("RCI_BROKER_WS_PORT", "8081" if tls else "8080")
    path = os.environ.get("RCI_BROKER_WS_PATH", "/mqtt")

    host = os.environ.get("RCI_BROKER_WS_HOST")
    if not host:
        # RCI_BROKER_HOST 로 폴백하되 루프백은 거른다. 그 변수는 '서버 → 브로커'
        # 주소라 기본값이 127.0.0.1 인데, 그걸 그대로 내려보내면 브라우저에겐
        # '태블릿 자기 자신'이 되어 조용히 접속 실패한다. 서버에서의 localhost 와
        # 브라우저에서의 localhost 는 다른 기계다.
        # 거르면 아래에서 "" 를 돌려주고, 클라이언트가 현재 접속 호스트로 폴백한다
        # (static/js/rci-live.js — ws://location.hostname:8080/mqtt). 태블릿이
        # http://172.20.10.3:8123 으로 들어왔다면 그게 정확히 맞는 주소다.
        # (RCI_BROKER_WS_HOST 를 명시했다면 의도한 것으로 보고 그대로 쓴다.)
        candidate = os.environ.get("RCI_BROKER_HOST", "")
        host = "" if candidate in ("127.0.0.1", "localhost", "::1", "0.0.0.0") else candidate

    if not host:
        return ""          # 빈 값 → 클라이언트가 현재 접속 호스트로 폴백
    return f"{'wss' if tls else 'ws'}://{host}:{port}{path}"


def get_target(target_id):
    """경로의 target_id에 해당하는 대상 반환 (없으면 첫 대상으로 폴백)."""
    return next((t for t in TARGETS if t["id"] == target_id), TARGETS[0])


def get_content(content_id):
    return next((c for c in CONTENTS if c["id"] == content_id), None)


def content_title(content, target):
    """대상에 따라 달라지는 콘텐츠 제목 (메시지 작성 = CAN/DoIP 접두)."""
    if content["id"] == "message":
        return f"{target['transport']} 메시지 작성"
    return content["title"]


def content_icon(content, target):
    """강제구동은 대상별로 아이콘이 다르다 (RC=자동차 / UR=로봇팔)."""
    if content["id"] == "force" and target["id"] == "ur-robot":
        return "robotarm"
    return content["icon"]


def content_tree(content_id, target):
    """콘텐츠·대상별 세부 항목 트리. 중첩 가능({children}). 깊이는 콘텐츠마다 다름."""
    t = target["id"]
    if content_id == "prep":
        return [{"id": g["id"], "title": g["title"]} for g in PREP_GUIDES]
    # quiz 는 이 트리를 쓰지 않는다 — 주제 목록을 QUIZ_TOPICS 에서 직접 렌더한다.
    if content_id == "diag":
        sensors = ([{"id": "rc-cds", "title": "CDS 조도센서 진단"},
                    {"id": "rc-ultra", "title": "초음파 센서"},
                    {"id": "rc-temp", "title": "온습도 센서"}]
                   if t == "rc-car" else
                   [{"id": "ur-joint", "title": "조인트 각도·속도·온도·전류"},
                    {"id": "ur-power", "title": "로봇 전압·전류"},
                    {"id": "ur-vib", "title": "진동센서"}])
        return [{"id": "sensor-diag", "title": "센서데이터 진단", "children": sensors}]
    if content_id == "force":
        return ([{"id": "rc-motor", "title": "모터"},
                 {"id": "rc-servo", "title": "서보"},
                 {"id": "rc-led", "title": "LED"},
                 {"id": "rc-buzzer", "title": "부저"},
                 {"id": "rc-mp3", "title": "MP3 가상 사운드"}]
                if t == "rc-car" else
                [{"id": "ur-joint-drive", "title": "조인트 자세·위치·각도·속도"}])
    if content_id == "message":
        # UDS 서비스 분류가 아니라 주제별 실습 코스 = 실제 진단 순서 (MSG 블록 참조).
        return [{"id": sc["id"], "title": sc["title"],
                 "children": [{"id": st["id"], "title": st["title"]} for st in sc["steps"]]}
                for sc in message_scenarios(target)]
    return []


def find_leaf(nodes, item_id):
    """중첩 트리에서 item_id에 해당하는 잎(children 없는 노드)을 재귀로 찾는다.

    item_id가 없거나 트리에 없으면 '가장 먼저 만나는 잎'으로 폴백. 잎이 없으면 None.
    (평면 리스트용 로직의 트리 확장판 — 일치 잎과 첫 잎을 한 번의 DFS로 처리.)
    """
    first = None

    def walk(ns):
        nonlocal first
        for n in ns:
            if n.get("children"):
                hit = walk(n["children"])
                if hit is not None:
                    return hit
            else:
                if first is None:
                    first = n
                if item_id is not None and n["id"] == item_id:
                    return n
        return None

    match = walk(nodes)
    return match if match is not None else first


def status_text(target):
    """상단 상태 라벨의 **앞부분만** 돌려준다.

    뒤의 연결 여부("연결됨"/"연결안됨")는 서버가 알 수 없다 — 브라우저가 브로커에
    직접 붙기 때문이다(계약 §전송). 서버가 문구를 굳혀 두면 브로커·RCI 가 죽어
    있어도 '연결됨' 이라고 거짓말을 하게 된다. 그 부분은 link-status.js 가 채운다.
    """
    return f"대상 · {target['status']}"


def make_crumbs(target, section, title, leaf_title=None):
    """서브바 브레드크럼(섹션 › 콘텐츠 › 세부) 구성. 섹션은 그리드로 되돌아가는 링크."""
    crumbs = [
        {"text": section, "tier": "section", "href": f"/{target['id']}"},
        {"text": title, "tier": "content"},
    ]
    if leaf_title:
        crumbs.append({"text": leaf_title, "tier": "leaf"})
    return crumbs


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    """Step1 · 대상 선택 (RC Car / UR Robot)."""
    return templates.TemplateResponse(
        request, "index.html", {"targets": TARGETS, "bottom_nav": BOTTOM_NAV},
    )


@app.get("/search", response_class=HTMLResponse)
def search(request: Request, q: str | None = None):
    """통합 검색 — 현재 플레이스홀더."""
    return templates.TemplateResponse(
        request, "search.html", {"query": q or "", "bottom_nav": BOTTOM_NAV},
    )


# --------------------------------------------------------------------------- #
# MQTT API — 반드시 아래 `/{target_id}` 캐치올보다 **먼저** 선언해야 한다.
# Starlette 은 선언 순서대로 첫 일치를 쓰므로, 뒤에 두면 /api/health 가
# 대상 그리드 페이지로 잡아먹힌다.
# --------------------------------------------------------------------------- #


class DiagRequest(BaseModel):
    """`POST /api/diag/{device}/request` 본문 (계약 §요청 페이로드)."""

    raw: str = Field(..., examples=["22 01 07"], description="UDS 요청 hex")
    timeout_ms: int = Field(1000, ge=50, le=60_000)


@app.get("/api/health")
def api_health():
    """브로커 연결 상태 + 마지막으로 받은 RCI 생존 상태(retained)."""
    return bridge.health()


@app.get("/api/status/{device}")
def api_status(device: str):
    status = bridge.status_of(device)
    if status is None:
        raise HTTPException(404, f"{device} 상태 미수신 (RCI 가 아직 status 를 발행하지 않음)")
    return status


@app.post("/api/diag/{device}/request")
async def api_diag_request(device: str, body: DiagRequest):
    """웹 → RCI 로 UDS 요청을 발행하고 같은 id 의 응답을 기다려 그대로 돌려준다.

    raw 디코딩(물리값·NRC 이름)은 계약상 웹앱 몫이지만, 이 엔드포인트는 연결
    검증용이라 계약 페이로드를 가공 없이 노출한다 — 무엇이 오갔는지가 보여야 한다.
    """
    try:
        return await bridge.request(device, body.raw, body.timeout_ms)
    except ValueError as exc:                       # raw 표기 오류
        raise HTTPException(400, str(exc)) from None
    except RequestTimeout as exc:
        raise HTTPException(504, str(exc)) from None
    except BridgeError as exc:                      # 미연결·알 수 없는 device·발행 실패
        raise HTTPException(503, str(exc)) from None


@app.get("/api/events")
async def api_events(request: Request):
    """오가는 MQTT 메시지를 SSE 로 흘려보낸다(요청·응답·에러·상태·브로커 연결).

    `curl -N http://localhost:8123/api/events` 로 다른 터미널에서 통신을 관찰할 수 있다.
    """

    async def stream():
        queue = bridge.listen()
        yield f"data: {json.dumps(bridge.health(), ensure_ascii=False)}\n\n"
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"        # 프록시 유휴 끊김 방지
                    continue
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        finally:
            bridge.unlisten(queue)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/{target_id}", response_class=HTMLResponse)
def grid(request: Request, target_id: str):
    """Step2 · 컨텐츠 그리드 (학습·준비 / 진단·실습 2섹션, 대상 기준)."""
    target = get_target(target_id)
    sections = [
        {"name": s, "cards": [
            {**c, "title": content_title(c, target), "icon": content_icon(c, target)}
            for c in CONTENTS if c["section"] == s
        ]}
        for s in SECTIONS
    ]
    return templates.TemplateResponse(
        request, "grid.html",
        {"target": target, "sections": sections, "bottom_nav": BOTTOM_NAV,
         "status": status_text(target),
         # 실습에 들어가기 전에 연결 여부를 확인할 수 있어야 한다 — 이 화면도
         # 상단바 연결 표시를 그리므로 브로커 주소가 필요하다 (link-status.js).
         "ws_url": browser_ws_url(),
         "crumbs": [{"text": f"컨텐츠 선택 ({target['label']})", "tier": "content"}]},
    )


@app.get("/{target_id}/{content_id}", response_class=HTMLResponse)
def content_view(request: Request, target_id: str, content_id: str,
                 item: str | None = None, doc: str | None = None):
    """Step3 · 콘텐츠별 화면. content.view 로 템플릿을 디스패치한다."""
    target = get_target(target_id)
    content = get_content(content_id) or CONTENTS[0]
    title = content_title(content, target)
    section = content["section"]
    ctx = {
        "target": target, "content": content, "title": title,
        "section": section, "bottom_nav": BOTTOM_NAV, "status": status_text(target),
        # 상단바 연결 표시는 모든 서브 화면에서 같은 규칙으로 그린다 (link-status.js).
        "ws_url": browser_ws_url(),
    }

    view = content["view"]
    selected = None
    if view == "theory":
        # 좌 목록은 폴더 스캔(그룹 트리), 우 본문은 선택 자료의 md → HTML.
        # 선택이 없거나 없는 doc 이면 목록 첫 자료로 폴백한다.
        materials = theory_content.load_materials()
        selected = theory_content.load_material(doc)
        if selected is None:
            first_id = theory_content.first_material_id(materials)
            if first_id:
                selected = theory_content.load_material(first_id)
        ctx.update({"materials": materials, "selected": selected})
        tmpl = "theory.html"
    elif view == "quiz":
        # 좌 주제 목록 / 우 문항. 문항 진행·채점은 static/js/quiz.js (클라이언트) 몫이라
        # 선택 주제의 문항 배열을 통째로 내려보낸다.
        selected = find_leaf(QUIZ_TOPICS, item)
        ctx.update({"topics": QUIZ_TOPICS, "selected": selected,
                    "questions": selected["questions"] if selected else []})
        tmpl = "quiz.html"
    elif view == "ecu":
        tmpl = "ecu.html"
        # 리프로그래밍도 실제 왕복이다 — 진단·강제구동과 같은 라이브 화면으로 다룬다.
        ctx["live"] = True
        ctx["transport_switch"] = True
        ctx["sequence"] = auto_sequence(content_id, target, None)
    else:
        # detail(prep) / run(diag·force·message) 공통: 트리 + 선택 잎
        nodes = content_tree(content_id, target)
        selected = find_leaf(nodes, item)
        ctx.update({"nodes": nodes, "selected": selected})
        if view == "detail":
            tmpl = "detail.html"
            # 실습 준비 본문은 PREP_GUIDES 가 원천이다 (템플릿에 하드코딩하지 않는다).
            ctx["guide"] = prep_guide(selected["id"], target) if selected else None
        else:
            tmpl = "run.html"
            ctx["is_composer"] = content.get("composer", False)
            # 라이브(MQTT 연결) 대상 화면: 메시지 작성·진단·강제구동. 블록 간 공유 위해 컨텍스트로.
            ctx["live"] = ctx["is_composer"] or content_id in ("diag", "force")
            # 전송 방식(실 MQTT / 목업) 토글은 실제로 보낼 수 있는 화면에만 띄운다.
            ctx["transport_switch"] = ctx["live"]
            # 진단·강제구동은 '자동 시퀀스' 화면이다 (메시지 작성은 사람이 직접 친다).
            if not ctx["is_composer"]:
                ctx["sequence"] = auto_sequence(content_id, target, selected)
            if ctx["is_composer"]:
                # 메시지 작성: 상단 입력창은 정적이고, 선택 잎은 '아래에 깔릴 참고 자료'를 고른다.
                sc, step, idx, total = find_step(message_scenarios(target),
                                                 selected["id"] if selected else None)
                addr = MSG_ADDR[target["id"]]
                # 다음 단계 링크 — 단계를 통과하면 전송 버튼이 이 주소로 바뀐다.
                # (통과 여부는 서버가 모른다. 브라우저가 응답을 보고 판단한다 —
                #  static/js/step-progress.js)
                nxt = sc["steps"][idx]["id"] if idx < total else None
                ctx.update({"scenario": sc, "step": step, "step_no": idx, "step_total": total,
                            "addr": addr, "examples": step_examples(step["spec"], addr),
                            "layers": MSG_LAYERS, "nrc": MSG_NRC, "negative": MSG_NEGATIVE,
                            "next_url": f"/{target['id']}/{content_id}?item={nxt}" if nxt else None})

    ctx["crumbs"] = make_crumbs(
        target, section, title, selected["title"] if selected else None)
    return templates.TemplateResponse(request, tmpl, ctx)
