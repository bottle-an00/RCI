# UR3 RCI MQTT 계층 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `ur3/docs/UR3_RCI_기능명세서.md` §4(MQTT 인터페이스, 확정)를 만족하는 MQTT 클라이언트·페이로드·핸들러를 구현한다. UDS 디스패치(SID 라우팅)는 이 계획의 범위 밖이며, 나중에 이 계층 위에 얹는다.

**Architecture:** `shared/mqtt_client.py`의 `MQTTClient`를 확장해 QoS/retained/LWT/재연결/연결-전-구독 문제를 고친다. UR3 고유의 진단 페이로드(hex 인코딩, positive/negative 판별, 에러/상태 스키마)는 `ur3/uds_payload.py`에 순수 함수로 둔다. 둘을 엮는 `ur3/mqtt_handler.py`가 사양서 §4.1 토픽에 맞춰 구독/발행하고, 향후 UDS 디스패처가 꽂을 콜백 확장점(`on_request`)만 남겨둔다.

**Tech Stack:** Python 3.12, `paho-mqtt==2.1.0`, `pytest`, `unittest.mock`(가짜 브로커 — 실제 브로커 연결 없이 `paho.mqtt.client.Client`를 모의 대체).

## Global Constraints

- 토픽은 `ur3/docs/UR3_RCI_기능명세서.md` §4.1의 `minigit/...` 체계를 그대로 쓴다. `shared/topics.py`의 기존 `UR3_CMD`/`UR3_STATUS`(`rci/ur3/*`)는 **건드리지 않는다** — 이름 통합은 팀 합의 보류 사항이다.
- 모든 UR3 진단 토픽은 QoS **1**. `minigit/status/rci-ur`만 Retained **Y** + LWT. 나머지(`req`/`resp`/`error`)는 Retained **N**.
- hex 표기: 대문자, 바이트 공백 구분, `0x` 없음 (예: `"22 01 07"`). §4.5.
- `type` 판별: raw 첫 바이트가 `0x7F`면 `negative`, 그 외 `positive`. §4.5.
- `reason`은 `{"robot_unreachable", "dashboard_error", "internal_error"}` 중 하나만 허용. §4.4.
- `robot` 상태는 `{"connected", "disconnected"}` 중 하나만 허용. §4.4.
- 물리값 디코딩·NRC 이름 매핑은 웹앱 담당이다. RCI(이 계층)는 raw 바이트만 다룬다 — 절대 디코딩하지 않는다. §4.5.
- `paho-mqtt`는 `==2.1.0`으로 고정한다(상한 없는 `>=`가 있으면 2.x 미달 버전이 깔려 `CallbackAPIVersion` 관련 동작이 달라질 수 있다).
- `paho-mqtt` 2.1.0에서 `mqtt.Client()`의 `callback_api_version` 기본값은 `CallbackAPIVersion.VERSION1`이다 — 명시적으로 `CallbackAPIVersion.VERSION2`를 넘기지 않으면 이 계획의 콜백 시그니처와 어긋난다.
- 이 계획은 실제 MQTT 브로커에 연결하지 않는다. 모든 테스트는 `unittest.mock`으로 `paho.mqtt.client.Client`를 대체한 가짜 브로커로 검증한다.
- UDS SID 디스패치, 세션/보안/DTC, RTDE/Dashboard/그리퍼 링크는 이 계획의 범위 밖이다.

---

### Task 1: 의존성 고정 (`ur3/requirements.txt`)

**Files:**
- Modify: `ur3/requirements.txt`

**Interfaces:**
- Consumes: 없음
- Produces: 설치된 `paho-mqtt==2.1.0` 패키지 — 이후 모든 태스크의 테스트가 이 패키지에 의존한다.

- [ ] **Step 1: `ur3/requirements.txt`를 아래 내용으로 교체**

```
ur_rtde>=1.5.0,<1.7.0
paho-mqtt==2.1.0
```

- [ ] **Step 2: 설치**

Run: `python -m pip install -r ur3/requirements.txt`
Expected: `paho-mqtt-2.1.0`과 `ur_rtde`(1.5.x~1.6.x 범위)가 설치됨. 라즈베리파이 4(aarch64)용 `ur_rtde` wheel 유무는 이 태스크의 범위 밖이며 별도 확인 대상이다(설계서 미결 항목).

- [ ] **Step 3: 설치 확인**

Run: `python -c "import paho.mqtt.client as m; print(m.CallbackAPIVersion.VERSION2)"`
Expected: `CallbackAPIVersion.VERSION2` 출력 (에러 없이 import 성공)

- [ ] **Step 4: 커밋**

```bash
git add ur3/requirements.txt
git commit -m "chore(ur3): paho-mqtt 2.1.0 고정, ur_rtde 상한 추가"
```

---

### Task 2: 테스트 인프라 (`tests/conftest.py`)

리포지토리에 `tests/` 디렉토리와 pytest 설정이 없다. 네임스페이스 패키지(`shared`, `ur3`)를 테스트에서 import하려면 리포지토리 루트를 `sys.path`에 넣어야 한다 — `integration/test_integration.py`가 쓰는 것과 같은 방식을 `conftest.py`로 한 번만 처리한다.

**Files:**
- Create: `tests/conftest.py`
- Create: `tests/__init__.py` (빈 파일 — pytest가 `tests/shared`와 `tests/ur3`를 별개 최상위 패키지로 취급해 이름이 충돌하지 않게 함)

**Interfaces:**
- Consumes: 없음
- Produces: 리포지토리 루트가 `sys.path`에 포함된 상태 — 이후 모든 테스트 태스크가 `import shared.mqtt_client`, `import ur3.uds_payload` 등을 바로 쓸 수 있다.

