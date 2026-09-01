/* 진단 시퀀스 러너 — 카테고리 하나(진단 · 강제구동 · ECU 업그레이드)를 한 단계씩 밟는다.
 *
 * 왜 있는가: 진단 요청 한 줄을 띡 보내고 끝나면, 실제로 그 동작이 성립하기까지 무엇이
 * 오가는지 배울 수 없다. 세션을 열어야 하고, 여는 동안 세션 유지 메시지를 계속 보내야
 * 하고, 강제구동·리프로그래밍이면 보안 접근으로 잠금을 풀어야 한다. '메시지 작성'
 * 코스에서 사람이 한 단계씩 밟는 그 순서를, 여기서도 한 단계씩 밟으며 보여준다.
 *
 * 순서(단계 목록)는 서버가 정한다 — main.py `auto_sequence()` → 템플릿의
 * <script id="seq-plan"> JSON. 여기는 **실행·실패 정책**만 맡는다.
 *
 * 한 번 누르면 한 단계인 이유: 자동으로 12단계가 흘러가면 로그만 쌓이고 '지금 무엇을
 * 왜 하는지'는 지나가 버린다. 가운데 '기능 설명' 패널을 읽고 납득한 뒤 다음을 누르는
 * 리듬이라야 순서가 몸에 남는다. 그래서 단계가 끝나면 **멈춰서 기다린다**.
 *
 * 전송 방식(목업 / MQTT 목업 / RCI(MQTT))은 window.RCI.send() 가 이미 갈라 준다.
 * 이 파일이 모드를 보는 곳은 **정책** 뿐이다 — 아래 POLICY 표 참조.
 *
 * 의존: rci-live.js (window.RCI, "rci:answer" 이벤트) 뒤에 로드할 것.
 * 방송: "seq:step" — 지금 밟는 단계를 알린다 (seq-brief.js 가 설명 패널을 갈아 낀다).
 */
