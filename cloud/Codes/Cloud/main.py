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
import threading
from contextlib import asynccontextmanager
from datetime import datetime
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
# 화면 진입 안내 팝업 — "여기가 무엇을 하는 화면인가"
#
# 교육생은 컨텐츠 그리드에서 타일 하나를 눌러 곧장 실습 화면에 떨어진다. 화면은
# 3~4분할에 패널마다 역할이 달라서, 아무 설명 없이 들어오면 어디를 먼저 봐야 할지
# 부터 막힌다. 그래서 **진입 즉시 한 번** 무슨 화면인지 알려주고, 그 뒤로는 도움말
# 버튼으로 언제든 다시 부를 수 있게 한다 (static/js/guide-modal.js).
#
# '실습 준비'는 제외한다 — 그 화면 자체가 안내문을 읽는 곳이라 팝업이 겹친다.
#
#   lede    "본 실습은 ~ 입니다" 한 문장. 무엇을 하는 화면인지만 말한다
#   points  화면 구성·진행 방법. 팝업에서 다 읽을 분량이어야 하므로 3~4줄로 끊는다
#   note    없어도 되지만, 실물이 움직이는 화면에서는 반드시 경고를 남긴다
#
# `{label}`(RC카/UR로봇) · `{transport}`(CAN/DoIP) 는 대상마다 다르므로 page_guide()
# 가 채운다. 문구를 고치려면 여기 dict 만 손대면 된다 — 템플릿에는 없다.
# --------------------------------------------------------------------------- #
PAGE_GUIDES = {
    "theory": {
        "lede": "본 화면은 진단 통신의 배경 지식을 읽는 <b>이론 교육</b>입니다. "
                "실습에서 주고받는 바이트가 왜 그렇게 생겼는지를 여기서 먼저 익힙니다.",
        "points": [
            "왼쪽 목록에서 과목과 자료를 고르면 오른쪽에 본문이 나옵니다. "
            "과목은 디지털 통신 → CAN → UDS → 이더넷 → DoIP 순으로 쌓아 읽도록 배열돼 있습니다.",
            "자료는 소제목 단위로 페이지가 나뉩니다. 제목 오른쪽의 "
            "<b>1 PAGE / 15 PAGE</b> 와 이전·다음 버튼으로 넘기고, 내용이 길면 본문 안에서 스크롤됩니다.",
            "읽기 <b>전</b>에 퀴즈의 사전 문제를, 읽은 <b>뒤</b>에 사후 문제를 풀면 "
            "무엇이 늘었는지 점수로 확인할 수 있습니다.",
        ],
    },
    "quiz": {
        "lede": "본 화면은 학습 전후의 이해도를 스스로 확인하는 <b>퀴즈</b>입니다.",
        "points": [
            "과목마다 '사전'과 '사후'가 한 쌍입니다. 사전은 뭘 모르는지 드러내는 것이 목적이니 "
            "이론 교육을 보기 전에 푸는 편이 좋습니다.",
            "보기 순서는 응시할 때마다 새로 섞입니다. 고르지 않고 넘어간 문항은 오답 처리되고, "
            "마지막 문항의 '제출하기'로 채점합니다.",
            "제출하면 소속·이름·직급과 함께 <b>점수가 서버에 기록</b>됩니다. "
            "화면에는 남지 않으니 사전·사후 점수는 따로 적어 두고 비교하세요.",
        ],
    },
    "diag": {
        "lede": "본 실습은 진단기로 {label}의 센서 값을 실제로 읽어 보는 <b>진단</b> 실습입니다. "
                "값 하나를 읽기까지 어떤 순서를 밟아야 하는지가 핵심입니다.",
        "points": [
            "왼쪽에서 읽을 센서를 고르면, 오른쪽 시퀀스에 세션 오픈부터 정리까지의 순서가 잡힙니다.",
            "<b>다음 시퀀스 실행</b> 버튼은 누를 때마다 <b>한 단계씩</b>만 진행됩니다. "
            "가운데 그림과 설명을 읽고 납득한 뒤 다음을 누르세요.",
            "오간 메시지는 가운데 아래 통신 로그에 그대로 남습니다. "
            "요청(→)과 응답(←)을 짝지어 보면 순서가 눈에 들어옵니다.",
            "시퀀스 목록의 각 줄을 눌러 그 단계의 설명을 미리 읽어 볼 수도 있습니다 (전송되지 않습니다).",
        ],
    },
    "force": {
        "lede": "본 실습은 진단기로 {label}의 구동부를 직접 움직여 보는 <b>강제구동</b> 실습입니다. "
                "읽기만 하던 진단과 달리, 여기서는 ECU 에게 제어권을 넘겨받습니다.",
        "points": [
            "진단과 달리 <b>보안 접근(Seed·Key)</b>으로 잠금을 먼저 풀어야 구동 요청이 통과합니다. "
            "건너뛰면 부정 응답 NRC 0x33 이 돌아옵니다.",
            "<b>다음 시퀀스 실행</b> 버튼은 누를 때마다 한 단계씩만 진행됩니다. "
            "구동 단계에서는 장비가 실제로 움직이는지 눈으로 확인하고 다음을 누르세요.",
            "마지막에 제어권을 ECU 에게 돌려주는 단계까지 밟아야 실습이 끝납니다 — "
            "여기서 멈추면 장비가 강제 상태로 남습니다.",
        ],
        "note": "상단 전송 방식이 <b>RCI(MQTT)</b> 이면 실물 장비가 실제로 움직입니다. "
                "실행 전 주변 안전을 확인하세요.",
    },
    "ecu": {
        "lede": "본 실습은 ECU 의 펌웨어를 새 버전으로 바꿔 쓰는 "
                "<b>ECU 업그레이드(리프로그래밍)</b> 실습입니다.",
        "points": [
            "프로그래밍 세션 → 보안 접근 → 다운로드 요청(0x34) → 블록 전송(0x36) → "
            "전송 종료(0x37) → 검증(0x31) → 리셋(0x11) 순서로 진행됩니다.",
            "전송하는 것은 더미 블록 3개입니다. 실제 펌웨어가 아니라 "
            "<b>블록 카운터가 어떻게 흘러가는지</b>를 보는 것이 목적입니다.",
            "<b>다음 시퀀스 실행</b> 버튼은 누를 때마다 한 단계씩만 진행됩니다. "
            "이 화면은 고를 세부 항목이 없는 단일 코스라 왼쪽 목록이 없습니다.",
            "블록 카운터가 어긋나거나 검증에 실패하면 그 자리에서 멈춥니다 — "
            "뒤 단계가 성립하지 않기 때문입니다.",
        ],
        "note": "상단 전송 방식이 <b>RCI(MQTT)</b> 이면 실물 ECU 가 재기동합니다. "
                "리프로그래밍 도중 전원이 끊기면 ECU 가 복구 불능이 될 수 있습니다.",
    },
    "message": {
        "lede": "본 실습은 {transport} 진단 메시지를 <b>직접 한 바이트씩 조립해서 보내는</b> "
                "{transport} 메시지 작성 실습입니다. 시퀀스가 대신 밟아 주던 요청을 여기서는 손으로 씁니다.",
        "points": [
            "왼쪽 세부 항목은 <b>순차 진행</b>입니다 — 앞 단계의 응답을 제대로 받아야 다음 단계가 열립니다.",
            "가운데 위의 <b>배경·이론</b> 버튼으로 그 단계의 만화·설명을, "
            "<b>메시지 작성</b> 버튼으로 입력창을 오갈 수 있습니다.",
            "보낸 요청과 받은 응답은 오른쪽 통신 로그에 남습니다. "
            "부정 응답(0x7F)이 오면 뒤에 붙은 NRC 를 보고 무엇이 빠졌는지 찾으세요.",
            "처음부터 다시 하려면 왼쪽 위 '진행 초기화'를 누르면 됩니다 — 통과 표시와 "
            "세션 유지(0x3E) 발행이 함께 멈춥니다. 다른 세부 항목으로 옮기면 세션 유지가 "
            "중지되고, 이 화면을 벗어나면 통과 표시까지 모두 초기화됩니다.",
        ],
    },
}


