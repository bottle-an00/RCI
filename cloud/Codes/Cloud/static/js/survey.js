/* 사용성 평가(SUS) 진행·제출.
 *
 * 화면은 서버가 다 그려 두었다(templates/survey.html) — 여기서는 고른 값을 모으고,
 * 다 채웠는지 보고, 제출 한 번을 보낸다. 채점은 하지 않는다: 점수는 서버가 계산해
 * 응답으로 돌려준다(main.sus_score). 응답자 화면에서 계산하면 값을 신뢰할 수 없다.
 *
 * 저장 실패를 조용히 삼키지 않는 것은 퀴즈(static/js/quiz.js)와 같은 규칙이다 —
 * '냈는데 안 남았다'를 아무도 눈치채지 못하는 것이 가장 나쁘다.
 */
(function () {
  "use strict";

  var root = document.querySelector("[data-survey]");
  if (!root) return;

  var form = root.querySelector("[data-survey-form]");
  var result = root.querySelector("[data-survey-result]");
  var submitBtn = root.querySelector("[data-survey-submit]");
  var hint = root.querySelector("[data-survey-hint]");
  var doneCount = root.querySelector("[data-survey-done]");
  var items = Array.prototype.slice.call(root.querySelectorAll("[data-survey-item]"));

  var field = {
    team: root.querySelector("[data-survey-team]"),
    name: root.querySelector("[data-survey-name]"),
    comment: root.querySelector("[data-survey-comment]")
  };

  // answers[문항번호] = 1~5. 아직 안 고른 문항은 값이 없다.
  var answers = {};
  var position = null;                    // 직급 G1~G4 (고르기 전에는 null)
  var startedAt = Date.now();
  var posted = false;

  /* 문항 하나의 보기 버튼 — 라디오처럼 하나만 켠다. role=radio 를 쓰고 있으므로
     aria-checked 도 같이 옮겨야 스크린리더에서 선택이 읽힌다. */
  items.forEach(function (item) {
    var no = item.getAttribute("data-survey-item");
    var opts = Array.prototype.slice.call(item.querySelectorAll("[data-survey-value]"));
    opts.forEach(function (btn) {
      btn.addEventListener("click", function () {
        answers[no] = parseInt(btn.getAttribute("data-survey-value"), 10);
        opts.forEach(function (other) {
          var on = other === btn;
          other.classList.toggle("is-on", on);
          other.setAttribute("aria-checked", on ? "true" : "false");
        });
        item.classList.add("is-done");
        validate();
      });
    });
  });

  root.querySelectorAll("[data-survey-position]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      position = btn.getAttribute("data-survey-position");
      root.querySelectorAll("[data-survey-position]").forEach(function (other) {
        other.classList.toggle("is-on", other === btn);
      });
      validate();
    });
  });

  [field.team, field.name].forEach(function (el) {
    el.addEventListener("input", validate);
  });

  function answeredCount() {
    return Object.keys(answers).length;
  }

  /* 제출 가능 여부 + 무엇이 남았는지. 버튼만 잠그고 이유를 말하지 않으면
     "왜 안 눌리지" 에서 멈춘다 — 남은 것을 그대로 적어 준다. */
  function validate() {
    var missing = [];
    if (!field.team.value.trim()) missing.push("팀");
    if (!position) missing.push("직급");
    if (!field.name.value.trim()) missing.push("성함");
    var left = items.length - answeredCount();
    if (left > 0) missing.push(left + "개 문항");

    doneCount.textContent = answeredCount();
    submitBtn.disabled = missing.length > 0;
    hint.textContent = missing.length
      ? missing.join(" · ") + " 이(가) 남았습니다."
      : "제출하면 서버에 기록됩니다.";
  }

  function saveNote(text, ok) {
    var note = root.querySelector("[data-survey-save]");
    if (!note) return;
    note.className = "survey__done-note" + (ok ? " is-ok" : " is-ng");
    note.textContent = text;
  }

  /* 제출 완료 화면으로 넘긴다. 점수는 보여주지 않는다 (survey.html 주석 참고) —
     서버가 계산해 기록에만 남긴다. */
  function showResult() {
    form.hidden = true;
    result.hidden = false;
  }

  function payload() {
    return {
      team: field.team.value.trim(),
      position: position,
      name: field.name.value.trim(),
      // 1~10번 순서대로 — 서버가 이 순서를 문항 번호로 읽는다.
      answers: items.map(function (item) {
        return answers[item.getAttribute("data-survey-item")];
      }),
      duration_sec: Math.max(0, Math.round((Date.now() - startedAt) / 1000)),
      comment: field.comment.value.trim()
    };
  }

  function send(body, retriesLeft) {
    return fetch("/api/survey-result", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      keepalive: true
    }).then(function (res) {
      if (!res.ok) throw new Error("HTTP " + res.status);
      return res.json();       // 응답에 점수가 오지만 화면에는 쓰지 않는다
    }).then(function () {
      showResult();
      saveNote("감사합니다. 응답이 서버에 저장되었습니다.", true);
    }).catch(function (err) {
      if (retriesLeft > 0) {
        return new Promise(function (done) { setTimeout(done, 1000); })
          .then(function () { return send(body, retriesLeft - 1); });
      }
      // 실패해도 응답을 잃지 않게 화면은 넘기지 않는다 — 다시 누를 수 있어야 한다.
      posted = false;
      submitBtn.disabled = false;
      hint.textContent = "제출에 실패했습니다 (" + err.message + "). 다시 눌러 주세요.";
    });
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    if (posted || submitBtn.disabled) return;
    posted = true;
    submitBtn.disabled = true;
    hint.textContent = "제출하는 중…";
    send(payload(), 2);
  });

  validate();
})();
