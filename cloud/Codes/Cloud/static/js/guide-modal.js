/* 화면 진입 안내 팝업 — 열고, 닫고, '더 이상 보지 않기'를 기억한다.
 *
 * 왜 있는가: 교육생은 컨텐츠 그리드에서 타일 하나를 눌러 곧장 실습 화면에 떨어진다.
 * 화면은 3~4분할이고 패널마다 역할이 달라서, 설명 없이 들어오면 어디부터 봐야 할지
 * 모른다. 그래서 진입하면 한 번 가려서 설명하고, 확인을 받은 뒤 화면을 내준다.
 *
 * 기억 범위는 **화면(콘텐츠)별**이다. 진단을 익혔다고 퀴즈 규칙까지 아는 것은
 * 아니므로, 진단에서 껐어도 퀴즈에는 처음 진입할 때 뜬다. 대상(RC카/UR로봇)은
 * 구분하지 않는다 — 화면 사용법은 대상이 달라도 같다.
 *
 * 문구·표시 여부는 서버가 정한다 (main.PAGE_GUIDES). 여기는 여닫기만 맡는다.
 */
(function () {
  "use strict";

  var modal = document.querySelector("[data-guide-modal]");
  if (!modal) return;

  var KEY = "rci.guide." + modal.getAttribute("data-guide-key");
  var mute = modal.querySelector("[data-guide-mute]");
  var okBtn = modal.querySelector("[data-guide-ok]");
  var opener = document.querySelector("[data-guide-open]");
  var lastFocus = null;

  /* localStorage 는 사생활 보호 모드·정책에 따라 통째로 막힐 수 있다. 그때는
     '기억하지 못할 뿐' 이어야 한다 — 예외가 튀어 팝업 자체가 안 열리면 안 된다. */
  function muted() {
    try { return localStorage.getItem(KEY) === "off"; } catch (e) { return false; }
  }
  function remember(off) {
    try {
      if (off) localStorage.setItem(KEY, "off");
      else localStorage.removeItem(KEY);
    } catch (e) { /* 저장 못 해도 이번 화면은 정상 동작한다 */ }
  }
  /* 이 화면은 '더 이상 보지 않기'를 안 눌러도 같은 탭에서는 한 번만 뜬다.
     이론 교육·진단·강제구동처럼 이전/다음이 페이지를 통째로 다시 불러오는
     화면에서, 넘길 때마다 매번 떠서는 안 된다 — 탭을 새로 열면(sessionStorage
     라서) 다시 한 번 보여준다. */
  function seenThisTab() {
    try { return sessionStorage.getItem(KEY) === "seen"; } catch (e) { return false; }
  }
  function markSeen() {
    try { sessionStorage.setItem(KEY, "seen"); } catch (e) { /* 무시 */ }
  }

  function open() {
    lastFocus = document.activeElement;
    // 도움말로 다시 열었을 때 지금 설정을 그대로 보여준다 — 껐는지 켰는지를
    // 여기서 확인하고 되돌릴 수 있어야 한다.
    if (mute) mute.checked = muted();
    modal.hidden = false;
    document.body.classList.add("is-modal");
    if (okBtn) okBtn.focus();
  }

  function close() {
    // 확인이든 X 든 스크림이든, 닫는 순간의 체크 상태를 그대로 저장한다.
    // '체크해 놓고 X 를 눌렀는데 다음에 또 뜨는' 것은 체크박스를 무의미하게 만든다.
    if (mute) remember(mute.checked);
    markSeen();
    modal.hidden = true;
    document.body.classList.remove("is-modal");
    if (lastFocus && lastFocus.focus) lastFocus.focus();
    lastFocus = null;
  }

  modal.querySelectorAll("[data-guide-close], [data-guide-ok]").forEach(function (el) {
    el.addEventListener("click", close);
  });

  // 도움말 버튼으로 열 때는 '더 이상 보지 않기' 여부와 무관하게 항상 연다.
  if (opener) opener.addEventListener("click", open);

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !modal.hidden) close();
  });

  /* 팝업이 떠 있는 동안 Tab 이 뒤 화면으로 새어 나가지 않게 가둔다. 화면을 덮어
     놓고 보이지 않는 곳에 초점이 가면 키보드로는 닫을 길이 사라진다. */
  modal.addEventListener("keydown", function (e) {
    if (e.key !== "Tab") return;
    var f = modal.querySelectorAll("button, input, [href]");
    if (!f.length) return;
    var first = f[0], last = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  });

  if (!muted() && !seenThisTab()) open();
})();
