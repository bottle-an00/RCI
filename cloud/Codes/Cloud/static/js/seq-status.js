/* 시퀀스 상태 텍스트 — 3D 모델 뷰 안에 "지금 무엇을 하고 있는지" 를 글로 띄운다.
 *
 * 왜 있는가: 강제구동 중 일부 DID 는 3D 모델이 반응해 준다(조명 점멸·관절 구동·바퀴
 * 회전). 그런데 ECU 리프로그래밍의 단계들(다운로드 요청·블록 전송·검증·리셋)과 진단
 * 하위 기능의 읽기 단계들은 모델에 담을 표현이 아예 없다 — 응답은 오는데 화면은
 * 아무 변화가 없어 '연동이 안 된다'로 읽힌다. rci-live.js 가 표현 수단 없는 강제구동에
 * 배지(view3d__drive-badge)를 띄우는 것과 같은 이유로, 시퀀스 진행에도 글로 된 신호를 준다.
 *
 * 자리는 그 배지와 같은 3D 파인 안이다(_model3d.html) — 만화 탭에는 그리지 않는다.
 * 모델이 보여 주지 못하는 것을 글로 메우는 것이지, 만화를 가릴 일은 아니기 때문이다.
 * 강제구동 배지는 왼쪽 위, 이쪽은 왼쪽 아래 — 둘이 함께 떠도 겹치지 않는다.
 *
 * 패널 머리의 [data-brief-step] 과 역할이 다르다 — 그쪽은 **지금 읽고 있는** 단계(시퀀스
 * 목록에서 행을 눌러 미리 볼 수 있다)이고, 이쪽은 **러너가 실제로 밟은** 단계다. 둘이
 * 어긋나는 것이 정상이라 한 칸에 합치지 않았다.
 *
 * 의존: auto-sequence.js 의 "seq:state" 방송. 그 파일이 없는 화면에서는 조용히 쉰다.
 */
(function () {
  "use strict";

  var el = document.querySelector("[data-seq-state]");
  if (!el) return;

  // phase → [클래스 접미사, 접두 문구]. auto-sequence.js 의 paintProgress 가 보내는 값.
  var PHASES = {
    idle: ["idle", "대기 중"],
    run:  ["run",  "진행 중"],
    pass: ["pass", "통과"],
    fail: ["fail", "실패"],
    stop: ["stop", "중단"],
    done: ["done", "완료"],
  };

  function paint(d) {
    var spec = PHASES[d.phase] || PHASES.idle;
    var text = spec[1];

    if (d.phase === "run" || d.phase === "pass" || d.phase === "fail") {
      // 어느 단계인지가 핵심 정보다 — 단계 제목에 이미 요청 바이트가 붙어 있다
      // (예: "블록 전송 2/3 (36 02)").
      if (d.step && d.step.title) text += " · " + d.step.title;
    } else if (d.phase === "stop") {
      text += " · " + (d.index + 1) + "단계에서 끊김";
    } else if (d.phase === "done") {
      text += " · 전체 " + d.total + "단계";
    } else if (d.total) {
      text += " · 0 / " + d.total;
    }

    el.className = "seqstate is-" + spec[0];
    el.textContent = text;
    el.hidden = false;
    // 스크린리더에게도 상태 변화를 알린다 — 색과 점멸만으로는 전달되지 않는다.
    el.setAttribute("aria-label", "시퀀스 상태: " + text);
  }

  document.addEventListener("seq:state", function (e) {
    if (e.detail) paint(e.detail);
  });
})();
