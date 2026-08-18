<#
  RCI 교육 플랫폼 · 로컬 개발 서버 일괄 종료 (Windows / PowerShell 5.1+)

  dev.ps1 이 Ctrl+C 로 정상 종료되면 자기 finally 에서 이미 정리한다. 이 스크립트는
  그러지 못한 경우 — 콘솔 창을 X 로 닫았거나, 작업관리자로 부모만 죽였거나, 재부팅
  없이 다시 띄우려는데 포트가 잡혀 있을 때 — 를 위한 안전망이다.

  다섯 경로로 찾는다(합집합). 하나만으로는 빠지는 게 생긴다:
    ① PID 파일 (.dev-pids)  — dev.ps1/dev.sh 가 남긴 자식 PID. 가장 정확.
    ② 포트 소유자           — 1883·8080(브로커) + 웹 포트. 웹 포트는 고정 8123 에
                              .claude/launch.json 의 port 들(8129·8130 등)을 합쳐서
                              쓴다. 손으로 관리하면 구성이 늘 때마다 새는 포트가 생긴다.
    ③ 커맨드라인 스캔       — mock_rci.py 는 **포트를 열지 않아** ② 로 안 잡힌다.
                              venv 런처 스텁(아래 참고)도 여기서 함께 걸린다.
    ④ 자손 추적             — uvicorn --reload 의 워커는 커맨드라인이
                              `multiprocessing.spawn ...` 이라 ③ 에 안 걸리고, 포트도
                              부모가 쥐고 있어 ② 에도 안 걸린다. 부모만 죽이면 고아로
                              남아 **이후 어떤 실행도 못 찾는다** — 실제로 이렇게 쌓였다.
    ⑤ 고아 spawn 워커       — 이미 고아가 된 것은 커맨드라인의 parent_pid 로 판정한다.
                              부모가 없으면 아무 일도 못 하므로 기본으로 정리한다.

  종료 후 남은 것이 있으면 목록으로 알려준다. '몇 건 종료'만 찍고 끝내면 덜 치웠는데도
  다 된 줄 알게 되기 때문이다.

  신원 검증 — 왜 실행파일 경로가 아니라 커맨드라인인가
    Windows venv 의 Scripts\python.exe 는 런처 스텁이라 실제 인터프리터를 **자식
    프로세스로 다시 띄운다.** 포트를 쥐고 있는 쪽은 그 자식이고, 자식의 실행 경로는
    venv 가 아니라 베이스 파이썬(...\Python313\python.exe)으로 보고된다. 반면
    커맨드라인은 그대로 상속되므로 'dev_broker.py' 같은 서비스 시그니처가 남는다.

  사용:
    ./scripts/stop.ps1                # 정리
    ./scripts/stop.ps1 -WhatIf        # 무엇을 죽일지 보기만 (실제 종료 안 함)
    ./scripts/stop.ps1 -Force         # 우리 것이 아닌 포트 점유자까지 종료(주의)
    ./scripts/stop.ps1 -KeepOrphans   # 고아 spawn 워커는 손대지 않음
    ./scripts/stop.ps1 -Ports 8123,9000   # 확인할 포트를 직접 지정
#>
param(
  [switch]$WhatIf,
  [switch]$Force,
  [switch]$KeepOrphans,
  [int[]]$Ports
)
$ErrorActionPreference = "Stop"

$root    = Split-Path $PSScriptRoot -Parent
$repo    = Split-Path $root -Parent          # .claude/launch.json 은 저장소 루트에 있다
$pidFile = Join-Path $root ".dev-pids"

# 감시할 포트. 브로커는 고정이지만 웹은 여러 포트에 뜬다 — dev.ps1 은 8123,
# .claude/launch.json 은 8123·8129·8130(reload·alt 구성). 목록을 손으로 관리하면
# launch.json 에 구성이 하나 늘 때마다 조용히 새는 포트가 생기므로 거기서 읽어 합친다.
$FIXED_PORTS = @(1883, 8080, 8123)