# lede 는 한 문단으로 흘려 쓰면 한 덩어리로 보여 읽히지 않는다. 문장(온점)마다
# 줄을 바꿔 "무슨 화면인가" 와 "왜 보는가" 를 눈으로 나눠 읽게 한다.
# 한국어 종결어미(다/요) 뒤의 온점만 문장 끝으로 본다 — "0x22." 같은 표기나
# 소수점을 문장 경계로 오인하지 않기 위해서다.
_LEDE_SENTENCE_END = re.compile(r"(?<=[다요])\.[ \t]+")


def _lede_lines(text):
    """lede 한 문단을 문장 단위로 끊어 `<br>` 로 잇는다 (팝업의 첫 문단 전용)."""
    return _LEDE_SENTENCE_END.sub(".<br>", text)


def page_guide(content, target):
    """콘텐츠 화면 진입 안내 (없으면 None — 실습 준비·그 밖의 화면).

    문구의 `{label}`·`{transport}` 를 대상에 맞게 채우고, 제목과 저장 키를 붙여
    돌려준다. 저장 키가 콘텐츠 id 인 이유: '더 이상 보지 않기'는 화면마다 따로
    기억해야 한다 — 진단을 익혔다고 퀴즈 규칙까지 아는 것은 아니다.
    """
    guide = PAGE_GUIDES.get(content["id"])
    if guide is None:
        return None

    fmt = {"label": target["label"], "transport": target["transport"]}
    return {
        "key": content["id"],
        "name": content_title(content, target),
        "lede": _lede_lines(guide["lede"].format(**fmt)),
        "points": [p.format(**fmt) for p in guide["points"]],
        "note": guide["note"].format(**fmt) if guide.get("note") else None,
    }


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
#   topic    단계 배경을 설명하는 브리핑 주제. with_briefs 가 붙인다
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
                f"{label} · 제어 옵션 0x03 단기 조정. 긍정 응답은 요청을 그대로 되돌려준다. "
                "다음 단계를 누르기 전에 장비가 실제로 움직이는지 눈으로 확인할 것."),
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
            "hardReset. 재기동하면 새 펌웨어로 올라온다."),
    ]
    return {"id": "ecu", "title": "ECU 리프로그래밍 시퀀스", "danger": True, "steps": steps}


def auto_sequence(content_id, target, selected):
    """카테고리(+선택 잎)별 자동 시퀀스. 해당 없으면 None.

    단계별 배경 설명(만화 + 글)은 with_briefs 가 붙인다 — 화면 가운데의 '기능 설명'
    패널이 지금 밟는 단계에 맞춰 갈아 끼우는 재료다.
    """
    leaf = selected["id"] if selected else None
    if content_id == "diag":
        return with_briefs(_seq_diag(target, leaf))
    if content_id == "force":
        return with_briefs(_seq_force(target, leaf))
    if content_id == "ecu":
        return with_briefs(_seq_ecu(target))
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
# 배경·이론 브리핑 (만화 + 글)
#
# 메시지 작성 실습의 각 단계에는 '왜 이 메시지를 보내는가' 를 먼저 보여주는 화면이
# 붙는다. 같은 윈도우 안에서 [배경 · 이론] ↔ [메시지 작성] 버튼으로 갈아 끼운다
# (templates/partials/_briefing.html + static/js/stage-switch.js).
#
# 원천은 **주제(topic)** 다. 단계는 코스마다 반복되기 때문이다 — 세션 오픈은 네 코스
# 모두에 있고, 보안 접근은 강제구동·데이터쓰기에 함께 있다. 그래서 단계 id 를 주제로
# 접어(STEP_BRIEF) 만화·글을 한 벌만 두고 여러 단계가 나눠 쓴다.
#
# 만화 이미지는 static/img/comic/{topic}-{n}.png 규칙으로 찾고, 아직 없으면
# placeholder.png(준비중 더미)로 대체한다 — 그림이 준비되는 대로 파일만 넣으면 된다.
# --------------------------------------------------------------------------- #

