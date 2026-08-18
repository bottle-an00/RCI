/* 세부 항목 트리 접기/펴기.
 *
 * 이 앱은 서버 렌더링이라 트리의 잎을 누르면 `?item=…` 으로 페이지가 통째로 다시
 * 로드된다. 그래서 접힘 상태를 DOM 에만 두면 항목을 고를 때마다 전부 다시 펴져
 * 토글이 쓸모없어진다 — localStorage 에 경로별로 남겨 리로드를 건너 살린다.
 *
 * 기본값은 **접힘**이다. 실습은 한 번에 한 코스만 하는데 네 코스가 다 펴져 있으면
 * 트리가 화면보다 길어져, 다음 단계로 넘어갈 때마다 스크롤이 맨 위로 튀어 지금
 * 어디인지 잃는다. 그래서 지금 하고 있는 코스만 펴고 나머지는 접어 둔다.
 *
 * 저장하는 것도 '접은 것' 이 아니라 **손으로 펴 둔 것**이다(기본이 접힘이므로).
 * 예외: 선택된 항목이 든 그룹은 저장 상태와 무관하게 늘 펴 둔다 — 접으면 보고
 * 있는 항목이 화면에서 사라진다.
 *
 * 그래도 트리가 화면보다 길 수 있어서, 마지막에 선택된 행을 보이는 위치로 끌어온다.
 */
(function () {
  "use strict";

  var groups = Array.prototype.slice.call(
    document.querySelectorAll(".tree__group[data-group]"));
  if (!groups.length) return;

  // 키 이름에 :open 이 붙은 이유 — 예전 키(rci:tree:)는 '접은 것' 을 담았다.
  // 의미를 뒤집었으니 같은 키를 재사용하면 옛 값을 거꾸로 읽는다.
  var KEY = "rci:tree:open:" + location.pathname;   // 콘텐츠(경로)별로 따로 기억

  function load() {
    try { return JSON.parse(localStorage.getItem(KEY)) || []; } catch (e) { return []; }
  }
  function save(ids) {
    try { localStorage.setItem(KEY, JSON.stringify(ids)); } catch (e) { /* 사생활 모드 등 */ }
  }

  function childrenOf(group) {
    return document.querySelector(
      '.tree__children[data-children="' + group.dataset.group + '"]');
  }

  function setCollapsed(group, on) {
    var kids = childrenOf(group);
    group.classList.toggle("is-collapsed", on);
    group.setAttribute("aria-expanded", on ? "false" : "true");
    if (kids) kids.classList.toggle("is-collapsed", on);
  }

  // 초기 상태 적용 — 기본 접힘, 선택된 항목이 든 그룹과 손으로 펴 둔 그룹만 펴진다.
  var opened = load();
  var selectedRow = null;
  groups.forEach(function (group) {
    var kids = childrenOf(group);
    var holdsSelected = kids && kids.querySelector(".tree__row.is-selected");
    if (holdsSelected) selectedRow = holdsSelected;
    setCollapsed(group, !holdsSelected && opened.indexOf(group.dataset.group) === -1);
  });

  // 리로드 뒤 스크롤은 0 으로 돌아간다 — 선택된 행을 다시 눈에 들어오게 끌어온다.
  // "nearest" 라서 이미 보이는 경우엔 아무것도 하지 않는다(화면이 튀지 않는다).
  if (selectedRow && selectedRow.scrollIntoView) {
    selectedRow.scrollIntoView({block: "nearest"});
  }

  function toggle(group) {
    var willCollapse = !group.classList.contains("is-collapsed");
    setCollapsed(group, willCollapse);
    var ids = load().filter(function (x) { return x !== group.dataset.group; });
    if (!willCollapse) ids.push(group.dataset.group);   // 저장하는 것은 '펴 둔 것'
    save(ids);
  }

  document.addEventListener("click", function (e) {
    var group = e.target.closest(".tree__group[data-group]");
    if (group) toggle(group);
  });
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Enter" && e.key !== " ") return;
    var group = e.target.closest && e.target.closest(".tree__group[data-group]");
    if (!group) return;
    e.preventDefault();
    toggle(group);
  });
})();