- [ ] **Step 1: `tests/__init__.py` 생성 (빈 파일)**

```python
```

- [ ] **Step 2: `tests/conftest.py` 작성**

```python
"""pytest가 리포지토리 루트를 sys.path에 포함시키도록 한다.

shared/, ur3/ 에는 __init__.py가 없는 네임스페이스 패키지이므로,
`import shared.mqtt_client` 형태가 동작하려면 리포지토리 루트가
sys.path에 있어야 한다. integration/test_integration.py가 쓰는
sys.path.append 트릭을 테스트 전체에 한 번만 적용한다.
"""
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
```

- [ ] **Step 3: 확인용 스모크 테스트로 동작 검증**

Run: `python -m pytest --collect-only tests/ -q`
Expected: `no tests ran` 또는 `0 tests collected` (에러 없이 수집 단계 통과. 아직 테스트 파일이 없으므로 0개가 정상)

- [ ] **Step 4: 커밋**

```bash
git add tests/__init__.py tests/conftest.py
git commit -m "test: pytest 루트 경로 설정 추가"
```

---

### Task 3: `shared/mqtt_client.py` 확장 — paho 2.x 호환 + QoS/Retain

**Files:**
- Modify: `shared/mqtt_client.py`
- Create: `tests/shared/__init__.py` (빈 파일 — `tests/ur3/__init__.py`와 대칭을 맞춰 두 서브패키지 모두 `tests.<part>.test_*` 형태로 수집되게 한다)
- Test: `tests/shared/test_mqtt_client.py`

**Interfaces:**
- Consumes: `paho.mqtt.client`(외부 패키지, Task 1에서 설치)
- Produces:
  - `MQTTClient.__init__(self, client_id: str, broker_host: str = "localhost", broker_port: int = 1883, will_topic: str | None = None, will_payload: str | None = None, will_qos: int = 1, will_retain: bool = True)`
  - `MQTTClient.connect(self) -> None`
  - `MQTTClient.disconnect(self) -> None`
  - `MQTTClient.publish(self, topic: str, payload: str, qos: int = 0, retain: bool = False) -> None`
  - `MQTTClient.subscribe(self, topic: str, callback=None, qos: int = 1) -> None`
  - 이 4개 메서드 시그니처를 이후 태스크(4, 5)가 그대로 소비한다.

**배경 — 고치는 결함 3가지:**
1. `mqtt.Client(client_id=client_id)`가 paho 2.x에서 `callback_api_version` 필수 인자 없이 호출되면 동작이 달라진다 → `CallbackAPIVersion.VERSION2`를 명시.
2. `publish()`에 `qos`/`retain` 인자가 없다 → 추가.
3. `subscribe()`가 `connect()` 이전에 호출되면 실제 구독이 일어나지 않는다(`integration/test_integration.py:22-23`가 정확히 이 순서) → 구독 요청을 큐에 쌓아두고, 연결 성공(`on_connect`) 시점에 일괄 구독하도록 바꾼다.

- [ ] **Step 1: `tests/shared/__init__.py` 생성 (빈 파일)**

```python
```

- [ ] **Step 2: 실패하는 테스트 작성 — `Client()`가 `CallbackAPIVersion.VERSION2`로 생성되는지**

`tests/shared/test_mqtt_client.py` 새로 작성:

```python
"""shared.mqtt_client.MQTTClient 단위 테스트. 실제 브로커 없이
paho.mqtt.client.Client를 모의 대체(가짜 브로커)해서 검증한다."""
from unittest.mock import MagicMock, patch

import paho.mqtt.client as mqtt

from shared.mqtt_client import MQTTClient


def _make_client_with_mock():
    """MQTTClient를 만들고, 내부에서 생성된 mock Client 인스턴스를 함께 반환한다."""
    with patch("shared.mqtt_client.mqtt.Client") as mock_client_cls:
        mock_instance = MagicMock()
        mock_instance.is_connected.return_value = False
        mock_client_cls.return_value = mock_instance
        client = MQTTClient("test-client")
        return client, mock_client_cls, mock_instance


def test_uses_callback_api_version_2():
    client, mock_client_cls, _ = _make_client_with_mock()

    _, kwargs = mock_client_cls.call_args
    assert kwargs.get("callback_api_version") == mqtt.CallbackAPIVersion.VERSION2
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `python -m pytest tests/shared/test_mqtt_client.py::test_uses_callback_api_version_2 -v`
Expected: `FAIL` — `shared.mqtt_client`에 `mqtt`가 없거나 `client_id=`만 넘기고 `callback_api_version`을 넘기지 않아 `kwargs.get(...)`이 `None`이라 assert 실패

- [ ] **Step 4: `shared/mqtt_client.py`를 아래로 전체 교체**

```python
"""공통 MQTT 클라이언트 래퍼."""
import paho.mqtt.client as mqtt


