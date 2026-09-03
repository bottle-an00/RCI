/* 실습 진행 상태의 수명 — 화면을 벗어나면 진행 체크와 세션 유지(3E)를 지운다.
 *
 * 메시지 작성 실습은 '순차 진행'이라 통과한 단계를 localStorage 에 체크해 두고
 * (static/js/step-progress.js), 세션 유지(3E) 반복 발행은 sessionStorage 에 적어
 * 페이지를 넘어가도 이어진다 (static/js/rci-live.js). 둘 다 **그 실습 화면에
 * 머무는 동안** 만 뜻이 있는 상태다.
 *
 * 그런데 예전에는 화면을 벗어나도 그대로 남아, 이론 교육을 보고 돌아오면 지난
 * 사람이 밟아 둔 체크가 그대로 열려 있고 3E 가 여전히 나가고 있었다. 교육생이
 * 번갈아 쓰는 화면에서는 이게 곧 '앞 사람 상태로 시작하는' 문제가 된다.
 *
 * 그래서 화면(경로)이 바뀌면 앞 화면의 상태를 지운다. 판정 기준은 pathname 이다:
 *   같은 경로 + ?item= 만 다름  → 같은 실습 안의 단계 이동. 유지한다.
 *   경로 자체가 바뀜            → 실습을 떠난 것. 앞 경로의 진행과 3E 를 지운다.
 *
 * 이 스크립트는 base.html <head> 에서 동기 실행된다 — rci-live.js 가 세션 유지
 * 발행을 되살리기 **전에** 지워져 있어야 하기 때문이다.
 */
(function () {
  "use strict";

  var PAGE_KEY = "rci:page";
  var here = location.pathname;
  var prev = null;

  try { prev = sessionStorage.getItem(PAGE_KEY); } catch (e) { return; }
  try { sessionStorage.setItem(PAGE_KEY, here); } catch (e) { /* 사생활 모드 등 */ }

  if (!prev || prev === here) return;

  // 앞 화면의 순차 진행 체크 (step-progress.js 의 저장 키와 같아야 한다).
  try { localStorage.removeItem("rci:progress:" + prev); } catch (e) { /* 무시 */ }

  // 세션 유지 발행 선언. 대상(device)별로 키가 갈리므로 접두어로 모두 지운다.
  try {
    for (var i = sessionStorage.length - 1; i >= 0; i--) {
      var k = sessionStorage.key(i);
      if (k && k.indexOf("rci:keepalive:") === 0) sessionStorage.removeItem(k);
    }
  } catch (e) { /* 무시 */ }
})();