function Get-LaunchJsonPorts {
  $file = Join-Path $repo ".claude/launch.json"
  if (-not (Test-Path $file)) { return @() }
  try {
    @((Get-Content $file -Raw | ConvertFrom-Json).configurations |
      ForEach-Object { $_.port } | Where-Object { $_ })
  } catch {
    Write-Host "[stop] launch.json 을 읽지 못했습니다 — 고정 포트만 확인합니다." -ForegroundColor DarkYellow
    @()
  }
}

if (-not $Ports) {
  $Ports = @($FIXED_PORTS + (Get-LaunchJsonPorts)) | Sort-Object -Unique
}

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

function Get-PythonProcesses {
  @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue)
}

function Get-PidsFromCommandLine($all) {
  $all | Where-Object { $_.CommandLine -and (Test-OurCommandLine $_.CommandLine) } |
    Select-Object -ExpandProperty ProcessId
}

# --------------------------------------------------------------------------- #
# 혈통 추적 — uvicorn --reload 워커가 새는 것을 막는다
#
# --reload 는 실제 앱을 multiprocessing 으로 spawn 한다. 그 워커의 커맨드라인은
#   python -X utf8 -c "from multiprocessing.spawn import spawn_main; spawn_main(parent_pid=30800, ...)"
# 이라 'uvicorn main:app' 같은 시그니처가 **없다.** 그래서:
#   · 커맨드라인 스캔에 안 걸리고
#   · 포트도 안 쥐고 있어(부모가 리슨한다) 포트 스캔에도 안 걸린다
# 부모만 죽으면 이 워커는 고아로 남고, 시그니처가 없으니 이후 어떤 stop 실행도
# 영영 발견하지 못한다. (측정 2026-08-11: reload 구성 1회 기동→정리에 고아 1개 잔류.
# 기존 Stop-Process -Force 는 트리가 아니라 그 프로세스 하나만 죽인다.)
#
# 대책 둘:
#   ① 죽이기 전에 자손을 미리 모은다 — 부모를 죽인 뒤엔 혈통 정보가 사라진다.
#   ② 이미 고아가 된 것은 커맨드라인의 parent_pid 로 판정한다(아래 Get-SpawnParentPid).
# --------------------------------------------------------------------------- #

function Get-Descendants([int[]]$roots, $all) {
  $byParent = @{}
  foreach ($p in $all) {
    $key = [int]$p.ParentProcessId
    if (-not $byParent.ContainsKey($key)) { $byParent[$key] = @() }
    $byParent[$key] += [int]$p.ProcessId
  }
  $seen = @{}
  $queue = New-Object System.Collections.Queue
  foreach ($r in $roots) { $queue.Enqueue([int]$r) }
  while ($queue.Count -gt 0) {
    foreach ($child in @($byParent[[int]$queue.Dequeue()])) {
      if ($child -and -not $seen.ContainsKey($child)) {
        $seen[$child] = $true
        $queue.Enqueue($child)
      }
    }
  }
  @($seen.Keys)
}

# spawn 워커가 커맨드라인에 적어둔 부모 PID. 부모가 죽어도 이 값은 남는다 —
# 고아를 판정할 수 있는 유일한 단서다(실행파일 경로는 베이스 파이썬이라 무의미).
function Get-SpawnParentPid([string]$cmd) {
  if ($cmd -and $cmd -match 'spawn_main\(parent_pid=(\d+)') { return [int]$Matches[1] }
  return $null
}

# 부모가 이미 사라진 spawn 워커. 부모의 파이프를 기다리며 아무 일도 못 하는
# 확정 쓰레기라, 남겨둘 이유가 없어 기본으로 정리한다(-KeepOrphans 로 보존).
# 다만 '우리 것'임을 증명할 방법은 없으므로 로그에 부모 PID 를 붙여 구분해 찍는다.
function Get-AbandonedSpawnWorkers($all) {
  # 부모 생존 여부는 실제 프로세스로 확인한다. $all(파이썬만)에서 찾으면
  # 부모가 다른 실행파일인 경우를 '죽었다'고 오판한다.
  $all | Where-Object {
    $parent = Get-SpawnParentPid $_.CommandLine
    $parent -and -not (Get-Process -Id $parent -ErrorAction SilentlyContinue)
  }
}

# --------------------------------------------------------------------------- #
# 신원 검증
# --------------------------------------------------------------------------- #

