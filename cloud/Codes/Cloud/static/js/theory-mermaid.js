// 이론 교육 md 안의 ```mermaid 블록(서버가 <div class="mermaid"> 로 뽑아 둔 것)을 그린다.
//
// 서버는 다이어그램을 그릴 수 없다(SVG 레이아웃은 브라우저 전용) — model-viewer 를
// 브라우저에 맡긴 것과 같은 이유로, mermaid 렌더만 여기서 처리한다. vendor 로 담아
// 오프라인·태블릿에서도 CDN 없이 동작하게 한다(mqtt.js·model-viewer 와 동일 방침).
(function () {
  if (typeof mermaid === "undefined") return; // vendor 미탑재 시 코드블록 원문으로 남는다
  mermaid.initialize({ startOnLoad: false, theme: "neutral", securityLevel: "strict" });
  const nodes = document.querySelectorAll(".viewer__md .mermaid");
  if (nodes.length) mermaid.run({ nodes });
})();
