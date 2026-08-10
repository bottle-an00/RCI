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
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

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
templates = Jinja2Templates(directory=BASE_DIR / "templates")


# --------------------------------------------------------------------------- #
# 데이터 (§8) — 추후 DB/백엔드 연동 시 이 계층만 교체.
# --------------------------------------------------------------------------- #

# 대상. tile_sub=타일 보조문구, status=상단 상태표시 라벨, transport=전송수단.
# device = MQTT 토픽 접미사 (minigit/req/{device}), 사양서 계약.
# model = 3D 뷰어 .glb 파일명(static/models/). UR3 로봇팔 모델 준비 전까지는
#   양 대상 모두 아이오닉5 차량 모델을 임시로 공유한다(준비되면 ur-robot만 교체).
_PLACEHOLDER_MODEL = "hyundai_ioniq_5_lowpoly.glb"
TARGETS = [
    {"id": "rc-car", "label": "RC Car", "status": "RC카", "device": "rccar",
     "transport": "CAN", "tile_sub": "CAN · OBD", "icon": "car",
     "model": _PLACEHOLDER_MODEL},
    {"id": "ur-robot", "label": "UR Robot", "status": "UR Robot", "device": "urrobot",
     "transport": "DoIP", "tile_sub": "DoIP · 이더넷", "icon": "robotarm",
     "model": _PLACEHOLDER_MODEL},
]

# 하단 5메뉴 (GDS-SMART 라벨 그대로).
BOTTOM_NAV = [
    {"label": "GSW", "icon": "globe"},
    {"label": "사용자 지원", "icon": "headset"},
    {"label": "정비 매뉴얼", "icon": "book"},
    {"label": "e-Report", "icon": "ereport"},
    {"label": "환경 설정", "icon": "gear"},
]

# 이론 교육 자료 (공통 — 대상 무관).
THEORY_MATERIALS = [
    {"id": "can", "title": "CAN 통신", "viewer_title": "CAN 통신 기초", "pages": 24},
    {"id": "uds", "title": "UDS 진단 통신", "viewer_title": "UDS 진단 통신", "pages": 18},
]

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
        return [{"id": "prep-equip", "title": "실습 장비 체결"}]
    if content_id == "quiz":
        return [{"id": "quiz-can", "title": "CAN/UDS"},
                {"id": "quiz-doip", "title": "이더넷/DoIP"}]
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
        diag_children = [
            {"id": "uds-session", "title": "진단 세션 제어 / 세션 유지"},
            {"id": "uds-dtc", "title": "DTC(고장코드) 읽기 / 지우기"},
            {"id": "uds-read", "title": "센서·사양 데이터 읽기"},
            {"id": "uds-actuator", "title": "액추에이터 강제구동"},
            {"id": "uds-write", "title": "데이터 쓰기 / 보안 접근"},
        ]
        if t == "ur-robot":
            diag_children.append({"id": "uds-reprog", "title": "리프로그래밍"})
        return [{"id": "msg-force", "title": "강제 구동"},
                {"id": "msg-diag", "title": "진단", "children": diag_children}]
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
    return f"대상 · {target['status']} · 연결됨"


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
    }

    view = content["view"]
    selected = None
    if view == "theory":
        selected = find_leaf(THEORY_MATERIALS, doc)
        ctx.update({"materials": THEORY_MATERIALS, "selected": selected})
        tmpl = "theory.html"
    elif view == "quiz":
        tmpl = "quiz.html"
    elif view == "ecu":
        tmpl = "ecu.html"
    else:
        # detail(prep) / run(diag·force·message) 공통: 트리 + 선택 잎
        nodes = content_tree(content_id, target)
        selected = find_leaf(nodes, item)
        ctx.update({"nodes": nodes, "selected": selected})
        if view == "detail":
            tmpl = "detail.html"
        else:
            tmpl = "run.html"
            ctx["is_composer"] = content.get("composer", False)
            # 라이브(MQTT 연결) 대상 화면: 메시지 작성·진단·강제구동. 블록 간 공유 위해 컨텍스트로.
            ctx["live"] = ctx["is_composer"] or content_id in ("diag", "force")

    ctx["crumbs"] = make_crumbs(
        target, section, title, selected["title"] if selected else None)
    return templates.TemplateResponse(request, tmpl, ctx)
