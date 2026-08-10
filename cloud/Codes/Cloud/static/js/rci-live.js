/* RCI 라이브 통신 — 브라우저 ↔ MQTT-over-WebSocket ↔ 브로커 (minigit 계약).
 *
 * 계약: Documents/MQTT_Interface_Contract.md
 *   요청  minigit/req/{device}    {id, raw, timeout_ms}
 *   응답  minigit/resp/{device}   {id, type, raw, nrc?}
 *   에러  minigit/error/{device}  {id, type:"error", reason, message}
 *   상태  minigit/status/rci-*    {state, robot}  (retained)
 *
 * 책임(요청서 §1.1): 게이트웨이는 raw 만, 물리값 디코딩·NRC 매핑은 웹앱(여기).
 * 프레임워크·빌드 없음. mqtt.js(CDN 전역 `mqtt`)만 사용.
 */
(function () {
  "use strict";

  var root = document.querySelector(".run[data-live]");
  if (!root || typeof mqtt === "undefined") return;

  var target = root.dataset.target;    // rc-car | ur-robot
  var device = root.dataset.device;    // rccar | urrobot
  var reqTopic = "minigit/req/" + device;
  var respTopic = "minigit/resp/" + device;
  var errTopic = "minigit/error/" + device;
  var statusTopic = "minigit/status/rci-" + (device === "urrobot" ? "ur" : "rc");

  var logBody = document.getElementById("log-body");
  var seq = 0;
  var seen = {};   // QoS1 중복 수신 방지 (id → true)

  function log(cls, text) {
    var line = document.createElement("span");
    line.className = "log-line " + cls;
    line.textContent = text;
    logBody.appendChild(line);
    logBody.scrollTop = logBody.scrollHeight;
  }

  /* ---- UDS 디코딩 (raw → 사람이 읽는 값) ------------------------------- */

  var NRC = {
    "10": "generalReject", "11": "serviceNotSupported", "12": "subFunctionNotSupported",
    "13": "길이/포맷 오류", "14": "responseTooLong", "21": "busyRepeatRequest",
    "22": "조건 불충족", "24": "requestSequenceError", "31": "요청 범위 밖",
    "33": "보안 접근 거부", "35": "잘못된 키", "36": "키 시도 횟수 초과",
    "37": "지연시간 미경과", "78": "처리 중", "7E": "세션 미지원 서브펑션",
    "7F": "세션 미지원 서비스", "92": "voltageTooHigh", "93": "voltageTooLow",
  };
  var ROBOT_MODE = {"-1": "NO_CONTROLLER", "0": "DISCONNECTED", "1": "CONFIRM_SAFETY",
    "2": "BOOTING", "3": "POWER_OFF", "4": "POWER_ON", "5": "IDLE", "6": "BACKDRIVE",
    "7": "RUNNING", "8": "UPDATING_FIRMWARE"};
  var SAFETY_MODE = {"1": "NORMAL", "2": "REDUCED", "3": "PROTECTIVE_STOP", "4": "RECOVERY",
    "5": "SAFEGUARD_STOP", "6": "SYSTEM_EMERGENCY_STOP", "7": "ROBOT_EMERGENCY_STOP",
    "8": "VIOLATION", "9": "FAULT"};
  var PROG_STATE = {"0": "STOPPING", "1": "STOPPED", "2": "PLAYING", "3": "PAUSING",
    "4": "PAUSED", "5": "RESUMING"};
  var CONTROL_OPT = {"0": "제어권 반환", "1": "리셋 후 고정", "2": "고정 해제 대기", "3": "단기 조정"};

  function u16(d, k) { return (d[k] << 8) | d[k + 1]; }
  function i16(d, k) { var v = u16(d, k); return v >= 0x8000 ? v - 0x10000 : v; }
  function i8(v) { return v >= 0x80 ? v - 0x100 : v; }
  function bcdDate(d) { return d.map(function (x) { return ("0" + x.toString(16)).slice(-2); }).join(""); }
  function ascii(d) { return d.map(function (x) { return String.fromCharCode(x); }).join(""); }
  function hex2(x) { return ("0" + x.toString(16)).slice(-2).toUpperCase(); }

  function decodeJoints(d) {
    // 6개 int16(빅엔디안, 2의 보수) → 0.1도 단위. 2바이트씩 k=0,2,…,10.
    if (d.length < 12) return null;   // 데이터 부족 시 raw 만 표시
    var deg = [];
    for (var k = 0; k < 12; k += 2) deg.push((i16(d, k) / 10).toFixed(1));
    return "관절 [" + deg.join(", ") + "]도";
  }

  // 대상:DID → 데이터 바이트 배열을 사람이 읽는 문자열로.
  var DECODE = {
    "rc-car:0101": function (d) { return "초음파 " + u16(d, 0) + " mm"; },
    "rc-car:0102": function (d) { return "배터리 " + u16(d, 0) + " mV"; },
    "rc-car:0103": function (d) { return "온도 " + (i16(d, 0) / 10) + " ℃"; },
    "rc-car:0104": function (d) { return "습도 " + (u16(d, 0) / 10) + " %RH"; },
    "rc-car:0105": function (d) { return "조도 " + u16(d, 0) + " lux"; },
    "rc-car:0106": function (d) { return "서보 " + d[0] + "°"; },
    "rc-car:0107": function (d) { return "LED 0b" + ("00" + d[0].toString(2)).slice(-3); },
    "rc-car:0108": function (d) { return "부저 " + (d[0] ? "ON" : "OFF"); },
    "ur-robot:0101": decodeJoints,
    "ur-robot:0107": function (d) { return "로봇 모드 " + ROBOT_MODE[String(i8(d[0]))]; },
    "ur-robot:0108": function (d) { return "안전 모드 " + SAFETY_MODE[String(d[0])]; },
    "ur-robot:0109": function (d) { return "프로그램 " + PROG_STATE[String(d[0])]; },
    "ur-robot:010A": function (d) { return "전압 " + (u16(d, 0) / 1000) + " V"; },
    "ur-robot:010B": function (d) { return "전류 " + u16(d, 0) + " mA"; },
    "ur-robot:010F": function (d) { return "그리퍼 " + d[0] + " %"; },
    "ur-robot:0110": function (d) { return "카메라 " + (d[0] ? "연결됨" : "연결안됨"); },
  };
  // 사양 DID(0xF1xx)는 대상 공통.
  var DECODE_SPEC = {
    "F199": function (d) { var s = bcdDate(d); return "SW 날짜 20" + s.slice(0, 2) + "-" + s.slice(2, 4) + "-" + s.slice(4, 6); },
    "F195": function (d) { return "SW 버전 " + ascii(d); },
    "F18C": function (d) { return "시리얼 " + ascii(d); },
    "F1A0": function (d) {
      return target === "rc-car"
        ? "CAN ID 0x" + ("0000" + u16(d, 0).toString(16).toUpperCase()).slice(-4)
        : "IP " + d.join(".");
    },
  };

  // 긍정 응답 raw → 해석 문자열(없으면 null).
  function decodePositive(bytes) {
    if (bytes[0] !== 0x62 || bytes.length < 3) return null;   // 0x22 읽기 응답만 해석
    var did = ("0" + bytes[1].toString(16)).slice(-2).toUpperCase()
            + ("0" + bytes[2].toString(16)).slice(-2).toUpperCase();
    var data = bytes.slice(3);
    var fn = DECODE[target + ":" + did] || DECODE_SPEC[did];
    return fn ? fn(data) : null;
  }

  // 0x2F InputOutputControl 응답(0x6F) raw → 해석 문자열(없으면 null).
  function decodeControl(bytes) {
    if (bytes[0] !== 0x6F || bytes.length < 4) return null;   // 제어 응답만 해석
    var did = hex2(bytes[1]) + hex2(bytes[2]);
    var opt = CONTROL_OPT[String(bytes[3])] || ("옵션 0x" + hex2(bytes[3]));
    var state = bytes.slice(4);
    var val = state.length ? " · 값 " + (state.length === 1 ? state[0] : state.map(hex2).join(" ")) : "";
    return "제어 수락 · DID 0x" + did + " · " + opt + val;
  }

  function toBytes(raw) { return raw.trim().split(/\s+/).map(function (h) { return parseInt(h, 16); }); }

  /* ---- 3D 모델 연동 (조명 반짝임) ------------------------------------- */
  // 강제구동 조명 제어(0x2F, DID 0x0207)가 정상 응답하면 3D 모델 조명을 반짝인다.
  // 현재 통합 모델(아이오닉5)은 앞뒤 조명이 단일 발광 머티리얼 M_Emission 으로 묶여
  // 함께 켜진다. 모델 교체 시 EMISSIVE_MAT 를 새 조명 머티리얼 이름으로 맞출 것.
  var LIGHTS_DID = "0207";           // 조명 강제구동 DID
  var EMISSIVE_MAT = "M_Emission";   // 발광 머티리얼 이름 (모델 의존)

  function emissiveMat() {
    var mv = document.querySelector("model-viewer");
    if (!mv || !mv.model) return null;
    return mv.model.materials.find(function (x) { return x.name === EMISSIVE_MAT; }) || null;
  }
  var LIGHT_STRENGTH = 100;   // 점등 시 발광 강도(HDR, 어두운 배경에서 강조).
  function setEmissive(on) {
    var m = emissiveMat();
    if (!m) return;
    m.setEmissiveFactor(on ? [1, 1, 1] : [0, 0, 0]);
    if (typeof m.emissiveStrength !== "undefined") {   // v4 KHR_materials_emissive_strength
      try { m.emissiveStrength = on ? LIGHT_STRENGTH : 1; } catch (e) {}
    }
  }
  // 로드 직후 소등한다. (하우징 검정 baseColor 는 glb 파일에 구워져 있음 → OFF 시
  //  어두운 하우징, ON 시 흰 발광으로 대비.)
  (function () {
    var mv = document.querySelector("model-viewer");
    if (mv) mv.addEventListener("load", function () { setEmissive(false); });
  })();
  // 3회(6토글) 깜빡인 뒤 기본 상태(소등 = 검정 하우징)로 복귀한다.
  function blinkLights() {
    if (!emissiveMat()) return;
    var on = false, n = 0;
    var timer = setInterval(function () {
      on = !on;
      setEmissive(on);
      if (++n >= 6) { clearInterval(timer); setEmissive(false); }   // 점멸 후 기본 baseColor 로
    }, 180);
  }

  /* ---- MQTT ------------------------------------------------------------ */

  var url = "ws://" + location.hostname + ":8080/mqtt";
  var client = mqtt.connect(url, { reconnectPeriod: 2000, connectTimeout: 4000 });

  client.on("connect", function () {
    logBody.innerHTML = "";
    log("muted", "● 브로커 연결됨 · " + url);
    client.subscribe([respTopic, errTopic, statusTopic], { qos: 1 });
  });
  client.on("error", function (e) { log("muted", "✗ 연결 오류: " + e.message); });

  function startsWith(s, p) { return s.indexOf(p) === 0; }

  client.on("message", function (topic, payload) {
    var m;
    try { m = JSON.parse(payload.toString()); } catch (_) { return; }
    try {
      // 토픽 접두어로 라우팅 (device 접미사 무관하게 견고).
      if (startsWith(topic, "minigit/status/")) {
        log("muted", "◆ RCI " + (m.state || "") + (m.robot ? " · robot " + m.robot : ""));
        return;
      }
      if (startsWith(topic, "minigit/error/")) {
        log("err", "✗ 에러: " + (m.message || m.reason || ""));
        return;
      }
      if (!startsWith(topic, "minigit/resp/")) return;   // 응답 외 토픽 무시

      // QoS1 중복 무시. id 만으로 잡으면 nrc=78(진행 중) 직후 같은 id 로 오는
      // 최종 응답까지 버려지므로, id+raw 쌍으로 판별한다(계약 §표기·처리 규칙).
      if (m.id) {
        var key = m.id + "|" + (m.raw || "") + "|" + (m.nrc || "");
        if (seen[key]) return;
        seen[key] = true;
      }

      if (m.type === "negative") {
        var name = NRC[String(m.nrc).toUpperCase()] || "알 수 없음";
        if (String(m.nrc) === "78") log("note", "   ↳ 진행 중… (최종 응답 대기)");
        else log("err", "← " + m.raw + "   ✗ NRC " + m.nrc + " " + name);
        return;
      }
      if (!m.raw) return;
      log("recv", "← " + m.raw);
      var bytes = toBytes(m.raw);
      var note = decodePositive(bytes) || decodeControl(bytes);   // 0x62 읽기 / 0x6F 제어
      if (note) log("note", "   ↳ " + note);
      // 조명 ON 제어(0x6F, DID 0x0207, 상태≠0) 정상 응답 → 점멸 후 기본 상태 복귀.
      if (bytes[0] === 0x6F && hex2(bytes[1]) + hex2(bytes[2]) === LIGHTS_DID
          && bytes[bytes.length - 1] !== 0x00) {
        blinkLights();
      }
    } catch (e) {
      log("err", "✗ 처리 오류: " + e.message);
    }
  });

  /* ---- 전송 버튼 배선 -------------------------------------------------- */

  var input = document.getElementById("uds-req");
  Array.prototype.forEach.call(root.querySelectorAll(".js-send"), function (btn) {
    btn.addEventListener("click", function () {
      var raw = (input ? input.value : btn.dataset.uds || "").trim();
      if (!raw) return;
      var id = "u-" + (++seq);
      client.publish(reqTopic, JSON.stringify({ id: id, raw: raw, timeout_ms: 1000 }), { qos: 1 });
      log("send", "→ " + raw);
    });
  });
})();
