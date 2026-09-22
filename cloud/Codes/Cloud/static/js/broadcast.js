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

  function wsUrl() {
    var proto = location.protocol === "https:" ? "wss:" : "ws:";
    return proto + "//" + location.host + "/ws/broadcast";
  }

  function showSection(section) {
    [listSection, hostSection, viewSection].forEach(function (el) {
      el.hidden = el !== section;
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
    showSection(listSection);
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

  function createPeerForViewer(viewerId) {
    var pc = new RTCPeerConnection();
    peers[viewerId] = pc;
    screenStream.getTracks().forEach(function (track) {
      pc.addTrack(track, screenStream);
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
            if (pc) pc.setRemoteDescription(msg.sdp);
          } else if (msg.type === "ice") {
            var pc2 = peers[msg.viewer_id];
            if (pc2 && msg.candidate) pc2.addIceCandidate(msg.candidate);
          } else if (msg.type === "viewer_left") {
            var pc3 = peers[msg.viewer_id];
            if (pc3) {
              pc3.close();
              delete peers[msg.viewer_id];
              updateViewerCount();
            }
          }
        });
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

  function leaveView() {
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
    viewErrorEl.hidden = true;
    viewLabelEl.textContent = label || "";
    showSection(viewSection);

    viewPeer = new RTCPeerConnection();
    viewPeer.addEventListener("track", function (event) {
      videoEl.srcObject = event.streams[0];
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
        viewErrorEl.textContent = msg.message || "방송에 참여할 수 없습니다.";
        viewErrorEl.hidden = false;
      } else if (msg.type === "offer") {
        viewPeer
          .setRemoteDescription(msg.sdp)
          .then(function () {
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
          });
      } else if (msg.type === "ice") {
        if (msg.candidate) viewPeer.addIceCandidate(msg.candidate);
      } else if (msg.type === "channel_closed") {
        viewErrorEl.textContent = "방송이 종료되었습니다.";
        viewErrorEl.hidden = false;
        if (viewPeer) {
          viewPeer.close();
          viewPeer = null;
        }
        setTimeout(leaveView, 1500);
      }
    });
  }

  backBtn.addEventListener("click", leaveView);
})();
