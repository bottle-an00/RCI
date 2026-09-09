/* 통신 로그 ↔ 디버그 로그 전환 — 실제 UDS 왕복(raw)과 연결·모드·에러 같은 운영
 * 메시지를 뒤섞으면 학습자가 지금 무엇이 오갔는지 읽어내기 어렵다. rci-live.js 가
 * 두 로그에 각각 쓰고(log()/dbg()), 여기서는 보이는 쪽만 바꾼다.
 * 실행 화면에 로그 패널은 하나뿐이라 스코프를 나누지 않는다(stage-switch.js 와
 * 같은 방식이지만 페이지에 한 벌만 있다고 가정한다).
 */
(function () {
  "use strict";

  var sw = document.querySelector("[data-log-switch]");
  if (!sw) return;

  var panel = sw.closest(".panel");
  var panes = panel.querySelectorAll("[data-log-pane]");
  var btns = panel.querySelectorAll("[data-log-view]");

  function show(view) {
    Array.prototype.forEach.call(panes, function (p) {
      p.hidden = p.dataset.logPane !== view;
    });
    Array.prototype.forEach.call(btns, function (b) {
      b.classList.toggle("is-on", b.dataset.logView === view);
    });
  }

  Array.prototype.forEach.call(btns, function (b) {
    b.addEventListener("click", function () { show(b.dataset.logView); });
  });
})();