class MQTTClient:
    def __init__(
        self,
        client_id: str,
        broker_host: str = "localhost",
        broker_port: int = 1883,
        will_topic: str | None = None,
        will_payload: str | None = None,
        will_qos: int = 1,
        will_retain: bool = True,
    ):
        self._broker_host = broker_host
        self._broker_port = broker_port
        self._subscriptions = []  # list[tuple[str, int, callable | None]] — connect() 전 구독 요청 큐

        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
        )
        self._client.on_connect = self._on_connect
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)

        if will_topic is not None:
            self._client.will_set(
                will_topic, payload=will_payload, qos=will_qos, retain=will_retain
            )

    def _on_connect(self, client, userdata, connect_flags, reason_code, properties):
        """연결(또는 재연결) 성공 시 큐에 쌓인 구독을 전부 적용한다.

        connect() 이전에 subscribe()가 호출돼도 실제 구독이 누락되지 않게 하기 위함이다.
        """
        for topic, qos, callback in self._subscriptions:
            self._client.subscribe(topic, qos=qos)
            if callback is not None:
                self._client.message_callback_add(topic, callback)

    def connect(self):
        self._client.connect(self._broker_host, self._broker_port)
        self._client.loop_start()

    def disconnect(self):
        self._client.loop_stop()
        self._client.disconnect()

    def publish(self, topic: str, payload: str, qos: int = 0, retain: bool = False):
        return self._client.publish(topic, payload, qos=qos, retain=retain)

    def subscribe(self, topic: str, callback=None, qos: int = 1):
        """구독을 등록한다. 아직 연결되지 않았으면 큐에 쌓아두고 connect() 성공 시 적용한다."""
        self._subscriptions.append((topic, qos, callback))
        if self._client.is_connected():
            self._client.subscribe(topic, qos=qos)
            if callback is not None:
                self._client.message_callback_add(topic, callback)
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `python -m pytest tests/shared/test_mqtt_client.py::test_uses_callback_api_version_2 -v`
Expected: `PASS`

- [ ] **Step 6: `publish()`가 qos/retain을 그대로 전달하는지 실패하는 테스트 추가**

`tests/shared/test_mqtt_client.py`에 추가:

```python
def test_publish_forwards_qos_and_retain():
    client, _, mock_instance = _make_client_with_mock()

    client.publish("minigit/resp/urrobot", '{"id":"u-0001"}', qos=1, retain=False)

    mock_instance.publish.assert_called_once_with(
        "minigit/resp/urrobot", '{"id":"u-0001"}', qos=1, retain=False
    )
```

- [ ] **Step 7: 테스트 실행 — 이미 통과할 것 확인 (Step 4 구현에 이미 포함됨)**

Run: `python -m pytest tests/shared/test_mqtt_client.py -v`
Expected: 지금까지 작성한 테스트 전부 `PASS`. (이 스텝은 회귀 확인용 — 새 구현이 없어도 통과해야 정상이다. 만약 실패하면 Step 4 구현을 다시 확인한다.)

- [ ] **Step 8: `will_set`이 생성자 인자로 정확히 호출되는지 실패하는 테스트 추가**

```python
def test_will_set_called_with_topic_and_payload():
    with patch("shared.mqtt_client.mqtt.Client") as mock_client_cls:
        mock_instance = MagicMock()
        mock_client_cls.return_value = mock_instance

        MQTTClient(
            "test-client",
            will_topic="minigit/status/rci-ur",
            will_payload='{"state":"offline","robot":"disconnected"}',
            will_qos=1,
            will_retain=True,
        )

        mock_instance.will_set.assert_called_once_with(
            "minigit/status/rci-ur",
            payload='{"state":"offline","robot":"disconnected"}',
            qos=1,
            retain=True,
        )


def test_will_set_not_called_when_no_will_topic():
    _, _, mock_instance = _make_client_with_mock()
    mock_instance.will_set.assert_not_called()
```

- [ ] **Step 9: 테스트 실행 확인**

Run: `python -m pytest tests/shared/test_mqtt_client.py -v`
Expected: 전부 `PASS` (Step 4 구현이 이미 `will_topic is not None` 분기를 갖고 있으므로 새 코드 추가 없이 통과해야 한다. 실패하면 Step 4의 `will_set` 호출부를 점검한다)

- [ ] **Step 10: 연결 전 구독이 큐에 쌓이고, `on_connect` 발생 시 일괄 구독되는지 실패하는 테스트 추가**

```python
def test_subscribe_before_connect_is_queued_then_applied_on_connect():
    client, _, mock_instance = _make_client_with_mock()
    callback = MagicMock()

    # connect() 이전 subscribe() 호출 — 이 시점엔 실제 구독이 일어나면 안 된다
    client.subscribe("minigit/req/urrobot", callback=callback, qos=1)
    mock_instance.subscribe.assert_not_called()

    # 브로커가 on_connect를 호출했다고 가정 (reason_code=0은 성공)
    client._on_connect(mock_instance, None, MagicMock(), 0, MagicMock())

    mock_instance.subscribe.assert_called_once_with("minigit/req/urrobot", qos=1)
    mock_instance.message_callback_add.assert_called_once_with(
        "minigit/req/urrobot", callback
    )


def test_subscribe_after_connect_applies_immediately():
    client, _, mock_instance = _make_client_with_mock()
    mock_instance.is_connected.return_value = True
    callback = MagicMock()

    client.subscribe("minigit/req/urrobot", callback=callback, qos=1)

    mock_instance.subscribe.assert_called_once_with("minigit/req/urrobot", qos=1)
    mock_instance.message_callback_add.assert_called_once_with(
        "minigit/req/urrobot", callback
    )
```

- [ ] **Step 11: 테스트 실행 확인**

Run: `python -m pytest tests/shared/test_mqtt_client.py -v`
Expected: 전부 `PASS`

- [ ] **Step 12: 재연결 설정(`reconnect_delay_set`)이 호출되는지 확인하는 테스트 추가**

```python
def test_reconnect_delay_set_is_configured():
    _, _, mock_instance = _make_client_with_mock()
    mock_instance.reconnect_delay_set.assert_called_once_with(min_delay=1, max_delay=30)
```

- [ ] **Step 13: 전체 테스트 실행**

