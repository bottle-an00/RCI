/* 단계 순차 진행 — 코스(트리 토글 그룹) 안에서 ①→②→③→④ 순서를 강제한다.
 *
 * 규칙: 코스마다 '첫 미통과 단계'까지만 열려 있고 그 뒤는 잠긴다. 통과 조건은
 * 작성한 메시지에 **정상 응답이 돌아온 것**이다 (응답 SID = 요청 SID + 0x40).
 * 통과하면 전송 버튼이 '다음 단계 →' 로 바뀌고 좌측 트리의 다음 항목이 열린다.
 *
 * 통과 여부는 서버가 알 수 없다 — 응답은 브라우저가 MQTT 로 직접 받기 때문이다.
 * 그래서 진행 상태는 localStorage 에 두고, 서버는 '다음 단계 주소'만 내려준다.
 *
 * 의존: rci-live.js 의 "rci:resp" 이벤트. can-composer.js 뒤에 로드해야
 *       입력 잠금이 덮이지 않는다.
 */
(function () {
  "use strict";

  var KEY = "rci:progress:" + location.pathname;   // 콘텐츠(경로)별로 따로 기억

  function load() {
    try { return JSON.parse(localStorage.getItem(KEY)) || []; } catch (e) { return []; }
  }
  function save(ids) {
    try { localStorage.setItem(KEY, JSON.stringify(ids)); } catch (e) { /* 사생활 모드 등 */ }
  }
  function markCleared(id) {
    var ids = load();
    if (ids.indexOf(id) === -1) { ids.push(id); save(ids); }
  }

  function itemOf(a) {
    var m = /[?&]item=([^&#]+)/.exec(a.getAttribute("href") || "");
    return m ? decodeURIComponent(m[1]) : null;
  }

  var state = {};      // 단계 id → "done" | "open" | "locked"
  var courseOf = {};   // 단계 id → 코스 id

  /* 트리에 진행 상태를 반영. 코스별로 앞 단계가 다 끝난 지점까지만 열어 둔다. */
  function applyTree() {
    var cleared = load();
    state = {};
    courseOf = {};
    Array.prototype.forEach.call(
      document.querySelectorAll(".tree__children[data-children]"), function (group) {
        var course = group.dataset.children;
        var allow = true;
        Array.prototype.forEach.call(group.querySelectorAll(".tree__row"), function (row) {
          var id = itemOf(row);
          if (!id) return;
          var done = cleared.indexOf(id) !== -1;
          var s = !allow ? "locked" : (done ? "done" : "open");
          state[id] = s;
          courseOf[id] = course;
          row.classList.toggle("is-done", s === "done");
          row.classList.toggle("is-locked", s === "locked");
          if (s === "locked") row.setAttribute("aria-disabled", "true");
          else row.removeAttribute("aria-disabled");
          if (!done) allow = false;     // 이 단계를 아직 못 지났으면 그 다음부터 잠긴다
        });
      });
  }

  // 잠긴 항목은 클릭해도 이동하지 않는다. href 는 남겨 둔다 — 열리면 그대로 쓰인다.
  document.addEventListener("click", function (e) {
    var row = e.target.closest && e.target.closest(".tree__row.is-locked");
    if (row) e.preventDefault();
  }, true);

  applyTree();

  // 반복 실습을 위한 초기화 (좌측 '세부 항목' 머리에 있다).
  var resetBtn = document.querySelector(".js-progress-reset");
  if (resetBtn) {
    resetBtn.addEventListener("click", function () {
      save([]);
      location.href = location.pathname;      // 첫 단계로 되돌아간다
    });
  }

  var composer = document.querySelector(".composer[data-composer]");
  if (!composer) return;

  var stepId = composer.dataset.stepId;
  var sid = composer.dataset.sid;
  var nextUrl = composer.dataset.nextUrl;
  var gate = document.getElementById("step-gate");
  var bar = composer.querySelector(".write__bar");
  var sendBtn = composer.querySelector(".js-send-frame");
  var input = document.getElementById("frame-input");

  /* 잠긴 단계로 직접 들어온 경우 — 입력을 막고 지금 할 단계를 알려준다. */
  if (state[stepId] === "locked") {
    var openId = null;
    for (var id in state) {
      if (state[id] === "open" && courseOf[id] === courseOf[stepId]) { openId = id; break; }
    }
    gate.hidden = false;
    gate.className = "gate gate--locked";
    gate.innerHTML = "앞 단계를 먼저 통과해야 열립니다."
      + (openId ? ' <a href="?item=' + encodeURIComponent(openId) + '">지금 할 단계로 이동 →</a>' : "");
    input.disabled = true;
    input.placeholder = "";
    sendBtn.disabled = true;
    return;
  }

  /* 정상 응답 판정. 응답 SID = 요청 SID + 0x40 이면 통과. */
  function positiveFor(bytes) {
    if (!bytes || !bytes.length) return false;
    if (bytes[0] !== parseInt(sid, 16) + 0x40) return false;
    // 보안 접근만 예외: Seed 응답(0x67 + 홀수 서브펑션)은 절반일 뿐이다.
    // Key 가 수락된 짝수 서브펑션(0x02/0x12)이어야 잠금이 풀린 것이다.
    if (sid === "27") return bytes.length >= 2 && bytes[1] % 2 === 0;
    return true;
  }

  function showNext() {
    if (bar.querySelector(".js-next")) return;
    // 세션 유지 단계는 예외 — 전송 버튼이 반복 발행 토글이라 통과 후에도 남겨야
    // 다시 돌아와서 켜고 끌 수 있다 (can-composer.js 의 KEEPALIVE 분기).
    if (!composer.dataset.keepalive) sendBtn.hidden = true;
    var el = document.createElement(nextUrl ? "a" : "span");
    el.className = "btn btn--primary js-next";
    el.textContent = nextUrl ? "다음 단계 →" : "코스 완료 ✓";
    if (nextUrl) el.href = nextUrl;
    bar.appendChild(el);
    gate.hidden = false;
    gate.className = "gate gate--ok";
    gate.textContent = nextUrl
      ? "정상 응답 확인 — 다음 단계가 열렸습니다."
      : "정상 응답 확인 — 이 코스를 모두 마쳤습니다.";
  }

  if (state[stepId] === "done") showNext();       // 이미 통과한 단계로 되돌아온 경우

  document.addEventListener("rci:resp", function (e) {
    if (!positiveFor(e.detail.bytes)) return;
    markCleared(stepId);
    applyTree();
    showNext();
  });
})();
