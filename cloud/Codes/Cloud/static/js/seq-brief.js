/* 시퀀스 단계 설명 패널 — 지금 밟는 단계에 맞춰 가운데 그림·글을 갈아 낀다.
 *
 * 왜 별도 파일인가: auto-sequence.js 는 브로커·목업(window.RCI)이 있어야 돌아간다.
 * 하지만 '이 단계가 무엇을 왜 하는가' 는 통신과 무관하게 읽을 수 있어야 한다 —
 * 연결이 없어도 시퀀스 목록을 눌러 가며 공부하는 것이 이 화면의 절반이다.
 *
 * 패널은 서버가 주제별로 **미리 다 그려 두었다**(partials/_seq_brief.html).
 * 여기서 하는 일은 hidden 을 옮기는 것뿐 — 그림이 이미 받아져 있으니 단계를 넘길 때
 * 화면이 깜빡이지 않는다.
 *
 * 두 갈래 입력
 *   "seq:step" 이벤트   auto-sequence.js 가 단계를 실행할 때 (진행을 따라간다)
 *   행 클릭             사람이 목록에서 골랐을 때 (미리 읽어 본다)
 */
(function () {
  "use strict";

  var planEl = document.getElementById("seq-plan");
  var brief = document.querySelector(".seqbrief");
  if (!planEl || !brief) return;

  var plan;
  try { plan = JSON.parse(planEl.textContent || "null"); } catch (e) { plan = null; }
  if (!plan || !plan.steps || !plan.steps.length) return;

  var steps = plan.steps;
  var stepEl = brief.querySelector("[data-brief-step]");
  var rawEl = brief.querySelector("[data-brief-raw]");
  var panes = Array.prototype.slice.call(brief.querySelectorAll(".seqbrief__pane"));
  var empties = Array.prototype.slice.call(brief.querySelectorAll("[data-brief-empty]"));
  var bodies = Array.prototype.slice.call(brief.querySelectorAll(".seqbrief__body"));
  var rows = Array.prototype.slice.call(document.querySelectorAll("[data-seq-row]"));

  var shown = null;   // 지금 띄운 주제

  function show(i) {
    var step = steps[i];
    if (!step) return;

    // 브리핑이 없는 단계는 이전 화면을 그대로 둔다 — 비워 봐야 알려주는 것이 없다.
    if (step.topic && step.topic !== shown) {
      shown = step.topic;
      panes.forEach(function (p) {
        var topic = p.getAttribute("data-brief-comic") || p.getAttribute("data-brief-doc");
        p.hidden = topic !== step.topic;
      });
      empties.forEach(function (el) { el.hidden = true; });
      // 단계를 넘기면 새 설명은 처음부터 읽어야 한다.
      bodies.forEach(function (b) { b.scrollTop = 0; });
    }

    if (stepEl) stepEl.textContent = (i + 1) + ". " + step.title
      + " (" + (i + 1) + "/" + steps.length + ")";
    if (rawEl) rawEl.textContent = step.raw || "";

    rows.forEach(function (r, k) { r.classList.toggle("is-open", k === i); });
  }

  // 진행을 따라간다.
  document.addEventListener("seq:step", function (e) {
    if (e.detail && typeof e.detail.index === "number") show(e.detail.index);
  });

  // 사람이 목록에서 고르면 그 단계를 미리 읽는다. 진행 상태(is-now/done/fail)는
  // auto-sequence.js 가 쥐고 있으므로 여기서는 건드리지 않는다.
  rows.forEach(function (row, i) {
    row.addEventListener("click", function () { show(i); });
  });

  show(0);
})();