function Test-OurCommandLine([string]$cmd) {
  if (-not $cmd) { return $false }
  foreach ($pattern in $SERVICES.Keys) { if ($cmd -match $pattern) { return $true } }
  return $false
}

# $extra: pid → 시그니처 말고 다른 근거로 '우리 것'이라 판정된 이유(자손·고아).
# 시그니처가 없는 프로세스도 이 표에 있으면 우리 것으로 본다.
function Get-ProcInfo([int]$procId, $extra) {
  $ci = Get-CimInstance Win32_Process -Filter "ProcessId=$procId" -ErrorAction SilentlyContinue
  if (-not $ci) { return $null }
  $label = "python"
  foreach ($pattern in $SERVICES.Keys) {
    if ($ci.CommandLine -match $pattern) { $label = $SERVICES[$pattern]; break }
  }
  $reason = if ($extra -and $extra.ContainsKey($procId)) { $extra[$procId] } else { $null }
  if ($reason -and $label -eq "python") { $label = $reason }
  [pscustomobject]@{
    Id     = $procId
    Label  = $label
    Cmd    = $ci.CommandLine
    Reason = $reason
    Ours   = ((Test-OurCommandLine $ci.CommandLine) -or [bool]$reason)
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

$allPython = Get-PythonProcesses

$matched = @(Get-PidsFromFile) + @(Get-PidsFromPorts) + @(Get-PidsFromCommandLine $allPython) |
  Sort-Object -Unique

# 시그니처 밖의 근거들. 왜 죽이는지 로그에 남기려고 이유를 함께 들고 다닌다.
$extra = @{}

# ① 자손 — 반드시 죽이기 **전에** 모은다. 부모가 죽으면 혈통을 잃는다.
foreach ($descendant in (Get-Descendants $matched $allPython)) {
  if ($matched -notcontains $descendant) { $extra[[int]$descendant] = "자식" }
}

# ② 이미 고아가 된 spawn 워커 — 부모가 없어 아무것도 못 하는 확정 쓰레기.
if (-not $KeepOrphans) {
  foreach ($orphan in (Get-AbandonedSpawnWorkers $allPython)) {
    $procId = [int]$orphan.ProcessId
    if ($matched -notcontains $procId -and -not $extra.ContainsKey($procId)) {
      $extra[$procId] = "고아(부모 $(Get-SpawnParentPid $orphan.CommandLine) 없음)"
    }
  }
}

$candidates = @(@($matched) + @($extra.Keys)) | Sort-Object -Unique

if (-not $candidates) {
  Write-Host "[stop] 실행 중인 개발 서버가 없습니다." -ForegroundColor DarkGray
  if (Test-Path $pidFile) { Remove-Item $pidFile -Force }
  exit 0
}

Write-Host "[stop] 종료 대상 확인 중...  (포트 $($Ports -join ', '))" -ForegroundColor Cyan
$stopped = 0
$skipped = @()

foreach ($procId in $candidates) {
  $info = Get-ProcInfo $procId $extra
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

# 남은 것이 있는지 확인해서 알려준다. '종료 N 건'만 찍고 끝내면 정리가 덜 됐는데도
# 다 된 줄 알게 된다 — 이 스크립트가 원래 놓치던 부분이 정확히 그 지점이었다.
if (-not $WhatIf) {
  $left = @(Get-PythonProcesses | Where-Object {
    (Test-OurCommandLine $_.CommandLine) -or (Get-SpawnParentPid $_.CommandLine)
  })
  if ($left) {
    Write-Host "[stop] 아직 남아 있습니다:" -ForegroundColor Red
    $left | ForEach-Object { Write-Host ("        pid {0,-6} {1}" -f $_.ProcessId, $_.CommandLine) -ForegroundColor Red }
  } else {
    Write-Host "[stop] 개발 서버 프로세스가 모두 정리되었습니다." -ForegroundColor Green
  }
}

# taskkill 의 종료코드가 그대로 스크립트 종료코드로 새면 stop.bat 이
# "exited with code 128" 을 찍어 실패처럼 보인다. 정상 완료는 0 으로 못박는다.
exit 0
