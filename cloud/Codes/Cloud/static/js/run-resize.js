/* 실습 실행 3분할 패널 리사이즈 — 좌/우 고정폭 패널을 핸들 드래그로 조절.
 *
 * 레이아웃(styles.css): .run 은 flex, .run__left(고정폭)·.run__center(flex:1)·
 *   .run__right(고정폭), 사이에 .run__grip 두 개. 가운데는 flex 라 나머지를 흡수하므로
 *   각 핸들은 인접한 '고정폭' 패널만 조절하면 된다.
 *   grip[0]: 앞이 .run__left → 좌 패널(오른쪽으로 끌면 넓어짐, dir=+1)
 *   grip[1]: 뒤가 .run__right → 우 패널(왼쪽으로 끌면 넓어짐, dir=-1)
 *
 * 서버 렌더라 트리 항목 클릭마다 전체 리로드된다 → 폭을 localStorage 에 저장해 유지.
 */
(function () {
  "use strict";

  var run = document.querySelector(".run");
  if (!run) return;

  var MIN = 180, MAX = 640, KEY = "rci.panel.";

  function clamp(v) { return Math.max(MIN, Math.min(MAX, v)); }
  function load(name) { try { return parseInt(localStorage.getItem(KEY + name), 10); } catch (e) { return NaN; } }
  function save(name, v) { try { localStorage.setItem(KEY + name, v); } catch (e) { /* 무시 */ } }

  Array.prototype.forEach.call(run.querySelectorAll(".run__grip"), function (grip) {
    var prev = grip.previousElementSibling, next = grip.nextElementSibling;
    var target, dir, name;
    if (prev && prev.classList.contains("run__left")) { target = prev; dir = 1; name = "left"; }
    else if (next && next.classList.contains("run__right")) { target = next; dir = -1; name = "right"; }
    else return;

    var saved = load(name);                       // 저장된 폭 복원
    if (saved) target.style.width = clamp(saved) + "px";

    grip.addEventListener("pointerdown", function (e) {
      e.preventDefault();
      var startX = e.clientX;
      var startW = target.getBoundingClientRect().width;
      try { grip.setPointerCapture(e.pointerId); } catch (err) { /* 커서가 핸들 밖으로 나가도 추적 */ }
      document.body.style.userSelect = "none";

      function move(ev) {
        target.style.width = clamp(startW + dir * (ev.clientX - startX)) + "px";
      }
      function up() {
        try { grip.releasePointerCapture(e.pointerId); } catch (err) { /* 무시 */ }
        document.body.style.userSelect = "";
        grip.removeEventListener("pointermove", move);
        grip.removeEventListener("pointerup", up);
        save(name, parseInt(target.style.width, 10));
      }
      grip.addEventListener("pointermove", move);
      grip.addEventListener("pointerup", up);
    });
  });
})();
