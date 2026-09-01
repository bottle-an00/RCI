/* 이론 교육 페이지 이동 — 키보드 ←/→ 를 이전·다음 버튼에 얹는다.
 *
 * 버튼 자체는 서버가 그린 <a> 라 이 파일 없이도 동작한다. 여기서는 태블릿에 키보드를
 * 붙여 보거나 PC 로 볼 때의 편의만 더한다(진행 방향이 왼→오른쪽이라 화살표가 자연스럽다).
 *
 * 주소 이동인 이유는 theory_content.split_pages 주석 참고 — 서버가 보이는 페이지만
 * 변환해 내려주고, mermaid 는 그 페이지에서만 그려진다.
 */
(function () {
  "use strict";

  var pager = document.querySelector("[data-pager]");
  if (!pager) return;

  document.addEventListener("keydown", function (e) {
    if (e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return;
    // 글을 쓰는 중이면 화살표는 커서 이동이다 — 가로채지 않는다.
    var el = document.activeElement;
    if (el && (el.isContentEditable
               || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName))) return;

    var url = e.key === "ArrowLeft" ? pager.dataset.prev
            : e.key === "ArrowRight" ? pager.dataset.next
            : null;
    if (!url) return;
    e.preventDefault();
    location.href = url;
  });
})();
