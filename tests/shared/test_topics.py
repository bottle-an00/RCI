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
