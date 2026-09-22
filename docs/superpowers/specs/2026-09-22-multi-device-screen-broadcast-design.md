# 화면 실시간 송출(멀티 채널 브로드캐스트) 설계

## 개요

`cloud/Codes/Cloud` 진단 교육 플랫폼에 "강사 화면 실시간 공유" 기능을 추가한다.
여러 강사(마스터) PC가 각자 독립된 채널을 동시에 열어 자기 화면을 학생 노트북에
실시간으로 공유할 수 있고, 학생은 `/broadcast` 페이지에서 현재 생방송 중인
채널 목록을 보고 원하는 채널에 참여한다.

## 범위

- 화면(비디오)만 송출한다. 음성(마이크/시스템 오디오)은 다루지 않는다.
- 같은 교실/사내망(LAN) 접속을 전제로 한다. 외부 인터넷 경유 접속은 다루지 않는다.
- 채널당 학생 10대 이하를 기준으로 설계한다.
- 인증/권한 체계는 두지 않는다(로컬망 신뢰 전제 — 기존 플랫폼도 로그인이 없다).
- WS 재연결, TURN 서버, 녹화/재생 기능은 이번 범위에 넣지 않는다.

## 아키텍처

**WebRTC 메시(mesh) 구조 + FastAPI WebSocket 시그널링.**

마스터가 브라우저의 `getDisplayMedia()`로 화면을 캡처하고, 참여한 학생 노트북마다
별도의 `RTCPeerConnection`을 맺어 영상을 P2P로 직접 전송한다. FastAPI에 새
WebSocket 엔드포인트(`/ws/broadcast`)를 추가해 SDP offer/answer와 ICE candidate만
중계하는 "시그널링" 역할을 하고, 실제 영상 데이터는 서버를 거치지 않는다. 같은
LAN이므로 STUN/TURN 서버 없이 로컬(host) ICE candidate만으로 연결된다.

### 검토했으나 제외한 대안

- **서버 중계 MJPEG 스트리밍**: 마스터가 캔버스에서 프레임을 JPEG로 캡처해
  서버에 올리고, 서버가 모든 학생 WebSocket에 그대로 뿌리는 방식. 프로토콜은
  단순하지만 서버 대역폭·지연이 채널·학생 수에 비례해 늘고 화질/프레임레이트가
  떨어진다.
- **기존 MQTT 브로커로 프레임 전달**: 이미 UR3/RC카 진단 트래픽이 오가는
  mosquitto 브로커에 무거운 영상 프레임을 얹는 방식. UDS 진단은 지연시간에
  민감한데, 영상 데이터가 같은 브로커를 타면 그 지연시간에 영향을 줄 위험이 있어
  제외했다.

메시 구조의 대역폭 부담(마스터 업로드 × 채널당 학생 수)은 "채널당 10대 이하 ·
같은 LAN(기가비트)"이라는 조건에서는 문제되지 않는다.

## 컴포넌트 & 데이터 흐름

### 서버 — 채널 레지스트리 (프로세스 메모리)

`main.py`에 이미 있는 `MqttBridge`처럼 프로세스 메모리에 상태를 둔다(별도 DB
불필요 — 서버 재시작 시 방송도 함께 끊기는 게 자연스럽다).

```python
channels: dict[str, Channel]  # channel_id(uuid) -> Channel

class Channel:
    label: str                          # 강사가 입력한 채널 이름
    master_ws: WebSocket
    viewers: dict[str, WebSocket]       # viewer_id(uuid) -> WebSocket
    created_at: datetime
```

### WebSocket 엔드포인트 — `/ws/broadcast`

마스터·학생·목록 구독자가 모두 같은 엔드포인트에 붙되, 첫 메시지로 역할을
선언한다. 메시지는 JSON, 서버는 채널 상태 변화와 SDP/ICE 페이로드를 그대로
중계만 한다(내용을 해석하지 않음).

**클라이언트 → 서버**

| type | 필드 | 보내는 쪽 | 의미 |
|------|------|-----------|------|
| `create` | `label` | 마스터 | 채널 생성 요청 |
| `list` | - | 뷰어(목록 화면) | 현재 채널 목록 요청 + 이후 변경사항 구독 |
| `join` | `channel_id` | 뷰어 | 채널 참여 요청 |
| `offer` | `channel_id`, `viewer_id`, `sdp` | 마스터 | 특정 뷰어에게 보낼 offer |
| `answer` | `channel_id`, `sdp` | 뷰어 | offer에 대한 answer |
| `ice` | `channel_id`, `viewer_id?`, `candidate` | 마스터/뷰어 | ICE candidate 교환 (마스터는 viewer_id로 대상 지정) |
| `close` | `channel_id` | 마스터 | 방송 종료(명시적) |