Run: `python -m pytest tests/shared/test_mqtt_client.py -v`
Expected: 전부 `PASS` (총 7개 테스트: `test_uses_callback_api_version_2`, `test_publish_forwards_qos_and_retain`, `test_will_set_called_with_topic_and_payload`, `test_will_set_not_called_when_no_will_topic`, `test_subscribe_before_connect_is_queued_then_applied_on_connect`, `test_subscribe_after_connect_applies_immediately`, `test_reconnect_delay_set_is_configured`)

- [ ] **Step 14: 커밋**

```bash
git add shared/mqtt_client.py tests/shared/__init__.py tests/shared/test_mqtt_client.py
git commit -m "fix(shared): MQTTClient paho 2.x 호환 + QoS/Retain/LWT/큐잉 구독 지원"
```

---

### Task 4: UR3 진단 토픽 상수 (`shared/topics.py`)

**Files:**
- Modify: `shared/topics.py`
- Test: `tests/shared/test_topics.py`

**Interfaces:**
- Consumes: 없음
- Produces: `UR3_DIAG_REQ`, `UR3_DIAG_RESP`, `UR3_DIAG_ERROR`, `UR3_DIAG_STATUS` (문자열 상수) — Task 6(`ur3/mqtt_handler.py`)가 그대로 가져다 쓴다.

**주의**: 기존 `UR3_CMD = "rci/ur3/cmd"`, `UR3_STATUS = "rci/ur3/status"`는 **그대로 둔다.** 이름이 겹치므로 새 상수는 `UR3_DIAG_*` 접두어를 쓴다(사양서 §4.1의 `minigit/...` 체계와 기존 체계는 팀 합의 전까지 병존).

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/shared/test_topics.py` 새로 작성:

```python
"""shared.topics 상수 값 검증. UR3_RCI_기능명세서.md §4.1과 축자 일치해야 한다."""
from shared import topics


def test_ur3_diag_topics_match_spec():
    assert topics.UR3_DIAG_REQ == "minigit/req/urrobot"
    assert topics.UR3_DIAG_RESP == "minigit/resp/urrobot"
    assert topics.UR3_DIAG_ERROR == "minigit/error/urrobot"
    assert topics.UR3_DIAG_STATUS == "minigit/status/rci-ur"


def test_legacy_ur3_topics_untouched():
    """기존 rci/ur3/* 체계는 손대지 않는다 — 통합은 팀 합의 보류 사항."""
    assert topics.UR3_CMD == "rci/ur3/cmd"
    assert topics.UR3_STATUS == "rci/ur3/status"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/shared/test_topics.py -v`
Expected: `test_ur3_diag_topics_match_spec`이 `AttributeError: module 'shared.topics' has no attribute 'UR3_DIAG_REQ'`로 FAIL. `test_legacy_ur3_topics_untouched`는 이미 PASS(회귀 확인용).

- [ ] **Step 3: `shared/topics.py`에 추가**

```python
"""MQTT 토픽 상수 정의."""

RC_CAR_CMD = "rci/rc-car/cmd"
RC_CAR_STATUS = "rci/rc-car/status"

UR3_CMD = "rci/ur3/cmd"
UR3_STATUS = "rci/ur3/status"

# UR3 RCI 진단 인터페이스 토픽 (UR3_RCI_기능명세서.md §4.1, 확정)
# 위 UR3_CMD/UR3_STATUS(rci/ur3/*)와 이름 체계가 다르다.
# 통합 여부는 팀 합의 보류 — 지금은 두 체계가 병존한다.
UR3_DIAG_REQ = "minigit/req/urrobot"       # 웹앱 발행 → RCI 구독. QoS 1, Retained N
UR3_DIAG_RESP = "minigit/resp/urrobot"     # RCI 발행 → 웹앱 구독. QoS 1, Retained N
UR3_DIAG_ERROR = "minigit/error/urrobot"   # RCI 발행 → 웹앱 구독. QoS 1, Retained N
UR3_DIAG_STATUS = "minigit/status/rci-ur"  # RCI 발행 → 웹앱 구독. QoS 1, Retained Y (+LWT)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/shared/test_topics.py -v`
Expected: 전부 `PASS`

- [ ] **Step 5: 커밋**

```bash
git add shared/topics.py tests/shared/test_topics.py
git commit -m "feat(shared): UR3 진단 토픽 상수 추가 (사양서 §4.1)"
```

---

### Task 5: UR3 진단 페이로드 인코딩/봉투 (`ur3/uds_payload.py`)

**Files:**
- Create: `ur3/uds_payload.py`
- Create: `tests/ur3/__init__.py` (빈 파일)
- Test: `tests/ur3/test_uds_payload.py`

**Interfaces:**
- Consumes: 없음 (표준 라이브러리 `json`만 사용)
- Produces:
  - `encode_hex(data: bytes) -> str`
  - `decode_hex(text: str) -> bytes`
  - `classify_type(raw: bytes) -> str` (`"positive"` 또는 `"negative"`)
  - `parse_request(payload: str) -> dict` — 반환 형태 `{"id": str, "raw": bytes, "timeout_ms": int | None}`
  - `build_response(request_id: str, raw: bytes) -> str` (JSON 문자열)
  - `build_error(request_id: str, reason: str, message: str) -> str` (JSON 문자열, `reason`이 유효하지 않으면 `ValueError`)
  - `build_status(state: str, robot: str) -> str` (JSON 문자열, `robot`이 유효하지 않으면 `ValueError`)
  - Task 6(`ur3/mqtt_handler.py`)이 이 6개 함수를 그대로 가져다 쓴다.

- [ ] **Step 1: `tests/ur3/__init__.py` 생성 (빈 파일)**

