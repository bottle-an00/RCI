/* 만화 이전/다음 페이징 — 배경·이론 탭(partials/_briefing.html) 과
 * 진단·강제구동·ECU 시퀀스 설명(partials/_seq_brief.html)이 함께 쓴다.
 *
 * 컷은 서버가 모두 미리 그려 두었다 — 페이지를 다시 받지 않고 인덱스만
 * 옮겨 현재 컷만 보이게 토글한다.
 */
(function () {
  "use strict";

  Array.prototype.forEach.call(
    document.querySelectorAll("[data-comic-pager]"), initPager);

  function initPager(root) {
    var slides = root.querySelectorAll("[data-comic-slide]");
    var prevBtn = root.querySelector("[data-comic-prev]");
    var nextBtn = root.querySelector("[data-comic-next]");
    var counter = root.querySelector("[data-comic-current]");
    var zoomBtn = root.querySelector("[data-comic-zoom]");
    // 실습하러가기 · 학습 시작 — 만화를 끝까지(마지막 컷) 봐야 눌린다.
    var ctaBtn = root.querySelector("[data-comic-cta]");
    /* 이론 표지(templates/theory.html)만 켜는 모드. CTA 를 '다음' 옆에 따로 두지 않고
       마지막 컷에서 '다음' 자리를 CTA 가 대신한다 — 버튼 수가 늘지 않으니 다음으로
       넘기던 손이 그대로 학습 시작을 누른다. 다른 화면(커버·브리핑)은 CTA 가 제자리에
       늘 보여야 해서(누를 수만 없다) 기존 방식을 그대로 쓴다. */
    var swapCta = root.hasAttribute("data-comic-swap-cta");
    var idx = 0;

    function render() {
      var last = idx === slides.length - 1;
      Array.prototype.forEach.call(slides, function (s, i) {
        s.classList.toggle("is-active", i === idx);
      });
      if (counter) counter.textContent = idx + 1;
      prevBtn.disabled = idx === 0;
      if (swapCta && ctaBtn) {
        nextBtn.hidden = last;                 // 자리를 비켜 준다
        ctaBtn.hidden = !last;
      } else {
        nextBtn.disabled = last;
        if (ctaBtn) ctaBtn.disabled = !last;
      }
    }

    prevBtn.addEventListener("click", function () {
      if (idx === 0) return;
      idx -= 1;
      render();
    });
    nextBtn.addEventListener("click", function () {
      if (idx === slides.length - 1) return;
      idx += 1;
      render();
    });
    if (ctaBtn) {
      ctaBtn.addEventListener("click", function () {
        if (ctaBtn.disabled) return;
        location.href = ctaBtn.getAttribute("data-href");
      });
    }

    render();
    if (zoomBtn) initZoom(root, zoomBtn);
  }

  /* 확대 — 만화를 화면 거의 전체로 키운다.
   *
   * 예전에는 '기능 설명' 패널이 차지하던 사각형에 맞췄는데, 그러면 원래 크기와
   * 별 차이가 없어 확대의 뜻이 없었다. 지금은 뒤를 어둡게 덮고(백드롭) 브라우저
   * 창 전체를 쓴다 — 크기는 CSS(.comic-pager.is-expanded) 가 vw/vh 로 잡으므로
   * 창이 바뀌어도 다시 잴 일이 없다.
   *
   * 닫는 길은 셋이다: 같은 자리의 아이콘 버튼 · ESC · 백드롭 클릭.
   */
  function initZoom(root, btn) {
    var iconExpand = btn.getAttribute("data-icon-expand");
    var iconCollapse = btn.getAttribute("data-icon-collapse");
    var backdrop = null;
    var onKey = null;

    btn.addEventListener("click", function () {
      if (root.classList.contains("is-expanded")) collapse();
      else expand();
    });

    function expand() {
      root.classList.add("is-expanded");
      backdrop = document.createElement("div");
      backdrop.className = "comic-backdrop";
      backdrop.addEventListener("click", collapse);
      document.body.appendChild(backdrop);
      // ESC — 확대 중일 때만 듣는다(다른 화면의 ESC 동작을 가로채지 않기 위해).
      onKey = function (e) {
        if (e.key === "Escape" || e.key === "Esc") { e.stopPropagation(); collapse(); }
      };
      document.addEventListener("keydown", onKey, true);
      paint(true);
      // 키보드로도 바로 닫을 수 있게 — 포커스를 닫기(축소) 버튼에 둔다.
      try { btn.focus(); } catch (e) { /* 무시 */ }
    }

    function collapse() {
      if (!root.classList.contains("is-expanded")) return;
      root.classList.remove("is-expanded");
      if (backdrop && backdrop.parentNode) backdrop.parentNode.removeChild(backdrop);
      backdrop = null;
      if (onKey) document.removeEventListener("keydown", onKey, true);
      onKey = null;
      paint(false);
    }

    function paint(on) {
      if (on && iconCollapse) btn.innerHTML = iconCollapse;
      if (!on && iconExpand) btn.innerHTML = iconExpand;
      btn.setAttribute("aria-label", on ? "축소 (ESC)" : "확대");
      btn.setAttribute("title", on ? "축소 (ESC)" : "확대");
    }
  }
})();
