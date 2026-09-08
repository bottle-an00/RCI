/* 만화 ↔ 3D 모델 뷰 전환 — 배경·이론(_briefing.html)과 기능 설명(_seq_brief.html)의
 * 만화 자리를 3D 모델 뷰와 나눠 쓴다. 같은 [data-view3d-scope](panel__body) 안에
 * 두 파인([data-view3d-pane="comic"|"model"])이 함께 그려져 있고, 보이는 쪽만
 * 남기고 나머지를 감춘다 — stage-switch.js 와 같은 방식이다. 전환 버튼은 그
 * 바로 위 panel__head 에 있다(둘 다 같은 .panel 의 자식) — 그래서 scope 의
 * 부모(.panel)에서 버튼을 찾는다.
 *
 * 페이지마다 스코프가 최대 하나뿐이다(메시지 작성 화면엔 배경·이론, 진단·강제구동·
 * ECU 화면엔 기능 설명) — 그래도 여러 개 있어도 되게 각각 독립적으로 짠다.
 */
(function () {
  "use strict";

  Array.prototype.forEach.call(
    document.querySelectorAll("[data-view3d-scope]"), function (scope) {
      var panes = scope.querySelectorAll("[data-view3d-pane]");
      var btns = scope.parentNode.querySelectorAll("[data-view3d-view]");

      function show(view) {
        Array.prototype.forEach.call(panes, function (p) {
          p.hidden = p.dataset.view3dPane !== view;
        });
        Array.prototype.forEach.call(btns, function (b) {
          b.classList.toggle("is-on", b.dataset.view3dView === view);
        });
      }

      Array.prototype.forEach.call(btns, function (b) {
        b.addEventListener("click", function () { show(b.dataset.view3dView); });
      });

      show("comic");
    });
})();
