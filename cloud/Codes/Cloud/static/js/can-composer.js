/* 메시지 작성 — 사용자가 타이핑한 CAN 프레임을 뜯어보고 검증하고 전송한다.
 *
 * 방향이 중요하다. 이 화면은 프레임을 **만들어 주지 않는다**. 사람이 쓴 것을 읽는다:
 *
 *   입력  000007E0  8  02  10  03  55 55 55 55 55
 *          │        │  │   └UDS┘  └── 필러 ──┘
 *          └CAN ID  │  └ PCI(ISO-TP 길이)
 *                   └ DLC
 *   출력  층별 색 분해 + 검증 결과 + (UDS 만) 전송
 *
 * 검증이 이 화면의 교육 가치다. 직접 쓰면 틀리게 되고, 틀린 지점을 짚어주는 것이
 * 자동 조립기가 줄 수 없는 것이다. 특히 자주 틀리는 것:
 *   · PCI 길이 바이트에 DLC(8)를 적음 — PCI 는 UDS 바이트 수다
 *   · 필러를 방향과 반대로 씀 (요청 0x55 / 응답 0xAA)
 *   · UDS 가 8바이트를 넘는데 PCI 를 `0L` 로 둠 (첫 프레임 `1L LL` 이어야 함)
 *
 * 전송되는 것은 계약(Documents/MQTT_Interface_Contract.md §역할 분담)대로 UDS raw 뿐이다.
 * CAN 프레이밍은 RCI 몫이라, 위 프레임 층은 화면에서만 존재한다.
 *
 * 의존: rci-live.js 가 먼저 로드되어 window.RCI(.send/.log)를 제공.
 */
