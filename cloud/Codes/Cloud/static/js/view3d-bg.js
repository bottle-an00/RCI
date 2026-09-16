/* 3D 모델 뷰 배경색 — 팔레트에서 고른 색을 파인 배경에 입힌다.
 *
 * 왜 있는가: 기본 배경은 어두운 그라데이션이다. 흰색·하늘색 계열 모델(UR3·아이오닉5
 * 둘 다 밝다)은 어두운 배경에서 잘 보이지만, 교육장 프로젝터나 인쇄 자료에서는 반대로
 * 밝은 배경이 필요할 때가 있다. 그때마다 CSS 를 고치는 대신 화면에서 고르게 한다.
 *
 * 어떻게: styles.css 의 .view3d 가 background 를 var(--view3d-bg, <기본 그라데이션>)
 * 으로 읽는다. 여기서는 그 변수만 얹거나 지운다 — 지우면 CSS 의 기본값(그라데이션)이
 * 그대로 살아난다. 그래서 '기본' 으로 되돌리는 것이 따로 색을 지정하는 일이 아니다.
 *
 * 고른 색은 localStorage 에 남긴다. 이 앱은 화면마다 서버에서 새로 받는 다중 페이지라,
 * 남기지 않으면 진단 → 강제구동으로 넘길 때마다 원래 색으로 돌아가 쓸모가 없다.
 *
 * 색은 페이지의 모든 .view3d 에 함께 건다 — 한 화면에 파인이 하나뿐이지만(만화와
 * 자리를 나눠 쓴다) 여러 개여도 같은 배경이어야 '설정' 으로 읽힌다.
 */
(function () {
  "use strict";

  var KEY = "rci.view3d.bg";
  var panes = document.querySelectorAll(".view3d");
  var root = document.querySelector("[data-view3d-bg]");
  if (!panes.length || !root) return;

  var btn = root.querySelector("[data-view3d-bg-toggle]");
  var pop = root.querySelector("[data-view3d-bg-pop]");
  var custom = root.querySelector("[data-view3d-bg-custom]");
  var swatches = root.querySelectorAll("[data-bg]");

  /* 색을 입힌다. value 가 빈 값이면 변수를 지워 CSS 기본 그라데이션으로 돌린다. */
  function apply(value) {
    Array.prototype.forEach.call(panes, function (p) {
      if (value) p.style.setProperty("--view3d-bg", value);
      else p.style.removeProperty("--view3d-bg");
      // 기본 배경은 색이 아니라 정비소 장면(.view3d__scene, styles.css)이다.
      // 색을 고르면 이 클래스가 장면을 덮어 숨기고 고른 색이 대신 드러난다 —
      // '기본' 스와치(값이 빈 문자열)를 고르면 다시 장면으로 돌아간다.
      p.classList.toggle("has-custom-bg", !!value);
    });
    Array.prototype.forEach.call(swatches, function (s) {
      s.classList.toggle("is-on", (s.dataset.bg || "") === (value || ""));
    });
    if (custom && value && /^#[0-9a-f]{6}$/i.test(value)) custom.value = value;
  }

  function save(value) {
    try {
      if (value) window.localStorage.setItem(KEY, value);
      else window.localStorage.removeItem(KEY);
    } catch (e) {
      /* 시크릿 모드 등에서 막힐 수 있다 — 이번 화면에만 적용되고 조용히 넘어간다. */
    }
  }

  function open(on) {
    pop.hidden = !on;
    btn.setAttribute("aria-expanded", on ? "true" : "false");
  }

  btn.addEventListener("click", function (e) {
    e.stopPropagation();
    open(pop.hidden);
  });

  // 팔레트 밖을 누르면 닫는다. 파인 안에서 모델을 돌리려 드래그할 때도 닫혀야 한다.
  document.addEventListener("click", function (e) {
    if (!pop.hidden && !root.contains(e.target)) open(false);
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !pop.hidden) open(false);
  });

  Array.prototype.forEach.call(swatches, function (s) {
    s.addEventListener("click", function () {
      var v = s.dataset.bg || "";
      apply(v);
      save(v);
      open(false);
    });
  });

  if (custom) {
    // input 은 드래그하는 동안 계속 온다 — 그대로 미리보기로 쓰고 저장까지 한다.
    custom.addEventListener("input", function () {
      apply(custom.value);
      save(custom.value);
    });
  }

  var saved = null;
  try { saved = window.localStorage.getItem(KEY); } catch (e) { saved = null; }
  apply(saved);
})();
