/* 실습 실행 3분할 패널 리사이즈 — 좌/우 고정폭 패널을 핸들 드래그로 조절.
 *
 * 레이아웃(styles.css): .run 은 flex, .run__left(고정폭)·.run__center(flex:1)·
 *   .run__right(고정폭), 사이에 .run__grip 두 개. 가운데는 flex 라 나머지를 흡수하므로
 *   각 핸들은 인접한 '고정폭' 패널만 조절하면 된다.
 *   grip[0]: 앞이 .run__left → 좌 패널(오른쪽으로 끌면 넓어짐, dir=+1)
 *   grip[1]: 뒤가 .run__right → 우 패널(왼쪽으로 끌면 넓어짐, dir=-1)
 *
 * 최소 폭이 둘 있다. 끄는 쪽(고정폭 패널)의 최소와, **밀리는 쪽**(가변 = 가운데)의
 * 최소다. 예전에는 둘 다 없어 ① 우 패널을 끝까지 넓히면 가운데가 0 까지 눌려 화면이
 * 깨지고 ② 시퀀스 패널을 좁히면 '다음 시퀀스 실행' 버튼이 밖으로 밀려났다. 지금은
 * 드래그 시작 시점의 가운데 폭에서 그 min-width 까지 남은 만큼만 더 넓힐 수 있게
 * 상한을 잡는다. 두 최소 폭 모두 원천은 CSS 다 — 한계의 근거가 레이아웃이므로 숫자도
 * 레이아웃 쪽에 두고, 드래그·저장값 복원·CSS 가 같은 값을 쓴다.
 *
 * 서버 렌더라 트리 항목 클릭마다 전체 리로드된다 → 폭을 localStorage 에 저장해 유지.
 */
(function () {
  "use strict";

  var run = document.querySelector(".run");
  if (!run) return;

  var KEY = "rci.panel.";

  /* 줄일 수 있는 한계는 패널마다 다르다 — 좌 트리는 항목 이름만 들어가면 되지만, 우
   * 시퀀스는 '단계 이름 + 페이로드' 두 칸이 한 줄에 들어가야 한다. 그래서 숫자를 여기
   * 두지 않고 styles.css 의 min-width/max-width 에서 읽는다: 한계의 근거가 레이아웃에
   * 있으니 레이아웃과 같은 자리에 적고, 드래그·저장값 복원·CSS 가 한 값을 함께 쓴다.
   * (CSS 가 하한을 이미 걸어 두므로 JS 가 없거나 늦게 떠도 패널이 무너지지 않는다.)
   */
  function limits(el) {
    var cs = window.getComputedStyle(el);
    var min = parseFloat(cs.minWidth), max = parseFloat(cs.maxWidth);
    return {
      min: isFinite(min) && min > 0 ? min : 180,   // max-width:none → NaN → 기본값
      max: isFinite(max) && max > 0 ? max : 640,
    };
  }

  /* 밀리는 쪽의 최소는 따로 읽는다. limits() 의 기본값(180)을 쓰면 안 된다 — 가운데는
   * min-width 를 두지 않는 화면도 있어서, 없을 때는 0(= 양보할 수 있는 만큼 다 양보)
   * 으로 봐야 한다. */
  function cssMin(el) {
    var v = parseInt(window.getComputedStyle(el).minWidth, 10);
    return isNaN(v) ? 0 : v;
  }
  function load(name) { try { return parseInt(localStorage.getItem(KEY + name), 10); } catch (e) { return NaN; } }
  function save(name, v) { try { localStorage.setItem(KEY + name, v); } catch (e) { /* 무시 */ } }

  Array.prototype.forEach.call(run.querySelectorAll(".run__grip"), function (grip) {
    var prev = grip.previousElementSibling, next = grip.nextElementSibling;
    var target, flexEl, dir, name;
    if (prev && prev.classList.contains("run__left")) {
      // 좌 트리 — 밀리는 쪽은 오른쪽 이웃(메시지 작성은 .run__center, 진단은 .run__body)
      target = prev; flexEl = next; dir = 1; name = "left";
    } else if (next && next.classList.contains("run__right")) {
      // 우 컬럼 — 밀리는 쪽은 왼쪽 이웃(.run__center)
      target = next; flexEl = prev; dir = -1; name = "right";
    } else return;

    var lim = limits(target);
    function clamp(v, max) { return Math.max(lim.min, Math.min(max, v)); }

    /* 지금 가운데가 가진 여유만큼만 더 넓힐 수 있다. 인자는 드래그 시작 시점의
       (대상 폭, 가운데 폭) — 둘을 합친 총량은 드래그 중에 변하지 않는다. */
    function maxFor(startW, flexW) {
      return Math.min(lim.max, Math.max(lim.min, startW + (flexW - cssMin(flexEl))));
    }

    // 저장된 폭 복원. 한계가 좁아지기 전에 저장된 값(예전 하한 180px)이 남아 있을 수
    // 있으므로 복원할 때도 clamp 를 거친다 — 그래야 한 번 줄여 둔 사람도 고쳐진다.
    var saved = load(name);
    if (saved) {
      var w = target.getBoundingClientRect().width;
      target.style.width = clamp(saved, maxFor(w, flexEl.getBoundingClientRect().width)) + "px";
    }

    grip.addEventListener("pointerdown", function (e) {
      e.preventDefault();
      var startX = e.clientX;
      var startW = target.getBoundingClientRect().width;
      var max = maxFor(startW, flexEl.getBoundingClientRect().width);
      try { grip.setPointerCapture(e.pointerId); } catch (err) { /* 커서가 핸들 밖으로 나가도 추적 */ }
      document.body.style.userSelect = "none";

      function move(ev) {
        target.style.width = clamp(startW + dir * (ev.clientX - startX), max) + "px";
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