```python
```

- [ ] **Step 2: hex 인코딩/디코딩 실패하는 테스트 작성**

`tests/ur3/test_uds_payload.py` 새로 작성:

```python
"""ur3.uds_payload 단위 테스트. UR3_RCI_기능명세서.md §4.2~4.5 기준."""
import pytest

from ur3 import uds_payload


def test_encode_hex_produces_uppercase_space_separated_no_prefix():
    assert uds_payload.encode_hex(bytes([0x22, 0x01, 0x07])) == "22 01 07"


def test_encode_hex_empty_bytes():
    assert uds_payload.encode_hex(b"") == ""


def test_decode_hex_round_trip():
    assert uds_payload.decode_hex("22 01 07") == bytes([0x22, 0x01, 0x07])


def test_decode_hex_lowercase_input_also_accepted():
    # 사양서는 발행 시 대문자를 요구하지만, 파싱은 대소문자에 관용적이어야 한다
    # (웹앱이 보내는 요청 payload를 우리가 통제할 수 없기 때문).
    assert uds_payload.decode_hex("22 01 07") == uds_payload.decode_hex("22 01 07".lower())
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `python -m pytest tests/ur3/test_uds_payload.py -v`
Expected: `ModuleNotFoundError: No module named 'ur3.uds_payload'`로 전부 FAIL

- [ ] **Step 4: `ur3/uds_payload.py` 최소 구현 — hex 인코딩/디코딩만**

```python
"""UR3 진단 MQTT 페이로드 인코딩/봉투 구성.

UR3_RCI_기능명세서.md §4.2~4.5 (확정) 기준. 물리값 디코딩·NRC 이름 매핑은
웹앱 담당이므로, 이 모듈은 raw 바이트만 다루고 절대 값을 해석하지 않는다.
"""
import json


def encode_hex(data: bytes) -> str:
    """바이트열을 사양서 §4.5 표기로 인코딩한다: 대문자, 공백 구분, 0x 없음."""
    return " ".join(f"{b:02X}" for b in data)


def decode_hex(text: str) -> bytes:
    """§4.5 표기(또는 대소문자 관용 입력)를 바이트열로 디코딩한다."""
    tokens = text.split()
    return bytes(int(tok, 16) for tok in tokens)
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `python -m pytest tests/ur3/test_uds_payload.py -v`
Expected: 전부 `PASS`

- [ ] **Step 6: `classify_type` 실패하는 테스트 추가**

```python
def test_classify_type_positive():
    assert uds_payload.classify_type(bytes([0x62, 0x01, 0x07, 0x07])) == "positive"


def test_classify_type_negative():
    assert uds_payload.classify_type(bytes([0x7F, 0x22, 0x31])) == "negative"


def test_classify_type_empty_raw_is_positive():
    # 빈 바이트열은 0x7F로 시작할 수 없으므로 positive로 분류한다.
    assert uds_payload.classify_type(b"") == "positive"
```

- [ ] **Step 7: 테스트 실패 확인 후 구현 추가**

Run: `python -m pytest tests/ur3/test_uds_payload.py::test_classify_type_positive -v`
Expected: `AttributeError` FAIL

`ur3/uds_payload.py`에 추가:

```python
def classify_type(raw: bytes) -> str:
    """§4.5: raw 첫 바이트가 0x7F면 negative, 그 외 positive."""
    if raw and raw[0] == 0x7F:
        return "negative"
    return "positive"
```

- [ ] **Step 8: 테스트 통과 확인**

Run: `python -m pytest tests/ur3/test_uds_payload.py -v`
Expected: 전부 `PASS`

- [ ] **Step 9: `parse_request` 실패하는 테스트 추가**

```python
def test_parse_request_full_payload():
    result = uds_payload.parse_request('{"id":"u-0001","raw":"22 01 01","timeout_ms":1000}')
    assert result == {"id": "u-0001", "raw": bytes([0x22, 0x01, 0x01]), "timeout_ms": 1000}


def test_parse_request_without_timeout_ms():
    result = uds_payload.parse_request('{"id":"u-0002","raw":"3E 00"}')
    assert result == {"id": "u-0002", "raw": bytes([0x3E, 0x00]), "timeout_ms": None}
```

- [ ] **Step 10: 테스트 실패 확인 후 구현 추가**

Run: `python -m pytest tests/ur3/test_uds_payload.py::test_parse_request_full_payload -v`
Expected: `AttributeError` FAIL

`ur3/uds_payload.py`에 추가:

```python
def parse_request(payload: str) -> dict:
    """§4.2 요청 페이로드를 파싱한다: {"id", "raw"(hex str), "timeout_ms"?}."""
    obj = json.loads(payload)
    return {
        "id": obj["id"],
        "raw": decode_hex(obj["raw"]),
        "timeout_ms": obj.get("timeout_ms"),
    }
```

- [ ] **Step 11: 테스트 통과 확인**

Run: `python -m pytest tests/ur3/test_uds_payload.py -v`
Expected: 전부 `PASS`

- [ ] **Step 12: `build_response` 실패하는 테스트 추가 (positive/negative 양쪽)**

```python
def test_build_response_positive():
    result = uds_payload.build_response("u-0001", bytes([0x62, 0x01, 0x07, 0x07]))
    assert json.loads(result) == {"id": "u-0001", "type": "positive", "raw": "62 01 07 07"}


def test_build_response_negative_extracts_nrc():
    result = uds_payload.build_response("u-0001", bytes([0x7F, 0x22, 0x31]))
    assert json.loads(result) == {
        "id": "u-0001",
        "type": "negative",
        "raw": "7F 22 31",
        "nrc": "31",
    }


def test_build_response_negative_too_short_raises():
    with pytest.raises(ValueError):
        uds_payload.build_response("u-0001", bytes([0x7F, 0x22]))
```

