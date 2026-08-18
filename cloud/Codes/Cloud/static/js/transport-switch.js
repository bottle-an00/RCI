/* 상단바 전송 방식 토글 — 실 MQTT ↔ 목업.
 *
 * 실제 전환은 rci-live.js 가 한다(연결 정리 → 새 경로 시작). 여기서는 버튼 상태를
 * 활성 경로에 맞춰 칠하고 클릭을 넘긴다. 리로드 없이 바뀌고, 선택은 화면을 옮겨도
 * 유지된다(rci-live.js 가 localStorage 에 저장).
 */
(function () {
  "use strict";

  var sw = document.querySelector("[data-transport-switch]");
  if (!sw || !window.RCI || !window.RCI.setMode) return;

  var btns = Array.prototype.slice.call(sw.querySelectorAll(".modesw__btn"));

  function paint() {
    var mode = window.RCI.mode();
    btns.forEach(function (b) {
      var on = b.dataset.mode === mode;
      b.classList.toggle("is-on", on);
      b.setAttribute("aria-pressed", on ? "true" : "false");
    });
    sw.dataset.mode = mode;
  }

  sw.addEventListener("click", function (e) {
    var btn = e.target.closest(".modesw__btn");
    if (btn) window.RCI.setMode(btn.dataset.mode);
  });

  // rci-live.js 가 전환을 마치면 알려준다 (프로그램적 전환도 반영되게).
  document.addEventListener("rci:mode", paint);
  paint();
})();
