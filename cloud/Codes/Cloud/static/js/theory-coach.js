/* 이론 교육 진입 코치마크 — 화면을 음영으로 덮고 우상단 '이전·다음'만 남겨
 * 거기를 보게 한다.
 *
 * 왜 있는가: 자료가 소제목 단위로 끊겨 있다는 사실 자체를 모르면, 교육생은 본문을
 * 스크롤해 끝까지 읽고 "이게 전부인가" 하고 나가 버린다. 진입 안내 팝업(guide-modal)
 * 에 글로도 적어 두었지만, 글은 읽히지 않고 눈은 움직이는 곳을 본다 — 그래서 버튼
 * 자리를 한 번 짚어준다.
 *
 * 팝업과의 순서: 안내 팝업이 먼저다(화면 전체가 무슨 화면인지), 코치마크가 그 뒤다
 * (그 화면에서 어디를 누르는지). 둘이 동시에 뜨면 음영이 두 겹이 되므로, 팝업이
 * 닫히는 것을 보고 나서 연다.
 *
 * 강조 표시 자체는 CSS 가 한다 — body.is-coach + [data-coach-target].
 */
(function () {
  "use strict";

  var coach = document.querySelector("[data-coach]");
  var target = document.querySelector("[data-coach-target]");
  if (!coach || !target) return;

  var tip = coach.querySelector("[data-coach-tip]");
  // 저장 키. 이론 교육 화면 하나에 대한 것이므로 대상(RC카/UR로봇)은 구분하지 않는다.
  var KEY = "rci.coach.theory";

  /* 오늘 날짜 "YYYY-MM-DD" (로컬 기준) — 저장 값으로 쓸 수 있다. UTC 인 toISOString()
     은 자정 근처에서 하루가 어긋나 쓰지 않는다. */
  function todayKey() {
    var d = new Date();
    return d.getFullYear() + "-" + ("0" + (d.getMonth() + 1)).slice(-2)
      + "-" + ("0" + d.getDate()).slice(-2);
  }

  /* 표시 정책 — guide-modal.js 와 같은 두 겹이다.
   *
   *   localStorage   "오늘 하루" 의 기억. 한 번 닫으면 그날은 다시 덮지 않는다.
   *                  값이 오늘 날짜라서 자정이 지나면 저절로 만료된다 — 실습실
   *                  공용 PC 라 다음 교육생에게는 다시 한 번 보여야 한다.
   *   sessionStorage "이 탭에서 한 번". 이론 교육은 이전·다음이 페이지를 통째로 다시
   *                  로드하므로 이게 없으면 페이지를 넘길 때마다 음영이 다시 덮인다.
   *
   * 두 겹이 필요한 이유: 날짜 기억만 두면 localStorage 가 막힌 브라우저(사생활 보호
   * 모드)에서 매 페이지마다 뜬다. 탭 기억만 두면 탭을 새로 열 때마다 뜬다.
   * 안내 팝업과 달리 이 코치마크에는 '오늘 보지 않기' 체크박스가 없다 — 닫는 행위
   * 자체를 "봤다" 로 받아, 사용자가 고를 것을 늘리지 않는다.
   *
   * 저장소 접근은 정책·설정에 따라 통째로 막힐 수 있다. 그때는 '기억하지 못할 뿐'
   * 이어야 한다 — 예외가 튀어 코치마크가 아예 안 뜨거나 닫히지 않으면 안 된다.
   */
  function shouldShow() {
    var seenToday = false, seenThisTab = false;
    try { seenToday = localStorage.getItem(KEY) === todayKey(); } catch (e) { /* 기억 없음 */ }
    try { seenThisTab = sessionStorage.getItem(KEY) === "seen"; } catch (e) { /* 기억 없음 */ }
    return !seenToday && !seenThisTab;
  }

  function remember() {
    try { localStorage.setItem(KEY, todayKey()); } catch (e) { /* 이번 탭 기억으로 버틴다 */ }
    try { sessionStorage.setItem(KEY, "seen"); } catch (e) { /* 이번 화면은 정상 동작 */ }
  }

  /* 설명 말풍선을 강조된 버튼 바로 아래·오른쪽 맞춤으로 놓는다. 버튼 위치는 창 크기에
     따라 움직이므로(우상단 고정이 아니라 헤더 안의 흐름), 좌표는 그때그때 잰다. */
  function place() {
    var r = target.getBoundingClientRect();
    tip.style.top = (r.bottom + 14) + "px";
    tip.style.right = Math.max(14, window.innerWidth - r.right) + "px";
  }

  function open() {
    coach.hidden = false;
    document.body.classList.add("is-coach");
    place();
    window.addEventListener("resize", place);
    var ok = coach.querySelector("[data-coach-close].btn");
    if (ok) ok.focus();
  }

  function close() {
    coach.hidden = true;
    document.body.classList.remove("is-coach");
    window.removeEventListener("resize", place);
    remember();
  }

  Array.prototype.forEach.call(
    coach.querySelectorAll("[data-coach-close]"),
    function (el) { el.addEventListener("click", close); });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !coach.hidden) close();
  });

  /* 안내 팝업이 떠 있으면 그것이 닫히기를 기다린다. 팝업은 hidden 속성을 껐다 켜는
     방식이라(guide-modal.js), 그 속성만 지켜보면 된다. */
  function openWhenFree() {
    var modal = document.querySelector("[data-guide-modal]");
    if (!modal || modal.hidden) { open(); return; }
    var mo = new MutationObserver(function () {
      if (!modal.hidden) return;
      mo.disconnect();
      open();
    });
    mo.observe(modal, {attributes: true, attributeFilter: ["hidden"]});
  }

  if (shouldShow()) openWhenFree();
})();