COMIC_DIR = "img/comic"
COMIC_PENDING = f"{COMIC_DIR}/placeholder.png"


def _cut(caption, note=""):
    """만화 한 컷. caption = 컷 아래 한 줄, note = 보조 설명(있으면 작게)."""
    return {"caption": caption, "note": note}


def _brief(title, lede, cuts, sections, takeaway):
    return {"title": title, "lede": lede, "cuts": cuts,
            "sections": sections, "takeaway": takeaway}


def _sec(h, p):
    return {"h": h, "p": p}


# 주제별 브리핑. cuts 는 4컷 또는 8컷 — 길이는 주제마다 다를 수 있고, 화면은
# 컷 수에 따라 2열(4컷)/4열(8컷)로 알아서 배치한다.
BRIEFINGS = {
    "session-open": _brief(
        "진단 세션을 연다 (0x10)",
        "ECU 는 평소 '기본 세션'에 있다. 이 상태에서는 읽기 몇 가지만 허용되고 쓰기·"
        "강제구동은 거절된다. 그래서 모든 실습의 첫 줄은 세션을 여는 요청이다.",
        [
            _cut("정비사가 진단기를 차량에 연결한다", "아직 아무 말도 하지 않은 상태"),
            _cut("진단기: “확장 세션 열어줘” — 10 03", "SID 0x10 · 서브펑션 0x03"),
            _cut("ECU: “열었다” — 50 03 00 32 01 F4", "뒤 4바이트는 P2 50ms · P2* 5000ms"),
            _cut("이제부터 쓰기·강제구동 요청을 받아준다", "단, 계속 말을 걸어야 유지된다"),
        ],
        [
            _sec("세션이란", "ECU 가 요청을 어디까지 받아줄지 정하는 '모드'다. 01 기본 · "
                            "02 프로그래밍 · 03 확장 진단 세션이 대표적이다."),
            _sec("왜 확장 세션인가", "읽기(0x22)는 기본 세션에서도 되지만, 실차 절차는 진단을 "
                                     "확장 세션에서 진행한다. 뒤따르는 보안 접근·강제구동이 "
                                     "확장 세션을 전제로 하기 때문이다."),
            _sec("응답 읽는 법", "요청 SID 0x10 에 0x40 을 더한 0x50 이 긍정 응답이다. "
                                 "거절이면 7F 10 {NRC} 형태로 돌아온다."),
        ],
        "요청 10 03 → 긍정 응답 50 03. 이 한 줄이 통과해야 다음 단계가 열린다."),

    "session-keepalive": _brief(
        "세션을 살려 둔다 (0x3E)",
        "세션은 가만두면 꺼진다. ECU 는 마지막 요청 뒤 약 5초(S3 타이머) 동안 아무 말이 "
        "없으면 스스로 기본 세션으로 돌아간다.",
        [
            _cut("진단기가 잠시 조용해진다", "정비사가 화면을 들여다보는 사이"),
            _cut("ECU 안에서 S3 타이머가 흐른다", "약 5초"),
            _cut("진단기: “살아 있다” — 3E 00", "TesterPresent · 2초 주기 반복"),
            _cut("세션이 유지된다", "발행을 멈추면 다시 기본 세션으로"),
        ],
        [
            _sec("TesterPresent", "0x3E 는 아무 일도 하지 않는 요청이다. '진단기가 아직 붙어 "
                                  "있다'는 사실만 알린다."),
            _sec("서브펑션 0x00 과 0x80", "00 은 응답을 요구하고(7E 00 이 돌아온다), 80 은 "
                                          "응답을 요구하지 않는다. 실습에서는 왕복이 보이도록 00 을 쓴다."),
            _sec("주기", "S3 가 5초이므로 그 절반인 2초 주기로 보낸다. 이 화면의 전송 버튼은 "
                         "한 번 누르면 반복 발행 토글이 되고, 다음 단계로 넘어가도 계속 발행한다."),
        ],
        "요청 3E 00 → 긍정 응답 7E 00. 뒤 단계가 NRC 0x7F/0x33 으로 거절된다면 세션이 꺼진 것이다."),

    "read-did": _brief(
        "센서값을 읽는다 (0x22)",
        "ECU 안의 값은 이름이 아니라 번호(DID)로 부른다. 읽고 싶은 DID 를 지정하면 "
        "ECU 가 그 DID 를 그대로 되돌려 주고 뒤에 데이터를 붙인다.",
        [
            _cut("정비사: “지금 초음파 거리 얼마야?”", "사람의 말"),
            _cut("진단기: 22 01 01", "SID 0x22 + DID 2바이트"),
            _cut("ECU: 62 01 01 00 2A", "0x62 + 같은 DID + 데이터"),
            _cut("진단기가 0x002A → 42cm 로 풀어 보여준다", "물리값 해석은 DID 정의를 따른다"),
        ],
        [
            _sec("DID 란", "Data Identifier — ECU 안의 값 하나하나에 매긴 2바이트 번호다. "
                           "어떤 DID 가 무슨 값인지는 제조사 사양(또는 이 실습의 참고 자료)에 있다."),
            _sec("응답 확인", "응답에는 **요청한 DID 가 그대로** 실려 온다. 엉뚱한 DID 가 오면 "
                              "다른 값을 읽은 것이니 그대로 넘어가면 안 된다."),
            _sec("자주 보는 거절", "NRC 0x31 requestOutOfRange — 없는 DID. "
                                   "NRC 0x33 securityAccessDenied — 보호된 DID."),
        ],
        "요청 22 {DID} → 긍정 응답 62 {DID} {데이터}."),

    "session-close": _brief(
        "세션을 정리한다 (0x10 01)",
        "실습을 끝낼 때는 열어 둔 것을 되돌린다. 기다리면 자동으로 돌아가지만, 명시적으로 "
        "닫는 것이 실차 절차다.",
        [
            _cut("작업이 끝났다", "제어권도 이미 ECU 에 돌려준 상태"),
            _cut("세션 유지 발행을 멈춘다", "반복 발행 중지"),
            _cut("진단기: 10 01 — 기본 세션으로", "서브펑션 0x01"),
            _cut("ECU: 50 01 — 평상시 상태로 복귀", "다음 사람이 안전하게 이어받는다"),
        ],
        [
            _sec("왜 닫는가", "확장 세션을 열어 둔 채 자리를 뜨면, 그 사이 들어오는 요청이 "
                              "예상치 못한 권한으로 처리될 수 있다."),
            _sec("자동 복귀와의 차이", "발행을 멈추면 5초 뒤 알아서 기본 세션이 된다. 그래도 "
                                       "명시적으로 닫아야 '언제 끝났는지'가 로그에 남는다."),
        ],
        "요청 10 01 → 긍정 응답 50 01. 코스의 마지막 줄이다."),

    "dtc-read": _brief(
        "고장코드를 조회한다 (0x19)",
        "ECU 는 이상을 감지하면 고장코드(DTC)를 스스로 저장해 둔다. 0x19 는 그 기록을 "
        "꺼내 보는 요청이다.",
        [
            _cut("경고등이 켜졌던 차가 들어온다", "지금은 증상이 없다"),
            _cut("진단기: 19 02 0C — 확인된 고장만", "서브펑션 0x02 · 상태 마스크 0x0C"),
            _cut("ECU: 59 02 FF 00 12 34 …", "레코드 4바이트 = DTC 3 + 상태 1"),
            _cut("코드를 표로 풀어 원인을 좁힌다", "상태 바이트가 '지금도 고장인가'를 말해준다"),
        ],
        [
            _sec("서브펑션 0x02", "reportDTCByStatusMask — 상태 마스크에 걸리는 DTC 만 보고한다. "
                                  "0x08 은 확정 고장, 0x0C 는 확정 + 이번 주행 중 발생."),
            _sec("레코드 읽는 법", "3바이트 DTC + 1바이트 상태. 상태 비트로 현재 활성인지, "
                                   "과거 기록인지 구분한다."),
            _sec("NRC 0x78", "requestCorrectlyReceived-ResponsePending — '처리 중'이라는 뜻이다. "
                             "잠시 뒤 같은 요청에 대한 최종 응답이 따로 온다."),
        ],
        "요청 19 02 {마스크} → 긍정 응답 59 02 {마스크} {레코드…}."),

    "dtc-clear": _brief(
        "고장코드를 지운다 (0x14)",
        "수리를 끝냈으면 기록을 지워 다음 주행부터 새로 판단하게 한다. 원인을 고치지 않고 "
        "지우면 같은 코드가 다시 뜬다.",
        [
            _cut("원인을 고쳤다", "부품 교체 완료"),
            _cut("진단기: 14 FF FF FF — 전체 소거", "그룹 0xFFFFFF = 모든 DTC"),
            _cut("ECU: 54 — 지웠다", "데이터 없는 짧은 긍정 응답"),
            _cut("다시 19 로 조회해 비었는지 확인", "지웠다는 말만 믿지 않는다"),
        ],
        [
            _sec("그룹 지정", "3바이트로 지울 범위를 고른다. 0xFFFFFF 는 전체, 그 밖에는 "
                              "파워트레인·섀시 등 그룹별 소거다."),
            _sec("소거 검증", "소거 요청이 성공해도 실제로 비었는지는 재조회로 확인한다. "
                              "레코드 없이 마스크만 돌아오면(예 59 02 08) 남은 고장이 없다는 뜻이다."),
            _sec("주의", "고장 기록은 진단의 근거다. 원인 분석 전에 지우면 단서를 잃는다."),
        ],
        "요청 14 FF FF FF → 긍정 응답 54."),

    "security-access": _brief(
        "잠금을 푼다 (0x27)",
        "쓰기와 강제구동은 아무나 못 한다. ECU 가 낸 문제(Seed)를 풀어 답(Key)을 맞혀야 "
        "잠금이 열린다.",
        [
            _cut("진단기: 27 01 — 문제 내 줘", "홀수 서브펑션 = Seed 요청"),
            _cut("ECU: 67 01 11 22 33 44 — Seed", "매번 달라진다"),
            _cut("진단기가 약속된 계산으로 Key 를 만든다", "실습용 규칙: 각 바이트 + 0x44"),
            _cut("27 02 {Key} → 67 02 — 잠금 해제", "짝수 서브펑션 = Key 전송"),
        ],
        [
            _sec("Seed–Key 방식", "고정 비밀번호를 주고받지 않는다. 매번 다른 Seed 에 같은 "
                                  "계산 규칙을 적용해, 통신을 엿들어도 다음 번에 못 쓰게 한다."),
            _sec("두 번의 왕복", "홀수(01) 요청으로 Seed 를 받고, 짝수(02) 요청으로 Key 를 낸다. "
                                 "**짝수 응답(67 02)이 와야** 실제로 열린 것이다."),
            _sec("실패하면", "Key 가 틀리면 NRC 0x35 invalidKey, 여러 번 틀리면 0x36/0x37 로 "
                             "일정 시간 잠긴다. 이 단계를 건너뛰면 뒤 동작이 0x33 으로 거절된다."),
        ],
        "요청 27 01 → 67 01 {Seed}, 이어서 27 02 {Key} → 67 02."),

    "force-drive": _brief(
        "액추에이터를 강제로 움직인다 (0x2F)",
        "센서값만으로 판단이 안 될 때, 부품을 직접 켜 보면 배선·부품·제어 중 어디가 "
        "문제인지 갈린다. 실제로 물체가 움직이므로 안전이 먼저다.",
        [
            _cut("주변에 사람이 없는지 확인한다", "강제구동은 진짜로 움직인다"),
            _cut("진단기: 2F {DID} 03 {값} — 단기 조정", "제어 옵션 0x03"),
            _cut("ECU: 6F {DID} 03 {값} — 구동 중", "눈으로 동작을 확인한다"),
            _cut("2F {DID} 00 — 제어권 반환", "끝나면 반드시 ECU 에 돌려준다"),
        ],
        [
            _sec("제어 옵션", "00 제어권 반환 · 01 기본값 리셋 · 02 현재값 고정 · 03 단기 조정. "
                              "실습에서 쓰는 것은 03 과 00 이다."),
            _sec("반드시 반환", "제어권을 쥔 채로 두면 ECU 가 정상 제어를 못 한다. 00 을 보내 "
                                "돌려주는 것까지가 한 단계다."),
            _sec("전제 조건", "확장 세션 + 보안 해제가 되어 있어야 한다. 아니면 NRC 0x33, "
                              "지원하지 않는 옵션이면 0x12 subFunctionNotSupported."),
        ],
        "요청 2F {DID} 03 {값} → 6F …, 마무리로 2F {DID} 00 → 6F {DID} 00."),

    "write-did": _brief(
        "값을 써 넣는다 (0x2E)",
        "설정값·보정값처럼 ECU 안에 남는 값을 바꾼다. 읽기와 달리 흔적이 남으므로 "
        "보안 해제가 전제다.",
        [
            _cut("교체한 부품에 맞춰 보정값을 바꿔야 한다", "읽기만으로는 끝나지 않는 작업"),
            _cut("진단기: 2E F1 A0 07 E0", "SID 0x2E + DID + 쓸 데이터"),
            _cut("ECU: 6E F1 A0 — 받았다", "데이터 없이 SID + DID 만 돌아온다"),
            _cut("22 F1 A0 로 다시 읽어 확인한다", "쓴 값이 실제로 들어갔는지"),
        ],
        [
            _sec("길이가 맞아야 한다", "DID 마다 데이터 길이가 정해져 있다. 어긋나면 "
                                       "NRC 0x13 incorrectMessageLength 로 거절된다."),
            _sec("긍정 응답의 모양", "0x6E + DID 까지만 온다. 데이터가 없다고 실패한 것이 아니다."),
            _sec("자주 보는 거절", "0x33 보안 해제 전 · 0x31 쓰기 금지 항목 · 0x22 조건 불충족"
                                   "(예: 주행 중)."),
        ],
        "요청 2E {DID} {값} → 긍정 응답 6E {DID}."),

    "ecu-download": _brief(
        "펌웨어를 받을 자리를 연다 (0x34)",
        "리프로그래밍은 파일을 통째로 던지는 것이 아니다. 먼저 '어디에 얼마짜리를 쓸 것인지' "
        "합의하고, ECU 가 '한 번에 이만큼씩 보내라'고 답한다.",
        [
            _cut("새 펌웨어 파일을 준비한다", "주소 0x00001000 · 길이 0x00002000"),
            _cut("진단기: 34 00 44 {주소} {길이}", "형식 0x00 무압축·무암호"),
            _cut("ECU: 74 20 0F FF — 블록당 0x0FFF 까지", "받을 준비가 됐다는 뜻"),
            _cut("이제부터 0x36 으로 나눠 보낸다", "블록 크기는 ECU 가 정한다"),
        ],
        [
            _sec("주소/길이 형식 0x44", "한 자리씩 읽는다 — 상위 4비트가 길이 바이트 수, 하위 "
                                        "4비트가 주소 바이트 수다. 0x44 는 '각각 4바이트'."),
            _sec("응답의 maxNumberOfBlockLength", "0x74 뒤 값이 한 블록의 최대 길이다. 이보다 "
                                                  "크게 보내면 NRC 0x13 으로 거절된다."),
            _sec("실패하면 멈춰야 한다", "자리를 열지 못했는데 블록을 보내면 갈 곳이 없다. "
                                         "이 단계는 어느 모드에서든 실패 시 중단한다."),
        ],
        "요청 34 00 44 {주소} {길이} → 긍정 응답 74 {길이형식} {최대 블록 길이}."),

    "ecu-transfer": _brief(
        "펌웨어를 블록으로 보낸다 (0x36)",
        "합의한 크기로 잘라 순서대로 보낸다. 블록마다 번호(카운터)가 붙고, 같은 번호로 "
        "응답이 와야 다음 블록을 보낸다.",
        [
            _cut("펌웨어를 블록으로 자른다", "각 블록에 01, 02, 03… 번호를 붙인다"),
            _cut("진단기: 36 01 {데이터}", "블록 카운터 0x01"),
            _cut("ECU: 76 01 — 1번 받았다", "번호가 맞아야 다음으로"),
            _cut("36 02 → 76 02, 36 03 → 76 03 …", "끝까지 반복한다"),
        ],
        [
            _sec("블록 카운터", "0x01 부터 1씩 오르고 0xFF 다음은 0x00 으로 되감는다. 응답 번호가 "
                                "어긋나면 블록을 빠뜨렸거나 중복 전송한 것이다."),
            _sec("왜 나눠 보내는가", "CAN 한 프레임은 8바이트다. 수십 KB 펌웨어는 ISO-TP 로 이어 "
                                     "붙여도 한 번에 안 들어가고, 중간에 끊겼을 때 어디부터 다시 "
                                     "보낼지도 알 수 없다."),
            _sec("중간에 끊기면", "카운터가 남아 있으므로 그 번호부터 다시 보낼 수 있다. 다만 "
                                  "실차에서는 0x34 부터 다시 하는 것이 안전하다."),
        ],
        "요청 36 {카운터} {데이터} → 긍정 응답 76 {같은 카운터}."),

    "ecu-transfer-exit": _brief(
        "전송을 끝냈다고 알린다 (0x37)",
        "마지막 블록을 보냈다고 ECU 가 알 방법은 없다. 더 보낼 것이 없다는 사실을 "
        "명시적으로 알려야 ECU 가 받은 것을 마무리한다.",
        [
            _cut("마지막 블록까지 보냈다", "36 03 → 76 03"),
            _cut("진단기: 37 — 전송 종료", "데이터 없는 짧은 요청"),
            _cut("ECU: 77 — 마무리했다", "받은 블록을 플래시에 정리한다"),
            _cut("이제 검증 단계로 넘어간다", "쓰인 것이 맞는지 확인"),
        ],
        [
            _sec("왜 필요한가", "0x36 만으로는 '아직 더 올 것인가'를 구분할 수 없다. 0x37 이 "
                                "와야 ECU 가 전송 구간을 닫고 다음 요청을 받는다."),
            _sec("생략하면", "0x31 검증이나 0x11 리셋이 NRC 0x22 conditionsNotCorrect 로 "
                             "거절된다 — 전송이 끝나지 않은 상태라서다."),
        ],
        "요청 37 → 긍정 응답 77."),

    "ecu-verify": _brief(
        "제대로 쓰였는지 검사한다 (0x31)",
        "보냈다고 해서 올바로 쓰인 것은 아니다. 리셋하기 전에 체크섬과 의존성을 확인한다 — "
        "여기서 실패했는데 리셋하면 반쯤 쓰인 펌웨어로 부팅한다.",
        [
            _cut("전송은 끝났다", "77 을 받은 상태"),
            _cut("진단기: 31 01 FF 01 — 검사 시작", "0x01 start · 루틴 0xFF01"),
            _cut("ECU 가 체크섬·의존성을 확인한다", "checkProgrammingDependencies"),
            _cut("71 01 FF 01 — 이상 없음", "실패하면 절대 리셋하지 않는다"),
        ],
        [
            _sec("루틴 제어 0x31", "ECU 안에 미리 심어 둔 '작업'을 부르는 서비스다. 0x01 시작 · "
                                   "0x02 중지 · 0x03 결과 요청 세 가지 서브펑션이 있다."),
            _sec("무엇을 검사하는가", "쓰인 영역의 체크섬이 맞는지, 그리고 이 펌웨어가 요구하는 "
                                      "다른 소프트웨어 버전이 갖춰졌는지를 본다."),
            _sec("실패했다면", "리셋하지 말고 0x34 부터 다시 내려보낸다. 대부분의 ECU 는 검증 "
                               "전까지 기존 펌웨어로 되돌아갈 수 있게 설계돼 있다."),
        ],
        "요청 31 01 FF 01 → 긍정 응답 71 01 FF 01 {결과}."),

    "ecu-reset": _brief(
        "새 펌웨어로 다시 켠다 (0x11)",
        "플래시에 쓰인 코드는 다시 부팅해야 실행된다. 리셋은 리프로그래밍의 마지막 줄이자, "
        "되돌릴 수 없는 지점이다.",
        [
            _cut("검증까지 통과했다", "71 01 FF 01"),
            _cut("세션 유지 발행을 먼저 멈춘다", "어차피 리셋되면 세션은 사라진다"),
            _cut("진단기: 11 01 — hardReset", "전원을 껐다 켜는 것과 같다"),
            _cut("ECU 가 새 펌웨어로 올라온다", "잠시 응답이 끊긴다"),
        ],
        [
            _sec("리셋 종류", "0x01 hardReset(전원 재인가) · 0x02 keyOffOnReset · 0x03 softReset. "
                              "리프로그래밍 뒤에는 보통 hardReset 을 쓴다."),
            _sec("응답이 늦는 이유", "긍정 응답 51 01 을 보낸 직후 ECU 가 실제로 꺼진다. 다시 "
                                     "올라올 때까지 수백 ms ~ 수 초 동안 아무 응답이 없다."),
            _sec("리셋 뒤 확인", "재기동한 뒤 버전 DID 를 읽어 새 버전이 맞는지 본다. "
                                 "여기까지 해야 리프로그래밍이 끝난 것이다."),
        ],
        "요청 11 01 → 긍정 응답 51 01. 이후 ECU 가 재기동한다."),
}

