/* 브라우저 안의 목업 RCI 게이트웨이 — 브로커 없이 계약 응답을 만들어낸다.
 *
 * `Codes/board/mock_rci.py` 의 `build_response()` 를 그대로 이식한 것이다. 목적은
 * 브로커·게이트웨이가 안 떠 있어도 화면(작성 → 검증 → 응답 해석 → 단계 통과)이
 * 끝까지 돌아가게 하는 것 — RCI 실물과의 MQTT 왕복 테스트와 UI 작업을 분리한다.
 *
 * ⚠ 두 파일은 같은 표를 들고 있다. 한쪽 DID·Seed/Key·DTC 를 바꾸면 다른 쪽도 바꿔야
 *   목업 모드와 실 MQTT 모드의 응답이 어긋나지 않는다.
 *
 * 책임 경계는 실물과 동일하다: 게이트웨이는 raw 바이트만 만든다. 물리값 디코딩·
 * NRC 이름 매핑은 웹앱(rci-live.js) 몫이므로 여기서 하지 않는다.
 */
(function () {
  "use strict";

  // 대상·DID → 0x22 읽기 응답 데이터 바이트. 빅엔디안, int16 음수는 2의 보수.
  var DIDS = {
    urrobot: {
      "0101": "FC 7C FC AB 03 F9 FB C6 FC 7E 00 03",  // 조인트각 6축 0.1도
      "0102": "00 00 00 00 00 00 00 00 00 00 00 00",  // 조인트속도 (정지)
      "0103": "01 F4 01 EC 02 08 01 F0 01 FA 02 12",  // 조인트온도 0.1도
      "0104": "00 64 00 5A 00 78 00 46 00 50 00 3C",  // 조인트전류 mA
      "0107": "07",                  // 로봇 모드 = RUNNING
      "0108": "01",                  // 안전 모드 = NORMAL
      "0109": "01",                  // 프로그램 상태 = STOPPED
      "010A": "BB E4",               // 48100mV = 48.1V
      "010B": "03 E8",               // 1000mA
      "010F": "32",                  // 그리퍼 50%
      "0110": "01",                  // 카메라 연결됨
      "0111": "00 2A",               // 진동 RMS 42 = 0.42 m/s²
      "F199": "26 07 27",            // SW 날짜 2026-07-27
      "F195": "33 2E 31 35 2E 38",   // "3.15.8"
      "F1A0": "C0 A8 01 65",         // 로봇 IP 192.168.1.101
    },
    rccar: {
      "0101": "00 EB",               // 초음파 235mm
      "0102": "12 8E",               // 배터리 4750mV
      "0103": "00 FA",               // 온도 25.0도
      "0104": "02 49",               // 습도 58.5%RH
      "0105": "01 56",               // 조도 342 lux
      "0106": "5A",                  // 서보 90도
      "0107": "05",                  // LED bitfield (적+백)
      "0108": "00",                  // 부저 OFF
      "F199": "26 07 23",            // SW 날짜 2026-07-23
      "F195": "56 31 2E 32",         // "V1.2"
      "F1A0": "07 E0",               // 제어기 CAN ID 0x07E0
    },
  };

  // 학습용 고정 Seed/Key (실제 보안 아님).
  var SECURITY = {
    urrobot: {seed: "11 22 33 44", key: "55 66 77 88"},
    rccar: {seed: "12 34", key: "56 78"},
  };

  // DTC 읽기(0x19). statusAvailabilityMask 뒤로 [3바이트 DTC + 1바이트 상태] × n.
  var DTC_MASK = "08";               // confirmedDTC
  var DTC = {
    urrobot: "B1 00 02 08",                    // 보호정지
    rccar: "90 00 01 08 C1 01 01 08",          // 버스단선 + 초음파 이상
  };

  // 0x14 로 소거된 device. 세션 오픈(0x10)마다 초기화 — 실습을 반복할 수 있게.
  var cleared = {};

  function up(bytes) {
    return bytes.map(function (b) { return ("0" + b.toString(16).toUpperCase()).slice(-2); });
  }

  /* UDS 요청 raw → 응답 raw. 서비스별 분기는 mock_rci.py 와 1:1 대응. */
  function buildResponse(device, raw) {
    var parts = (raw || "").trim().split(/\s+/).filter(Boolean);
    if (!parts.length) return "7F 10 13";                  // 포맷 오류
    var b = [];
    for (var i = 0; i < parts.length; i++) {
      if (!/^[0-9A-Fa-f]{2}$/.test(parts[i])) return "7F 10 13";
      b.push(parseInt(parts[i], 16));
    }
    var u = up(b);
    var sid = b[0];
    var dids = DIDS[device] || {};

    if (sid === 0x10) {                                    // DiagnosticSessionControl
      delete cleared[device];                              // 새 세션 = 실습 초기화
      return "50 " + (u[1] || "01") + " 00 32 01 F4";      // P2=50ms, P2*=5000ms
    }
    if (sid === 0x3E) return "7E 00";                      // TesterPresent
    if (sid === 0x11) return "51 " + (u[1] || "01");        // ECUReset (가상)
    if (sid === 0x27) {                                     // SecurityAccess
      var sub = u[1] || "01";
      if (sub === "01") return "67 01 " + SECURITY[device].seed;
      if (sub === "02") {
        return u.slice(2).join(" ") === SECURITY[device].key ? "67 02" : "7F 27 35";
      }
      return "7F 27 12";
    }
    if (sid === 0x22) {                                     // ReadDataByIdentifier
      if (u.length < 3) return "7F 22 13";
      var data = dids[u[1] + u[2]];
      return data ? "62 " + u[1] + " " + u[2] + " " + data : "7F 22 31";
    }
    if (sid === 0x2E) {                                     // WriteDataByIdentifier
      if (u.length < 3) return "7F 2E 13";
      if (u[1] + u[2] === "F195") return "7F 2E 31";        // 쓰기 불가 항목
      return "6E " + u[1] + " " + u[2];
    }
    if (sid === 0x2F) return "6F " + u.slice(1).join(" ");   // 요청 echo
    if (sid === 0x31) return "71 " + u.slice(1).join(" ");   // 접수/결과 (단순화)
    if (sid === 0x19) {                                     // ReadDTCInformation
      var records = cleared[device] ? "" : (DTC[device] || "");
      return "59 " + (u[1] || "02") + " " + DTC_MASK + (records ? " " + records : "");
    }
    if (sid === 0x14) {                                     // ClearDiagnosticInformation
      cleared[device] = true;
      return "54";
    }
    // 리프로그래밍 3종. ECU 업그레이드 자동 시퀀스가 왕복하려면 목도 답해야 한다.
    // 블록을 저장하지는 않는다 — 카운터 흐름만 사실대로 되돌려준다.
    if (sid === 0x34) return "74 20 0F FF";                 // RequestDownload
    if (sid === 0x36) return u.length > 1 ? "76 " + u[1] : "7F 36 13";   // TransferData
    if (sid === 0x37) return "77";                          // RequestTransferExit
    return "7F " + u[0] + " 11";                            // serviceNotSupported
  }

  /* 응답 raw → 계약 페이로드 ({id, type, raw, nrc?}). */
  function toResponseMsg(id, raw) {
    var parts = raw.split(/\s+/);
    var negative = parts[0] === "7F";
    var msg = {id: id, type: negative ? "negative" : "positive", raw: raw};
    if (negative && parts.length >= 3) msg.nrc = parts[2];
    return msg;
  }

  window.MockRci = {
    buildResponse: buildResponse,
    toResponseMsg: toResponseMsg,
    // 실물 RCI 가 retained 로 올리는 생존 상태와 같은 모양.
    status: function () { return {state: "online", robot: "connected"}; },
  };
})();