위 테스트가 `json`을 쓰므로 파일 상단에 `import json`을 추가한다.

- [ ] **Step 13: 테스트 실패 확인 후 구현 추가**

Run: `python -m pytest tests/ur3/test_uds_payload.py::test_build_response_positive -v`
Expected: `AttributeError` FAIL

`ur3/uds_payload.py`에 추가:

```python
def build_response(request_id: str, raw: bytes) -> str:
    """§4.3 응답 페이로드를 조립한다. negative면 raw[2]를 NRC로 추출한다."""
    response_type = classify_type(raw)
    response = {"id": request_id, "type": response_type, "raw": encode_hex(raw)}
    if response_type == "negative":
        if len(raw) < 3:
            raise ValueError(
                f"negative response raw too short to contain NRC: {encode_hex(raw)!r}"
            )
        response["nrc"] = f"{raw[2]:02X}"
    return json.dumps(response, ensure_ascii=False)
```

- [ ] **Step 14: 테스트 통과 확인**

Run: `python -m pytest tests/ur3/test_uds_payload.py -v`
Expected: 전부 `PASS`

- [ ] **Step 15: `build_error`/`build_status` 실패하는 테스트 추가**

```python
def test_build_error_valid_reason():
    result = uds_payload.build_error("u-0003", "robot_unreachable", "로봇 무응답")
    assert json.loads(result) == {
        "id": "u-0003",
        "type": "error",
        "reason": "robot_unreachable",
        "message": "로봇 무응답",
    }


def test_build_error_invalid_reason_raises():
    with pytest.raises(ValueError):
        uds_payload.build_error("u-0003", "not_a_real_reason", "x")


def test_build_status_valid():
    result = uds_payload.build_status("online", "connected")
    assert json.loads(result) == {"state": "online", "robot": "connected"}


def test_build_status_invalid_robot_value_raises():
    with pytest.raises(ValueError):
        uds_payload.build_status("online", "not_a_real_state")


def test_build_error_keeps_korean_message_unescaped():
    # json.loads()로 비교하면 \uXXXX 이스케이프 여부를 놓친다(디코드하면 같아지므로).
    # MQTT로 나가는 실제 문자열(raw string)에 한글이 그대로 있는지 직접 확인해야 한다.
    result = uds_payload.build_error("u-0003", "robot_unreachable", "로봇 무응답")
    assert "로봇 무응답" in result
    assert "\\u" not in result
```

- [ ] **Step 16: 테스트 실패 확인 후 구현 추가**

Run: `python -m pytest tests/ur3/test_uds_payload.py::test_build_error_valid_reason -v`
Expected: `AttributeError` FAIL

`ur3/uds_payload.py`에 추가:

```python
VALID_ERROR_REASONS = {"robot_unreachable", "dashboard_error", "internal_error"}
VALID_ROBOT_STATES = {"connected", "disconnected"}


def build_error(request_id: str, reason: str, message: str) -> str:
    """§4.4 에러 페이로드를 조립한다."""
    if reason not in VALID_ERROR_REASONS:
        raise ValueError(f"invalid error reason: {reason!r} (allowed: {VALID_ERROR_REASONS})")
    return json.dumps(
        {"id": request_id, "type": "error", "reason": reason, "message": message},
        ensure_ascii=False,
    )


def build_status(state: str, robot: str) -> str:
    """§4.4 상태 페이로드를 조립한다."""
    if robot not in VALID_ROBOT_STATES:
        raise ValueError(f"invalid robot state: {robot!r} (allowed: {VALID_ROBOT_STATES})")
    return json.dumps({"state": state, "robot": robot}, ensure_ascii=False)
```

- [ ] **Step 17: 전체 테스트 실행**

Run: `python -m pytest tests/ur3/test_uds_payload.py -v`
Expected: 전부 `PASS` (총 18개 테스트)

- [ ] **Step 18: 커밋**

```bash
git add ur3/uds_payload.py tests/ur3/__init__.py tests/ur3/test_uds_payload.py
git commit -m "feat(ur3): 진단 MQTT 페이로드 인코딩/봉투 구현 (사양서 §4.2~4.5)"
```

---

### Task 6: UR3 MQTT 핸들러 (`ur3/mqtt_handler.py`)

**Files:**
- Create: `ur3/mqtt_handler.py`
- Test: `tests/ur3/test_mqtt_handler.py`

**Interfaces:**
- Consumes:
  - `shared.mqtt_client.MQTTClient` (Task 3의 시그니처 그대로)
  - `shared.topics.UR3_DIAG_REQ/RESP/ERROR/STATUS` (Task 4)
  - `ur3.uds_payload.parse_request/build_response/build_error/build_status` (Task 5)
- Produces:
  - `UR3MqttHandler.__init__(self, broker_host: str = "localhost", broker_port: int = 1883, client_id: str = "ur3-rci")`
  - `UR3MqttHandler.on_request: Callable[[dict], None] | None` (속성, 기본 `None`) — 이후 UDS 디스패처(이 계획의 범위 밖)가 이 속성에 콜백을 대입해 요청을 받는다. 콜백 인자는 `ur3.uds_payload.parse_request()`의 반환 형태와 동일한 `dict`.
  - `UR3MqttHandler.connect(self) -> None`
  - `UR3MqttHandler.disconnect(self) -> None`
  - `UR3MqttHandler.publish_response(self, request_id: str, raw: bytes) -> None`
  - `UR3MqttHandler.publish_error(self, request_id: str, reason: str, message: str) -> None`
  - `UR3MqttHandler.publish_status(self, state: str, robot: str) -> None`

