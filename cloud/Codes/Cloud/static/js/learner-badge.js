/* 상단바 학습자 배지 — 퀴즈 게이트(learner-gate.js)가 sessionStorage 에 남긴
 * 소속·이름·직급을 전 화면 상단바에 표시한다.
 *
 * 퀴즈 화면이 아니어도 뜬다 — sessionStorage 는 탭(세션) 전체에서 공유되므로,
 * 한 번 채운 뒤로는 어느 화면을 가든 그대로 보인다. 아직 채운 적이 없으면
 * (또는 값이 이상하면) 빈 배지를 보여주는 대신 자리 자체를 감춘 채로 둔다.
 */
(function () {
  "use strict";

  var el = document.querySelector("[data-topbar-learner]");
  if (!el) return;

  var raw;
  try { raw = sessionStorage.getItem("rci.learner"); } catch (e) { raw = null; }
  if (!raw) return;

  var learner;
  try { learner = JSON.parse(raw); } catch (e) { return; }
  if (!learner || !learner.org || !learner.name || !learner.position) return;

  el.textContent = learner.org + " · " + learner.name + " (" + learner.position + ")";
  el.hidden = false;
})();