# 단계 id → 브리핑 주제. 반복되는 단계는 같은 주제를 함께 쓴다 (만화 재사용).
STEP_BRIEF = {
    "read-open": "session-open", "dtc-open": "session-open",
    "force-open": "session-open", "write-open": "session-open",

    "read-tp": "session-keepalive", "dtc-tp": "session-keepalive",
    "force-tp": "session-keepalive", "write-tp": "session-keepalive",

    "read-did": "read-did", "write-verify": "read-did",

    "read-close": "session-close", "dtc-close": "session-close",
    "force-close": "session-close", "write-close": "session-close",

    "dtc-read": "dtc-read", "dtc-verify": "dtc-read",
    "dtc-clear": "dtc-clear",

    "force-sec": "security-access", "write-sec": "security-access",
    "force-drive": "force-drive",
    "write-do": "write-did",
}

# 주제를 못 찾을 때의 폴백 — 단계의 SID 로 되짚는다 (코스가 늘어도 빈 화면이 없게).
_SID_BRIEF = {"10": "session-open", "3E": "session-keepalive", "22": "read-did",
              "19": "dtc-read", "14": "dtc-clear", "27": "security-access",
              "2F": "force-drive", "2E": "write-did"}


def _comic_src(topic, idx):
    """만화 컷 URL. 아직 그림이 없으면 '준비중' 더미로 대체하고 그 사실을 함께 알린다."""
    rel = f"{COMIC_DIR}/{topic}-{idx}.png"
    if (BASE_DIR / "static" / rel).exists():
        return asset(rel), False
    return asset(COMIC_PENDING), True


