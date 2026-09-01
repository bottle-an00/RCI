/* 배경·이론 ↔ 메시지 작성 화면 전환.
 *
 * 두 패널(.panel[data-stage-panel])은 같은 윈도우 안에 함께 렌더되어 있고, 보이는
 * 쪽만 남기고 나머지를 감춘다. 서버 왕복(페이지 이동) 없이 바꾸는 이유는 두 가지다:
 *   - 세션 유지(3E) 반복 발행이 화면 전환 때문에 끊기면 안 된다 (rci-live.js 는
 *     페이지 수명에 묶여 있다).
 *   - 작성 중이던 입력이 날아가지 않는다.
 *
 * 기본은 '배경·이론' — 무엇을 왜 보내는지 먼저 읽고 작성으로 넘어가는 순서다.
 * 단계를 옮기면(=페이지가 새로 뜨면) 다시 배경·이론부터 시작한다.
 */
(function () {
  "use strict";

  var stage = document.querySelector("[data-stage]");
  if (!stage) return;

  var panels = stage.querySelectorAll("[data-stage-panel]");

  function show(view) {
    Array.prototype.forEach.call(panels, function (p) {
      p.hidden = p.dataset.stagePanel !== view;
    });
    // 두 패널의 머리에 같은 버튼이 있으므로 모두 갱신한다.
    Array.prototype.forEach.call(
      stage.querySelectorAll(".stagesw__btn"), function (b) {
        b.classList.toggle("is-on", b.dataset.stageView === view);
      });
    stage.dataset.stageView = view;
  }

  // 감춰진 패널 안의 버튼은 눌릴 수 없으니, 위임으로 한 번만 듣는다.
  stage.addEventListener("click", function (e) {
    var btn = e.target.closest && e.target.closest("[data-stage-view]");
    if (!btn || !stage.contains(btn)) return;
    show(btn.dataset.stageView);
    // 작성으로 넘어오면 바로 칠 수 있게 입력에 초점을 준다 (잠긴 단계는 제외).
    if (btn.dataset.stageView === "compose") {
      var input = document.getElementById("frame-input");
      if (input && !input.disabled) input.focus();
    }
  });

  show("brief");
})();