(function () {
  "use strict";

  var root = document.querySelector(".composer[data-composer]");
  if (!root) return;

  var CAN_REQ = root.dataset.canReq || "";
  var CAN_RESP = root.dataset.canResp || "";
  var FILL_REQ = root.dataset.fillReq || "";
  var FILL_RESP = root.dataset.fillResp || "";
  var CAN_LAYER = !!CAN_REQ;          // DoIP 대상은 CAN 층이 없다
  var DLC_EXPECTED = 8;

  var input = document.getElementById("frame-input");
  var parseBox = document.getElementById("frame-parse");
  var verdictBox = document.getElementById("frame-verdict");
  var countBox = document.getElementById("frame-count");
  var sendBtn = root.querySelector(".js-send-frame");

  function hex2(n) { return ("0" + n.toString(16).toUpperCase()).slice(-2); }
  function isByte(t) { return /^[0-9A-F]{2}$/.test(t); }

  // 요청 서비스 (사양서 §5.1 + 실차 로그에 등장한 0x29 Authentication).
  var REQ_SID = {
    "10": "DiagnosticSessionControl", "11": "ECUReset", "14": "ClearDiagnosticInformation",
    "19": "ReadDTCInformation", "22": "ReadDataByIdentifier", "27": "SecurityAccess",
    "29": "Authentication", "2E": "WriteDataByIdentifier",
    "2F": "InputOutputControlByIdentifier", "31": "RoutineControl",
    "3E": "TesterPresent", "85": "ControlDTCSetting",
  };

  /* ---- 파싱 -------------------------------------------------------------- */

  function tokenize(text) {
    return text.trim().toUpperCase().split(/[\s,]+/).filter(Boolean);
  }

  // 토큰 배열 → {canId, dlc, data[]}. CAN ID 는 3자리 이상 hex, DLC 는 한 자리 10진수로
  // 구분한다 (로그 표기 `000007E0  8  02 …` 를 그대로 받아들이려는 규칙).
  function parse(text) {
    var t = tokenize(text);
    if (!t.length) return null;
    var r = {canId: null, dlc: null, data: t};
    if (CAN_LAYER) {
      if (/^[0-9A-F]{3,8}$/.test(t[0])) { r.canId = t[0]; t = t.slice(1); }
      if (t.length && /^[0-8]$/.test(t[0])) { r.dlc = parseInt(t[0], 10); t = t.slice(1); }
      r.data = t;
    }
    return r;
  }

  // 데이터 첫 바이트 = ISO-TP PCI. 상위 니블이 프레임 종류를 정한다.
  function decodePci(data) {
    if (!data.length || !isByte(data[0])) return null;
    var b0 = parseInt(data[0], 16), hi = b0 >> 4, lo = b0 & 0xF;
    if (hi === 0) return {kind: "SF", tag: "SF", label: "단일 프레임", len: lo, size: 1};
    if (hi === 1) {
      if (!isByte(data[1])) return {kind: "FF", tag: "FF", label: "첫 프레임", len: null, size: 2};
      return {kind: "FF", tag: "FF", label: "첫 프레임",
              len: (lo << 8) | parseInt(data[1], 16), size: 2};
    }
    if (hi === 2) return {kind: "CF", tag: "CF", label: "연속 프레임 · 순번 " + lo.toString(16).toUpperCase(), len: null, size: 1};
    if (hi === 3) return {kind: "FC", tag: "FC", label: "흐름 제어", len: null, size: 1};
    return {kind: "?", tag: "??", label: "알 수 없는 PCI", len: null, size: 1};
  }

  /* PCI 가 주장하는 길이와, 뒤에서 필러를 걷어내 얻은 길이가 어긋나는지 본다.
   *
   * 단일 프레임에서 PCI 길이 바이트는 'UDS 가 몇 바이트인가'다. 그런데 입력만 보면
   * 어디까지가 UDS 이고 어디부터가 필러인지 두 가지로 읽을 수 있다 — PCI 를 믿는
   * 방법과, 뒤쪽 필러를 걷어내 역산하는 방법. 둘이 어긋나는 지점이 사용자가 틀린
   * 지점이다.
   *
   * 세 경우를 심각도로 나눈다:
   *   body < pciLen        오류. PCI 가 없는 바이트를 가리킨다 (프레임이 잘림).
   *   역산 > pciLen        오류. 필러가 아닌 바이트가 PCI 범위 밖에 있다 → PCI 가 작다.
   *   역산 < pciLen        경고. PCI 가 필러까지 UDS 로 세고 있다. 다만 UDS 데이터의
   *                        마지막 바이트가 우연히 필러와 같은 값일 수 있어(예 `2E F1 A0 55`)
   *                        단정하지 않고 경고로 둔다.
   *
   * @param  {string[]} body    PCI 뒤의 바이트 전부 (UDS + 필러)
   * @param  {number}   pciLen  PCI 가 주장하는 UDS 길이
   * @param  {string}   filler  이 방향에서 기대되는 필러 값 ("55" 또는 "AA")
   * @return {?{sev: string, text: string}}  어긋나면 심각도와 설명, 맞으면 null
   */
  function checkLength(body, pciLen, filler) {
    if (body.length < pciLen) {
      return {sev: "err", text: "PCI 는 UDS " + pciLen + "바이트라고 하는데 뒤에 "
        + body.length + "바이트만 있습니다 — 프레임이 잘렸거나 PCI 길이가 너무 큽니다"};
    }
    // 뒤에서 필러가 연속으로 나오는 만큼 걷어내 '실제로 쓴 길이'를 역산한다.
    var real = body.length;
    while (real > 0 && body[real - 1] === filler) real--;
    if (real === pciLen) return null;

    if (real > pciLen) {
      return {sev: "err", text: "PCI 는 UDS " + pciLen + "바이트라고 하는데 필러(0x" + filler
        + ") 앞까지 " + real + "바이트가 쓰여 있습니다 — PCI 를 " + hex2(real)
        + " 로 고치거나, " + pciLen + "바이트 뒤는 필러로 채우세요"};
    }
    return {sev: "warn", text: "PCI 는 UDS " + pciLen + "바이트라고 하는데 필러(0x" + filler
      + ") 앞까지는 " + real + "바이트뿐입니다 — PCI 는 DLC(8)가 아니라 UDS 바이트 수입니다"
      + " (여기선 " + hex2(real) + "). 데이터 마지막 값이 정말 0x" + filler
      + " 라면 이 경고는 무시해도 됩니다"};
  }

  // PCI 뒤를 UDS 와 필러로 나눈다. 단일 프레임만 필러 개념이 있다.
  function extract(data, pci) {
    var body = data.slice(pci.size);
    if (pci.kind === "SF" && pci.len >= 0 && pci.len <= body.length) {
      return {body: body, uds: body.slice(0, pci.len), filler: body.slice(pci.len)};
    }
    return {body: body, uds: body, filler: []};
  }

  /* ---- 검증 -------------------------------------------------------------- */

  function validate(r, pci, ex, dir, filler) {
    var v = [];
    var ok = function (t) { v.push({s: "ok", t: t}); };
    var warn = function (t) { v.push({s: "warn", t: t}); };
    var err = function (t) { v.push({s: "err", t: t}); };

    var lengthBroken = false;      // PCI 길이가 어긋나면 필러 검사를 건너뛴다
    var bad = r.data.filter(function (t) { return !isByte(t); });
    if (bad.length) err("바이트가 아닌 토큰: " + bad.join(" ") + " — 2자리 hex 로 적습니다");

    if (CAN_LAYER) {
      if (!r.canId) {
        err("CAN ID 가 없습니다 — 프레임은 식별자로 시작합니다 (요청 " + CAN_REQ + ")");
      } else if (dir === "req") {
        ok("CAN ID " + r.canId + " · 진단기 → 제어기 (응답은 " + CAN_RESP + " 로 돌아온다)");
      } else if (dir === "resp") {
        ok("CAN ID " + r.canId + " · 제어기 → 진단기 (요청 " + CAN_REQ + " + 8)");
      } else {
        warn("CAN ID " + r.canId + " 는 이 대상의 요청(" + CAN_REQ + ")·응답(" + CAN_RESP + ") ID 가 아닙니다");
      }
      // 전송이 왜 잠겼는지 화면에 남긴다 — 버튼만 회색이면 이유를 알 수 없다.
      if (r.canId && dir !== "req") {
        warn(dir === "resp"
          ? "응답 프레임은 제어기가 보내는 것이라 전송할 수 없습니다 — 읽고 해석하는 연습용입니다"
          : "요청 ID(" + CAN_REQ + ") 로 시작해야 전송할 수 있습니다");
      }

      if (r.dlc === null) warn("DLC 가 없습니다 — CAN Classic 진단 프레임은 항상 8 입니다");
      else if (r.dlc !== DLC_EXPECTED) warn("DLC " + r.dlc + " — 실차 로그의 진단 프레임은 모두 8 입니다");

      if (r.data.length && r.data.length !== DLC_EXPECTED) {
        warn("데이터 " + r.data.length + "바이트 — 8칸을 필러까지 모두 채웁니다 (지금 "
             + (r.data.length < 8 ? (8 - r.data.length) + "칸 비었음" : (r.data.length - 8) + "칸 넘침") + ")");
      }
    }

    // DoIP 는 ISO-TP 를 타지 않아 PCI 층이 아예 없다 — 입력 전체가 UDS 페이로드다.
    if (!CAN_LAYER) {
      if (ex.uds.length) ok("UDS 페이로드 " + ex.uds.length + "바이트 (DoIP — PCI·필러 없음)");
    } else if (!pci) {
      err("PCI(길이) 바이트를 읽을 수 없습니다");
      return v;
    } else if (pci.kind === "SF") {
      if (pci.len === 0) {
        err("PCI 00 — 길이 0 은 프레임이 될 수 없습니다");
      } else if (pci.len > 7) {
        err("PCI " + r.data[0] + " — 단일 프레임에 담을 수 있는 UDS 는 최대 7바이트입니다. "
            + pci.len + "바이트라면 첫 프레임 `1" + ((pci.len >> 8) & 0xF).toString(16).toUpperCase()
            + " " + hex2(pci.len & 0xFF) + "` 로 시작해 연속 프레임(2N)으로 이어야 합니다");
      } else {
        ok("PCI " + r.data[0] + " · " + pci.label + " · UDS " + pci.len + "바이트");
        // 7바이트 초과는 위에서 이미 짚었으니, 범위 안일 때만 길이 대조를 한다.
        var problem = checkLength(ex.body, pci.len, filler);
        if (problem) {
          v.push({s: problem.sev, t: problem.text});
          // 길이가 어긋나면 UDS/필러 경계 자체가 어긋난 것이라 필러 검사는 뜻이 없다.
          if (problem.sev === "err") lengthBroken = true;
        }
      }
    } else if (pci.kind === "FF") {
      if (pci.len === null) err("첫 프레임은 PCI 가 2바이트(`1L LL`)입니다");
      else ok("PCI " + r.data[0] + " " + r.data[1] + " · " + pci.label + " · 전체 " + pci.len
              + "바이트 → 뒤이어 연속 프레임(21, 22 …)이 필요합니다");
    } else if (pci.kind === "CF") {
      ok("PCI " + r.data[0] + " · " + pci.label + " — 앞선 첫 프레임의 이어지는 데이터입니다");
    } else if (pci.kind === "FC") {
      ok("PCI " + r.data[0] + " · " + pci.label + " · 블록크기 "
         + (r.data[1] || "?") + " · 최소간격 " + (r.data[2] || "?") + "ms — 수신측이 보내는 프레임입니다");
    } else {
      err("PCI " + r.data[0] + " — 상위 니블은 0(단일)·1(첫)·2(연속)·3(흐름제어) 중 하나여야 합니다");
    }

    // 필러
    if (ex.filler.length && !lengthBroken) {
      var wrong = ex.filler.filter(function (x) { return x !== filler; });
      if (wrong.length) {
        warn("필러가 " + ex.filler.join(" ") + " 입니다 — "
             + (dir === "resp" ? "응답" : "요청") + " 방향의 필러는 0x" + filler + " 입니다");
      } else {
        ok("필러 " + ex.filler.length + "바이트 0x" + filler + " 로 8칸을 채웠습니다");
      }
    }

    // SID
    var sid = ex.uds[0];
    if (sid && isByte(sid) && (!pci || pci.kind === "SF" || pci.kind === "FF")) {
      if (sid === "7F") {
        var reqSid = ex.uds[1], nrc = ex.uds[2];
        ok("부정 응답 · 요청 SID 0x" + (reqSid || "??") + " 거부 · NRC 0x" + (nrc || "??"));
      } else if (dir === "resp" || (REQ_SID[hex2(parseInt(sid, 16) - 0x40)] && dir !== "req")) {
        var origin = hex2(parseInt(sid, 16) - 0x40);
        if (REQ_SID[origin]) ok("긍정 응답 0x" + sid + " ← 요청 0x" + origin + " " + REQ_SID[origin]);
        else err("응답 SID 0x" + sid + " 에 대응하는 요청 서비스가 없습니다");
      } else if (REQ_SID[sid]) {
        ok("SID 0x" + sid + " " + REQ_SID[sid] + " → 긍정 응답 0x" + hex2(parseInt(sid, 16) + 0x40));
      } else {
        err("SID 0x" + sid + " 는 알려진 진단 서비스가 아닙니다");
      }
    }

    return v;
  }

  /* ---- 렌더 -------------------------------------------------------------- */

  function cell(text, kind) {
    return '<span class="frame__cell frame__cell--' + kind + '">' + text + "</span>";
  }

  function renderFrame(r, pci, ex) {
    var row = "";
    if (CAN_LAYER) {
      row += '<span class="frame__tag">' + (pci ? pci.tag : "??") + "</span>";
      row += cell(r.canId || "없음", r.canId ? "id" : "err");
      row += cell(r.dlc === null ? "?" : r.dlc, r.dlc === DLC_EXPECTED ? "dlc" : "err");
    }
    if (pci) {
      for (var i = 0; i < pci.size; i++) row += cell(r.data[i] || "??", "pci");
    }
    ex.uds.forEach(function (b, i) {
      // 연속 프레임(CF)은 이어지는 데이터라 SID 가 없다. DoIP 는 PCI 가 없어 첫 바이트가 SID.
      var isSid = i === 0 && (!CAN_LAYER || (pci && (pci.kind === "SF" || pci.kind === "FF")));
      row += cell(b, !isByte(b) ? "err" : (isSid ? "sid" : "data"));
    });
    ex.filler.forEach(function (b) { row += cell(b, "fill"); });
    parseBox.innerHTML = '<div class="frame__row">' + row + "</div>"
      + '<div class="frame__legend">'
      + (CAN_LAYER ? '<span><em class="lg-id">CAN ID</em></span><span><em class="lg-dlc">DLC</em></span>'
                   + '<span><em class="lg-pci">PCI</em></span>' : "")
      + '<span><em class="lg-sid">SID</em></span><span><em class="lg-data">데이터</em></span>'
      + (CAN_LAYER ? '<span><em class="lg-fill">필러</em></span>' : "")
      + "<span>· 전송되는 것은 SID+데이터 뿐</span></div>";
  }

  function renderVerdict(list) {
    verdictBox.innerHTML = list.map(function (x) {
      return '<li class="verdict__item verdict__item--' + x.s + '">' + x.t + "</li>";
    }).join("");
  }

  /* ---- 메인 루프 --------------------------------------------------------- */

  var sendable = "";     // 전송 가능한 UDS raw ("" 면 전송 불가)

  function refresh() {
    var r = parse(input.value);
    if (!r) {
      parseBox.innerHTML = "";
      verdictBox.innerHTML = "";
      countBox.textContent = "";
      setSendable("");
      return;
    }
    var pci = CAN_LAYER ? decodePci(r.data) : null;   // DoIP 는 PCI 층이 없다
    var ex = pci ? extract(r.data, pci) : {body: r.data, uds: r.data, filler: []};
    var dir = !CAN_LAYER ? "req"
            : r.canId === CAN_REQ ? "req"
            : r.canId === CAN_RESP ? "resp" : "unknown";
    var filler = dir === "resp" ? FILL_RESP : FILL_REQ;

    renderFrame(r, pci, ex);
    var verdict = validate(r, pci, ex, dir, filler);
    renderVerdict(verdict);

    countBox.textContent = "UDS " + ex.uds.filter(isByte).length + "바이트"
      + (CAN_LAYER ? " · 데이터 " + r.data.length + "/8칸" : "");

    // 오류가 하나라도 있으면 전송을 막는다. 경고는 전송을 막지 않는다.
    var fatal = verdict.some(function (x) { return x.s === "err"; });
    var uds = ex.uds.filter(isByte).join(" ");
    setSendable(!fatal && uds && dir === "req" ? uds : "");
  }

  function setSendable(raw) {
    sendable = raw;
    paintSend();
  }

  /* ---- 자동 반복 전송 (세션 유지 단계) -----------------------------------
   * 세션 유지(0x3E)는 1회 전송으로 끝나는 요청이 아니다 — 2초 이내 주기로 계속
   * 발행해야 세션이 유지된다(계약 §표기·처리 규칙). 그래서 이 단계에서는 전송
   * 버튼 자체가 반복 발행의 시작·중지 토글이 된다.
   *
   * 타이머는 여기서 돌리지 않는다. 다음 단계로 넘어가는 것은 전체 페이지
   * 재로딩이라 이 스크립트째로 사라지기 때문이다. 발행의 주인은 페이지를 넘어
   * 살아 있는 rci-live.js 쪽(window.RCI.keepalive)이고, 여기서는 조작만 한다.
   * ---------------------------------------------------------------------- */
  var KEEPALIVE = !!root.dataset.keepalive;
  var KA_PERIOD = parseInt(root.dataset.keepalive, 10) || 2000;
  function ka() { return window.RCI.keepalive; }

  function paintSend() {
    if (!KEEPALIVE) { sendBtn.disabled = !sendable; return; }
    var on = ka().on();
    sendBtn.textContent = on
      ? "자동 반복 전송 중지 ■"
      : "자동 반복 전송 시작 ↻ (" + (KA_PERIOD / 1000) + "초 주기)";
    sendBtn.classList.toggle("btn--ghost", on);
    sendBtn.classList.toggle("btn--primary", !on);
    // 발행 중이면 입력이 비어도 버튼은 살아 있어야 한다 — 멈출 방법이 필요하다.
    sendBtn.disabled = !on && !sendable;
  }

  sendBtn.addEventListener("click", function () {
    if (!KEEPALIVE) {
      if (sendable) window.RCI.send(sendable);
      return;
    }
    if (ka().on()) ka().stop();
    else if (sendable) ka().start(sendable, KA_PERIOD);
  });
  input.addEventListener("input", refresh);
  // 다른 곳(로그 머리의 중지 버튼)에서 발행이 꺼져도 버튼 문구가 따라간다.
  document.addEventListener("rci:keepalive", paintSend);

  refresh();
})();
