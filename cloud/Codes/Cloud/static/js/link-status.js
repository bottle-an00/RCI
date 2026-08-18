/* 상단바 연결 표시 — "대상 · UR Robot · 연결됨" 의 뒷부분.
 *
 * 서버는 이 값을 알 수 없다. 브라우저가 브로커에 **직접** 붙기 때문이다(계약 §전송).
 * 서버에서 문구를 굳혀 두면 브로커도 RCI 도 죽어 있는데 '연결됨' 이라고 거짓말을 한다.
 * 실물 연동 테스트에서 가장 먼저 보게 되는 표시라 거짓말이면 곤란하다.
 *
 * '연결됨' 의 정의 = 브로커에 붙었고 + RCI 가 minigit/status/rci-* 로 online 을 알렸다.
 * 브로커만 붙은 상태는 RCI 가 죽어 있는 것이므로 연결됨이 아니다. 둘을 구분해야
 * "브로커가 안 떴나 / RCI 가 안 떴나" 를 화면만 보고 가를 수 있다 → title 에 남긴다.
 *
 * 상태를 얻는 경로가 두 가지다:
 *   실습 화면(.run[data-live])   rci-live.js 가 이미 브로커를 쥐고 있다 → "rci:link" 를 받는다
 *   그 밖의 화면(컨텐츠 선택 등)  붙은 사람이 없다 → 여기서 관찰용으로만 직접 붙는다
 * 두 번째가 없으면 정작 실습에 들어가기 전에 연결 여부를 확인할 방법이 없다.
 * 관찰용 접속은 **아무것도 발행하지 않는다** — RCI 연동 테스트를 방해하면 안 된다.
 *
 * 소유자 판별은 window.RCI 유무가 아니라 DOM(.run[data-live])으로 한다. 스크립트
 * 로드 순서에 따라 window.RCI 가 아직 없을 수 있어서다.
 */
(function () {
  "use strict";

  var el = document.querySelector("[data-link-status]");
  if (!el) return;
  var device = el.dataset.device;
  if (!device) return;                      // 대상이 없는 화면 (홈 등)

  var out = el.querySelector(".crumbbar__link");
  var wsUrl = el.dataset.wsUrl || "";
  var statusTopic = "minigit/status/rci-" + (device === "urrobot" ? "ur" : "rc");
  var GRACE = 3000;                         // 브로커 접속 후 RCI 소식을 기다리는 시간

  /* 표시 상태. cls 는 .crumbbar__status 에 붙어 점(●) 색을 정한다. */
  var VIEW = {
    mock:  {cls: "link--mock",  text: "브라우저 목업",
            title: "브로커 없이 브라우저 안에서 응답을 만듭니다 (mock-rci.js)"},
    probe: {cls: "link--probe", text: "확인 중…", title: "브로커 접속을 확인하고 있습니다"},
    up:    {cls: "link--up",    text: "연결됨",   title: ""},
    down:  {cls: "link--down",  text: "연결안됨", title: ""},
  };

  function paint(key, title) {
    var v = VIEW[key];
    out.textContent = v.text;
    el.classList.remove("link--mock", "link--probe", "link--up", "link--down");
    el.classList.add(v.cls);
    el.title = title || v.title;
  }

  /* {mode, broker, rci} → 표시 상태.
     브로커는 붙었는데 RCI 소식이 없는 구간은 바로 '연결안됨' 이라 하지 않는다.
     retained status 가 도착하기까지 한 박자 걸려서, 매 페이지 로드마다 빨간불이
     번쩍이면 실제 장애와 구분이 안 된다. */
  var graceTimer = null;

  function render(st) {
    if (graceTimer) { clearTimeout(graceTimer); graceTimer = null; }
    if (st.mode === "mock") { paint("mock"); return; }
    if (!wsUrl) {
      paint("down", "브로커 WS 주소가 설정되지 않았습니다 — RCI_BROKER_WS_HOST 를 지정하세요");
      return;
    }
    if (!st.broker) {
      paint("down", "브로커(" + wsUrl + ")에 붙지 못했습니다");
      return;
    }
    if (st.rci === "online") {
      paint("up", "브로커 연결됨 · RCI online (" + statusTopic + ")");
      return;
    }
    if (st.rci) {                            // offline 등 명시적으로 알려온 경우
      paint("down", "브로커는 연결됨 · RCI 상태 " + st.rci);
      return;
    }
    paint("probe", "브로커 연결됨 · RCI 상태 수신 대기 중");
    graceTimer = setTimeout(function () {
      graceTimer = null;
      paint("down", "브로커는 연결됨 · RCI 가 " + statusTopic
        + " 을 발행하지 않았습니다 (RCI 미기동으로 보입니다)");
    }, GRACE);
  }

  /* --- 실습 화면: rci-live.js 가 쥔 접속의 상태를 받아 그린다 --------------- */
  if (document.querySelector(".run[data-live]")) {
    paint("probe");
    document.addEventListener("rci:link", function (e) { render(e.detail); });
    return;
  }

  /* --- 그 밖의 화면: 관찰 전용으로 직접 붙는다 ---------------------------- */
  var st = {mode: "mqtt", broker: false, rci: null};
  try { st.mode = localStorage.getItem("rci:transport:" + device) || "mqtt"; } catch (e) { /* 기본값 */ }

  render(st);
  if (st.mode === "mock") return;            // 목업 모드면 붙을 이유가 없다
  if (typeof mqtt === "undefined" || !wsUrl) return;

  var client = mqtt.connect(wsUrl, {reconnectPeriod: 5000, connectTimeout: 4000});
  client.on("connect", function () {
    st.broker = true; st.rci = null;
    client.subscribe(statusTopic, {qos: 1});  // 구독만 — 발행은 하지 않는다
    render(st);
  });
  client.on("message", function (topic, payload) {
    try { st.rci = (JSON.parse(payload.toString()) || {}).state || null; }
    catch (e) { st.rci = null; }
    render(st);
  });
  client.on("close", function () { st.broker = false; st.rci = null; render(st); });
  client.on("error", function () { st.broker = false; st.rci = null; render(st); });
})();