(function () {
  "use strict";

  var root = document.querySelector(".run[data-live]");
  var planEl = document.getElementById("seq-plan");
  if (!root || !planEl || !window.RCI) return;

  var plan;
  try { plan = JSON.parse(planEl.textContent || "null"); } catch (e) { plan = null; }
  if (!plan || !plan.steps || !plan.steps.length) return;

  var steps = plan.steps;
  var runBtn = document.querySelector(".js-seq-run");
  var statusEl = document.querySelector("[data-seq-status]");
  var modeEl = document.querySelector("[data-seq-mode]");
  var barEl = document.querySelector("[data-seq-progress] > span");
  var rows = Array.prototype.slice.call(document.querySelectorAll("[data-seq-row]"));

  var KA_PERIOD = 2000;     // 세션 유지 발행 주기 (계약 §표기·처리 규칙: 2초 이내)

  /* 전송 방식별 정책.
   *
   * 갈리는 것은 두 가지다 — **얼마나 기다리는가**와 **실패했을 때 이어갈 수 있는가**.
   *   목업 / MQTT 목업  교육용이다. 한 단계가 어긋나도 다음 단계를 밟아 볼 수 있다
   *                     (거부당하는 모습 자체가 학습 자료다). 다만 critical 단계는
   *                     뒤가 성립하지 않으므로 어느 모드에서든 거기서 끝난다.
   *   RCI(MQTT)         실물이다. 앞 단계가 확인되지 않았는데 다음 요청을 던지는 것은
   *                     장비에 대고 조건 없이 명령하는 짓이라 무조건 멈춘다. 첫 단계
   *                     전에도 사람에게 한 번 묻는다(강제구동·리프로그래밍만).
   */
  var POLICY = {
    mock: {
      label: "브라우저 목업", timeout: 2500, confirm: false, stopOnFail: false,
      intro: "브라우저 안에서 응답을 만들어 낸다 — 브로커·RCI 없이 순서만 익히는 모드.",
    },
    mqtt: {
      label: "MQTT 목업", timeout: 3000, confirm: false, stopOnFail: false,
      intro: "브로커를 거쳐 PC 의 목업(mock_rci.py)이 답한다 — 계약·왕복을 확인하는 모드.",
    },
    rci: {
      label: "RCI(MQTT) 실물", timeout: 5000, confirm: true, stopOnFail: true,
      intro: "브로커를 거쳐 실물 RCI 가 답한다 — 장비가 실제로 반응하고, "
           + "한 단계라도 어긋나면 시퀀스를 즉시 멈춘다.",
    },
  };
  function policy() { return POLICY[window.RCI.mode()] || POLICY.mqtt; }

  /* Seed → Key. 학습용 알고리즘(각 바이트 + 0x44)이고 목업의 고정 표와 일치한다
     — mock_rci.SECURITY: rccar 12 34 → 56 78 / urrobot 11 22 33 44 → 55 66 77 88.
     실물 RCI 가 다른 알고리즘을 쓰면 여기서 NRC 0x35 로 갈린다(그게 정상이다). */
  var KEY_OFFSET = 0x44;
  function hex(b) { return ("0" + b.toString(16).toUpperCase()).slice(-2); }
  function keyFrom(seedBytes) {
    return seedBytes.map(function (b) { return hex((b + KEY_OFFSET) & 0xFF); }).join(" ");
  }

  /* 단계 통과 판정 — 받은 긍정 응답이 이 단계가 기대한 것인가?
   *
   * 부정 응답(7F)·에러·NRC 0x78(처리 중)은 아래 러너가 이미 걸러낸다. 여기 오는 것은
   * 긍정 응답뿐이므로, 판단할 것은 '기대한 응답과 같은 것인가' 하나다.
   *
   *   step.expect  서버가 준 기대 응답 **접두** hex 문자열. "50 03" · "67 01" · "76 02"
   *                처럼 길이가 제각각이고, 없는 단계도 있다(그때는 통과).
   *   bytes        실제로 받은 응답 바이트 배열. 예: [0x62, 0x01, 0x05, 0x01, 0x56]
   *
   * 접두만 맞추고 뒤는 자유로 둔다. 전체 일치로 하면 데이터가 붙는 응답
   * (`62 01 05 01 56`)은 영영 통과하지 못하고, 첫 바이트만 보면 `22 01 05` 를 보냈는데
   * `62 01 07` 이 와도 넘어간다. 어디까지 엄격할지는 서버가 expect 를 몇 바이트로
   * 적느냐로 정한다 — 그래서 ECU 블록 전송은 카운터까지("76 02") 적혀 있다.
   *
   * 반환: true 통과 · false 어긋남(단계 실패로 기록된다)
   */
  function matches(step, bytes) {
    var want = (step.expect || "").trim();
    if (!want) return true;                       // 기대를 정하지 않은 단계는 통과
    var exp = want.split(/\s+/);
    if (bytes.length < exp.length) return false;
    for (var i = 0; i < exp.length; i++) {
      if (bytes[i] !== parseInt(exp[i], 16)) return false;
    }
    return true;                                   // 접두가 맞으면 뒤 데이터는 자유
  }

  /* ---- 화면 그리기 ------------------------------------------------------- */

  // state = "now" | "done" | "fail" | null. CSS 는 .stepper__row.is-* 로 잡는다.
  function paintRow(i, state) {
    if (!rows[i]) return;
    rows[i].classList.remove("is-now", "is-done", "is-fail");
    if (state) rows[i].classList.add("is-" + state);
  }

  function paintProgress(done, label) {
    if (barEl) barEl.style.width = Math.round(done / steps.length * 100) + "%";
    if (statusEl) statusEl.textContent = label + " · " + done + " / " + steps.length;
  }

  /* 버튼 하나가 세 가지 일을 한다 — 다음 단계 실행 / 실행 중(잠금) / 처음부터 다시.
     단계마다 사람이 눌러야 나아가므로, 지금 누르면 무엇이 일어나는지가 버튼에
     그대로 적혀 있어야 한다. */
  function paintBtn() {
    if (!runBtn) return;
    runBtn.textContent = busy ? "실행 중…"
      : ended ? "↻ 처음부터 다시" : "다음 시퀀스 실행 →";
    runBtn.disabled = busy;
    runBtn.classList.toggle("btn--stop", ended);
  }

  function paintMode() {
    if (modeEl) modeEl.textContent = policy().label;
  }

  // 가운데 '기능 설명' 패널에게 지금 단계를 알린다 (seq-brief.js).
  function announce(i) {
    document.dispatchEvent(new CustomEvent("seq:step", {
      detail: { index: i, step: steps[i], total: steps.length },
    }));
  }

  /* ---- 러너 -------------------------------------------------------------- */

  var idx = -1;        // 마지막으로 밟은 단계 (-1 = 아직 시작 전)
  var busy = false;    // 한 단계가 왕복 중 — 중복 클릭을 막는다
  var ended = false;   // 더 밟을 단계가 없다 (완주했거나 치명적 실패로 끊겼다)
  var pending = null;  // 응답을 기다리는 중 {reqId, step, timer}
  var seed = null;     // 보안 Seed 단계에서 받아 Key 단계로 넘긴다
  var link = { broker: false, rci: null };   // rci-live 가 방송하는 접속 상태

  function log(cls, text) { window.RCI.log(cls, text); }

  function expectSid(step) {
    var first = (step.expect || "").trim().split(/\s+/)[0];
    return first ? parseInt(first, 16) : NaN;
  }

  function reset() {
    idx = -1;
    seed = null;
    busy = false;
    ended = false;
    if (pending) { clearTimeout(pending.timer); pending = null; }
    rows.forEach(function (r) { r.classList.remove("is-now", "is-done", "is-fail"); });
    paintProgress(0, "대기 중");
    paintBtn();
    log("muted", "○ 시퀀스를 처음으로 되돌렸습니다 · " + plan.title);
    if (window.RCI.keepalive.on()) window.RCI.keepalive.stop("시퀀스 초기화");
    announce(0);
  }

  /* 한 단계를 수행한다. 성공이든 실패든 끝나면 멈춰서 다음 클릭을 기다린다. */
  function runNext() {
    var p = policy();
    // 브로커에 붙기 전에 발행하면 그 메시지는 그냥 사라진다 — 화면상으로는 그 단계가
    // '무응답' 으로 죽어 원인을 브로커·RCI 쪽에서 찾게 된다. 여기서 미리 막는다.
    if (window.RCI.mode() !== "mock" && !link.broker) {
      log("err", "✗ 아직 브로커에 붙지 않았습니다 — 로그에 '● 브로커 연결됨' 이 뜬 뒤에 "
        + "실행하세요. 브로커 없이 순서만 볼 거라면 상단에서 '목업' 으로 전환하세요.");
      return;
    }
    // 첫 단계 전에 한 번만 묻는다. 단계마다 물으면 확인 대화상자가 12번 뜬다.
    if (idx < 0) {
      if (plan.danger && p.confirm && !window.confirm(
          plan.title + "\n\nRCI(MQTT) 실물 모드입니다. 장비가 실제로 움직입니다."
          + "\n주변 안전을 확인했습니까?")) {
        return;
      }
      log("muted", "▶ 시퀀스 시작 · " + plan.title + " · 전송 " + p.label
        + " · 단계 " + steps.length + "개 (한 번에 한 단계)");
      log("muted", "   " + p.intro);
    }

    idx++;
    var st = steps[idx];
    busy = true;
    paintRow(idx, "now");
    paintProgress(idx, "진행 중");
    paintBtn();
    announce(idx);

    // 보낼 것이 없는 단계 — 세션 유지 발행 중지가 여기 해당한다.
    if (st.kind === "ka_stop") {
      if (window.RCI.keepalive.on()) window.RCI.keepalive.stop("시퀀스 진행");
      else log("muted", "○ 세션 유지 발행은 이미 멈춰 있습니다");
      if (st.note) log("note", "   ↳ " + st.note);
      return pass();
    }

    var raw = st.raw;
    if (st.kind === "key") {
      if (!seed || !seed.length) return fail(st, "앞 단계에서 Seed 를 받지 못해 Key 를 만들 수 없습니다");
      raw = "27 02 " + keyFrom(seed);
    }
    if (!raw) return fail(st, "보낼 페이로드가 정의되지 않았습니다");

    var reqId = null;
    if (st.kind === "ka_start") {
      // 반복 발행은 rci-live 가 쥔다 — 화면을 옮겨도 계속돼야 하는 '연결의 상태'라서다.
      // 대신 발행 id 를 돌려받지 못하므로, 이 단계만 응답 SID 로 짝을 맞춘다.
      if (!window.RCI.keepalive.start(raw, KA_PERIOD)) {
        return fail(st, "세션 유지 발행을 시작하지 못했습니다");
      }
    } else {
      reqId = window.RCI.send(raw, p.timeout);
      if (!reqId) return fail(st, "전송하지 못했습니다 (전송 경로가 없습니다)");
    }
    pending = { reqId: reqId, step: st };
    pending.timer = setTimeout(onTimeout, p.timeout);
  }

  function onTimeout() {
    if (!pending) return;
    var st = pending.step;
    pending = null;
    fail(st, "응답 없음 (" + (policy().timeout / 1000) + "초) — 브로커·RCI 가 떠 있는지 "
       + "확인하거나 상단에서 '목업' 으로 전환해 보세요");
  }

  /* 단계 통과. 마지막이었다면 완주로 마무리한다. */
  function pass() {
    paintRow(idx, "done");
    busy = false;
    if (idx >= steps.length - 1) {
      ended = true;
      paintProgress(steps.length, "완료");
      log("muted", "■ 시퀀스 완료 · " + plan.title);
    } else {
      paintProgress(idx + 1, "대기 중");
    }
    paintBtn();
  }

  /* 단계 실패. 뒤가 성립하지 않는 단계(critical)나 실물 모드면 거기서 끝낸다. */
  function fail(st, why) {
    paintRow(idx, "fail");
    busy = false;
    log("err", "✗ 단계 " + (idx + 1) + " 실패 · " + st.title + " — " + why);

    if (st.critical || policy().stopOnFail || idx >= steps.length - 1) {
      ended = true;
      paintProgress(Math.max(0, idx), "중단");
      log("muted", "■ 시퀀스 중단 — 단계 " + (idx + 1) + " 에서 끊겼습니다");
      // 뒤 단계(세션 정리)를 밟지 못했으므로 발행만이라도 손수 거둔다.
      if (window.RCI.keepalive.on()) window.RCI.keepalive.stop("시퀀스 중단");
    } else {
      paintProgress(idx, "대기 중");
      log("muted", "   ↳ " + policy().label + " 모드라 다음 단계를 이어서 밟아 볼 수 있습니다 "
        + "(RCI(MQTT) 모드였다면 여기서 끊깁니다)");
    }
    paintBtn();
  }

  /* ---- 응답 수신 ---------------------------------------------------------- */

  document.addEventListener("rci:answer", function (e) {
    if (!busy || !pending) return;
    var m = e.detail || {};

    // 짝 맞추기. 우리가 보낸 요청은 id 로, 세션 유지 발행은 응답 SID 로 (id 를 모른다).
    if (pending.reqId) {
      if (m.id !== pending.reqId) return;
    } else if (!m.bytes || m.bytes[0] !== expectSid(pending.step)) {
      return;
    }

    // 0x78 responsePending 은 '처리 중' 일 뿐 — 같은 id 로 최종 응답이 뒤따른다.
    if (m.type === "negative" && m.nrc === "78") return;

    clearTimeout(pending.timer);
    var st = pending.step;
    pending = null;

    if (m.type !== "positive") {
      return fail(st, m.type === "negative"
        ? "부정 응답 NRC " + m.nrc + " " + (m.nrcName || "")
        : "에러 " + (m.message || "원인 불명"));
    }
    if (!matches(st, m.bytes)) {
      return fail(st, "기대한 응답(" + st.expect + ")이 아닙니다 — 받은 값 " + m.raw);
    }

    if (st.kind === "seed") {
      seed = m.bytes.slice(2);                     // 67 01 <Seed…>
      log("note", "   ↳ Key 계산 " + seed.map(hex).join(" ") + " → " + keyFrom(seed)
        + " (각 바이트 + 0x" + hex(KEY_OFFSET) + ")");
    }
    if (st.note) log("note", "   ↳ " + st.note);
    pass();
  });

  /* ---- 조작 --------------------------------------------------------------- */

  if (runBtn) {
    runBtn.addEventListener("click", function () {
      if (busy) return;
      if (ended) reset();
      else runNext();
    });
  }

  // 접속 상태는 rci-live 가 방송한다 (상단바 연결 표시와 같은 소스).
  document.addEventListener("rci:link", function (e) {
    if (e.detail) link = e.detail;
  });

  // 전송 방식이 바뀌면 응답의 주인이 바뀐다 — 밟던 자리를 그대로 이어갈 수 없다.
  document.addEventListener("rci:mode", function () {
    if (idx >= 0 && !ended) {
      log("muted", "○ 전송 방식이 바뀌어 시퀀스를 처음으로 되돌립니다");
      if (pending) { clearTimeout(pending.timer); pending = null; }
      reset();
    }
    paintMode();
  });

  paintMode();
  paintBtn();
  paintProgress(0, "대기 중");
})();
