/* 퀴즈 진입 게이트 — 소속·이름·직급을 받아 window.RCI_LEARNER 에 채운다.
 *
 * sessionStorage 에 이미 있으면(같은 탭에서 이전 주제를 한 번 거쳤으면) 모달을
 * 띄우지 않고 즉시 채운다. 없으면 모달을 띄우고, 다 채워야 "시작" 이 눌리게
 * 한다 — 스크림·Esc 로 닫는 길은 없다(필수 입력이라 강제 진행).
 *
 * quiz.js 는 이 스크립트 뒤에 실행된다(quiz.html 의 script 순서). 이미 알고
 * 있으면 window.RCI_LEARNER 를 그 자리에서 곧장 읽고, 아직 모달을 기다리는
 * 중이면 "rci:learner-ready" 이벤트로 뒤늦게 받는다.
 */
(function () {
  "use strict";

  var KEY = "rci.learner";
  var modal = document.querySelector("[data-learner-gate]");
  if (!modal) return;

  var fields = {
    org: modal.querySelector("[data-learner-org]"),
    name: modal.querySelector("[data-learner-name]"),
    position: modal.querySelector("[data-learner-position]")
  };
  var startBtn = modal.querySelector("[data-learner-start]");

  function saved() {
    try {
      var raw = sessionStorage.getItem(KEY);
      return raw ? JSON.parse(raw) : null;
    } catch (e) { return null; }
  }

  function remember(learner) {
    try { sessionStorage.setItem(KEY, JSON.stringify(learner)); }
    catch (e) { /* 저장 못 해도 이번 응시는 진행한다 */ }
  }

  function ready(learner) {
    window.RCI_LEARNER = learner;
    document.dispatchEvent(new CustomEvent("rci:learner-ready", { detail: learner }));
  }

  function validate() {
    var filled = fields.org.value.trim() && fields.name.value.trim() && fields.position.value.trim();
    startBtn.disabled = !filled;
  }

  Object.keys(fields).forEach(function (k) {
    fields[k].addEventListener("input", validate);
  });

  startBtn.addEventListener("click", function () {
    var learner = {
      org: fields.org.value.trim(),
      name: fields.name.value.trim(),
      position: fields.position.value.trim()
    };
    if (!learner.org || !learner.name || !learner.position) return;
    remember(learner);
    modal.hidden = true;
    document.body.classList.remove("is-modal");
    ready(learner);
  });

  var existing = saved();
  if (existing) {
    ready(existing);
    return;
  }
  modal.hidden = false;
  document.body.classList.add("is-modal");
  fields.org.focus();
})();
