/* 화면 실시간 송출 — 강사(마스터) 시연 화면을 학생 노트북에 WebRTC로 공유.
 *
 * 서버(/ws/broadcast)는 SDP/ICE 를 그대로 중계만 한다 — 영상은 P2P 로 흐른다.
 * 프로토콜은 docs/superpowers/specs/2026-09-22-multi-device-screen-broadcast-design.md
 * 와 그 계획 문서(Global Constraints)의 viewer_left 보충을 따른다.
 */
(function () {
  "use strict";

  var root = document.querySelector("[data-broadcast]");
  if (!root) return;

  var listSection = root.querySelector("[data-broadcast-list]");
  var hostSection = root.querySelector("[data-broadcast-host]");
  var viewSection = root.querySelector("[data-broadcast-view]");

  var channelsEl = root.querySelector("[data-broadcast-channels]");
  var emptyEl = root.querySelector("[data-broadcast-empty]");
  var startModeBtn = root.querySelector("[data-broadcast-start-mode]");

  var labelInput = root.querySelector("[data-broadcast-label]");
  var goLiveBtn = root.querySelector("[data-broadcast-go-live]");
  var cancelHostBtn = root.querySelector("[data-broadcast-cancel-host]");
  var liveEl = root.querySelector("[data-broadcast-live]");
  var viewerCountEl = root.querySelector("[data-broadcast-viewer-count]");
  var stopBtn = root.querySelector("[data-broadcast-stop]");
  var hostErrorEl = root.querySelector("[data-broadcast-host-error]");

  var backBtn = root.querySelector("[data-broadcast-back]");
  var viewLabelEl = root.querySelector("[data-broadcast-view-label]");
  var videoEl = root.querySelector("[data-broadcast-video]");
  var viewErrorEl = root.querySelector("[data-broadcast-view-error]");
  var fullscreenBtn = root.querySelector("[data-broadcast-fullscreen]");

  function wsUrl() {
    var proto = location.protocol === "https:" ? "wss:" : "ws:";
    return proto + "//" + location.host + "/ws/broadcast";
  }

  function showSection(section) {
    [listSection, hostSection, viewSection].forEach(function (el) {
      el.hidden = el !== section;
    });
  }

  /* ---- ICE 후보 버퍼링 ----
   * STUN/TURN 이 없는 LAN 전용 설계라, host candidate 들이 setLocalDescription
   * 직후 한꺼번에 도착한다 — 이게 하필 상대쪽 setRemoteDescription(비동기) 이
   * 아직 안 끝난 타이밍과 겹치기 쉽다. 그러면 addIceCandidate 가
   * InvalidStateError 로 실패해 후보가 조용히 사라진다. 그래서 원격 설명이
   * 준비되기 전에 온 후보는 일단 버퍼에 쌓아 뒀다가, 준비되는 즉시 흘려보낸다. */
  function bufferOrAddIce(pc, candidate) {
    if (!pc || !candidate) return;
    if (pc._broadcastRemoteReady) {
      pc.addIceCandidate(candidate).catch(function (e) {
        console.error("broadcast: ICE 후보 추가 실패", e);
      });
    } else {
      pc._broadcastIceBuffer.push(candidate);
    }
  }

  function markRemoteReady(pc) {
    pc._broadcastRemoteReady = true;
    var buffered = pc._broadcastIceBuffer;
    pc._broadcastIceBuffer = [];
    buffered.forEach(function (candidate) {
      pc.addIceCandidate(candidate).catch(function (e) {
        console.error("broadcast: ICE 후보 추가 실패", e);
      });
    });
  }

  /* ---- 목록 모드 — 페이지 진입 즉시 연결해 생방송 목록을 구독한다 ---- */

  var listSocket = null;

  function renderChannels(channels) {
    channelsEl.innerHTML = "";
    emptyEl.hidden = channels.length > 0;
    channels.forEach(function (ch) {
      var li = document.createElement("li");
      li.className = "broadcast__channel";
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "broadcast__channel-btn";
      btn.textContent = ch.label || "(이름 없음)";
      btn.addEventListener("click", function () {
        joinChannel(ch.channel_id, ch.label);
      });
      li.appendChild(btn);
      channelsEl.appendChild(li);
    });
  }

  function connectList() {
    if (listSocket) return;
    listSocket = new WebSocket(wsUrl());
    listSocket.addEventListener("open", function () {
      listSocket.send(JSON.stringify({ type: "list" }));
    });
    listSocket.addEventListener("message", function (event) {
      var msg = JSON.parse(event.data);
      if (msg.type === "channel_list") renderChannels(msg.channels || []);
    });
    listSocket.addEventListener("close", function () {
      // 재연결 로직은 설계 제약으로 두지 않는다 — 목록 구독이 끊겼다는 사실만
      // 콘솔에 남겨 조용히 죽지 않게 한다.
      console.warn("broadcast: 목록 소켓 연결이 끊겼습니다(재연결하지 않음)");
    });
  }

  connectList();

  /* ---- 방송 시작 모드 (마스터) ---- */

  var hostSocket = null;
  var hostChannelId = null;
  var screenStream = null;
  var peers = {}; // viewer_id -> RTCPeerConnection

  startModeBtn.addEventListener("click", function () {
    labelInput.value = "";
    liveEl.hidden = true;
    hostErrorEl.hidden = true;
    showSection(hostSection);
  });

  cancelHostBtn.addEventListener("click", function () {
    // 이미 방송 중(hostSocket 있음)일 때는 화면 공유·소켓·채널을 그대로 둔 채
    // 목록으로만 돌아가면 화면 캡처와 유령 채널이 남는다 — 방송을 실제로
    // 종료시킨 뒤 돌아간다.
    if (hostSocket) {
      stopBroadcast();
    } else {
      showSection(listSection);
    }
  });

  function updateViewerCount() {
    viewerCountEl.textContent = String(Object.keys(peers).length);
  }

  function closeAllPeers() {
    Object.keys(peers).forEach(function (vid) {
      peers[vid].close();
    });
    peers = {};
    updateViewerCount();
  }

  function stopBroadcast() {
    if (hostSocket && hostChannelId) {
      try {
        hostSocket.send(JSON.stringify({ type: "close", channel_id: hostChannelId }));
      } catch (e) {
        /* 이미 끊긴 경우 무시 */
      }
    }
    closeAllPeers();
    if (screenStream) {
      screenStream.getTracks().forEach(function (t) {
        t.stop();
      });
      screenStream = null;
    }
    if (hostSocket) {
      hostSocket.close();
      hostSocket = null;
    }
    hostChannelId = null;
    showSection(listSection);
  }

  function dropFailedPeer(viewerId) {
    // viewer_left 와 같은 정리 — peers 에서 빠져야 updateViewerCount() 가 "실제로
    // 붙어 있는 시청자 수"를 보여준다(그냥 "peer 를 만들어 본 횟수"가 아니라).
    var pc = peers[viewerId];
    if (!pc) return;
    pc.close();
    delete peers[viewerId];
    updateViewerCount();
  }

  function createPeerForViewer(viewerId) {
    var pc = new RTCPeerConnection();
    pc._broadcastRemoteReady = false; // answer 의 setRemoteDescription 완료 전
    pc._broadcastIceBuffer = [];
    peers[viewerId] = pc;
    screenStream.getTracks().forEach(function (track) {
      pc.addTrack(track, screenStream);
    });
    // 연결이 끊기거나 아예 붙지 못하면(방화벽·AP 클라이언트 격리·VLAN 분리 등 같은
    // LAN 에서도 흔하다) 조용히 죽은 채로 "N명 시청 중"에 잡혀 있지 않도록 정리한다.
    // 재연결 로직은 두지 않는다(설계 제약) — 순수히 집계를 실제와 맞추는 목적이다.
    pc.addEventListener("connectionstatechange", function () {
      if (pc.connectionState === "failed" || pc.connectionState === "disconnected") {
        dropFailedPeer(viewerId);
      }
    });
    pc.addEventListener("icecandidate", function (event) {
      if (event.candidate) {
        hostSocket.send(
          JSON.stringify({
            type: "ice",
            channel_id: hostChannelId,
            viewer_id: viewerId,
            candidate: event.candidate,
          })
        );
      }
    });
    pc.createOffer()
      .then(function (offer) {
        return pc.setLocalDescription(offer);
      })
      .then(function () {
        hostSocket.send(
          JSON.stringify({
            type: "offer",
            channel_id: hostChannelId,
            viewer_id: viewerId,
            sdp: pc.localDescription,
          })
        );
      });
    updateViewerCount();
    return pc;
  }

  goLiveBtn.addEventListener("click", function () {
    if (hostSocket) return; // 이미 방송 중 — 중복 클릭으로 스트림/소켓을 덮어쓰지 않는다.
    hostErrorEl.hidden = true;
    if (!navigator.mediaDevices || !navigator.mediaDevices.getDisplayMedia) {
      hostErrorEl.textContent = "이 브라우저는 화면 공유를 지원하지 않습니다.";
      hostErrorEl.hidden = false;
      return;
    }
    navigator.mediaDevices
      .getDisplayMedia({ video: true })
      .then(function (stream) {
        screenStream = stream;
        screenStream.getVideoTracks()[0].addEventListener("ended", stopBroadcast);

        hostSocket = new WebSocket(wsUrl());
        hostSocket.addEventListener("open", function () {
          hostSocket.send(
            JSON.stringify({
              type: "create",
              label: labelInput.value.trim() || "이름 없는 방송",
            })
          );
        });
        hostSocket.addEventListener("message", function (event) {
          var msg = JSON.parse(event.data);
          if (msg.type === "created") {
            hostChannelId = msg.channel_id;
            liveEl.hidden = false;
            updateViewerCount();
          } else if (msg.type === "viewer_joined") {
            createPeerForViewer(msg.viewer_id);
          } else if (msg.type === "answer") {
            var pc = peers[msg.viewer_id];
            if (pc) {
              pc.setRemoteDescription(msg.sdp)
                .then(function () {
                  markRemoteReady(pc);
                })
                .catch(function (e) {
                  console.error("broadcast: answer setRemoteDescription 실패", e);
                });
            }
          } else if (msg.type === "ice") {
            var pc2 = peers[msg.viewer_id];
            if (pc2) bufferOrAddIce(pc2, msg.candidate);
          } else if (msg.type === "viewer_left") {
            var pc3 = peers[msg.viewer_id];
            if (pc3) {
              pc3.close();
              delete peers[msg.viewer_id];
              updateViewerCount();
            }
          } else if (msg.type === "error") {
            // 서버가 무언가를 거부했을 때(예: 상한 offer/viewer_id) 마스터가 알 수
            // 있는 유일한 경로 — 그냥 무시되면 방송자는 이유를 알 길이 없다.
            hostErrorEl.textContent = msg.message || "오류가 발생했습니다.";
            hostErrorEl.hidden = false;
          }
        });
        // 서버 재시작 등으로 소켓이 끊기면 재연결하지 않고(설계 제약) 목록으로
        // 돌아간다 — 화면 캡처를 계속 붙잡고 있거나 죽은 상태로 "N명 시청 중"을
        // 계속 보여주지 않도록 한다. stopBroadcast 는 이미 닫힌 소켓/빈 peers
        // 에 대해서도 안전하게 다시 호출할 수 있다(각 단계가 null 가드로 감싸짐).
        hostSocket.addEventListener("close", stopBroadcast);
      })
      .catch(function () {
        hostErrorEl.textContent = "화면 공유가 취소되었거나 권한이 거부되었습니다.";
        hostErrorEl.hidden = false;
      });
  });

  stopBtn.addEventListener("click", stopBroadcast);

  /* ---- 시청 모드 (뷰어) ---- */

  var viewSocket = null;
  var viewPeer = null;
  var viewCloseTimer = null; // channel_closed/error 이후 자동 복귀 타이머(취소 가능해야 함)

  function leaveView() {
    if (viewCloseTimer) {
      clearTimeout(viewCloseTimer);
      viewCloseTimer = null;
    }
    if (viewPeer) {
      viewPeer.close();
      viewPeer = null;
    }
    if (viewSocket) {
      viewSocket.close();
      viewSocket = null;
    }
    videoEl.srcObject = null;
    showSection(listSection);
  }

  function joinChannel(channelId, label) {
    // 직전 채널에서 예약돼 있던 자동 복귀 타이머가 새 세션에 대해 잘못
    // 발동하지 않도록 먼저 지운다(Finding 4).
    if (viewCloseTimer) {
      clearTimeout(viewCloseTimer);
      viewCloseTimer = null;
    }
    viewErrorEl.hidden = true;
    viewLabelEl.textContent = label || "";
    showSection(viewSection);

    viewPeer = new RTCPeerConnection();
    viewPeer._broadcastRemoteReady = false; // offer 의 setRemoteDescription 완료 전
    viewPeer._broadcastIceBuffer = [];
    viewPeer.addEventListener("track", function (event) {
      videoEl.srcObject = event.streams[0];
    });
    // 연결이 실패/단절되면(방화벽·AP 클라이언트 격리·VLAN 분리 등) 학생 화면에는
    // 그냥 멈춘 검은 <video> 만 남는다 — 이유를 알려주기만 한다(재연결 로직은 설계
    // 제약으로 두지 않는다). channel_closed 와 달리 자동으로 목록에 복귀시키지는
    // 않는다: 서버가 아니라 P2P 경로 문제라 방송 자체는 계속 살아 있을 수 있다.
    // pc 를 클로저로 고정해 둔다 — 이 사이에 leaveView/joinChannel 이 다시 불려
    // viewPeer 가 다른(또는 null) 값으로 바뀌어도, 이 리스너는 자신이 붙은 그 피어
    // 연결의 상태만 본다.
    var thisPeer = viewPeer;
    thisPeer.addEventListener("connectionstatechange", function () {
      if (viewPeer !== thisPeer) return; // 이미 떠났거나 다른 채널로 교체됨
      var state = thisPeer.connectionState;
      if (state === "failed" || state === "disconnected") {
        viewErrorEl.textContent = "연결이 원활하지 않습니다. 네트워크 상태를 확인해 주세요.";
        viewErrorEl.hidden = false;
      }
    });
    viewPeer.addEventListener("icecandidate", function (event) {
      if (event.candidate && viewSocket) {
        viewSocket.send(
          JSON.stringify({ type: "ice", channel_id: channelId, candidate: event.candidate })
        );
      }
    });

    viewSocket = new WebSocket(wsUrl());
    viewSocket.addEventListener("open", function () {
      viewSocket.send(JSON.stringify({ type: "join", channel_id: channelId }));
    });
    viewSocket.addEventListener("message", function (event) {
      var msg = JSON.parse(event.data);
      if (msg.type === "error") {
        // 목록에 뜬 뒤 클릭 전에 방송이 끝났을 수 있다(join 실패) — 메시지만
        // 보여주고 방치하지 않고 channel_closed 와 같은 방식으로 목록에
        // 자동 복귀한다(Finding 5).
        viewErrorEl.textContent = msg.message || "방송에 참여할 수 없습니다.";
        viewErrorEl.hidden = false;
        if (viewCloseTimer) clearTimeout(viewCloseTimer);
        viewCloseTimer = setTimeout(leaveView, 1500);
      } else if (msg.type === "offer") {
        viewPeer
          .setRemoteDescription(msg.sdp)
          .then(function () {
            markRemoteReady(viewPeer);
            return viewPeer.createAnswer();
          })
          .then(function (answer) {
            return viewPeer.setLocalDescription(answer);
          })
          .then(function () {
            viewSocket.send(
              JSON.stringify({
                type: "answer",
                channel_id: channelId,
                sdp: viewPeer.localDescription,
              })
            );
          })
          .catch(function (e) {
            console.error("broadcast: offer 처리 실패", e);
          });
      } else if (msg.type === "ice") {
        bufferOrAddIce(viewPeer, msg.candidate);
      } else if (msg.type === "channel_closed") {
        viewErrorEl.textContent = "방송이 종료되었습니다.";
        viewErrorEl.hidden = false;
        if (viewPeer) {
          viewPeer.close();
          viewPeer = null;
        }
        if (viewCloseTimer) clearTimeout(viewCloseTimer);
        viewCloseTimer = setTimeout(leaveView, 1500);
      }
    });
    // 서버 재시작 등으로 소켓이 끊기면 재연결하지 않고(설계 제약) 목록으로
    // 돌아간다 — 멈춘 <video> 앞에 방치되지 않도록 한다. leaveView 는 이미
    // 닫힌 소켓/피어에 대해서도 안전하게 다시 호출할 수 있다.
    viewSocket.addEventListener("close", leaveView);
  }

  backBtn.addEventListener("click", leaveView);

  fullscreenBtn.addEventListener("click", function () {
    if (videoEl.requestFullscreen) {
      videoEl.requestFullscreen();
    }
  });
})();