**서버 → 클라이언트**

| type | 필드 | 받는 쪽 | 의미 |
|------|------|---------|------|
| `created` | `channel_id` | 마스터 | 채널 생성 완료, id 발급 |
| `channel_list` | `channels: [{channel_id, label}]` | 목록 구독자 | 전체 목록(초기 응답 + 변경시마다) |
| `viewer_joined` | `viewer_id` | 마스터 | 새 뷰어 입장 → offer 생성 트리거 |
| `offer` | `sdp` | 뷰어 | 마스터가 보낸 offer 전달 |
| `answer` | `viewer_id`, `sdp` | 마스터 | 뷰어가 보낸 answer 전달 |
| `ice` | `viewer_id?`, `candidate` | 마스터/뷰어 | ICE candidate 전달 |
| `channel_closed` | `channel_id` | 뷰어 | 방송 종료 알림 |
| `error` | `message` | 요청자 | 존재하지 않는 채널 참여 등 |

### 채널 수명주기

1. 강사가 "방송 시작" → 채널 이름 입력 → WS 연결 → `create` 전송 → 서버가
   `channel_id`(uuid) 발급 후 `created` 응답, 목록 구독자들에게 `channel_list` 갱신 푸시
2. 학생이 목록에서 채널 클릭 → WS 연결(또는 기존 연결 재사용) → `join` 전송 →
   서버가 마스터에게 `viewer_joined` 전달
3. 마스터가 해당 뷰어용 `RTCPeerConnection` 생성 → offer 생성 → `offer` 전송(서버
   경유) → 뷰어가 answer 생성 → `answer` 전송(서버 경유) → 양쪽 ICE candidate
   교환(`ice`) → P2P 영상 시작
4. 마스터 WS 연결 종료(탭 닫기, 명시적 `close` 등) → 서버가 채널 제거, 모든
   뷰어에게 `channel_closed` 전송 → 뷰어는 PeerConnection 정리 후 목록 화면으로 복귀
5. 학생 WS 연결 종료 → 서버가 해당 채널의 viewer 항목만 제거 → 마스터에게 알려
   해당 PeerConnection만 정리(다른 뷰어에는 영향 없음)

### UI — `/broadcast` (신규 독립 페이지, target 구분과 무관)

- **목록/시청 모드(기본 진입 화면)**: 생방송 중인 채널을 카드로 나열(강사가 입력한
  이름 표시). WS로 `list` 구독을 유지해 채널이 열리고 닫히는 것을 실시간 반영한다.
  카드 클릭 → 해당 채널 시청 화면으로 전환, `<video>` 엘리먼트에 수신 스트림을 붙인다.
- **방송 시작 모드**: "화면 공유 시작" 버튼 → 채널 이름 입력 → 브라우저 화면 선택
  프롬프트(`getDisplayMedia`) → 송출 시작. 송출 중에는 "방송 종료" 버튼과 현재
  참여 중인 학생 수를 보여준다.

기존 페이지 라우팅(`/{target}/{content}`)과 독립적이므로 `main.py`에 `/broadcast`
GET 라우트 하나와 `templates/broadcast.html` 템플릿 하나를 추가하고, 전용 JS는
`static/js/broadcast.js`로 분리한다(기존 코드베이스가 화면별로 JS 파일을 나누는
패턴을 따른다).

## 에러 처리

- `getDisplayMedia()`를 지원하지 않거나 사용자가 화면 선택을 취소한 경우: 안내
  메시지를 보여주고 방송 시작 모드로 되돌린다.
- 학생이 참여를 시도했는데 이미 종료된 채널(목록 갱신 전 클릭 등)이면 서버가
  `error` 응답 → "방송이 종료되었습니다" 표시 후 목록 화면으로 복귀.
- WS 연결이 끊기면 재연결을 시도하지 않는다. 학생 쪽은 목록 화면으로 돌아가 다시
  선택하게 한다 — 이 규모(로컬 LAN, 10대 이하)에서 재연결 로직까지 넣는 것은
  과하다.

## 테스트 전략

- **자동 테스트**: 시그널링 상태 전이 위주 — 채널 생성/목록 조회/제거, 뷰어
  추가/제거, 마스터 종료 시 전체 뷰어에게 `channel_closed`가 가는지. FastAPI
  `TestClient`의 WebSocket 테스트로 검증한다.
- **수동 확인**: 실제 WebRTC 영상 송출은 자동화하지 않고, 브라우저 2개(또는 탭
  2개)로 마스터/학생 역할을 직접 실행해 화면이 정상 수신되는지, 마스터 종료 시
  학생 화면이 정리되는지, 채널 2개를 동시에 띄워 목록·참여가 서로 간섭하지
  않는지 확인한다.