def topic_briefing(topic):
    """주제 → 브리핑(만화 컷 URL 까지 채운 것). 없는 주제면 None."""
    brief = BRIEFINGS.get(topic)
    if not brief:
        return None
    cuts = []
    for i, cut in enumerate(brief["cuts"], start=1):
        src, pending = _comic_src(topic, i)
        cuts.append({"no": i, "src": src, "pending": pending,
                     "caption": cut["caption"], "note": cut["note"]})
    return dict(brief, topic=topic, cuts=cuts)


def _comic_cuts(topic):
    """주제 → 만화 컷 목록(글 없이 그림만). static/img/comic/{topic}-1.png, -2.png ...
    를 순서대로 찾아 실제 있는 개수만큼 컷을 만든다 — 몇 장을 준비해 두었는지가
    곧 컷 수다. 하나도 없으면 '준비중' 한 장으로 대체한다."""
    cuts = []
    n = 1
    while True:
        src, pending = _comic_src(topic, n)
        if pending:
            break
        cuts.append({"no": n, "src": src})
        n += 1
    if not cuts:
        return [{"no": 1, "src": asset(COMIC_PENDING), "pending": True}]
    return cuts


def step_briefing(step):
    """메시지 작성 단계 → 배경·이론 만화(그림만, 이전/다음으로 넘긴다). 주제가 없으면 None."""
    topic = STEP_BRIEF.get(step["id"]) or _SID_BRIEF.get(step["spec"]["sid"])
    if not topic:
        return None
    return {"topic": topic, "cuts": _comic_cuts(topic)}