- [ ] **Step 1: 실패하는 테스트 작성 — 생성 시 올바른 토픽/LWT로 구독·설정되는지**

`tests/ur3/test_mqtt_handler.py` 새로 작성:

```python
"""ur3.mqtt_handler.UR3MqttHandler 단위 테스트.
shared.mqtt_client.MQTTClient를 모의 대체(가짜 브로커)해서 검증한다."""
from unittest.mock import MagicMock, patch

from ur3.mqtt_handler import UR3MqttHandler


def _make_handler_with_mock():
    with patch("ur3.mqtt_handler.MQTTClient") as mock_client_cls:
        mock_instance = MagicMock()
        mock_client_cls.return_value = mock_instance
        handler = UR3MqttHandler()
        return handler, mock_client_cls, mock_instance


def test_constructs_with_offline_will():
    handler, mock_client_cls, _ = _make_handler_with_mock()

    _, kwargs = mock_client_cls.call_args
    assert kwargs["will_topic"] == "minigit/status/rci-ur"
    assert kwargs["will_qos"] == 1
    assert kwargs["will_retain"] is True

    import json

    will_payload = json.loads(kwargs["will_payload"])
    assert will_payload == {"state": "offline", "robot": "disconnected"}


def test_subscribes_to_req_topic_with_qos_1():
    handler, _, mock_instance = _make_handler_with_mock()

    mock_instance.subscribe.assert_called_once()
    args, kwargs = mock_instance.subscribe.call_args
    assert args[0] == "minigit/req/urrobot"
    assert kwargs["qos"] == 1
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/ur3/test_mqtt_handler.py -v`
Expected: `ModuleNotFoundError: No module named 'ur3.mqtt_handler'`로 전부 FAIL

- [ ] **Step 3: `ur3/mqtt_handler.py` 최소 구현 — 생성자 + 구독**

```python
"""UR3 진단 MQTT 핸들러. shared.mqtt_client.MQTTClient를 UR3_RCI_기능명세서.md
§4.1 토픽에 맞춰 감싼다. SID 디스패치(uds_server)는 이 모듈의 범위 밖이며,
on_request 콜백으로 연결한다."""
from shared import topics
from shared.mqtt_client import MQTTClient
from ur3 import uds_payload


class UR3MqttHandler:
    def __init__(
        self,
        broker_host: str = "localhost",
        broker_port: int = 1883,
        client_id: str = "ur3-rci",
    ):
        offline_status = uds_payload.build_status("offline", "disconnected")
        self._client = MQTTClient(
            client_id,
            broker_host,
            broker_port,
            will_topic=topics.UR3_DIAG_STATUS,
            will_payload=offline_status,
            will_qos=1,
            will_retain=True,
        )
        self.on_request = None
        self._client.subscribe(topics.UR3_DIAG_REQ, callback=self._handle_message, qos=1)

    def _handle_message(self, client, userdata, msg):
        request = uds_payload.parse_request(msg.payload.decode("utf-8"))
        if self.on_request is not None:
            self.on_request(request)

    def connect(self):
        self._client.connect()

    def disconnect(self):
        self._client.disconnect()
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/ur3/test_mqtt_handler.py -v`
Expected: 전부 `PASS`

- [ ] **Step 5: `publish_response`/`publish_error`/`publish_status` 실패하는 테스트 추가**

```python
def test_publish_response_uses_resp_topic_qos_1_not_retained():
    handler, _, mock_instance = _make_handler_with_mock()

    handler.publish_response("u-0001", bytes([0x62, 0x01, 0x07, 0x07]))

    mock_instance.publish.assert_called_once_with(
        "minigit/resp/urrobot", '{"id": "u-0001", "type": "positive", "raw": "62 01 07 07"}',
        qos=1, retain=False,
    )


def test_publish_error_uses_error_topic_qos_1_not_retained():
    handler, _, mock_instance = _make_handler_with_mock()

    handler.publish_error("u-0003", "robot_unreachable", "로봇 무응답")

    mock_instance.publish.assert_called_once_with(
        "minigit/error/urrobot",
        '{"id": "u-0003", "type": "error", "reason": "robot_unreachable", "message": "로봇 무응답"}',
        qos=1, retain=False,
    )


def test_publish_status_uses_status_topic_qos_1_retained():
    handler, _, mock_instance = _make_handler_with_mock()

    handler.publish_status("online", "connected")

    mock_instance.publish.assert_called_once_with(
        "minigit/status/rci-ur", '{"state": "online", "robot": "connected"}',
        qos=1, retain=True,
    )
```

- [ ] **Step 6: 테스트 실패 확인**

Run: `python -m pytest tests/ur3/test_mqtt_handler.py -v`
Expected: 새로 추가한 3개가 `AttributeError`로 FAIL (메서드 없음)

- [ ] **Step 7: 구현 추가**

`ur3/mqtt_handler.py`에 추가:

```python
    def publish_response(self, request_id: str, raw: bytes):
        payload = uds_payload.build_response(request_id, raw)
        self._client.publish(topics.UR3_DIAG_RESP, payload, qos=1, retain=False)

    def publish_error(self, request_id: str, reason: str, message: str):
        payload = uds_payload.build_error(request_id, reason, message)
        self._client.publish(topics.UR3_DIAG_ERROR, payload, qos=1, retain=False)

    def publish_status(self, state: str, robot: str):
        payload = uds_payload.build_status(state, robot)
        self._client.publish(topics.UR3_DIAG_STATUS, payload, qos=1, retain=True)
```

