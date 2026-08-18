/* 퀴즈 진행·채점 — 좌측에서 고른 주제의 문항을 우측에서 하나씩 풀고 제출한다.
 *
 * 서버(main.py)는 선택 주제의 문항 배열을 templates/quiz.html 의
 * data-questions 에 통째로 실어 보낸다. 문항 이동·선택·채점은 전부 여기서
 * 처리해 서버 왕복이 없다(주제 전환만 링크로 리로드).
 *
 * 문항 스키마 (data/quiz.json): {id, text, choices[4], answer(정답 인덱스), explain?}
 *
 * 보기 순서는 응시할 때마다 섞는다. 원문(특히 UDS 사전)은 정답이 A에 몰려 있어
 * 문제를 안 읽어도 찍어 맞힐 수 있기 때문. 섞는 건 '표시 순서'뿐이고 quiz.json 은
 * 담당자 원문 그대로 두어 검수가 가능하게 한다.
 *
 * 상태
 *   picks[i]  = i번 문항에서 고른 보기의 **원본** 인덱스. 건너뛰면 null.
 *               (표시 순서가 아니라 원본 기준이라 채점이 answer 와 바로 비교된다)
 *   orders[i] = i번 문항의 보기 표시 순서. orders[i][표시위치] = 원본 인덱스.
 *   at        = 현재 문항 번호(0-base)
 *   done      = 제출 후 결과 화면 여부
 */
(function () {
  "use strict";

  var root = document.querySelector("[data-quiz]");
  if (!root) return;

  var questions = JSON.parse(root.getAttribute("data-questions") || "[]");
  if (!questions.length) return;

  var homeUrl = root.getAttribute("data-home");

  var el = {
    tag: root.querySelector("[data-quiz-tag]"),
    play: root.querySelector("[data-quiz-play]"),
    result: root.querySelector("[data-quiz-result]"),
    index: root.querySelector("[data-quiz-index]"),
    percent: root.querySelector("[data-quiz-percent]"),
    bar: root.querySelector("[data-quiz-bar]"),
    text: root.querySelector("[data-quiz-text]"),
    opts: root.querySelector("[data-quiz-opts]"),
    score: root.querySelector("[data-quiz-score]"),
    sub: root.querySelector("[data-quiz-sub]"),
    marks: root.querySelector("[data-quiz-marks]"),
    prev: root.querySelector("[data-quiz-prev]"),
    next: root.querySelector("[data-quiz-next]")
  };

  var picks = questions.map(function () { return null; });
  var orders = questions.map(shuffledOrder);
  var at = 0;
  var done = false;

  /* 문항의 보기 표시 순서를 Fisher-Yates 로 섞어 반환.
   * 반환값[표시위치] = 원본 보기 인덱스. 응시 1회 동안은 고정이라
   * 이전/다음으로 오가도 보기 순서가 흔들리지 않는다. */
  function shuffledOrder(q) {
    var idx = q.choices.map(function (_, i) { return i; });
    for (var i = idx.length - 1; i > 0; i--) {
      var j = Math.floor(Math.random() * (i + 1));
      var tmp = idx[i]; idx[i] = idx[j]; idx[j] = tmp;
    }
    return idx;
  }

  /* 채점 — 제출 시 한 번 호출된다.
   *
   * @param {Array}  qs    문항 배열. qs[i].answer 가 정답 보기 인덱스.
   * @param {Array}  sel   선택 배열. sel[i] 는 보기 인덱스이거나, 건너뛰었으면 null.
   * @returns {{score:number, correctCount:number, total:number, marks:boolean[]}}
   *   score        화면에 '○○점' 으로 표시할 점수
   *   correctCount 맞힌 문항 수
   *   total        전체 문항 수
   *   marks        문항별 정오 (true=정답) — 결과 화면의 O/X 칩에 그대로 쓰인다
   */
  function gradeQuiz(qs, sel) {
    // 미응답(null)은 오답 처리. 건너뛰기를 허용하는 대신 점수로 책임진다.
    var marks = qs.map(function (q, i) { return sel[i] === q.answer; });
    var correctCount = marks.filter(Boolean).length;
    var total = qs.length;

    // 문항 수가 10개가 아닐 수도 있어(담당자 JSON 교체) 정답률 100점 환산으로 둔다.
    var score = total ? Math.round((correctCount / total) * 100) : 0;

    return { score: score, correctCount: correctCount, total: total, marks: marks };
  }

  /* 진행 화면 그리기 */
  function renderQuestion() {
    var q = questions[at];
    var ratio = Math.round(((at + 1) / questions.length) * 100);

    el.index.textContent = "문항 " + (at + 1) + " / " + questions.length;
    el.percent.textContent = "진행률 " + ratio + "%";
    el.bar.style.width = ratio + "%";
    el.text.textContent = q.text;

    // 섞인 순서로 그리되, 고른 값은 원본 인덱스로 기록한다
    el.opts.textContent = "";
    orders[at].forEach(function (origin) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "quiz-opt" + (picks[at] === origin ? " is-on" : "");
      btn.innerHTML = '<span class="quiz-mark"></span>';
      btn.appendChild(document.createTextNode(q.choices[origin]));
      btn.addEventListener("click", function () {
        picks[at] = origin;
        renderQuestion();
      });
      el.opts.appendChild(btn);
    });

    el.prev.disabled = at === 0;
    el.prev.textContent = "← 이전";
    el.next.textContent = at === questions.length - 1 ? "제출하기" : "다음 →";
  }

  /* 결과 화면 그리기 */
  function renderResult() {
    var r = gradeQuiz(questions, picks);

    el.score.textContent = r.score + "점";
    el.sub.textContent = questions.length + "문항 중 " + r.correctCount + "문항 정답";

    el.marks.textContent = "";
    r.marks.forEach(function (ok, i) {
      var chip = document.createElement("div");
      chip.className = "quiz-chip " + (ok ? "is-ok" : "is-ng");
      chip.innerHTML =
        '<span class="quiz-chip__no">' + (i + 1) + "</span>" +
        '<span class="quiz-chip__sign">' + (ok ? "O" : "X") + "</span>";
      el.marks.appendChild(chip);
    });

    if (el.tag) el.tag.textContent = "결과";
    el.prev.disabled = false;
    el.prev.textContent = "다시 풀기";
    el.next.textContent = "확인 · 퀴즈 처음으로";
  }

  /* 진행/결과 화면 전환 */
  function render() {
    el.play.hidden = done;
    el.result.hidden = !done;
    if (done) renderResult();
    else renderQuestion();
  }

  /* 처음부터 다시 (같은 주제) — 보기 순서도 새로 섞는다 */
  function restart() {
    picks = questions.map(function () { return null; });
    orders = questions.map(shuffledOrder);
    at = 0;
    done = false;
    if (el.tag) el.tag.textContent = "퀴즈";
    render();
  }

  el.prev.addEventListener("click", function () {
    if (done) { restart(); return; }          // 결과 화면에서는 '다시 풀기'
    if (at > 0) { at -= 1; render(); }
  });

  el.next.addEventListener("click", function () {
    if (done) {                               // 결과 화면에서는 '확인' → 첫 주제로
      window.location.href = homeUrl;
      return;
    }
    if (at < questions.length - 1) { at += 1; render(); }
    else { done = true; render(); }           // 마지막 문항 → 제출
  });

  render();
})();