# 시퀀스 단계 → 브리핑 주제. 요청 SID 로 되짚는다 (단계 id 가 따로 없기 때문).
_SEQ_TOPIC_SID = {
    "22": "read-did", "19": "dtc-read", "14": "dtc-clear",
    "2F": "force-drive", "2E": "write-did",
    "34": "ecu-download", "36": "ecu-transfer", "37": "ecu-transfer-exit",
    "31": "ecu-verify", "11": "ecu-reset",
}


def _seq_topic(step):
    """자동 시퀀스 단계 → 브리핑 주제. 성격이 같은 단계는 만화 한 벌을 나눠 쓴다."""
    kind = step.get("kind")
    if kind in ("ka_start", "ka_stop"):
        return "session-keepalive"
    if kind in ("seed", "key"):
        return "security-access"
    parts = (step.get("raw") or "").upper().split()
    if not parts:
        return None
    # 0x10 은 여는 쪽과 닫는 쪽이 같은 SID 다 — 서브펑션 0x01(기본 세션)이 '정리'.
    if parts[0] == "10":
        return "session-close" if parts[1:2] == ["01"] else "session-open"
    return _SEQ_TOPIC_SID.get(parts[0])


def with_briefs(sequence):
    """시퀀스 각 단계에 브리핑 주제를 붙이고, 쓰인 주제의 만화·글을 한 벌씩 모은다.

    화면은 주제별 패널을 **미리 다 그려 두고** 지금 단계의 것만 보인다
    (partials/_seq_brief.html + static/js/seq-brief.js). 단계를 넘길 때마다 서버에
    다시 묻지 않기 위해서다 — 시퀀스는 한 화면 안에서 끝까지 진행된다.
    """
    if not sequence:
        return sequence
    briefs = {}
    for step in sequence["steps"]:
        topic = _seq_topic(step)
        if topic and topic not in briefs:
            briefs[topic] = topic_briefing(topic)
        # 브리핑이 없는 주제는 아예 달지 않는다 — 화면이 빈 패널로 갈아 끼우지 않도록.
        step["topic"] = topic if briefs.get(topic) else None
    sequence["briefs"] = [b for b in briefs.values() if b]
    return sequence


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


