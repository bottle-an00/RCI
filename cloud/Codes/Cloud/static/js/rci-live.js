/* RCI 라이브 통신 — 계약(minigit)을 두 갈래 전송 방식으로 이행한다.
 *
 * 계약: Documents/MQTT_Interface_Contract.md
 *   요청  minigit/req/{device}    {id, raw, timeout_ms}
 *   응답  minigit/resp/{device}   {id, type, raw, nrc?}
 *   에러  minigit/error/{device}  {id, type:"error", reason, message}
 *   상태  minigit/status/rci-*    {state, robot}  (retained)
 *
 * 전송 방식(상단바 토글 · transport-switch.js 가 조작):
 *   mqtt  브라우저 → WebSocket → 브로커 → RCI     RCI 측 구독·발행 연동 테스트
 *   mock  브라우저 안에서 응답 생성 (mock-rci.js)  브로커 없이 화면 작업
 *
 * 책임(요청서 §1.1): 게이트웨이는 raw 만, 물리값 디코딩·NRC 매핑은 웹앱(여기).
 * 프레임워크·빌드 없음. mqtt.js(CDN 전역 `mqtt`)만 사용 — 목업 모드에선 쓰지 않는다.
 */
(function () {
  "use strict";

  var root = document.querySelector(".run[data-live]");
  if (!root) return;

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
    "ur-robot:0111": function (d) { return "진동 " + (u16(d, 0) / 100).toFixed(2) + " m/s²"; },
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

  /* ---- DTC 디코딩 (0x59 ReadDTCInformation) ----------------------------- */
  // 응답 구조: 59 <서브펑션> <statusAvailabilityMask> [DTC 3바이트 + 상태 1바이트] × n
  // 2바이트 DTC → 5자리 코드: 상위 2비트 P/C/B/U, 다음 2비트 첫 자리, 나머지 니블 3개.
  // 3번째 바이트는 고장유형(failure type). 실차 로그 `59 02 08` = 마스크만 = 고장 없음.
  var DTC_PREFIX = ["P", "C", "B", "U"];
  var DTC_STATUS = ["현재 실패", "이번주기 실패", "보류 pending", "확정 confirmed",
    "소거후 미완료", "소거후 실패", "이번주기 미완료", "경고등 요청"];

  function dtcCode(hi, mid, lo) {
    return DTC_PREFIX[(hi >> 6) & 0x3] + ((hi >> 4) & 0x3)
         + (hi & 0xF).toString(16).toUpperCase() + hex2(mid) + "-" + hex2(lo);
  }
  function dtcStatus(b) {
    var on = [];
    for (var i = 0; i < 8; i++) if (b & (1 << i)) on.push(DTC_STATUS[i]);
    return on.length ? on.join("·") : "상태 없음";
  }
  function decodeDtc(bytes) {
    if (bytes[0] !== 0x59 || bytes.length < 2) return null;
    var mask = bytes.length > 2 ? " (마스크 0x" + hex2(bytes[2]) + ")" : "";
    if (hex2(bytes[1]) === "01") {                    // 개수만 조회
      return bytes.length >= 6 ? "DTC " + u16(bytes, 4) + "건" + mask : "DTC 개수 응답" + mask;
    }
    var recs = bytes.slice(3);                        // 59 + 서브펑션 + 마스크 = 3바이트
    if (recs.length < 4) return "고장 없음" + mask;    // 레코드 없음 = 소거됨/무고장
    var out = [];
    for (var i = 0; i + 3 < recs.length; i += 4) {
      out.push(dtcCode(recs[i], recs[i + 1], recs[i + 2]) + " [" + dtcStatus(recs[i + 3]) + "]");
    }
    return "DTC " + out.length + "건 · " + out.join(" / ");
  }

  /* ---- 나머지 긍정 응답 (0x50·0x7E·0x67·0x6E·0x54·0x51) ------------------ */
  var SESSION = {"01": "기본 Default", "02": "프로그래밍 Programming",
    "03": "확장 Extended", "04": "안전시스템 Safety"};

  function decodeSimple(bytes) {
    switch (bytes[0]) {
      case 0x50:   // 세션 응답 뒤 4바이트 = P2 / P2*(해상도 10ms)
        var s = SESSION[hex2(bytes[1])] || ("0x" + hex2(bytes[1]));
        return bytes.length >= 6
          ? "세션 " + s + " 진입 · P2 " + u16(bytes, 2) + "ms · P2* " + (u16(bytes, 4) * 10) + "ms"
          : "세션 " + s + " 진입";
      case 0x7E: return "세션 유지 확인 (TesterPresent)";
      case 0x67:
        var lv = hex2(bytes[1]);
        return (parseInt(lv, 16) % 2 === 1)          // 홀수 서브펑션 = Seed 요청 응답
          ? "Seed 수신 · " + bytes.slice(2).map(hex2).join(" ")
          : "보안 해제 성공 (레벨 0x" + lv + ")";
      case 0x6E: return "쓰기 완료 · DID 0x" + hex2(bytes[1]) + hex2(bytes[2]);
      case 0x54: return "DTC 소거 완료 — 재조회로 확인할 것";
      case 0x51: return "ECU 리셋 수락";
      // 리프로그래밍 3종. 0x74 뒤 첫 바이트는 lengthFormatIdentifier —
      // 상위 니블이 '뒤따르는 최대 블록 길이가 몇 바이트인가'다 (0x20 = 2바이트).
      case 0x74:
        return bytes.length >= 4
          ? "다운로드 수락 · 블록 최대 " + u16(bytes, 2) + " 바이트"
          : "다운로드 수락";
      case 0x76: return "블록 " + hex2(bytes[1]) + " 수신 확인";
      case 0x77: return "전송 종료 수락 — 검증 단계로";
      case 0x71: return bytes.length >= 4
        ? "루틴 수락 · 서브펑션 0x" + hex2(bytes[1]) + " · 루틴 ID 0x"
          + hex2(bytes[2]) + hex2(bytes[3])
        : "루틴 수락";
      default: return null;
    }
  }

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
  /* ---- 3D 모델 연동 (강제구동 동작 재생) --------------------------------
   * 강제구동(0x2F)이 수락되면 모델에 구워진 애니메이션을 1회 재생한다.
   * UR_Robot.glb 의 "UR3Track" — 채널 4개가 UR3·Shoulder·Elbow·Wrist02 의 rotation
   * 을 겨냥하고, 노드가 UR3→Shoulder→Elbow→Wrist01→Wrist02→Wrist03→EffectorJoint
   * 순으로 물려 있어 부모를 돌리면 아래 팔이 따라온다.
   *
   * 장기 목표는 실제 관절 각도(DID 0x0101, 6×int16 0.1도)로 자세를 직접 만드는 것이다.
   * 그건 이 방식으로는 안 된다 — model-viewer 는 머티리얼만 공개하고(mv.model.materials)
   * 노드 변환은 압축된 내부 심볼에 갇혀 있어 손댈 수 없다. 그때가 되면 3D 뷰만
   * three.js 로 직접 렌더해 getObjectByName("Shoulder").rotation 을 쓰게 될 것이다.
   * 지금은 '응답이 오면 움직인다' 는 왕복의 인과만 보여주는 단계다.
   */
  var MOTION_ANIM = "UR3Track";   // 없으면 첫 번째 애니메이션으로 대체한다
  var motionBusy = false;         // 연타로 겹쳐 재생하지 않는다

  function playMotion() {
    var mv = document.querySelector("model-viewer");
    if (!mv) return;
    if (!mv.model) {
      // 모델이 아직 안 떴는데 조용히 넘어가면 '연동이 안 된다'로 오해된다.
      log("muted", "   ↳ 3D 모델 로딩 전이라 동작을 재생하지 않았습니다");
      return;
    }
    var list = mv.availableAnimations || [];
    if (!list.length || motionBusy) return;     // 애니메이션 없는 모델(현재 RC카)
    var name = list.indexOf(MOTION_ANIM) !== -1 ? MOTION_ANIM : list[0];
    motionBusy = true;
    mv.animationName = name;
    mv.currentTime = 0;
    mv.play({repetitions: 1});
    log("note", "   ↳ 3D 모델 동작 재생 · " + name
      + (mv.duration ? " (" + mv.duration.toFixed(1) + "초)" : ""));
    // 끝나면 첫 프레임으로 되돌린다 — 다음 구동이 늘 같은 자세에서 시작하게.
    mv.addEventListener("finished", function done() {
      mv.removeEventListener("finished", done);
      mv.currentTime = 0;
      mv.pause();
      motionBusy = false;
    });
  }

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

  /* ---- 수신 처리 (전송 방식과 무관하게 공용) ---------------------------- */

  function startsWith(s, p) { return s.indexOf(p) === 0; }

  /* ---- 상단바 연결 표시로 내보내는 상태 ---------------------------------
   * '연결됨' 은 브로커 연결과 RCI online 이 둘 다여야 한다 — 둘을 따로 들고 있다가
   * 그대로 방송하고, 문구로 옮기는 판단은 link-status.js 에 맡긴다. 그 파일은
   * 실습 화면이 아닌 곳(컨텐츠 선택)에서도 같은 규칙으로 그려야 하기 때문이다.
   */
  var linkBroker = false;
  var linkRci = null;      // RCI 가 알려온 state ("online"/"offline"), 미수신은 null

  function linkPaint() {
    document.dispatchEvent(new CustomEvent("rci:link", {
      detail: {mode: mode, broker: linkBroker, rci: linkRci},
    }));
  }

  /* 도착한 것을 **있는 그대로** 알린다 (긍정·부정·에러 전부, 요청 id 포함).
   *
   * `rci:resp` 와 나눠 놓은 이유: 그쪽은 '정상 응답이 왔다'는 뜻이라 부정 응답에는
   * 아예 발행되지 않는다(step-progress.js 의 통과 판정이 그 전제로 서 있다).
   * 자동 시퀀스(auto-sequence.js)는 반대로 실패도 알아야 다음 단계를 멈출 수 있다.
   */
  function emitAnswer(detail) {
    document.dispatchEvent(new CustomEvent("rci:answer", { detail: detail }));
  }

  function handleMessage(topic, m) {
    try {
      // 토픽 접두어로 라우팅 (device 접미사 무관하게 견고).
      if (startsWith(topic, "minigit/status/")) {
        log("muted", "◆ RCI " + (m.state || "") + (m.robot ? " · robot " + m.robot : ""));
        linkRci = m.state || null;            // 상단바 연결 표시 (link-status.js)
        linkPaint();
        return;
      }
      if (startsWith(topic, "minigit/error/")) {
        log("err", "✗ 에러: " + (m.message || m.reason || ""));
        emitAnswer({ id: m.id, type: "error", raw: "", bytes: [],
                     message: m.message || m.reason || "" });
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

      // 세션 유지(3E)는 2초마다 왕복하므로 그대로 찍으면 로그가 그것만 남는다.
      // 두 번째 왕복부터는 한 줄에 접어 넣는다 — kaIntercept() 가 true 를 주면
      // 이 왕복은 그 줄에 이미 반영됐다는 뜻이라 새 줄을 만들지 않는다.
      var folded = kaIntercept(m);

      if (m.type === "negative") {
        var name = NRC[String(m.nrc).toUpperCase()] || "알 수 없음";
        if (folded) { /* 접힌 줄에 이미 표시됨 */ }
        else if (String(m.nrc) === "78") log("note", "   ↳ 진행 중… (최종 응답 대기)");
        else log("err", "← " + m.raw + "   ✗ NRC " + m.nrc + " " + name);
        emitAnswer({ id: m.id, type: "negative", raw: m.raw || "",
                     bytes: m.raw ? toBytes(m.raw) : [],
                     nrc: String(m.nrc || "").toUpperCase(), nrcName: name });
        return;
      }
      if (!m.raw) return;
      if (!folded) log("recv", "← " + m.raw);
      var bytes = toBytes(m.raw);
      // 0x62 읽기 / 0x6F 제어 / 0x59 DTC / 그 외 단순 응답 순으로 시도.
      var note = decodePositive(bytes) || decodeControl(bytes)
              || decodeDtc(bytes) || decodeSimple(bytes);
      if (note && !folded) log("note", "   ↳ " + note);
      // 프레임 조립기(can-composer.js)가 응답을 볼 수 있게 알린다 (Seed → Key 자동 채움 등).
      document.dispatchEvent(new CustomEvent("rci:resp", {detail: {raw: m.raw, bytes: bytes}}));
      emitAnswer({ id: m.id, type: "positive", raw: m.raw, bytes: bytes, note: note });
      // 강제구동 응답(0x6F) → 3D 모델 반응. 조명(0207)은 발광으로, 그 밖의 구동
      // DID(모터·조인트·그리퍼 …)는 내장 애니메이션으로 표현한다.
      if (bytes[0] === 0x6F && hex2(bytes[1]) === "02") {     // 0x02xx = 구동 DID 대역
        if (hex2(bytes[1]) + hex2(bytes[2]) === LIGHTS_DID) {
          if (bytes[bytes.length - 1] !== 0x00) blinkLights();   // 상태 0 = 소등
        } else {
          playMotion();
        }
      }
    } catch (e) {
      log("err", "✗ 처리 오류: " + e.message);
    }
  }

  /* ---- 전송 방식 두 갈래 -------------------------------------------------
   * 같은 계약(minigit/*)을 두 경로로 이행한다:
   *   mqtt  브라우저 → WebSocket → 브로커 → RCI    (RCI 측 연동 테스트용)
   *   mock  브라우저 안에서 응답 생성 (mock-rci.js)  (브로커 없이 UI 작업용)
   * 어느 쪽이든 수신은 handleMessage() 하나로 모이므로 디코딩·로그·이벤트는 공용이다.
   * ---------------------------------------------------------------------- */

  /* 모드 셋. 왼쪽부터 '실물에 가까워지는' 순서로 늘어놓는다.
   *   mock  브라우저 내부 목업. 브로커 없이 동작 — UI 작업용.
   *   mqtt  브로커 경유 + PC 의 목(mock_rci.py)이 응답 — 계약·왕복 확인용.
   *   rci   브로커 경유 + PC 의 목은 침묵, 실물 RCI 만 응답 — 실물 연동용.
   *
   * mqtt 와 rci 는 전송 경로가 **완전히 같다.** 다르게 하는 것은 목에게 보내는
   * 억제 선언 하나뿐이라, 웹 코드에서 두 모드는 플래그 하나 차이다.
   */
  /* 모드는 **device 마다 따로** 기억한다. 대상마다 뒤를 받치는 실체가 다르기
   * 때문이다 — UR3 는 실물 RCI 가 있고 RC카는 없다. 한 값을 공유하면 UR 을
   * RCI(MQTT) 로 돌린 순간 RC카 페이지까지 억제 선언을 내보내, 아무도 응답하지
   * 않는 화면이 된다(원인이 화면에 안 보여서 찾기 어렵다). */
  var MODE_KEY = "rci:transport:" + device;    // "mqtt" | "mock" | "rci"
  var MODES = { mqtt: 1, mock: 1, rci: 1 };
  var wsUrl = root.dataset.wsUrl || ("ws://" + location.hostname + ":8080/mqtt");
  // 목 억제 채널. device 마다 토픽을 나눠 UR 탭과 RC 탭이 서로를 덮어쓰지 않게 한다.
  var ctrlTopic = "minigit/control/mock/" + device;

  function loadMode() {
    try {
      var saved = localStorage.getItem(MODE_KEY);
      return MODES[saved] ? saved : "mock";
    } catch (e) { return "mock"; }
  }
  function saveMode(m) { try { localStorage.setItem(MODE_KEY, m); } catch (e) { /* 무시 */ } }

  // --- 브로커 직결 ---
  // suppressMock: 이 device 를 실물 RCI 가 맡는다고 목에게 선언할지 (rci 모드)
  function mqttTransport(suppressMock) {
    if (typeof mqtt === "undefined") {
      log("err", "✗ mqtt.js 를 불러오지 못했습니다");
      return { publish: function () {}, stop: function () {} };
    }
    // 접속에 시간이 걸리고 실패할 수도 있다 — 빈 로그로 두면 사용자는 뭐가 잘못됐는지
    // 알 수 없다. 시도·성공·끊김을 각각 한 줄로 남긴다(재접속 스팸은 한 번만).
    log("muted", "○ 브로커 접속 중… " + wsUrl);
    var client = mqtt.connect(wsUrl, { reconnectPeriod: 2000, connectTimeout: 4000 });
    var warned = false;
    client.on("connect", function () {
      warned = false;
      linkBroker = true; linkRci = null;   // retained status 가 곧 도착해 채운다
      linkPaint();
      log("muted", "● 브로커 연결됨 · " + wsUrl);
      client.subscribe([respTopic, errTopic, statusTopic], { qos: 1 });
      // 억제 선언은 retained 다. 목이 나중에 떠도, 페이지를 닫아도 마지막 선언이
      // 남는다 — 목을 껐다 켤 때마다 모드를 다시 누르지 않아도 되게 하려는 것이다.
      // 재접속마다 다시 쓰는 이유: 그 사이 다른 탭이 뒤집어 놨을 수 있다.
      client.publish(ctrlTopic, JSON.stringify({ suppress: !!suppressMock }),
                     { qos: 1, retain: true });
      log("muted", suppressMock
        ? "◆ 실물 RCI 모드 · PC 목업에 " + device + " 응답 중지를 선언했습니다"
        : "◆ MQTT 목업 모드 · PC 목업이 " + device + " 에 응답합니다");
    });
    client.on("error", function (e) {
      linkBroker = false; linkRci = null;
      linkPaint();
      if (warned) return;
      warned = true;
      log("err", "✗ 브로커 접속 실패: " + (e && e.message ? e.message : "알 수 없음")
        + " — 재시도 중입니다. RCI·브로커가 떠 있는지 확인하거나 '목업' 으로 전환하세요.");
    });
    client.on("close", function () {
      linkBroker = false; linkRci = null;
      linkPaint();
      if (warned) return;
      warned = true;
      log("muted", "○ 브로커 연결 끊김 — 재접속 시도 중…");
    });
    client.on("message", function (topic, payload) {
      var m;
      try { m = JSON.parse(payload.toString()); } catch (_) { return; }
      handleMessage(topic, m);
    });
    return {
      publish: function (payload) { client.publish(reqTopic, JSON.stringify(payload), { qos: 1 }); },
      stop: function () { try { client.end(true); } catch (e) { /* 무시 */ } },
    };
  }

  // --- 브라우저 내 목업 ---
  // 실물의 왕복 지연을 흉내내야 '요청 → 응답' 순서가 로그에서 보인다.
  var MOCK_DELAY = 120;
  function mockTransport() {
    var timers = [];
    log("muted", "● 목업 모드 · 브로커 없이 브라우저에서 응답 생성");
    timers.push(setTimeout(function () {
      handleMessage(statusTopic, window.MockRci.status());
    }, 60));
    return {
      publish: function (payload) {
        timers.push(setTimeout(function () {
          var raw = window.MockRci.buildResponse(device, payload.raw);
          handleMessage(respTopic, window.MockRci.toResponseMsg(payload.id, raw));
        }, MOCK_DELAY));
      },
      stop: function () { timers.forEach(clearTimeout); timers = []; },
    };
  }

  var mode = loadMode();
  var transport = null;

  function start() {
    logBody.innerHTML = "";
    seen = {};                                  // 모드가 바뀌면 중복 판별도 새로 시작
    linkBroker = false; linkRci = null;         // 연결 표시도 처음부터 다시
    linkPaint();
    // mqtt·rci 는 같은 전송 경로다 — 목에게 보내는 억제 선언만 다르다.
    transport = mode === "mock" ? mockTransport() : mqttTransport(mode === "rci");
  }

  function setMode(next) {
    if (!MODES[next]) return;
    if (next === mode && transport) return;
    if (transport) transport.stop();
    mode = next;
    saveMode(mode);
    start();
    document.dispatchEvent(new CustomEvent("rci:mode", { detail: { mode: mode } }));
  }

  /* ---- 전송 -------------------------------------------------------------- */

  // 계약상 발행하는 것은 **UDS 페이로드(raw)** 뿐이다. CAN ID·PCI·필러는 RCI 가
  // 붙이므로(계약 §역할 분담), 조립기의 프레임 표시는 교육용 시각화이고 여기 실리지 않는다.
  // quiet: 로그에 `→ raw` 를 남기지 않는다 (세션 유지 반복 발행이 쓴다).
  function sendRaw(raw, timeoutMs, quiet) {
    raw = (raw || "").trim();
    if (!raw || !transport) return null;
    var id = "u-" + (++seq);
    transport.publish({ id: id, raw: raw, timeout_ms: timeoutMs || 1000 });
    if (!quiet) log("send", "→ " + raw);
    return id;
  }

  /* ---- 세션 유지 자동 반복 발행 ------------------------------------------
   * 계약 §표기·처리 규칙: 세션 유지(0x3E)는 2초 이내 주기로 발행해야 하고,
   * 끊기면 5초 뒤 기본 세션으로 되돌아간다. 즉 이 발행은 **한 화면의 기능이
   * 아니라 연결 자체의 상태**다 — 다음 단계로 넘어가도 계속돼야 한다.
   *
   * 그런데 '다음 단계 →' 는 전체 페이지 재로딩이라 그 순간 타이머가 죽는다.
   * 그래서 타이머를 화면(can-composer.js)에 두지 않고 여기에 두고, '무엇을
   * 몇 초마다 보내는가' 를 sessionStorage 에 적어 매 로드마다 되살린다.
   *
   * localStorage 가 아니라 sessionStorage 인 이유: 탭을 닫으면 끝나야 한다.
   * localStorage 였다면 며칠 뒤 다시 열어도 발행이 되살아나는데, 누른 기억이
   * 없는 사용자에게는 원인 불명의 트래픽이 된다.
   *
   * 발행은 device 마다 따로 기억한다 — UR 탭과 RC 탭이 서로를 덮어쓰지 않게.
   *
   * 다만 '유지'에는 범위가 있다. 세션 유지는 **지금 밟고 있는 코스**의 것이라,
   * 같은 코스의 다음 단계로 넘어갈 때만 이어져야 한다. 다른 세부 항목(예: 센서
   * 리딩 → 강제 구동)이나 다른 화면으로 옮기면 그 발행은 주인이 없어진 것이다 —
   * 그래서 발행 선언에 소유 범위(scope)를 함께 적고, 되살릴 때 지금 화면의
   * 범위와 다르면 되살리지 않고 지운다. 범위 값은 서버가 내려준다
   * (run.html 의 data-ka-scope · main.content_view 의 ka_scope).
   * ---------------------------------------------------------------------- */

  var KA_KEY = "rci:keepalive:" + device;
  var KA_SCOPE = location.pathname + "#" + (root.dataset.kaScope || "");
  var KA_MIN = 500, KA_MAX = 5000;    // 5초를 넘기면 세션이 이미 풀린다
  var kaTimer = null;                 // setInterval 핸들 (null = 중지 상태)
  var kaRaw = "", kaPeriod = 0;
  var kaCount = 0, kaMiss = 0;
  var kaPending = null;               // 발행하고 응답을 기다리는 요청 id
  var kaAnswer = "";                  // 마지막으로 받은 응답 (접힌 줄에 표시)
  var kaLine = null;                  // 갱신해 재사용하는 로그 한 줄

  var kaBadge = document.getElementById("ka-badge");

  function kaLoad() {
    try { return JSON.parse(sessionStorage.getItem(KA_KEY)); } catch (e) { return null; }
  }
  function kaSave(v) {
    try {
      if (v) sessionStorage.setItem(KA_KEY, JSON.stringify(v));
      else sessionStorage.removeItem(KA_KEY);
    } catch (e) { /* 사생활 모드 등 */ }
  }

  /* 발행 상태를 화면에 그린다. 배지는 로그 패널 머리(logBody 밖)에 있어서
     모드 전환으로 로그를 비워도 살아남는다 — 어느 단계에서도 멈출 수 있다. */
  function kaPaint() {
    if (kaBadge) {
      kaBadge.hidden = !kaTimer;
      var t = kaBadge.querySelector(".ka-badge__text");
      if (t) t.textContent = "세션 유지 발행 중 · " + (kaPeriod / 1000) + "초 주기";
    }
    // 조립기가 전송 버튼 문구를 맞출 수 있게 알린다.
    document.dispatchEvent(new CustomEvent("rci:keepalive",
      { detail: { on: !!kaTimer, raw: kaRaw, period: kaPeriod } }));
  }

  function kaRender() {
    if (!kaLine || !kaLine.parentNode) {     // 모드 전환으로 로그가 비워졌으면 새로
      kaLine = document.createElement("span");
      kaLine.className = "log-line note log-line--fold";
      logBody.appendChild(kaLine);
    }
    kaLine.textContent = "↻ 세션 유지 " + kaRaw + " → " + (kaAnswer || "응답 대기…")
      + " · " + kaCount + "회 · " + (kaPeriod / 1000) + "초 주기"
      + (kaMiss ? " · 무응답 " + kaMiss + "회" : "");
    logBody.scrollTop = logBody.scrollHeight;
  }

  /* 세션 유지 왕복이면 접힌 줄에 반영하고 true 를 준다 (handleMessage 가 호출).
     첫 왕복만 일부러 그대로 흘려보낸다 — `→ 3E 00` / `← 7E 00` 를 한 번은
     눈으로 봐야 무엇이 오가는지 배울 수 있다. */
  function kaIntercept(m) {
    if (!kaTimer || !m.id || m.id !== kaPending) return false;
    kaPending = null;
    kaMiss = 0;
    if (m.type === "negative") {
      kaAnswer = "✗ NRC " + m.nrc;
      kaTrouble("negative", m);
    } else {
      kaAnswer = m.raw || "";
    }
    if (kaCount <= 1) return false;
    kaRender();
    return true;
  }

  function kaTick() {
    if (kaPending) {                  // 앞 요청의 응답이 끝내 오지 않았다
      kaMiss++;
      kaTrouble("silent", { misses: kaMiss, raw: kaRaw });
      if (!kaTimer) return;           // 정책이 발행을 멈췄으면 여기서 끝
    }
    kaCount++;
    // 두 번째 발행부터는 조용히 — 로그는 접힌 줄 하나로 갱신된다.
    kaPending = sendRaw(kaRaw, kaPeriod, kaCount > 1);
    if (kaCount > 1) kaRender();
  }

  function kaStart(raw, period) {
    raw = (raw || "").trim();
    if (!raw) return false;
    period = Math.min(KA_MAX, Math.max(KA_MIN, period || 2000));
    kaHalt();                                  // 주기·페이로드 교체를 겸한다
    kaRaw = raw; kaPeriod = period;
    kaCount = 0; kaMiss = 0; kaAnswer = ""; kaLine = null; kaPending = null;
    kaSave({ raw: kaRaw, period: kaPeriod, scope: KA_SCOPE });
    kaTick();                                  // 첫 발행은 기다리지 않는다
    kaTimer = setInterval(kaTick, kaPeriod);
    kaPaint();
    return true;
  }

  // 타이머만 끊는다 (로그·표시는 건드리지 않음). kaStart 의 교체용.
  function kaHalt() {
    if (kaTimer) { clearInterval(kaTimer); kaTimer = null; }
    kaPending = null;
    kaSave(null);
  }

  function kaStop(reason) {
    if (!kaTimer && !kaLoad()) return;
    kaHalt();
    log("muted", "○ 세션 유지 발행 중지" + (reason ? " — " + reason : "")
      + " · 5초 뒤 기본 세션으로 돌아갑니다");
    kaPaint();
  }

  /* 세션 유지 왕복이 실패했을 때의 정책.
   *
   * kind === "silent"    한 주기 안에 응답이 오지 않았다. info.misses 는 연속 횟수.
   *                      브로커가 끊겼거나, 목이 죽었거나, 서브펑션 0x80(응답 억제)를
   *                      쓰고 있을 수도 있다 — 0x80 은 원래 응답이 없는 게 정상이다.
   * kind === "negative"  NRC 가 돌아왔다. info.nrc 참조. 0x7F/0x11 이면 이 세션에서
   *                      3E 자체가 안 먹는 것이고, 0x78 은 잠시 처리 중일 뿐이다.
   *
   * 아무것도 하지 않으면 발행은 그대로 계속되고, 접힌 로그 줄에 무응답 횟수만
   * 쌓인다(현재 동작). 멈추려면 kaStop("이유") 를 부르면 된다.
   */
  var KA_MAX_MISS = 3;    // 연속 무응답 허용 횟수 (2초 주기 → 약 6초)

  function kaTrouble(kind, info) {
    if (kind === "negative") {
      var nrc = String(info.nrc || "").toUpperCase();
      if (nrc === "78") return;                  // 처리 중일 뿐 — 최종 응답이 뒤따른다
      // 이 세션에서 3E 자체가 거부된 것이라면 계속 두드려도 답이 달라지지 않는다.
      if (nrc === "11" || nrc === "12" || nrc === "7F" || nrc === "7E") {
        kaStop("세션 유지가 거부됨 (NRC " + nrc + ")");
      }
      return;
    }
    // 무응답. 서브펑션 0x80 은 응답 억제라 원래 답이 없는 게 정상이다 — 세지 않는다.
    if (/(^|\s)3E\s+80(\s|$)/i.test(kaRaw)) return;
    if (info.misses >= KA_MAX_MISS) {
      kaStop("연속 " + info.misses + "회 무응답 — 브로커·RCI 연결을 확인하세요");
    }
  }

  // 조립기(can-composer.js)·모드 스위치용 최소 표면. 전역 하나만 노출한다.
  window.RCI = {
    send: sendRaw, log: log,
    mode: function () { return mode; },
    setMode: setMode,
    keepalive: {
      start: kaStart,
      // 이유를 받는다 — 자동 시퀀스(auto-sequence.js)가 멈출 때는 '사용자 중지' 가
      // 아니라 '시퀀스 진행 중 정상 종료' 라서, 로그에 그대로 찍히면 오해가 된다.
      stop: function (reason) { kaStop(reason || "사용자 중지"); },
      on: function () { return !!kaTimer; },
      raw: function () { return kaRaw; },
      period: function () { return kaPeriod; },
    },
  };

  start();

  if (kaBadge) {
    var kaStopBtn = kaBadge.querySelector(".js-ka-stop");
    if (kaStopBtn) kaStopBtn.addEventListener("click", function () { kaStop("사용자 중지"); });
  }

  // 페이지를 넘어온 경우 남아 있는 발행 선언을 보고 이어서 띄운다 — 단, 그 발행의
  // 소유 범위가 지금 화면과 같을 때만. 다른 세부 항목으로 옮겨 왔다면 앞 코스의
  // 발행이므로 되살리지 않고 지운다(= 세션 유지 중지).
  // start() 뒤에 와야 한다 — transport 가 없으면 sendRaw 가 아무것도 못 한다.
  (function () {
    var saved = kaLoad();
    if (!saved || !saved.raw) return;
    if (saved.scope !== KA_SCOPE) {
      kaSave(null);
      kaPaint();
      log("muted", "○ 다른 세부 항목으로 이동 — 앞 항목의 세션 유지 발행을 중지했습니다"
        + " · 5초 뒤 기본 세션으로 돌아갑니다");
      return;
    }
    log("muted", "↻ 앞 단계에서 시작한 세션 유지 발행을 이어갑니다 · " + saved.raw);
    kaStart(saved.raw, saved.period);
  })();

  var input = document.getElementById("uds-req");
  Array.prototype.forEach.call(root.querySelectorAll(".js-send"), function (btn) {
    btn.addEventListener("click", function () {
      sendRaw(btn.dataset.uds || (input ? input.value : ""));
    });
  });
})();
