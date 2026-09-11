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

  /* 확대 — 페이저를 통째로 화면에 고정해, 기능 설명·시퀀스 기능 설명이 차지하던
   * 영역(.seqbrief) 크기·자리에 맞춘다. 창 크기가 바뀌면 그 영역도 바뀌므로
   * resize 때마다 다시 잰다.
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
      var brief = root.closest(".seqbrief");
      if (!brief) return null;
      var r = brief.getBoundingClientRect();
      return { top: r.top, left: r.left, width: r.width, height: r.height };
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
