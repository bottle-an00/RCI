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
    var idx = 0;

    function render() {
      Array.prototype.forEach.call(slides, function (s, i) {
        s.classList.toggle("is-active", i === idx);
      });
      if (counter) counter.textContent = idx + 1;
      prevBtn.disabled = idx === 0;
      nextBtn.disabled = idx === slides.length - 1;
      if (ctaBtn) ctaBtn.disabled = idx !== slides.length - 1;
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

  /* 확대 — 페이저를 통째로 화면에 고정해, 기능 설명·시퀀스 기능 설명·통신 로그가
   * 차지하던 영역(.seqbrief + .run__log) 크기·자리에 맞춘다. 창 크기가 바뀌면
   * 그 영역도 바뀌므로 resize 때마다 다시 잰다.
   */
  function initZoom(root, btn) {
    var onResize = null;
    var iconExpand = btn.getAttribute("data-icon-expand");
    var iconCollapse = btn.getAttribute("data-icon-collapse");

    btn.addEventListener("click", function () {
      if (root.classList.contains("is-expanded")) collapse();
      else expand();
    });

    function targetRect() {
      var zone = root.closest(".run__center--seq");
      var brief = zone && zone.querySelector(".seqbrief");
      var log = zone && zone.querySelector(".run__log");
      if (!brief) return null;
      var top = brief.getBoundingClientRect();
      var bottom = log ? log.getBoundingClientRect() : top;
      return {
        top: top.top, left: top.left, width: top.width,
        height: bottom.bottom - top.top
      };
    }

    function applyRect(r) {
      root.style.top = r.top + "px";
      root.style.left = r.left + "px";
      root.style.width = r.width + "px";
      root.style.height = r.height + "px";
    }

    function expand() {
      var r = targetRect();
      if (!r) return;
      root.classList.add("is-expanded");
      applyRect(r);
      onResize = function () {
        var rr = targetRect();
        if (rr) applyRect(rr);
      };
      window.addEventListener("resize", onResize);
      if (iconCollapse) btn.innerHTML = iconCollapse;
      btn.setAttribute("aria-label", "축소");
      btn.setAttribute("title", "축소");
    }

    function collapse() {
      root.classList.remove("is-expanded");
      root.removeAttribute("style");
      if (onResize) window.removeEventListener("resize", onResize);
      onResize = null;
      if (iconExpand) btn.innerHTML = iconExpand;
      btn.setAttribute("aria-label", "확대");
      btn.setAttribute("title", "확대");
    }
  }
})();
