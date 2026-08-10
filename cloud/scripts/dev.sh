#!/usr/bin/env bash
# RCI 교육 플랫폼 · 로컬 개발 서버 일괄 실행 (Git Bash / Linux)
#
# 브로커(amqtt) + 목 RCI 게이트웨이 + FastAPI 웹을 함께 띄우고, Ctrl+C 로 전체 종료.
# 옵션:
#   --lan      브로커·웹을 0.0.0.0 에 바인딩(다른 기기 접속 가능) — 핫스팟(LAN) 테스트용.
#   --no-mock  목 RCI 생략 (실물 RCI 사용 시).
# 사용:  bash scripts/dev.sh                 # 로컬 전용 + 목
#        bash scripts/dev.sh --lan --no-mock # 핫스팟에서 실물 RCI 테스트
set -euo pipefail

lan=0; nomock=0
for a in "$@"; do
  case "$a" in
    --lan) lan=1 ;;
    --no-mock) nomock=1 ;;
    *) echo "알 수 없는 옵션: $a" >&2; exit 2 ;;
  esac
done

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
py="$root/.venv/Scripts/python.exe"          # Windows venv
[ -x "$py" ] || py="$root/.venv/bin/python"  # Linux venv 폴백
export PYTHONUTF8=1

web_host="127.0.0.1"
if [ "$lan" = "1" ]; then
  export RCI_BIND_HOST="0.0.0.0"             # dev_broker.py 가 읽는다
  web_host="0.0.0.0"
  echo "[dev] LAN 모드 — 다른 기기에서 http://<이 PC IP>:8123 로 접속, RCI 는 <이 PC IP>:1883 을 브로커로."
fi

pid_file="$root/.dev-pids"   # Windows 쪽 stop.ps1/stop.bat 이 읽는 것과 같은 파일
pids=()
cleanup() {
  echo; echo "[dev] 종료 중..."
  for p in "${pids[@]}"; do kill "$p" 2>/dev/null || true; done
  rm -f "$pid_file"
}
trap cleanup EXIT INT TERM

echo "[dev] broker 시작..."
"$py" "$root/Codes/board/dev_broker.py" & pids+=($!)
sleep 2                                       # 목/RCI 가 붙기 전에 브로커가 떠 있어야 함
if [ "$nomock" = "0" ]; then
  echo "[dev] mock-rci 시작..."
  "$py" "$root/Codes/board/mock_rci.py" & pids+=($!)
else
  echo "[dev] 목 RCI 생략 (실물 RCI 사용)"
fi
echo "[dev] web 시작..."
( cd "$root/Codes/Cloud" && exec "$py" -m uvicorn main:app --host "$web_host" --port 8123 ) & pids+=($!)

printf '%s\n' "${pids[@]}" > "$pid_file"      # 고아가 남았을 때 stop 스크립트가 찾을 단서

echo "[dev] 웹 → http://localhost:8123   (Ctrl+C 로 전체 종료)"
wait
