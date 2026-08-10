<#
  RCI 교육 플랫폼 · 로컬 개발 서버 일괄 종료 (Windows / PowerShell 5.1+)

  dev.ps1 이 Ctrl+C 로 정상 종료되면 자기 finally 에서 이미 정리한다. 이 스크립트는
  그러지 못한 경우 — 콘솔 창을 X 로 닫았거나, 작업관리자로 부모만 죽였거나, 재부팅
  없이 다시 띄우려는데 포트가 잡혀 있을 때 — 를 위한 안전망이다.

  세 경로로 찾는다(합집합). 하나만으로는 빠지는 게 생긴다:
    ① PID 파일 (.dev-pids)  — dev.ps1/dev.sh 가 남긴 자식 PID. 가장 정확.
    ② 포트 소유자           — 1883(브로커 TCP) / 8080(브로커 WS) / 8123(웹).
                              PID 파일이 없거나 낡았을 때의 폴백.
    ③ 커맨드라인 스캔       — mock_rci.py 는 **포트를 열지 않아** ② 로 안 잡힌다.
                              venv 런처 스텁(아래 참고)도 여기서 함께 걸린다.

  신원 검증 — 왜 실행파일 경로가 아니라 커맨드라인인가
    Windows venv 의 Scripts\python.exe 는 런처 스텁이라 실제 인터프리터를 **자식
    프로세스로 다시 띄운다.** 포트를 쥐고 있는 쪽은 그 자식이고, 자식의 실행 경로는
    venv 가 아니라 베이스 파이썬(...\Python313\python.exe)으로 보고된다. 반면
    커맨드라인은 그대로 상속되므로 'dev_broker.py' 같은 서비스 시그니처가 남는다.

  사용:
    ./scripts/stop.ps1              # 정리
    ./scripts/stop.ps1 -WhatIf      # 무엇을 죽일지 보기만 (실제 종료 안 함)
    ./scripts/stop.ps1 -Force       # 우리 것이 아닌 포트 점유자까지 종료(주의)
#>
param(
  [switch]$WhatIf,
  [switch]$Force,
  [int[]]$Ports = @(1883, 8080, 8123)
)
$ErrorActionPreference = "Stop"

$root    = Split-Path $PSScriptRoot -Parent
$pidFile = Join-Path $root ".dev-pids"

$GRACE_SECONDS = 3   # 강제 종료 전 정상 종료를 기다리는 시간

# 이 프로젝트의 서비스임을 알아보는 커맨드라인 시그니처. 라벨과 짝지어 둔다.
# (python.exe 라는 이름만 보면 무관한 파이썬까지 걸린다 — 스크립트명까지 봐야 한다.)
$SERVICES = [ordered]@{
  'dev_broker\.py'  = 'broker'
  'mock_rci\.py'    = 'mock-rci'
  'uvicorn\s+main:app' = 'web'
}

# --------------------------------------------------------------------------- #
# 후보 수집
# --------------------------------------------------------------------------- #

function Get-PidsFromFile {
  if (-not (Test-Path $pidFile)) { return @() }
  Get-Content $pidFile | Where-Object { $_ -match '^\d+$' } | ForEach-Object { [int]$_ }
}

function Get-PidsFromPorts {
  # Listen 상태의 소유 프로세스만. (ESTABLISHED 는 접속해 온 '클라이언트' 라 죽이면 안 됨)
  foreach ($p in $Ports) {
    Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue |
      Select-Object -ExpandProperty OwningProcess
  }
}

function Get-PidsFromCommandLine {
  Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -and (Test-OurCommandLine $_.CommandLine) } |
    Select-Object -ExpandProperty ProcessId
}

# --------------------------------------------------------------------------- #
# 신원 검증
# --------------------------------------------------------------------------- #

function Test-OurCommandLine([string]$cmd) {
  if (-not $cmd) { return $false }
  foreach ($pattern in $SERVICES.Keys) { if ($cmd -match $pattern) { return $true } }
  return $false
}

function Get-ProcInfo([int]$procId) {
  $ci = Get-CimInstance Win32_Process -Filter "ProcessId=$procId" -ErrorAction SilentlyContinue
  if (-not $ci) { return $null }
  $label = "python"
  foreach ($pattern in $SERVICES.Keys) {
    if ($ci.CommandLine -match $pattern) { $label = $SERVICES[$pattern]; break }
  }
  [pscustomobject]@{
    Id    = $procId
    Label = $label
    Cmd   = $ci.CommandLine
    Ours  = (Test-OurCommandLine $ci.CommandLine)
  }
}

# --------------------------------------------------------------------------- #
# 종료
# --------------------------------------------------------------------------- #