class QuizResultSubmit(BaseModel):
    """`POST /api/quiz-result` 본문 — 학습자가 제출한 퀴즈 결과 한 건."""

    quiz_title: str = Field(..., min_length=1)
    org: str = Field(..., min_length=1, description="소속")
    name: str = Field(..., min_length=1, description="이름")
    position: str = Field(..., min_length=1, description="직급")
    duration_sec: int = Field(..., ge=0, description="응시 시작~제출까지 걸린 시간(초)")
    score: int = Field(..., ge=0, le=100)


# 결과 로그는 **서버 PC 의 이 폴더**에만 쌓인다. 학습자는 각자의 PC 브라우저에서
# 풀지만, 채점 결과는 POST /api/quiz-result 로 서버에 올라와 여기에 기록된다.
# BASE_DIR 기준의 절대 경로다 — 서버를 어느 작업 디렉터리에서 띄우든 같은 곳에 쌓인다.
RESULT_DIR = BASE_DIR / "TEST_RESULT"

# 날짜 파일 하나를 '읽기 → 덧붙이기 → 쓰기' 로 갱신한다. 교육장에서는 여러 학습자가
# 거의 동시에 제출하는데, 엔드포인트가 동기 함수라 FastAPI 가 스레드풀에서 병렬로
# 돌린다. 잠그지 않으면 두 요청이 같은 배열을 읽고 각자 덮어써 한쪽 기록이 사라진다
# (= "다른 PC 에서 낸 결과가 안 남는다"). 저장 전체를 이 락으로 직렬화한다.
_RESULT_LOCK = threading.Lock()

_quiz_log = logging.getLogger("quiz-result")


