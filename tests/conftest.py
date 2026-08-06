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