function Invoke-GracefulStop([int]$procId) {
  <#
    강제 종료 전에 '정상 종료'를 시도한다. 요청이 접수되면 $true.

    /F 를 빼면 강제 종료가 아니라 WM_CLOSE 를 보내는 '요청'이 된다.
    /T 는 자식 트리까지 — venv 런처 스텁과 실제 인터프리터가 부모·자식이라
    부모에게만 보내면 포트를 쥔 자식이 살아남는다.

    반환값은 '요청을 보냈다'이지 '죽는다'가 아니다. 콘솔 앱은 메시지 루프가 없어
    WM_CLOSE 를 못 받는 경우가 흔하므로, 호출부가 $GRACE_SECONDS 만 기다렸다가
    안 죽으면 강제 종료로 넘어간다.

    측정 결과(2026-08, 이 스택 기준): 브로커·목 RCI·uvicorn 셋 다 창이 없는 콘솔
    프로세스라 Windows 가 거부한다 —
        "This process can only be terminated forcefully (with /F option)"
    exit=255(자식 거부) / 128(자식이 남아 부모도 실패). 즉 지금은 항상 $false 가
    돌아와 곧바로 강제 종료로 넘어가고, $GRACE_SECONDS 대기는 발동하지 않는다.
    (그래서 비용도 없다. 나중에 창 있는 프로세스가 추가되면 그때 실제로 동작한다.)

    이 스택에서 정상 종료가 사실상 무의미한 이유도 있다: mock_rci 의 LWT(offline)를
    받아줄 브로커까지 같이 죽는다. LWT 가 의미를 갖는 건 브로커가 살아있는
    실환경(라즈베리파이 RCI ↔ 클라우드 브로커)이고, 거기선 Ctrl+C 가 스크립트의
    finally 를 태워 offline 을 직접 발행한다.
  #>
  $prev = $ErrorActionPreference
  $ErrorActionPreference = "Continue"   # taskkill 의 stderr 가 종료 오류가 되지 않게
  try {
    taskkill.exe /PID $procId /T 2>$null 1>$null
    # 0 = 요청 접수. 128(대상 없음)·1(거부) 은 실패로 보고 곧바로 강제 종료한다.
    return ($LASTEXITCODE -eq 0)
  }
  catch { return $false }
  finally { $ErrorActionPreference = $prev }
}

function Stop-DevProcess($info) {
  if ($WhatIf) {
    Write-Host ("  [건너뜀] pid {0,-6} {1,-9} (-WhatIf)" -f $info.Id, $info.Label) -ForegroundColor DarkGray
    return $false
  }
  if (Invoke-GracefulStop $info.Id) {
    $proc = Get-Process -Id $info.Id -ErrorAction SilentlyContinue
    if (-not $proc -or $proc.WaitForExit($GRACE_SECONDS * 1000)) {
      Write-Host ("  [정상종료] pid {0,-6} {1}" -f $info.Id, $info.Label) -ForegroundColor Green
      return $true
    }
  }
  Stop-Process -Id $info.Id -Force -ErrorAction SilentlyContinue
  Write-Host ("  [강제종료] pid {0,-6} {1}" -f $info.Id, $info.Label) -ForegroundColor Yellow
  return $true
}

# --------------------------------------------------------------------------- #

$candidates = @(Get-PidsFromFile) + @(Get-PidsFromPorts) + @(Get-PidsFromCommandLine) |
  Sort-Object -Unique

if (-not $candidates) {
  Write-Host "[stop] 실행 중인 개발 서버가 없습니다." -ForegroundColor DarkGray
  if (Test-Path $pidFile) { Remove-Item $pidFile -Force }
  return
}

Write-Host "[stop] 종료 대상 확인 중..." -ForegroundColor Cyan
$stopped = 0
$skipped = @()

foreach ($procId in $candidates) {
  $info = Get-ProcInfo $procId
  if (-not $info) { continue }                       # 이미 죽은 PID(낡은 PID 파일)

  if ($info.Ours) {
    if (Stop-DevProcess $info) { $stopped++ }
  }
  elseif ($Force) {
    Write-Host ("  [강제종료] pid {0,-6} {1}  (-Force: 시그니처 불일치)" -f $info.Id, $info.Label) -ForegroundColor Red
    Stop-Process -Id $info.Id -Force -ErrorAction SilentlyContinue
    $stopped++
  }
  else {
    $skipped += $info
    Write-Host ("  [보존] pid {0,-6} {1}  — 이 프로젝트의 서비스가 아닙니다" -f $info.Id, $info.Label) -ForegroundColor DarkYellow
  }
}

if (-not $WhatIf -and (Test-Path $pidFile)) { Remove-Item $pidFile -Force }

Write-Host "[stop] 종료 $stopped 건." -ForegroundColor Cyan
if ($skipped) {
  Write-Host "[stop] 아래 프로세스가 포트를 계속 점유합니다. 남의 것일 수 있으니 확인 후 처리하세요:" -ForegroundColor DarkYellow
  $skipped | ForEach-Object { Write-Host ("        pid {0,-6} {1}" -f $_.Id, $_.Cmd) -ForegroundColor DarkYellow }
  Write-Host "        정말 종료하려면:  ./scripts/stop.ps1 -Force" -ForegroundColor DarkYellow
}