def _load_records(path: Path) -> list:
    """날짜 파일을 읽어 배열로 돌려준다. 깨져 있으면 옆으로 치우고 새로 시작한다.

    여기서 예외가 나가면 그날의 **모든** 이후 제출이 500 으로 실패한다. 한 건이
    깨졌다고 나머지 응시자의 기록까지 잃는 쪽이 훨씬 나쁘므로, 손상 파일은
    `*.corrupt-<시각>.json` 으로 보존만 하고 진행한다.
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
        _quiz_log.error("결과 로그 %s 를 읽을 수 없어 %s 로 옮깁니다: %s", path.name, backup.name, exc)
        try:
            path.replace(backup)
        except OSError:
            pass
        return []


@app.post("/api/quiz-result")
def api_quiz_result(body: QuizResultSubmit, request: Request):
    """퀴즈 결과를 **서버 PC** 의 날짜별 로그(TEST_RESULT/YYYY-MM-DD.json)에 한 건 추가한다.

    같은 날 여러 건이면 그 날짜 파일의 배열에 계속 이어 붙인다. 응시자가 직접
    제출 시각을 조작할 수 없도록, '제출시각'은 클라이언트 값이 아니라 이 요청을
    받은 서버 시각으로 찍는다. 같은 이유로 '제출IP'도 서버가 본 접속 주소를 쓴다 —
    누가 어느 자리에서 냈는지 확인할 수 있어야 기록 누락도 눈에 띈다.

    쓰기는 임시 파일에 다 쓴 뒤 교체한다. 도중에 서버가 죽어도 반쪽짜리 JSON 이
    남지 않는다.
    """
    now = datetime.now()
    client_ip = request.client.host if request.client else "-"
    record = {
        "퀴즈": body.quiz_title,
        "소속": body.org,
        "이름": body.name,
        "직급": body.position,
        "제출시각": now.isoformat(timespec="seconds"),
        "소요시간_초": body.duration_sec,
        "점수": body.score,
        "제출IP": client_ip,
    }

    path = RESULT_DIR / f"{now:%Y-%m-%d}.json"
    try:
        with _RESULT_LOCK:
            RESULT_DIR.mkdir(parents=True, exist_ok=True)
            records = _load_records(path)
            records.append(record)
            tmp = path.with_suffix(".tmp")
            with tmp.open("w", encoding="utf-8") as fp:
                json.dump(records, fp, ensure_ascii=False, indent=2)
            tmp.replace(path)
    except OSError as exc:
        # 조용히 삼키면 "저장된 줄 알았는데 없다" 가 된다. 서버 로그에 남기고
        # 클라이언트에도 실패를 알려 화면에서 다시 보내거나 경고할 수 있게 한다.
        _quiz_log.exception("결과 저장 실패 (%s · %s)", client_ip, path)
        raise HTTPException(500, f"결과 저장 실패: {exc}") from None

    _quiz_log.info("결과 저장 · %s · %s/%s · %d점 · %s (총 %d건)",
                   body.quiz_title, body.org, body.name, body.score, client_ip, len(records))
    return {"ok": True, "saved_to": str(path), "count": len(records)}


@app.get("/api/quiz-result")
def api_quiz_result_list(date: str | None = None):
    """저장된 결과를 되읽는다 — 서버에 실제로 쌓였는지 확인하는 용도.

    `GET /api/quiz-result` 오늘치, `?date=2026-09-02` 로 특정 날짜.
    브라우저에서 바로 열어 볼 수 있어야 "저장이 되긴 하나" 를 즉시 확인할 수 있다.
    """
    day = date or f"{datetime.now():%Y-%m-%d}"
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        raise HTTPException(400, "date 는 YYYY-MM-DD 형식입니다")
    path = RESULT_DIR / f"{day}.json"
    with _RESULT_LOCK:
        records = _load_records(path)
    return {"date": day, "path": str(path), "count": len(records), "records": records}


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
                 item: str | None = None, doc: str | None = None,
                 page: int | None = None):
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
        # 진입 안내 팝업 + 도움말 버튼. None 이면 둘 다 그리지 않는다 (실습 준비).
        "page_guide": page_guide(content, target),
    }

    view = content["view"]
    selected = None
    if view == "theory":
        # 좌 목록은 폴더 스캔(그룹 트리), 우 본문은 선택 자료의 **한 페이지** md → HTML.
        # 자료는 소제목 단위로 끊겨 있고 page 로 그중 하나를 고른다 (theory_content).
        # 선택이 없거나 없는 doc(또는 영상 자료)이면 목록 첫 자료 1페이지로 폴백한다.
        materials = theory_content.load_materials()
        selected = theory_content.load_material(doc, page or 1)
        if selected is None:
            first_id = theory_content.first_material_id(materials)
            if first_id:
                selected = theory_content.load_material(first_id, 1)
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
                # 세션 유지(3E) 반복 발행의 소유 범위 — 고른 세부 항목이 바뀌면 남은
                # 발행은 그 항목의 것이 아니다 (static/js/rci-live.js).
                ctx["ka_scope"] = selected["id"] if selected else content_id
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
                            # 세션 유지(3E) 반복 발행은 **코스 하나** 안에서만 이어진다.
                            # 같은 코스의 다음 단계로 넘어가는 재로딩은 살아남지만,
                            # 다른 세부 항목(예: 센서 리딩 → 강제 구동)으로 옮기면
                            # 소유 범위가 달라져 발행이 끊긴다 (static/js/rci-live.js).
                            "ka_scope": sc["id"],
                            # 같은 윈도우에서 [배경·이론] ↔ [메시지 작성] 을 갈아 끼운다.
                            "briefing": step_briefing(step),
                            "next_url": f"/{target['id']}/{content_id}?item={nxt}" if nxt else None})

    ctx["crumbs"] = make_crumbs(
        target, section, title, selected["title"] if selected else None)
    return templates.TemplateResponse(request, tmpl, ctx)
