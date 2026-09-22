"""pytest가 cloud/Codes/Cloud 를 sys.path에 포함시키도록 한다.

main.py 가 `import theory_content` 처럼 형제 모듈을 절대 임포트로 불러오므로,
테스트에서도 이 디렉터리가 sys.path에 있어야 `import broadcast`/`import main`이
동작한다(루트 tests/conftest.py가 리포지토리 루트를 넣는 것과 같은 이유).
"""
import os
import sys

_APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)
