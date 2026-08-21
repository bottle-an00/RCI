<#
  RCI 교육 플랫폼 · 로컬 개발 서버 일괄 실행 (Windows / PowerShell 7+)

  브로커(amqtt) + 목 RCI 게이트웨이 + FastAPI 웹을 한 터미널에서 함께 띄우고,
  Ctrl+C 한 번으로 셋 다 종료한다.

  옵션:
    -Lan     브로커·웹을 0.0.0.0 에 바인딩(다른 기기에서 접속 가능) + 접속 IP 출력.
             사내 방화벽으로 포트가 막힐 때 폰 핫스팟(LAN)에서 실물 RCI·태블릿 테스트용.
    -NoMock  목 RCI 를 띄우지 않음. 실물 RCI 가 브로커에 붙는 경우 사용.

  종료:
    이 창에서 Ctrl+C  (아래 finally 가 자식 셋을 정리한다)
    창을 X 로 닫아 고아가 남았다면  ->  stop.bat  또는  ./scripts/stop.ps1

  환경변수 (자식 프로세스가 그대로 상속한다 — 여기서 설정하면 셋 다 적용된다):
    RCI_BROKER_LOG=info    브로커 로그를 켠다. 기본은 조용해서 아무것도 안 찍힌다.
                           접속/해제와 접속해 온 IP 가 보인다 — 실물 RCI 가 정말
                           도달했는지 확인할 때. debug 는 패킷까지(도배 주의).
    RCI_BROKER_HOST=<IP>   웹 브리지·브라우저가 붙을 브로커 주소. 브로커가 이 PC 에
                           있으면 건드릴 필요 없다.

  사용:
    ./scripts/dev.ps1                 # 로컬 전용 + 목 (기존 개발)
    ./scripts/dev.ps1 -Lan -NoMock    # 핫스팟에서 실물 RCI 테스트
    $env:RCI_BROKER_LOG="info"; ./scripts/dev.ps1 -Lan -NoMock   # + 브로커 로그
#>
param(
  [switch]$Lan,
  [switch]$NoMock
)
$ErrorActionPreference = "Stop"

$root  = Split-Path $PSScriptRoot -Parent
$py    = Join-Path $root ".venv/Scripts/python.exe"
$board = Join-Path $root "Codes/board"
$cloud = Join-Path $root "Codes/Cloud"
$pidFile = Join-Path $root ".dev-pids"      # stop.ps1 이 읽는다
$env:PYTHONUTF8 = "1"                       # 콘솔 cp949 인코딩 오류 방지

if (-not (Test-Path $py)) { throw ".venv 파이썬을 찾을 수 없습니다: $py  (먼저 가상환경을 만드세요)" }

# 사전 점검: 이전 실행이 고아로 남아 포트를 쥐고 있으면 지금 알려준다.
# (그대로 띄우면 브로커는 'address in use' 로 죽고 웹만 떠서 원인 찾기가 어렵다.)
$busy = @(1883, 8080, 8123) | Where-Object {
  Get-NetTCPConnection -LocalPort $_ -State Listen -ErrorAction SilentlyContinue
}
if ($busy) {
  Write-Host "[dev] 포트가 이미 사용 중입니다: $($busy -join ', ')" -ForegroundColor Red
  Write-Host "[dev] 이전 실행이 남아 있을 수 있습니다. 먼저 정리하세요:" -ForegroundColor Red
  Write-Host "        stop.bat  (또는)  ./scripts/stop.ps1" -ForegroundColor Red
  Write-Host "      무엇이 점유 중인지만 보려면:  ./scripts/stop.ps1 -WhatIf" -ForegroundColor DarkYellow
  exit 1
}

# LAN 모드: 모든 인터페이스 바인딩 + 접속용 IPv4 후보 안내.
$webHost = "0.0.0.0"
if ($Lan) {
  $env:RCI_BIND_HOST = "0.0.0.0"            # dev_broker.py 가 읽는다
  $webHost = "0.0.0.0"
  # '연결된(Up)' 어댑터의 IPv4 만 후보로. (끊긴 어댑터의 옛 고정 IP·APIPA 오인 방지)
  $cands = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -notmatch '^(127\.|169\.254\.)' } |
    ForEach-Object {
      $ad = Get-NetAdapter -InterfaceIndex $_.InterfaceIndex -ErrorAction SilentlyContinue
      if ($ad -and $ad.Status -eq "Up") { [pscustomobject]@{ IP = $_.IPAddress; Adapter = $_.InterfaceAlias } }
    }
  Write-Host "[dev] LAN 모드 — 다른 기기가 접속할 이 PC 의 IP 후보(연결된 어댑터):" -ForegroundColor Magenta
  $cands | ForEach-Object { Write-Host ("        {0,-16} ({1})" -f $_.IP, $_.Adapter) -ForegroundColor Magenta }
  Write-Host "[dev] 위 중 '핫스팟에 연결된' 어댑터 IP 를 사용:  웹 http://<IP>:8123 · RCI 브로커 <IP>:1883" -ForegroundColor Magenta
}

# 자식 프로세스를 한 콘솔에서 실행(-NoNewWindow)해 로그가 함께 보이게 하고,
# finally 에서 살아있는 것만 정리한다.
$procs = @()
function Start-Svc([string]$name, $svcArgs, [string]$wd) {
  Write-Host "[dev] $name 시작..." -ForegroundColor Cyan
  return Start-Process $py -ArgumentList $svcArgs -WorkingDirectory $wd -PassThru -NoNewWindow
}

try {
  $procs += Start-Svc "broker" "dev_broker.py" $board
  Start-Sleep -Seconds 2                    # 목/RCI 가 붙기 전에 브로커가 떠 있어야 함
  if (-not $NoMock) {
    $procs += Start-Svc "mock-rci" "mock_rci.py" $board
  } else {
    Write-Host "[dev] 목 RCI 생략 (실물 RCI 사용)" -ForegroundColor DarkYellow
  }
  $procs += Start-Svc "web" @("-m", "uvicorn", "main:app", "--host", $webHost, "--port", "8123") $cloud

  # 자식 PID 를 남긴다. 창을 X 로 닫으면 아래 finally 가 돌지 않으므로, stop.ps1 이
  # 이 파일을 보고 고아를 정리한다. (포트 스캔만으로는 남의 프로세스와 구분이 어렵다)
  $procs | ForEach-Object Id | Set-Content -Path $pidFile -Encoding ascii

  Write-Host "[dev] 웹 → http://localhost:8123   (Ctrl+C 로 전체 종료)" -ForegroundColor Green
  Wait-Process -Id ($procs | ForEach-Object Id)
}
finally {
  Write-Host "`n[dev] 종료 중..." -ForegroundColor Yellow
  foreach ($p in $procs) {
    if ($p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
  }
  if (Test-Path $pidFile) { Remove-Item $pidFile -Force -ErrorAction SilentlyContinue }
}
