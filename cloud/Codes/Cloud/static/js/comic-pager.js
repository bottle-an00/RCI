/* 배경·이론 탭의 만화 이전/다음 페이징.
 *
 * 컷은 서버가 모두 미리 그려 두었다(partials/_briefing.html) — 페이지를 다시 받지
 * 않고 인덱스만 옮겨 현재 컷만 보이게 토글한다.
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
    var idx = 0;

    function render() {
      Array.prototype.forEach.call(slides, function (s, i) {
        s.classList.toggle("is-active", i === idx);
      });
      if (counter) counter.textContent = idx + 1;
      prevBtn.disabled = idx === 0;
      nextBtn.disabled = idx === slides.length - 1;
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
  }
})();