- [ ] **Step 8: 테스트 통과 확인**

Run: `python -m pytest tests/ur3/test_mqtt_handler.py -v`
Expected: 전부 `PASS`

- [ ] **Step 9: `on_request` 콜백이 수신 메시지에서 호출되는지 실패하는 테스트 추가**

```python
def test_on_request_callback_invoked_with_parsed_request():
    handler, _, _ = _make_handler_with_mock()
    received = []
    handler.on_request = received.append

    fake_msg = MagicMock()
    fake_msg.payload = b'{"id":"u-0001","raw":"22 01 01","timeout_ms":1000}'
    handler._handle_message(None, None, fake_msg)

    assert received == [{"id": "u-0001", "raw": bytes([0x22, 0x01, 0x01]), "timeout_ms": 1000}]


def test_message_ignored_when_on_request_not_set():
    handler, _, _ = _make_handler_with_mock()
    fake_msg = MagicMock()
    fake_msg.payload = b'{"id":"u-0001","raw":"22 01 01"}'

    handler._handle_message(None, None, fake_msg)  # 예외 없이 조용히 무시되어야 함
```

- [ ] **Step 10: 테스트 실행 확인**

Run: `python -m pytest tests/ur3/test_mqtt_handler.py -v`
Expected: 전부 `PASS` (Step 3 구현에 이미 로직이 있으므로 새 코드 추가 없이 통과해야 한다. 실패하면 `_handle_message` 구현을 점검한다)

- [ ] **Step 11: `connect`/`disconnect`가 내부 클라이언트로 위임되는지 확인하는 테스트 추가**

```python
def test_connect_and_disconnect_delegate_to_client():
    handler, _, mock_instance = _make_handler_with_mock()

    handler.connect()
    mock_instance.connect.assert_called_once()

    handler.disconnect()
    mock_instance.disconnect.assert_called_once()
```

- [ ] **Step 12: 전체 테스트 실행**

Run: `python -m pytest tests/ur3/test_mqtt_handler.py -v`
Expected: 전부 `PASS` (총 9개 테스트)

- [ ] **Step 13: 커밋**

```bash
git add ur3/mqtt_handler.py tests/ur3/test_mqtt_handler.py
git commit -m "feat(ur3): UR3 진단 MQTT 핸들러 구현 (사양서 §4.1 토픽 결선)"
```

---

### Task 7: 전체 회귀 실행 및 마무리 점검

**Files:** 없음 (검증 전용 태스크)

**Interfaces:**
- Consumes: Task 1~6의 모든 산출물
- Produces: 없음 — 이 계획의 종료 게이트

- [ ] **Step 1: 전체 테스트 스위트 실행**

Run: `python -m pytest tests/ -v`
Expected: Task 3, 4, 5, 6에서 작성한 테스트 전부 `PASS` (총 34개: mqtt_client 7 + topics 2 + uds_payload 18 + mqtt_handler 9 — 정확한 개수는 각 태스크의 최종 스텝 기준. 실행 후 실제 합계가 이와 다르면 어느 태스크에서 스텝이 빠졌는지 역추적한다)

- [ ] **Step 2: `integration/test_integration.py`가 이 변경으로 깨지지 않았는지 확인 (실행이 아니라 정적 확인)**

Run: `python -c "import ast; ast.parse(open('integration/test_integration.py', encoding='utf-8').read())"`
Expected: 에러 없음 (문법 확인만 — 이 계획은 `integration/test_integration.py`를 수정하지 않으므로 브로커 없이 실제 실행은 불가능하다. `shared.topics.UR3_CMD`/`UR3_STATUS`를 그대로 남겨뒀으므로 import 자체는 여전히 성공한다)

- [ ] **Step 3: `shared/topics.py`와 `shared/mqtt_client.py`에 대해 다른 파트(rc-car, web-ui)가 여전히 import 가능한지 확인**

Run: `python -c "from shared.mqtt_client import MQTTClient; from shared import topics; print(topics.RC_CAR_CMD, topics.RC_CAR_STATUS)"`
Expected: `rci/rc-car/cmd rci/rc-car/status` 출력, 에러 없음

- [ ] **Step 4: 최종 커밋 (남은 변경이 있다면)**

```bash
git status
```

Expected: `nothing to commit, working tree clean` (Task 1~6에서 이미 전부 커밋했다면 이 스텝은 확인용으로만 통과한다)

---

## 이 계획이 끝난 뒤 남는 것 (범위 밖 — 별도 계획 필요)

- `uds_server`의 SID 디스패치가 아직 없다. `UR3MqttHandler.on_request`에 콜백을 붙이는 쪽이 다음 계획의 시작점이다.
- 실제 브로커 접속 정보(호스트/포트/인증)는 여전히 미수령이다(요청서 §9 액션 1). 수령 즉시 `UR3MqttHandler(broker_host=..., broker_port=...)`로 넘기면 되며, 이 계획의 코드 변경은 필요 없다.
- `shared/topics.py`의 `UR3_CMD`/`UR3_STATUS`(`rci/ur3/*`)와 `UR3_DIAG_*`(`minigit/...`)가 병존한다. 통합 여부는 팀 합의 사항이며 별도 결정이 필요하다.
- `integration/test_integration.py`는 이번 계획에서 손대지 않았다. 여전히 `subscribe()`를 `connect()` 전에 호출하는 구조이며, 토픽도 `UR3_CMD`/`UR3_STATUS`를 참조해 사양서 토픽과 다르다 — 팀 합의 후 재작성이 필요하다.
